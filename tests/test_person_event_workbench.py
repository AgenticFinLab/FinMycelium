from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest
from streamlit.testing.v1 import AppTest

from finmy.person_epg.build import run_event
from finmy.person_epg.input import freeze_search_input
from finmy.search.control import SearchController
from finmy.search.state import digest
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.store import Store
from finmy.workbench import search_page
from test_person_event_build import payload, SyntheticModel, TEXT


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('No real API'))


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'workspace');event=payload()['user_query']['extras']['person_event']
    root=tmp_path/'dataset';root.mkdir()
    catalog={k:v for k,v in event.items() if k not in {'scope','aliases'}}
    catalog.update(kind='person_event',root=str(root),event_dir='person-epg/Alex/Charitable commitments/Foundation transfer')
    task=dict(target_type='event',target_name=event['event_name'],query_text='Test the documented transfer',key_words=[],
              catalog=catalog,research_scope=event['scope'],scope_confirmation={'scope_sha256':digest(event['scope'])})
    requests=[]
    def transport(*args):
        requests.append('search')
        return {'data':{'webPages':{'value':[{'url':'https://example.org/notice','name':'Synthetic notice'}]}}}
    search=SearchController(store.root/'search',transport=transport,fetcher=lambda u:(TEXT.encode(),'txt','utf-8'))
    tid=search.create(task,{},'simple');search.start(tid);search.threads[tid].join(5)
    assert search.inspect(tid)['status']=='finished'
    return store,search,tid,requests


def execute(model):
    def wrapped(body,directory):
        state=run_event(body['input'],directory,body['person_config'],model=model,resume=body.get('resume',False))
        graph=json.loads((directory/state['output']).read_text()) if state.get('output') else None
        return {'state':state,'graph':graph}
    return wrapped


def queue(builds,tid):
    row=builds.inspect(tid)
    builds.save(tid,'queued',row['body'])


def test_prepare_freezes_actual_input_and_sources(setup,tmp_path):
    store,search,tid,requests=setup
    before=deepcopy(search.inspect(tid));builds=BuildController(store)
    with pytest.raises(ValueError,match='确认'):builds.create_person(search,tid)
    bid=builds.create_person(search,tid,confirmed=True,artifact_root=tmp_path/'runs')
    row=builds.inspect(bid);body=row['body']
    assert row['status']=='ready' and not (tmp_path/'runs').exists()
    assert body['input']['samples']==before['builder_input']['samples']
    assert body['provenance']['handoff_revision']==before['handoff_revision']
    assert all(r['source_url']=='https://example.org/notice' for r in body['input']['user_query']['extras']['source_registry'].values())
    assert search.inspect(tid)==before and requests==['search'] and store.events()==[]
    with pytest.raises(ValueError,match='明确允许'):builds.start(bid)
    search.reassemble(tid,1)
    assert builds.current(row)  # Explicitly confirmed old input is an immutable independent task.
    assert builds.inspect(bid)['body']==body


def test_worker_outputs_native_draft_in_dataset_output_only(setup,tmp_path):
    store,search,tid,requests=setup;builds=BuildController(store)
    bid=builds.create_person(search,tid,confirmed=True)
    assert not (tmp_path/'dataset/output/builds'/bid).exists()
    queue(builds,bid);builds.run(bid,executor=execute(SyntheticModel()))
    row=builds.inspect(bid)
    assert row['status']=='completed',row['body']
    path=Path(row['body']['artifact_directory'])/row['body']['run_state']['output']
    assert path.exists() and path.is_relative_to(tmp_path/'dataset/output/builds'/bid)
    assert (path.parent/'gantt.html').is_file()
    assert not list((tmp_path/'dataset/person-epg').rglob('epg.json'))
    assert not list((tmp_path/'dataset/person-epg').rglob('gantt.html'))
    assert (Path(row['body']['artifact_directory'])/'input.json').is_file()
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM graphs').fetchone()[0]==0
    assert requests==['search']


def test_native_task_resume_keeps_usage(setup,tmp_path):
    store,search,tid,_=setup;builds=BuildController(store);model=SyntheticModel()
    bid=builds.create_person(search,tid,{'max_calls':1},confirmed=True,artifact_root=tmp_path/'runs')
    queue(builds,bid);builds.run(bid,executor=execute(model))
    assert builds.inspect(bid)['status']=='limit'
    builds.prepare_person_resume(bid,max_calls=10)
    assert len(model.calls)==1 and builds.inspect(bid)['status']=='ready'
    queue(builds,bid);builds.run(bid,executor=execute(model))
    assert builds.inspect(bid)['status']=='completed'
    assert sum('Extract' in n for n in model.calls)==1


def test_handoff_tamper_is_detected_before_task_creation(setup,tmp_path):
    store,search,tid,_=setup
    file=search.root/tid/'runs/initial/builder_input.json'
    value=json.loads(file.read_text());value['samples'][0]['content']='Changed';file.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='不一致'):freeze_search_input(search,tid,confirmed=True)
    assert BuildController(store).tasks()==[]


def test_workbench_confirm_save_and_view_without_model(setup,tmp_path,monkeypatch):
    store,search,tid,_=setup
    monkeypatch.setenv('FINMY_WORKBENCH_HOME',str(store.root))
    monkeypatch.setattr(search_page,'get_controller',lambda _:search)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'finmy/workbench/app.py')).run(timeout=30)
    def find(items,label):return next(x for x in items if x.label==label)
    find(app.sidebar.button,'任务中心').click().run()
    assert not app.exception
    find(app.checkbox,'我已检查本次实际材料与缺口，确认用于这条 event 的构建').check()
    find(app.button,'保存人物构建任务').click().run(timeout=30)
    assert not app.exception
    row=BuildController(store).tasks()[0]
    assert row['status']=='ready' and not Path(row['body']['artifact_directory']).exists()
    assert find(app.button,'开始人物构建').disabled
    assert not store.events()


def test_saved_native_gantt_regeneration_preserves_task_and_usage(setup, tmp_path):
    from finmy.workbench.build_tasks import worker_lock
    store, search, tid, requests = setup
    builds = BuildController(store); model = SyntheticModel()
    bid = builds.create_person(search, tid, confirmed=True, artifact_root=tmp_path/'runs')
    queue(builds, bid); builds.run(bid, executor=execute(model))
    before = builds.inspect(bid)
    path = Path(before['body']['artifact_directory'])/before['body']['run_state']['visualization']['output']
    path.unlink()
    with worker_lock(builds.root, bid):
        with pytest.raises(ValueError, match='worker is still running'):
            builds.render_person(bid)
    assert builds.render_person(bid)['status'] == 'completed'
    after = builds.inspect(bid)
    assert path.exists() and after['status'] == before['status'] == 'completed'
    assert after['body']['usage'] == before['body']['usage']
    assert len(model.calls) == len(before['body']['usage']) and requests == ['search']
    assert not list((tmp_path/'dataset').rglob('gantt.html'))


def test_completed_person_panel_displays_and_rerenders_offline(setup, tmp_path, monkeypatch):
    store, search, tid, _ = setup
    builds = BuildController(store); model = SyntheticModel()
    bid = builds.create_person(search, tid, confirmed=True, artifact_root=tmp_path/'runs')
    queue(builds, bid); builds.run(bid, executor=execute(model))
    monkeypatch.setenv('FINMY_WORKBENCH_HOME', str(store.root))
    monkeypatch.setattr(search_page, 'get_controller', lambda _: search)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'finmy/workbench/app.py')).run(timeout=30)
    next(b for b in app.sidebar.button if b.label=='任务中心').click().run()
    app.session_state['task-selected'] = bid
    app.run(timeout=30)
    assert not app.exception
    button = next(b for b in app.button if b.label=='从已保存 JSON 重新生成 Gantt')
    calls = len(model.calls)
    button.click().run(timeout=30)
    assert not app.exception and len(model.calls) == calls
    assert builds.inspect(bid)['status'] == 'completed'
