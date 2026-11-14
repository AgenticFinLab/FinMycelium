"""Readable portable build folders; frozen manifests and runtimes are preserved."""
import json
from pathlib import Path

import pytest

from dataset_fixture import fixture_dataset
from test_event_collection import setup, finish, offline
from finmy.workbench import records
from finmy.workbench.build_tasks import BuildController


def test_build_name_uses_creation_time_event_and_full_id():
    task = dict(task_id='PBUILD-fad2d770d21f', created_at='2026-11-14T11:20:10Z',
                catalog={'event_name': 'Goldman Sachs crisis investment'})
    expected = '20261114-192010_goldman-sachs-crisis-investment_PBUILD-fad2d770d21f'
    assert records.build_record_name(task) == expected
    task.update(status='failed', configuration={'lm_name': 'different'})
    assert records.build_record_name(task) == expected


def test_legacy_build_migration_preserves_bytes_and_needs_no_runtime(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    _, folder = records.destination(root, 'build', 'PBUILD-test')
    record = dict(task_id='PBUILD-test', event_id='EVENT-TEST', created_at='2026-11-14T01:02:03Z',
                  catalog={'event_name': 'An event', 'person_name': 'A person'},
                  configuration={'lm_name': 'provider/model'}, artifact_directory='output/builds/PBUILD-test',
                  search_collection={'manifest': {'build_record': 'workbench/build/PBUILD-test/task.json'}})
    records.save(folder, 'task.json', record)
    records.save(folder, 'summary.json', dict(task_id='PBUILD-test', status='failed'))
    original = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert records.migrate_build_records(root) == [('PBUILD-test', '20261114-090203_an-event_PBUILD-test')]
    moved = records.find_build_record(root, 'PBUILD-test').parent
    assert {p.name: p.read_bytes() for p in moved.iterdir()} == original
    assert not folder.exists() and not (root/'output').exists()
    index = (root/'workbench/build/README.md').read_text()
    assert f']({moved.name}/)' in index and 'A person' in index and 'provider/model' in index
    assert records.migrate_build_records(root) == []


def test_exports_reuse_migrated_folder_and_update_index_only_as_needed(setup):
    root, store, search, _ = setup
    tid, _ = finish(setup)
    builds = BuildController(store); bid = builds.create_person(search, tid, confirmed=True)
    row = builds.inspect(bid); original_body = row['body']
    folder = records.find_build_record(root, bid).parent
    assert folder.name.endswith('_'+bid)
    assert not Path(row['body']['artifact_directory']).exists()
    index = root/'workbench/build/README.md'
    assert bid in index.read_text() and tid[:12] in index.read_text()
    assert '../search/' in index.read_text()
    # Simulate an old ID-only portable folder, then migrate without touching the task.
    legacy = folder.with_name(bid); folder.rename(legacy)
    records.migrate_build_records(root)
    assert records.find_build_record(root, bid).parent == folder
    builds.save(bid, 'failed', original_body)
    assert records.find_build_record(root, bid).parent == folder
    assert '| failed |' in index.read_text()
    assert builds.inspect(bid)['body'] == original_body
    snapshot = {p: p.read_bytes() for p in (root/'workbench').rglob('*') if p.is_file()}
    records.export_database(store.root)
    assert all(p.read_bytes() == value for p, value in snapshot.items())


def test_migrated_name_stays_stable_when_new_exports_add_event_metadata(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    _, base = records.destination(root, 'build')
    old = dict(task_id='BUILD-old', event_id='EVENT-TEST', created_at='2026-11-14T01:02:03Z')
    folder = base/'BUILD-old'; folder.mkdir()
    records.save(folder, 'task.json', old)
    records.migrate_build_records(root)
    renamed = records.find_build_record(root, old['task_id']).parent
    assert records._record_folder(base, {**old, 'event_name': 'Now known'}, records.build_record_name) == renamed


def test_duplicate_or_symlinked_records_are_not_overwritten(tmp_path):
    root = fixture_dataset(tmp_path/'dataset')
    _, base = records.destination(root, 'build')
    record = dict(task_id='PBUILD-test', event_id='EVENT-TEST', created_at='2026-11-14T01:02:03Z')
    for name in ('PBUILD-test', 'duplicate'):
        (base/name).mkdir(); records.save(base/name, 'task.json', record)
    before = (base/'PBUILD-test/task.json').read_bytes()
    with pytest.raises(ValueError, match='重复'):
        records.migrate_build_records(root)
    assert (base/'PBUILD-test/task.json').read_bytes() == before
    (base/'duplicate/task.json').unlink(); (base/'duplicate').rmdir()
    outside = tmp_path/'outside'; outside.mkdir()
    (base/'link').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='符号链接'):
        records.migrate_build_records(root)
    assert not list(outside.iterdir())
