"""Offline acceptance of catalog collection; all artifacts belong to tmp_path."""
from contextlib import contextmanager
from copy import deepcopy
import csv
import json
from pathlib import Path
import socket
import sqlite3

import pytest

from dataset_fixture import fixture_dataset
from finmy.dataset import DatasetCatalog, accepted_artifact_paths, catalog_event_directory
from finmy.search.control import SearchController
from finmy.search.state import digest
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.search_bridge import adopt_sources, create_catalog_search
from finmy.workbench.store import Store
from finmy.workbench.workspace import select_workspace


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No real API calls'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a, **k: pytest.fail('No real API calls'))


@pytest.fixture
def setup(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    store = Store(select_workspace(tmp_path/'code', root))
    calls = []
    def transport(*args):
        calls.append('search')
        return {'data': {'webPages': {'value': [
            {'url': 'https://example.org/notice', 'name': 'Notice'},
            {'url': 'https://example.org/closing', 'name': 'Closing'}]}}}
    controller = SearchController(store.root/'search', transport=transport,
        fetcher=lambda url: (('PRIVATE ORIGINAL: synthetic source '+url).encode(), 'txt', 'utf-8'))
    return root, store, controller, calls


def finish(setup, *, person=True):
    root, store, controller, _ = setup
    choice = DatasetCatalog(root).select('PERSON-EVENT-TEST' if person else 'EVENT-TEST',
                                        'PERSON-TEST' if person else None)
    tid = create_catalog_search(store, controller, choice, {}, 'simple',
        period=choice['period'], include=choice['scope_include'], exclude=choice['scope_exclude'],
        confirmed=True, seeds=[])
    controller.start(tid); controller.threads[tid].join(10)
    assert not controller.active(tid) and controller.inspect(tid)['status'] == 'finished'
    return tid, choice


def contents(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def test_person_collection_requires_confirmation_and_keeps_originals(setup):
    root, store, controller, calls = setup
    tid, choice = finish(setup)
    folder = catalog_event_directory(choice)/'search'
    assert not folder.exists()
    before = deepcopy(controller.inspect(tid))
    tables = {p: p.read_bytes() for p in root.rglob('*.csv') if 'output' not in p.parts and 'workbench' not in p.parts}
    builds = BuildController(store)
    with pytest.raises(ValueError, match='确认'):
        builds.create_person(controller, tid)
    assert not folder.exists() and builds.tasks() == []
    bid = builds.create_person(controller, tid, confirmed=True)
    body = builds.inspect(bid)['body']
    assert builds.inspect(bid)['status'] == 'ready'
    assert not Path(body['artifact_directory']).exists()  # no worker or graph construction
    assert set(contents(folder)) == {'manifest.json', 'search-summary.md', 'sources.csv', 'builder-input.json'}
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['build_task_id'] == bid and manifest['input_sha256'] == digest(body['input'])
    assert manifest['search_handoffs'][0]['handoff_revision'] == before['handoff_revision']
    assert manifest['search_handoffs'][0]['search_input_sha256'] == digest(before['builder_input'])
    assert manifest['graph_acceptance'] == 'not_implied'
    frozen = json.loads((folder/'builder-input.json').read_text())
    assert frozen == body['input']
    assert digest(frozen) == manifest['input_sha256']
    assert manifest['input_file'] == 'builder-input.json'
    assert manifest['file_sha256']['builder-input.json'] == digest((folder/'builder-input.json').read_bytes())
    assert 'PRIVATE ORIGINAL' in (folder/'builder-input.json').read_text()
    assert 'PRIVATE ORIGINAL' not in '\n'.join(v.decode() for k,v in contents(folder).items() if k != 'builder-input.json')
    assert controller.inspect(tid) == before and calls == ['search']
    assert all(p.read_bytes() == text for p, text in tables.items())
    assert not (folder.parent/'epg').exists()
    shared = json.loads((root/'workbench/build'/bid/'task.json').read_text())
    assert 'PRIVATE ORIGINAL' not in json.dumps(shared)
    assert shared['search_collection']['manifest'] == manifest
    assert shared['search_collection']['manifest_sha256'] == digest((folder/'manifest.json').read_bytes())


def test_reassembly_does_not_change_collection_and_new_adoption_retains_old_build(setup):
    root, store, controller, _ = setup
    tid, choice = finish(setup)
    builds = BuildController(store)
    first = builds.create_person(controller, tid, confirmed=True)
    first_body = builds.inspect(first)['body']
    folder = catalog_event_directory(choice)/'search'; original = contents(folder)
    controller.reassemble(tid, 10000)
    assert contents(folder) == original
    second = builds.create_person(controller, tid, confirmed=True)
    assert second != first
    assert json.loads((folder/'manifest.json').read_text())['build_task_id'] == second
    assert builds.inspect(first)['body'] == first_body and builds.current(builds.inspect(first))
    assert first_body['search_collection']['files']['manifest.json'].encode() == original['manifest.json']
    assert not list(folder.parent.glob('.search-*'))


def test_ordinary_collection_uses_reviewed_subset_and_frozen_handoff(setup):
    root, store, controller, calls = setup
    tid, choice = finish(setup, person=False)
    original = controller.inspect(tid)
    eid = original['task']['event_id']
    adopt_sources(controller, tid, store)
    association = json.loads((controller.root/tid/'runs/initial/workbench_sources.json').read_text())
    source = store.sources(eid)[0]
    store.include_source(eid, source['id'], False)
    extra = store.add_source(eid, 'Manual note', text='PRIVATE MANUAL MATERIAL', url='https://example.org/manual')
    builds = BuildController(store)
    with pytest.raises(ValueError, match='审核'):
        builds.create(eid, store.settings())
    store.review(eid, 'evidence', 'approved', 'Test reviewer', 'Known gaps accepted', store.target(eid, 'evidence'))
    # Reassembly after adoption must not attach a newer revision to older Store content.
    controller.reassemble(tid, 10000)
    assert controller.inspect(tid)['handoff_revision'] != original['handoff_revision']
    bid = builds.create(eid, store.settings())
    body = builds.inspect(bid)['body']
    folder = catalog_event_directory(choice)/'search'
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['search_handoffs'][0]['handoff_revision'] == original['handoff_revision']
    with (folder/'sources.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert {r['input_sample_id'] for r in rows} == {s['sample_id'] for s in body['input']['samples']}
    assert source['id'] not in {r['input_sample_id'] for r in rows}
    manual = next(r for r in rows if r['input_sample_id'] == extra)
    assert manual['search_task_id'] == '' and manual['status'] == 'workbench_material'
    assert manifest['confirmation']['reviewer'] == 'Test reviewer'
    assert 'PRIVATE' not in (folder/'manifest.json').read_text()
    frozen = json.loads((folder/'builder-input.json').read_text())
    assert frozen == body['input']
    assert source['id'] not in {s['sample_id'] for s in frozen['samples']}
    assert any(s['content'] == 'PRIVATE MANUAL MATERIAL' for s in frozen['samples'])
    assert not (folder.parent/'epg').exists() and calls == ['search']


@pytest.mark.parametrize('filename', ['manifest.json', 'sources.csv', 'search-summary.md', 'builder-input.json'])
def test_collection_preserves_manual_edits(setup, filename):
    _, store, controller, _ = setup
    tid, choice = finish(setup)
    builds = BuildController(store); builds.create_person(controller, tid, confirmed=True)
    folder = catalog_event_directory(choice)/'search'
    path = folder/filename
    if filename == 'manifest.json':
        data = json.loads(path.read_text()); data['confirmation']['note'] = 'Manual addition'
        path.write_text(json.dumps(data))
    else:
        path.write_text(path.read_text()+'Manual addition\n')
    before = contents(folder)
    with pytest.raises(ValueError, match='保留'):
        builds.create_person(controller, tid, confirmed=True)
    assert contents(folder) == before and len(builds.tasks()) == 1


@pytest.mark.parametrize('existing', [True, False])
def test_build_save_failure_rolls_back_collection(setup, monkeypatch, existing):
    _, store, controller, _ = setup
    tid, choice = finish(setup); builds = BuildController(store)
    if existing: builds.create_person(controller, tid, confirmed=True)
    folder = catalog_event_directory(choice)/'search'; before = contents(folder) if existing else None
    original = store.connection
    class FailingDB:
        def __init__(self, db): self.db = db
        def execute(self, statement, *args):
            if statement.startswith('INSERT INTO build_tasks'): raise sqlite3.OperationalError('synthetic failure')
            return self.db.execute(statement, *args)
    @contextmanager
    def fail_insert():
        with original() as db:
            yield FailingDB(db)
    monkeypatch.setattr(store, 'connection', fail_insert)
    with pytest.raises(sqlite3.OperationalError):
        builds.create_person(controller, tid, confirmed=True)
    assert (contents(folder) if folder.exists() else None) == before
    assert len(builds.tasks()) == int(existing)
    assert not list(folder.parent.glob('.search-*'))


def test_collection_rejects_redirected_catalog(setup, tmp_path):
    _, store, controller, _ = setup
    tid, choice = finish(setup); builds = BuildController(store)
    folder = catalog_event_directory(choice)
    folder.parent.mkdir(parents=True)
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    folder.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match='符号链接|越出'):
        builds.create_person(controller, tid, confirmed=True)
    assert not list(elsewhere.iterdir()) and not builds.tasks()


def test_accepted_artifacts_have_epg_subdirectory_without_creating_files(setup):
    root, _, _, _ = setup
    catalog = DatasetCatalog(root)
    person = catalog.select('PERSON-EVENT-TEST', 'PERSON-TEST')
    event = catalog.select('EVENT-TEST')
    assert accepted_artifact_paths(person) == dict(epg_path='Public service/Example appointment/epg/epg.json',
        gantt_path='Public service/Example appointment/epg/gantt.html', review_path='Public service/Example appointment/epg/review.md')
    assert accepted_artifact_paths(event)['epg_path'] == 'events/EVENT-TEST/epg/epg.json'
    assert not (root/'event-epg/events').exists()


def test_failed_directory_publish_keeps_original_collection(setup, monkeypatch):
    _, store, controller, _ = setup
    tid, choice = finish(setup); builds = BuildController(store)
    builds.create_person(controller, tid, confirmed=True)
    folder = catalog_event_directory(choice)/'search'; before = contents(folder)
    rename = Path.rename
    def fail_pending(path, target):
        if path.name.startswith('.search-pending-'):
            raise OSError('Synthetic publish failure')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', fail_pending)
    with pytest.raises(OSError, match='Synthetic publish failure'):
        builds.create_person(controller, tid, confirmed=True)
    assert contents(folder) == before and len(builds.tasks()) == 1
    assert not list(folder.parent.glob('.search-*'))


def test_legacy_collection_upgrades_on_confirmed_save_only(setup, monkeypatch):
    from finmy.workbench import build_tasks, collection as collection_module
    _, store, controller, _ = setup
    tid, choice = finish(setup)
    prepare = build_tasks.prepare_collection
    def legacy(*args, **kwargs):
        collection = prepare(*args, **kwargs)
        files = collection['files']; files.pop('builder-input.json')
        manifest = json.loads(files['manifest.json'])
        manifest['format_version'] = 1
        manifest.pop('input_file')
        manifest['file_sha256'].pop('builder-input.json')
        files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
        collection['manifest_sha256'] = digest(files['manifest.json'].encode())
        return collection
    builds = BuildController(store)
    with monkeypatch.context() as patch:
        patch.setattr(build_tasks, 'prepare_collection', legacy)
        patch.setattr(collection_module, 'FILES', collection_module.LEGACY_FILES)
        first = builds.create_person(controller, tid, confirmed=True)
    first_body = deepcopy(builds.inspect(first)['body'])
    folder = catalog_event_directory(choice)/'search'
    old = contents(folder)
    assert 'builder-input.json' not in old
    controller.reassemble(tid,10000)
    assert contents(folder) == old
    second = builds.create_person(controller,tid,confirmed=True)
    assert json.loads((folder/'manifest.json').read_text())['format_version'] == 2
    assert json.loads((folder/'builder-input.json').read_text()) == builds.inspect(second)['body']['input']
    assert builds.inspect(first)['body'] == first_body
    assert not list(folder.parent.glob('.search-*'))


def test_missing_confirmed_input_is_not_treated_as_legacy_collection(setup):
    _,store,controller,_ = setup
    tid,choice = finish(setup);builds = BuildController(store)
    builds.create_person(controller,tid,confirmed=True)
    folder = catalog_event_directory(choice)/'search'
    (folder/'builder-input.json').unlink()
    before = contents(folder)
    with pytest.raises(ValueError,match='保留'):
        builds.create_person(controller,tid,confirmed=True)
    assert contents(folder) == before and len(builds.tasks()) == 1
