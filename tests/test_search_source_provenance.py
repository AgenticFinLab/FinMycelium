"""Structured source provenance survives search budgeting and workbench adoption."""

import copy
import json
import socket
from types import SimpleNamespace

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.person_epg.sparse_adapter import build_person_facts
from finmy.person_epg.validation import validate_person_epg
from finmy.search.control import SearchController
from finmy.search.handoff import assemble, assemble_sources, derive_input, materialize_complete, prepare_complete_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest, write_json
from finmy.workbench.search_bridge import adopt_sources
from finmy.workbench.store import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('Unexpected network'))


def source(state, suffix, publication, text='Alice approved a share purchase.'):
    store = SourceStore(state)
    sid = store.register('https://example.test/' + suffix, title='Filing ' + suffix,
                         discovery={'published_at': publication})
    document = store.save_raw(sid, text.encode(), 'txt')
    store.read(sid)
    return sid, document


def state_at(tmp_path):
    return SearchState(tmp_path, 'case', task={'target_type': 'person', 'target_name': 'Alice',
        'query_text': 'Trace the share purchase', 'key_words': ['shares']})


def person_package(payload):
    inputs = SimpleNamespace(user_query=UserQueryInput(**payload['user_query']),
        samples=[DataSample(**row) for row in payload['samples']])
    package, _ = build_person_facts({'event_id': 'CASE', 'title': 'Documented investment', 'stages': []},
        inputs, {'subject_id': 'alice', 'name': 'Alice', 'coverage_start': '2023', 'coverage_end': '2023'})
    assert validate_person_epg(package) == {'valid': True, 'errors': []}
    return package


def test_complete_handoff_exports_canonical_metadata_and_freezes_selected_versions(tmp_path):
    state = state_at(tmp_path)
    dated, document = source(state, 'dated', '2023-05-01T10:00:00+08:00')
    partial, _ = source(state, 'partial', '2023-05-02', 'A second source provided background.')
    full, complete = prepare_complete_sources(state, [dated, partial])
    assert set(full) == {'user_query', 'samples'}
    registry = full['user_query']['extras']['source_registry']
    assert set(registry) == {dated, partial}
    assert registry[dated]['version'] == document['version']
    assert registry[dated]['source_version'] == document['version']
    assert registry[dated]['published_at'] == '2023-05-01T02:00:00Z'
    assert registry[partial]['published_at'] is None
    assert registry[partial]['published_at_raw'] == '2023-05-02'
    package = person_package(full)
    assert package['source_document'][0]['title'] == 'Filing dated'
    assert package['source_document'][0]['source_url'] == 'https://example.test/dated'
    assert package['source_document'][1]['published_at'] is None
    before = copy.deepcopy(full)
    state.data['sources'][dated].update(title='Later title', published_at='2025-01-01T00:00:00Z')
    SourceStore(state).save_raw(dated, b'A later amended body.', 'txt')
    assert materialize_complete(state, complete) == before
    full['user_query']['extras']['source_registry'][dated]['title'] = 'Caller mutation'
    assert materialize_complete(state, complete) == before


def test_budget_and_controller_rebudget_preserve_frozen_registry_without_spending_text_budget(tmp_path):
    controller = SearchController(tmp_path)
    task_id = controller.create({'target_type': 'person', 'target_name': 'Alice',
        'query_text': 'Approval shares', 'key_words': ['approval']}, {})
    state = SearchState(tmp_path, task_id)
    long, original = source(state, 'long', '2023-05-02T00:00:00Z',
        '\n\n'.join(f'Approval paragraph {i}: ' + 'Shares were subject to conditions. ' * 10 for i in range(12)))
    short, _ = source(state, 'short', '2023', 'Short filing with purchase confirmation.')
    limited = assemble_sources(state, [long, short], max_chars=900)
    saved_complete = (state.run_dir / 'complete_material.json').read_bytes()
    selection = json.loads((state.run_dir / 'selection.json').read_text())
    assert sum(len(row['content']) for row in limited['samples']) == selection['material_chars'] <= 900
    assert selection['omitted']
    before = copy.deepcopy(limited['user_query'])
    state.data['sources'][long]['title'] = 'Changed after snapshot'
    SourceStore(state).save_raw(long, b'Replacement content.', 'txt')
    expanded = controller.reassemble(task_id, 60000)
    assert expanded['user_query'] == before
    assert expanded['user_query']['extras']['source_registry'][long]['version'] == original['version']
    assert (state.run_dir / 'complete_material.json').read_bytes() == saved_complete
    assert 'Approval paragraph 11' in expanded['samples'][0]['content']
    assert person_package(expanded)['source_document'][0]['title'] == 'Filing long'


def test_legacy_manifest_stays_readable_without_made_up_metadata(tmp_path):
    state = state_at(tmp_path)
    sid, _ = source(state, 'legacy', None)
    _, complete = prepare_complete_sources(state, [sid])
    complete['user_query'].pop('extras')
    complete.pop('complete_id')
    complete['complete_id'] = digest(complete)
    full = materialize_complete(state, complete)
    budgeted, _ = derive_input(state, complete, max_chars=60000)
    assert budgeted == full
    assert 'extras' not in full['user_query']


def test_passage_handoff_records_multiple_known_versions_without_picking_one(tmp_path):
    state = state_at(tmp_path)
    sid, first = source(state, 'revised', '2023-05-02T00:00:00Z')
    store = SourceStore(state)
    second = store.save_raw(sid, b'Alice completed the share purchase.', 'txt')
    store.read(sid)
    selections = [{'source_id': sid, 'version': doc['version'], 'block': 0,
                   'start': 0, 'end': len(doc['blocks'][0]['text'])} for doc in (first, second)]
    payload = assemble(state, selections)
    metadata = payload['user_query']['extras']['source_registry'][sid]
    assert metadata['versions'] == [first['version'], second['version']]
    assert 'version' not in metadata
    assert metadata['published_at'] is None
    assert set(metadata['sample_versions']) == {sample['sample_id'] for sample in payload['samples']}
    assert len(person_package(payload)['source_document']) == 2


def test_workbench_adoption_persists_search_metadata_and_legacy_published_field(tmp_path):
    workbench = Store(tmp_path / 'workbench')
    event_id = workbench.create_events([{'event_name_en': 'Share purchase'}])[0]
    controller = SearchController(tmp_path / 'search')
    task_id = controller.create({'target_type': 'person', 'target_name': 'Alice',
        'query_text': 'Trace investment', 'event_id': event_id}, {})
    state = SearchState(controller.root, task_id)
    sid, document = source(state, 'adopted', '2023-05-02T08:00:00+08:00')
    assemble_sources(state, [sid])
    state.data['sources'][sid]['title'] = 'Later mutable title'
    state.save()
    assert adopt_sources(controller, task_id, workbench) == 1
    assert adopt_sources(controller, task_id, workbench) == 0
    reopened = Store(tmp_path / 'workbench')
    payload = reopened.input_bundle(event_id)
    metadata = payload['user_query']['extras']['source_registry'][payload['samples'][0]['raw_data_id']]
    assert metadata['title'] == 'Filing adopted'
    assert metadata['source_id'] == sid and metadata['version'] == document['version']
    assert metadata['published'] == metadata['published_at_raw'] == '2023-05-02T08:00:00+08:00'
    assert metadata['published_at'] == '2023-05-02T00:00:00Z'
    assert reopened.decision(event_id, 'evidence') is None
    assert person_package(payload)['source_document'][0]['published_at'] == '2023-05-02T00:00:00Z'
    manual = reopened.add_source(event_id, 'Manual date only', text='Another body.', published='2023-06-01')
    entry = reopened.input_bundle(event_id)['user_query']['extras']['source_registry'][manual]
    assert entry['published'] == entry['published_at_raw'] == '2023-06-01'
    assert entry['published_at'] is None


def test_conflicting_discovery_dates_remain_unresolved(tmp_path):
    state = state_at(tmp_path)
    sid, _ = source(state, 'conflicting', '2023-05-01T00:00:00Z')
    state.data['sources'][sid]['discoveries'].append({'published_at': '2023-06-01T00:00:00Z'})
    payload, _ = prepare_complete_sources(state, [sid])
    metadata = payload['user_query']['extras']['source_registry'][sid]
    assert metadata['published_at'] is None
    assert len(metadata['publication_candidates']) == 2
    assert person_package(payload)['source_document'][0]['published_at'] is None


def test_legacy_workbench_adoption_uses_selected_version_instead_of_latest(tmp_path):
    workbench = Store(tmp_path / 'workbench')
    event_id = workbench.create_events([{'event_name_en': 'Share purchase'}])[0]
    controller = SearchController(tmp_path / 'search')
    task_id = controller.create({'target_type': 'event', 'target_name': 'Purchase',
        'query_text': 'Trace investment', 'event_id': event_id}, {})
    state = SearchState(controller.root, task_id)
    sid, original = source(state, 'legacy-adoption', None)
    payload = assemble_sources(state, [sid])
    payload['user_query'].pop('extras')
    write_json(state.run_dir / 'builder_input.json', payload)
    replacement = SourceStore(state).save_raw(sid, b'A newer source body.', 'txt')
    assert original['version'] != replacement['version']
    assert adopt_sources(controller, task_id, workbench) == 1
    restored = workbench.input_bundle(event_id)
    metadata = next(iter(restored['user_query']['extras']['source_registry'].values()))
    assert metadata['source_version'] == original['version']
    assert metadata['published_at'] is None
