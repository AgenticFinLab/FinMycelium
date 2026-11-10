"""Exhausted saved catalogs cannot masquerade as fresh research indefinitely."""
import copy
import json

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


def fixture(tmp_path, count=15):
    state = SearchState(tmp_path, 'event', task={
        'target_type': 'event', 'target_name': 'Succession', 'query_text': 'Buffett succession 2022–2023',
        'existing_event': {'questions': ['What role did Greg Abel hold?']}},
        config=SearchConfig(max_model_calls=24))
    store = SourceStore(state)
    for index in range(count):
        sid = store.register(f'https://example.test/{index}', title=f'Candidate {index}')
        store.save_raw(sid, b'An unrelated investment report.', 'txt')
    state.save()
    tools = SearchTools(state, transport=lambda *a: pytest.fail('Unexpected provider call'),
                        fetcher=lambda *a: pytest.fail('Unexpected network fetch'))
    return state, tools


def empty_finish():
    return {'action': 'finish', 'source_ids': [], 'reason': 'supported',
            'gaps': ['No search requests were made and the catalog is empty.']}


def test_repeated_catalog_views_finish_without_reading_irrelevant_sources(tmp_path):
    state, tools = fixture(tmp_path)
    state.data['usage']['search'] = 12
    contexts = []
    def model(context):
        contexts.append(copy.deepcopy(context))
        return empty_finish() if context['phase'] == 'finalize' else {'action': 'list_sources', 'offset': 0}
    run_agent(state, tools, model)
    assert len(contexts) == 4
    assert state.data['status'] == 'insufficient'
    assert state.data['read_sources'] == []
    final = contexts[-1]
    assert final['sources'] == []  # Eligible list is empty, full catalog is not.
    assert final['activity_counts']['saved_candidates'] == 15
    assert final['activity_counts']['provider_requests'] == 12
    selection = json.loads((state.run_dir / 'selection.json').read_text())
    text = ' '.join(selection['gaps'])
    assert 'Recorded provider requests: 12' in text and 'saved candidates: 15' in text
    assert 'Unverified: What role did Greg Abel hold?' in text
    assert 'No search requests were made' not in text
    assert 'unverified_empty_handoff_gaps' in (state.run_dir / 'trace.jsonl').read_text()


def test_no_progress_history_survives_checkpoint_resume(tmp_path):
    state, tools = fixture(tmp_path)
    def model(context):
        return empty_finish() if context['phase'] == 'finalize' else {'action': 'list_sources', 'offset': 0}
    run_agent(state, tools, model, max_steps=2)
    assert state.data['status'] == 'paused'
    state = SearchState(tmp_path, 'event')
    tools = SearchTools(state)
    run_agent(state, tools, model)
    assert state.data['status'] == 'insufficient'
    assert state.data['usage']['model'] == 4


def test_provider_outage_allows_local_inspection_without_search(tmp_path):
    state, tools = fixture(tmp_path, count=1)
    sid = next(iter(state.data['sources']))
    tools.search_availability = lambda: {'providers_available': [], 'all_providers_unavailable': True}
    contexts = []
    def model(context):
        contexts.append(copy.deepcopy(context))
        assert 'search' not in context['allowed_actions']
        if len(contexts) == 1:
            return {'action': 'read_source', 'source': sid}
        return {'action': 'finish', 'source_ids': [sid], 'reason': 'insufficient',
                'gaps': ['Other sources could not be retrieved.']}
    run_agent(state, tools, model)
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'provider_unavailable'
    assert state.data['usage']['search'] == 0
    assert state.data['read_sources'] == [sid]
