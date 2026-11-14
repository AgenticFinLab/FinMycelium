import socket
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from finmy.search.control import SearchController, task_lock
from finmy.search.state import SearchState,SearchConfig
from finmy.search.sources import SourceStore
from finmy.search.handoff import assemble
from finmy.search.agent import execute_action
from finmy.search.tools import SearchTools

TASK=dict(target_type='event',target_name='Deal',query_text='Trace closing')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('Unexpected network'))

def test_writer_lock_and_config_revision_preserve_usage(tmp_path):
    controller=SearchController(tmp_path)
    tid=controller.create(TASK, {})
    state=SearchState(tmp_path,tid);state.consume('model')
    with task_lock(tmp_path,tid):
        with pytest.raises(ValueError):controller.configure(tid,{'max_model_calls':70})
    controller.configure(tid,{'max_model_calls':70})
    data=controller.inspect(tid)
    assert data['usage']['model']==1
    assert data['config_history'][0]['config']['max_model_calls']==40

def test_continued_span_union_can_be_selected(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK,config=SearchConfig(max_read_chars=4))
    store=SourceStore(state);sid=store.register('https://example.org/a')
    doc=store.save_raw(sid,b'Not approved.','txt')
    r=store.read(sid)
    while r['next_location']:r=store.read(sid,**r['next_location'])
    payload=assemble(state,[dict(source_id=sid,version=doc['version'],block=0,start=0,end=13)])
    assert payload['samples'][0]['content'].endswith('Not approved.')
    execute_action(state,SearchTools(state),dict(action='finish',selections=[dict(source_id=sid,version=doc['version'],block=0,start=0,end=13)],gaps=['Evidence missing'],reason='insufficient'))
    assert state.data['status']=='insufficient'

def test_pause_background_and_resume_preserves_count(tmp_path):
    entered=threading.Event();release=threading.Event()
    def model(context):
        entered.set();assert release.wait(3)
        return dict(action='search',query='closing')
    c=SearchController(tmp_path,model=model,transport=lambda *a:{'data':{'webPages':{'value':[]}}})
    tid=c.create(TASK,{})
    c.start(tid);assert entered.wait(3)
    with pytest.raises(ValueError):c.start(tid)
    c.pause(tid);release.set();c.threads[tid].join(3)
    assert c.inspect(tid)['status']=='paused'
    assert c.inspect(tid)['usage']['model']==1
    c.start(tid,steps=1);c.threads[tid].join(3)
    assert c.inspect(tid)['usage']['model']==2

def test_simple_task_does_not_call_model(tmp_path):
    c=SearchController(tmp_path,model=lambda c:pytest.fail('No model in simple mode'),
        transport=lambda *a:{'data':{'webPages':{'value':[{'url':'https://example.org/a'}]}}},
        fetcher=lambda u:(b'Closing was announced.','txt','utf-8'))
    tid=c.create(TASK,{},mode='simple');c.start(tid);c.threads[tid].join(3)
    data=c.inspect(tid)
    assert data['status']=='finished'
    assert data['usage']['model']==0
    assert data['builder_input']['samples']
    assert c.reassemble(tid,5)['samples']==[]


def test_credentials_load_only_on_explicit_enabled_start(tmp_path,monkeypatch):
    env=tmp_path/'fake.env';env.write_text('FINMY_TEST_CREDENTIAL=fixture-only\n')
    monkeypatch.delenv('FINMY_TEST_CREDENTIAL',raising=False)
    c=SearchController(tmp_path/'tasks',env_file=env)
    tid=c.create(TASK,{},mode='simple')
    import os
    assert 'FINMY_TEST_CREDENTIAL' not in os.environ
    with pytest.raises(ValueError):c.start(tid)
    assert 'FINMY_TEST_CREDENTIAL' not in os.environ
    c.configure(tid,{'allow_network':True})
    monkeypatch.setattr(c,'_worker',lambda *a:None)
    c.start(tid);c.threads[tid].join(3)
    assert os.environ['FINMY_TEST_CREDENTIAL']=='fixture-only'
    monkeypatch.delenv('FINMY_TEST_CREDENTIAL')
