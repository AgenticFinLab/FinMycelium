"""Dataset-owned storage and portable exports, with no real service calls."""
import csv
import fcntl
import json
from pathlib import Path
import socket
import sqlite3

import pytest

from dataset_fixture import fixture_dataset
from finmy.dataset import DatasetCatalog
from finmy.search.control import SearchController
from finmy.search.state import SearchState
from finmy.workbench import records
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.domain import FIELDS
from finmy.workbench.search_bridge import create_catalog_search
from finmy.workbench.store import Store
from finmy.workbench.workspace import assert_idle, resolve_workspace, select_workspace


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('No real network allowed')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.delenv('FINMY_WORKBENCH_HOME', raising=False)


@pytest.fixture
def workspace(tmp_path):
    project = tmp_path / 'code'
    root = fixture_dataset(tmp_path / 'dataset')
    path = select_workspace(project, root)
    return project, root, Store(path)


def search(store, root, *, mode='simple'):
    calls = []
    def transport(*args):
        calls.append('search')
        return {'data': {'webPages': {'value': [
            {'url': 'https://example.org/test', 'name': 'Synthetic source'}]}}}
    controller = SearchController(store.root / 'search', transport=transport,
        fetcher=lambda u: (b'PRIVATE_SOURCE_BODY: a synthetic appointment.', 'txt', 'utf-8'))
    selection = DatasetCatalog(root).select('PERSON-EVENT-TEST', 'PERSON-TEST')
    task_id = create_catalog_search(store, controller, selection, {}, mode,
        period=selection['period'], include=selection['scope_include'],
        exclude=selection['scope_exclude'], confirmed=True, seeds=[])
    return controller, task_id, calls


def read(path):
    return json.loads(path.read_text())


def search_record(root, task_id):
    matches = [path.parent for path in (root/'workbench/search').glob('*/task.json')
               if read(path)['task_id']==task_id]
    assert len(matches)==1
    return matches[0]


def test_workspace_is_in_dataset_and_bootstrap_has_no_runtime(tmp_path):
    project = tmp_path / 'code'
    assert resolve_workspace(project) is None
    assert not project.exists()
    root = fixture_dataset(tmp_path / 'dataset')
    path = select_workspace(project, root)
    assert path == root / 'output/workbench'
    assert resolve_workspace(project) == path
    assert read(project / 'output/workbench-location.json') == {'dataset_root': str(root)}
    assert not (project / 'output/workbench').exists()
    assert resolve_workspace(project, environ={'FINMY_WORKBENCH_HOME': str(tmp_path / 'custom')}) == tmp_path / 'custom'


def test_legacy_migration_preserves_task_bytes_and_id(tmp_path):
    project = tmp_path / 'code'
    root = fixture_dataset(tmp_path / 'dataset')
    old = Store(project / 'output/workbench')
    c, tid, calls = search(old, root)
    run = c.root / tid / 'runs/initial/run.json'
    before = run.read_bytes()
    db_before = old.path.read_bytes()
    with pytest.raises(ValueError, match='旧工作区'):
        resolve_workspace(project)
    with pytest.raises(ValueError, match='旧工作区'):
        select_workspace(project, root)
    assert not (root / 'output/workbench').exists()
    target = root / 'output/workbench'
    target.parent.mkdir(parents=True)
    old.root.rename(target)
    select_workspace(project, root)
    assert resolve_workspace(project) == target
    assert (target / 'search' / tid / 'runs/initial/run.json').read_bytes() == before
    assert (target / 'workbench.sqlite3').read_bytes() == db_before
    assert not calls
    assert all(r['status'] == 'saved' for r in records.export_all(target))
    assert read(search_record(root, tid) / 'task.json')['runtime_directory'] == f'output/workbench/search/{tid}'


def test_switching_keeps_previous_workspace_and_refuses_active_runs(workspace, tmp_path):
    project, root, store = workspace
    c, tid, _ = search(store, root)
    other = fixture_dataset(tmp_path / 'other')
    state = SearchState(c.root, tid)
    state.data['status'] = 'running'
    state.save()
    with pytest.raises(ValueError, match='检索'):
        select_workspace(project, other, current=store.root)
    assert resolve_workspace(project) == store.root
    state.data['status'] = 'ready'
    state.save()
    BuildController(store)
    with store.connection() as db:
        db.execute("INSERT INTO build_tasks VALUES('B', 'E', '{}', 'running', 'today')")
    with pytest.raises(ValueError, match='构建'):
        assert_idle(store.root)
    with store.connection() as db:
        db.execute("UPDATE build_tasks SET status='failed'")
    select_workspace(project, other, current=store.root)
    assert (store.root / 'search' / tid / 'runs/initial/run.json').exists()
    assert resolve_workspace(project) == other / 'output/workbench'


def test_ready_and_finished_search_records_are_automatic_and_private(workspace):
    _, root, store = workspace
    c, tid, calls = search(store, root)
    folder = search_record(root, tid)
    assert folder.name.endswith('_'+tid[:12]) and folder.name != tid
    task = read(folder / 'task.json')
    assert task['catalog']['event_id'] == 'PERSON-EVENT-TEST'
    assert task['research_scope']['include'] == 'The appointment and term.'
    assert read(folder / 'summary.json')['status'] == 'ready'
    index = root/'workbench/search/README.md'
    assert tid[:12] in index.read_text() and '| ready |' in index.read_text()
    assert not calls
    c.configure(tid, {'max_builder_material_chars': 90000})
    revised = read(folder / 'task.json')
    assert revised['configuration']['max_builder_material_chars'] == 90000
    assert len(revised['configuration_history']) == 1
    c.start(tid)
    c.threads[tid].join(10)
    assert not c.active(tid)
    summary = read(folder / 'summary.json')
    assert summary['status'] == 'finished'
    assert '| finished |' in index.read_text()
    assert summary['source_count'] == summary['input_source_count'] == 1
    assert summary['token_usage']['attempted_model_calls'] == 0
    assert summary['token_usage']['total_tokens'] == 0
    assert summary['monetary_cost'] is None
    rows = list(csv.DictReader((folder / 'sources.csv').open()))
    assert rows[0]['in_input'] == 'True' and rows[0]['url'] == 'https://example.org/test'
    assert calls == ['search']
    snapshots = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    state_before = (c.root / tid / 'runs/initial/run.json').read_bytes()
    assert records.sync_search(c.root, tid)['status'] == 'saved'
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == data for p, data in snapshots.items())
    assert (c.root / tid / 'runs/initial/run.json').read_bytes() == state_before
    shared = '\n'.join(p.read_text() for p in (root / 'workbench').rglob('*') if p.is_file())
    assert 'PRIVATE_SOURCE_BODY' not in shared and str(root) not in shared
    assert not list((root / 'person-epg').rglob('epg.json'))


def test_search_record_names_use_creation_time_not_model_or_status():
    record = {'task_id':'a11eef5ce4134cb4ad6c224da7ba3875',
              'created_at':'2026-11-14T07:03:51+00:00',
              'catalog':{'event_name':'Goldman Sachs crisis investment'},
              'configuration':{'lm_name':'model/first'}}
    expected = '20261114-150351_goldman-sachs-crisis-investment_a11eef5ce413'
    assert records.search_record_name(record)==expected
    record.update(status='failed',configuration={'lm_name':'model/second'})
    assert records.search_record_name(record)==expected


def test_legacy_shared_record_migration_preserves_bytes_without_runtime(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    tid = 'a'*32
    folder = root/'workbench/search'/tid
    folder.mkdir(parents=True)
    original = {'task_id':tid, 'created_at':'2026-11-14T01:02:03Z',
                'catalog':{'event_id':'PERSON-TEST-E1','event_name':'Appointment'},
                'research_request':{'target_name':'Person — Appointment'},
                'configuration':{'lm_name':'model/example'}, 'mode':'agent',
                'runtime_directory':f'output/workbench/search/{tid}'}
    records.save(folder,'task.json',original)
    records.save(folder,'summary.json',{'task_id':tid,'status':'finished','input_characters':1234})
    records.save(folder,'sources.csv','source_id,url\nsource-1,https://example.org/notice\n')
    (root/'workbench/README.md').write_text(
        '# Custom introduction\n\n- search/<task_id>/: task scope/configuration, execution summary and source index.\n\nKeep this note.\n')
    before = {p.name:p.read_bytes() for p in folder.iterdir()}
    changes = records.migrate_search_records(root)
    renamed = search_record(root,tid)
    assert changes==[(tid,'20261114-090203_appointment_aaaaaaaaaaaa')]
    assert renamed.name==changes[0][1] and not folder.exists()
    assert {p.name:p.read_bytes() for p in renamed.iterdir()}==before
    assert not (root/'output').exists()
    readme = (root/'workbench/README.md').read_text()
    assert 'Keep this note.' in readme and '[Search records](search/README.md)' in readme
    index = root/'workbench/search/README.md'
    assert f']({renamed.name}/)' in index.read_text()
    assert '| finished | pending | 1234 |' in index.read_text()
    snapshot = index.read_bytes(),index.stat().st_mtime_ns
    assert records.migrate_search_records(root)==[]
    assert (index.read_bytes(),index.stat().st_mtime_ns)==snapshot


def test_export_after_legacy_migration_reuses_folder_and_keeps_runtime(workspace):
    _,root,store = workspace
    controller,tid,_ = search(store,root,mode='agent')
    folder = search_record(root,tid)
    legacy = folder.with_name(tid)
    folder.rename(legacy)
    runtime = controller.root/tid/'runs/initial/run.json'
    before = runtime.read_bytes()
    assert records.export_search(controller.root,tid)==folder
    assert not legacy.exists() and runtime.read_bytes()==before
    controller.configure(tid,{'lm_name':'tokenhub/glm-5.3-flash'})
    assert search_record(root,tid)==folder
    assert 'tokenhub/glm-5.3-flash' in (root/'workbench/search/README.md').read_text()


def test_search_record_short_id_collision_does_not_overwrite(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    search_root = root/'output/workbench/search'
    folders=[]
    for tid in ['123456789abc'+'0'*20,'123456789abc'+'1'*20]:
        state=SearchState(search_root,tid,task={'target_type':'event','target_name':'Same event',
            'query_text':'Same scope','catalog':{'root':str(root)}})
        state.data['created_at']='2026-11-14T01:02:03Z';state.save()
        folders.append(records.export_search(search_root,tid))
    assert folders[0]!=folders[1]
    assert folders[0].name.endswith('_123456789abc')
    assert folders[1].name.endswith('_123456789abc'+'1'*20)
    assert read(folders[0]/'task.json')['task_id']=='123456789abc'+'0'*20
    assert records.export_search(search_root,'123456789abc'+'1'*20)==folders[1]


def test_search_record_labels_are_safe_and_support_non_english_names():
    record={'task_id':'case','created_at':'2026-11-14T01:02:03Z',
            'research_request':{'target_name':'../测试 / acquisition | title '*100}}
    name=records.search_record_name(record)
    assert name.startswith('20261114-090203_测试-acquisition-title-')
    assert len(name.encode('utf-8'))<255
    assert '/' not in name and '..' not in name and name.endswith('_case')


def test_missing_model_usage_stays_unknown_and_traces_are_not_copied(workspace):
    _, root, store = workspace
    c, tid, _ = search(store, root, mode='agent')
    state = SearchState(c.root, tid)
    state.data['usage']['model'] = 2
    state.trace({'action': 'model_response', 'usage': {'total_tokens': 12},
                 'response': 'PRIVATE_MODEL_RESPONSE'})
    state.save()
    records.sync_search(c.root, tid)
    summary = read(search_record(root, tid) / 'summary.json')
    assert summary['token_usage']['total_tokens'] is None
    assert summary['token_usage']['reported_total_tokens'] == 12
    assert 'PRIVATE_MODEL_RESPONSE' not in json.dumps(summary)


def test_committed_edits_and_reviews_export_without_bodies(workspace, monkeypatch):
    _, root, store = workspace
    eid = store.create_events([dict(event_name_en='Synthetic', description='A test.',
                                    scope_include='Appointment')])[0]
    store.review(eid, 'scope', 'approved', 'Reviewer', '', store.target(eid, 'scope'))
    store.add_source(eid, 'Notice', 'PRIVATE_SOURCE_BODY', raw=b'PRIVATE_RAW_BYTES')
    store.review(eid, 'evidence', 'approved', 'Reviewer', '', store.target(eid, 'evidence'))
    folder = root / 'workbench/events' / eid
    reviews = read(folder / 'reviews.json')
    assert len(reviews['reviews']) == 2
    assert len(reviews['handoffs']) == 1
    assert reviews['handoffs'][0]['input']['samples'][0]['characters'] == len('PRIVATE_SOURCE_BODY')
    fields = {k: v for k, v in store.event(eid).items() if k in FIELDS}
    store.update_event(eid, {**fields, 'description': 'Revised test.'}, 1)
    assert read(folder / 'event.json')['revision'] == 2
    assert len(read(folder / 'event.json')['history']) == 2
    assert len(read(folder / 'reviews.json')['reviews']) == 2
    assert not store.accepted(eid)
    for p in folder.iterdir():
        assert 'PRIVATE_SOURCE_BODY' not in p.read_text()
        assert 'PRIVATE_RAW_BYTES' not in p.read_text()
    def unexpected(*a):
        pytest.fail('A read or rollback must not export')
    monkeypatch.setattr(records, 'sync_database', unexpected)
    assert store.event(eid)['revision'] == 2
    with pytest.raises(RuntimeError):
        with store.connection() as db:
            db.execute("UPDATE events SET revision=99")
            raise RuntimeError('rollback')
    assert store.event(eid)['revision'] == 2


def test_build_configuration_and_person_call_usage_export(workspace):
    _, root, store = workspace
    eid = store.create_events([dict(event_name_en='Synthetic', description='A test.', scope_include='Appointment')])[0]
    store.review(eid, 'scope', 'approved', 'Reviewer', '', store.target(eid, 'scope'))
    store.add_source(eid, 'Notice', 'PRIVATE_BUILD_BODY')
    store.review(eid, 'evidence', 'approved', 'Reviewer', '', store.target(eid, 'evidence'))
    controller = BuildController(store)
    tid = controller.create(eid, {'model': 'ark/doubao-seed-2-0-pro-260215',
                                  'builder': 'SparseRagBuilder', 'concurrency': 1})
    folder = records.find_build_record(root, tid).parent
    task = read(folder / 'task.json')
    assert task['configuration']['sparse_builder_config']['enable_context_assets'] is True
    assert task['configuration']['sparse_builder_config']['evidence_policy'] == 'report'
    assert task['artifact_directory'] == f'output/builds/{tid}'
    assert 'PRIVATE_BUILD_BODY' not in (folder / 'task.json').read_text()
    body = controller.inspect(tid)['body']
    body['usage'] = [{'call_id': 'CALL-1', 'status': 'accepted', 'usage': {'total_tokens': 20}},
                     {'call_id': 'CALL-2', 'status': 'transport_error', 'usage': None}]
    body['run_state'] = {'execution_status': 'failed', 'result_status': 'none',
                         'render_status': 'not_started', 'calls': [{'text': 'PRIVATE_RESPONSE'}]}
    controller.save(tid, 'failed', body)
    summary = read(folder / 'summary.json')
    assert summary['usage']['total_tokens'] is None
    assert summary['usage']['reported_total_tokens'] == 20
    assert summary['run_state']['execution_status'] == 'failed'
    assert 'PRIVATE_RESPONSE' not in json.dumps(summary)
    assert not (root / 'output/builds' / tid).exists()


def test_export_failure_keeps_saved_task_and_explicit_retry_does_not_execute(workspace, monkeypatch):
    _, root, store = workspace
    original = records.atomic_text
    def denied(path, text):
        if path.is_relative_to(root / 'workbench'):
            raise PermissionError('Synthetic read-only record directory')
        return original(path, text)
    with monkeypatch.context() as m:
        m.setattr(records, 'atomic_text', denied)
        c, tid, calls = search(store, root)
    assert c.inspect(tid)['status'] == 'ready'
    status = store.root / 'record-exports' / f'search-{tid}.json'
    assert read(status)['status'] == 'failed'
    assert all(r['status'] == 'saved' for r in records.export_all(store.root))
    assert read(status)['status'] == 'saved'
    assert not calls


def test_record_paths_and_exported_configuration_do_not_leak(workspace, tmp_path):
    _, root, store = workspace
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'workbench').symlink_to(outside, target_is_directory=True)
    c, tid, calls = search(store, root)
    assert records.sync_search(c.root, tid)['status'] == 'failed'
    assert not list(outside.iterdir()) and not calls
    config = records.search_config({'lm_name': 'provider/model', 'api_key': 'PRIVATE_KEY',
        'base_url': 'PRIVATE_URL', 'generation_config': {'max_tokens': 8192,
        'extra_headers': {'Authorization': 'PRIVATE_KEY'},
        'extra_body': {'thinking': {'type': 'enabled'}, 'api_key': 'PRIVATE_KEY'}}})
    assert 'PRIVATE' not in json.dumps(config)
    assert config['generation_config']['extra_body'] == {'thinking': {'type': 'enabled'}}
    assert records.public_url('https://example.org/a?token=PRIVATE_KEY&page=2') == 'https://example.org/a?page=2'
    assert records.public_url('file:///PRIVATE_PATH') == ''


def test_person_build_record_links_exact_search_input_and_scope(workspace):
    _, root, store = workspace
    c, tid, calls = search(store, root)
    c.start(tid)
    c.threads[tid].join(10)
    builds = BuildController(store)
    bid = builds.create_person(c, tid, confirmed=True)
    folder = records.find_build_record(root, bid).parent
    record = read(folder / 'task.json')
    assert record['kind'] == 'person_event'
    assert record['research_scope'] == c.inspect(tid)['task']['research_scope']
    assert record['search_handoff']['search_task_id'] == tid
    assert record['search_handoff']['handoff_revision'] == c.inspect(tid)['handoff_revision']
    assert record['configuration']['max_calls'] == 40
    assert read(folder / 'summary.json')['status'] == 'ready'
    assert 'PRIVATE_SOURCE_BODY' not in (folder / 'task.json').read_text()
    assert calls == ['search']
    assert not (root / 'output/builds' / bid).exists()


def test_active_file_lock_blocks_switch_before_status_is_updated(workspace):
    _, root, store = workspace
    c, tid, _ = search(store, root)
    with (c.root / tid / '.writer.lock').open('r') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='执行'):
            assert_idle(store.root)
    assert_idle(store.root)


def test_paused_and_independent_tasks_export_without_catalog_acceptance(workspace):
    _, root, store = workspace
    c, tid, _ = search(store, root, mode='agent')
    c.dependencies['model'] = lambda context: {'action': 'search', 'query': 'Synthetic notice'}
    c.start(tid, steps=1)
    c.threads[tid].join(10)
    assert not c.active(tid)
    assert read(search_record(root, tid) / 'summary.json')['status'] == 'paused'
    other = c.create(dict(target_type='event', target_name='Independent', query_text='Research the synthetic appointment'), {}, 'simple')
    assert read(search_record(root, other) / 'task.json')['catalog'] == {}
    assert read(search_record(root, other) / 'summary.json')['status'] == 'ready'
