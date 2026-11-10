"""Offline regressions for generic multi-provider search and bounded handoff."""
import json
import socket
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from finmy.search.agent import SYSTEM_PROMPT, context_for, run_agent
from finmy.search.pipeline import run_search
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, request_payload


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Unexpected network'))


def task(kind='event'):
    return dict(target_type=kind, target_name='Example '+kind,
                query_text='Trace actions and unresolved outcomes; preserve uncertainty')


def transport(provider, payload, config):
    item=dict(url='https://example.org/'+provider, title=provider,
              name=provider, text='Expansion was announced. Completion is not confirmed.')
    if provider=='baidu': return {'references':[item]}
    if provider=='bocha': return {'data':{'webPages':{'value':[item]}}}
    return {'results':[item]}


def model(context):
    if context['phase']=='finalize':
        return dict(action='finish',source_ids=[s['source_id'] for s in context['sources'] if s['reviewed']],
                    gaps=['Completion remains unconfirmed'],reason='low_gain')
    if not context['sources']: return dict(action='search',query='example milestones')
    source=next(s for s in context['sources'] if not s['reviewed'])
    return dict(action='read_source',source=source['source_id'])


@pytest.mark.parametrize('kind',['event','person','company'])
def test_joint_full_chain_resume_and_independent_source_text(tmp_path,kind):
    options=dict(root=tmp_path,task_id='case',model=model,transport=transport,
                 fetcher=lambda u:(b'Expansion was announced. Completion is not confirmed.','txt','utf-8'))
    config=SearchConfig(providers=['baidu','bocha','exa'],max_search_requests=3,max_model_calls=5)
    first=run_search(task(kind),config=config,max_steps=3,**options)
    assert first['status']=='paused'
    final=run_search(**options)
    assert final['status']=='finished'
    assert final['usage']=={'model':5,'search':3}
    payload=json.loads(Path(final['builder_input_path']).read_text())
    assert set(payload)=={'user_query','samples'}
    assert len(payload['samples'])==1  # Identical documents are packaged once; aliases are recorded.
    assert all('Completion is not confirmed.' in s['content'] for s in payload['samples'])
    from finmy.generic import DataSample,UserQueryInput
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']: DataSample(**sample)
    state=SearchState(tmp_path,'case')
    assert any(s['status']=='partial' for s in state.data['sources'].values())
    assert json.loads((state.run_dir/'checkpoint.json').read_text())['review_required']


def test_last_call_cannot_spend_search_budget_or_fabricate_handoff(tmp_path):
    result=run_search(task(),root=tmp_path,task_id='case',config={'max_model_calls':1},
        model=lambda c:dict(action='search',query='extra'),transport=lambda *a:pytest.fail('No research in finalization'))
    assert result['status']=='limit' and result['usage']=={'model':1,'search':0}
    assert result['builder_input_path'] is None
    checkpoint=json.loads((Path(result['run_dir'])/'checkpoint.json').read_text())
    assert checkpoint['handoff_created'] is False


def test_finalization_recovers_earlier_read_text_and_retries_invalid_ids(tmp_path):
    config=SearchConfig(max_model_calls=8)
    state=SearchState(tmp_path,'case',task=task(),config=config)
    store=SourceStore(state)
    for name,text in [('a',b'First action was conditional.'),('b',b'Later action remains unknown.')]:
        sid=store.register('https://example.org/'+name);store.save_raw(sid,text,'txt');store.read(sid)
    state.data['usage']['model']=6;state.data['feedback']={'source_id':sid};state.save()
    calls=[]
    def decide(c):
        calls.append(c)
        assert c['phase']=='finalize'
        assert any('conditional' in e.get('preview','') for e in c['sources'])
        return dict(action='finish',source_ids=['bad'] if len(calls)==1 else [s['source_id'] for s in c['sources']],gaps=['Unresolved'],reason='low_gain')
    run_agent(state,SearchTools(state),decide)
    assert state.data['status']=='finished' and state.data['usage']['model']==8
    assert calls[1]['feedback']['hint']=='Unknown source ID: bad'


def test_tampered_evidence_cannot_enter_finalization_context(tmp_path):
    state=SearchState(tmp_path,'case',task=task(),config=SearchConfig(max_model_calls=1))
    store=SourceStore(state);sid=store.register('https://example.org/a')
    doc=store.save_raw(sid,b'Original.','txt');store.read(sid)
    (state.root/'sources'/sid/doc['version']/'raw').write_bytes(b'Changed.')
    context = context_for(state)
    assert context['eligible_source_ids'] == []
    assert context['sources'] == []
    assert context['quarantined_sources'][0]['source_id'] == sid
    assert 'integrity' in context['quarantined_sources'][0]['reason']


def test_search_model_does_not_overwrite_builder_model(tmp_path,monkeypatch):
    from finmy.runner import search_pipeline_runner as runner
    seen=[]
    class FakeModel:
        def __init__(self,config):seen.append(config.lm_name)
        def __call__(self,context):return model(context)
    monkeypatch.setattr('finmy.search.agent.LmbaseModel',FakeModel)
    build=Mock();build.lm_build_pipeline_with_contents.return_value={'fixture':'graph'}
    factory=Mock(return_value=build);monkeypatch.setattr(runner,'_create_pipeline',factory)
    cfg=dict(builder_config={'lm_name':'ark/builder-test'},search_config=dict(mode='agent',enhancement=dict(
        lm_name='ark/search-test',providers=['baidu','bocha','exa'],max_model_calls=5)))
    result=runner.run_search_pipeline(cfg,'Example',[],tmp_path,search_dependencies=dict(
        transport=transport,fetcher=lambda u:(b'Not completed.','txt','utf-8')))
    assert result['status']=='finished' and seen==['ark/search-test']
    assert factory.call_args.args[0]['builder_config']['lm_name']=='ark/builder-test'
