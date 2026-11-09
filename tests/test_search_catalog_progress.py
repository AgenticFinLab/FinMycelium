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


def test_complete_catalog_has_explicit_end_even_when_it_fits(tmp_path):
    state, tools = fixture(tmp_path)
    context = context_for(state)
    assert len(context['sources']) == 15
    assert context['source_listing'] == dict(total_unreviewed=15, offset=0, shown=15,
                                           next_offset=None, at_end=True, invalid_offset=False)
    assert context['activity_counts']['saved_candidates'] == 15
    assert context['activity_counts']['inspected_sources'] == 0


def test_out_of_bounds_offset_is_rejected_without_wrapping(tmp_path):
    state, tools = fixture(tmp_path)
    state.data['source_catalog_offset'] = 3
    for offset in (15, 30, 45):
        with pytest.raises(ValueError, match='outside 15 unread candidates'):
            execute_action(state, tools, {'action': 'list_sources', 'offset': offset})
        assert state.data['source_catalog_offset'] == 3
    # Old checkpoints with an invalid cursor expose it explicitly.
    state.data['source_catalog_offset'] = 75
    context = context_for(state)
    assert context['source_listing']['invalid_offset']
    assert context['source_listing']['offset'] == 75
    assert context['source_listing']['restart_offset'] == 0
    assert state.data['source_catalog_offset'] == 75


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


def test_actual_increasing_offsets_cannot_reset_error_counter_as_success(tmp_path):
    state, tools = fixture(tmp_path)
    replies = iter([{'action': 'list_sources', 'offset': x} for x in (15, 30, 45)] + [empty_finish()])
    run_agent(state, tools, lambda _: next(replies))
    assert state.data['usage']['model'] == 4
    assert state.data['status'] == 'insufficient'
    assert state.data['partial_finalization']['trigger'] == 'repeated_invalid_action'


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


def test_new_catalog_entry_resets_repeated_view_count(tmp_path):
    state, tools = fixture(tmp_path, count=1)
    steps = []
    def model(context):
        steps.append(context)
        if len(steps) == 3:
            return empty_finish()
        if len(steps) == 2:
            SourceStore(state).register('https://example.test/new', title='New candidate')
        return {'action': 'list_sources', 'offset': 0}
    run_agent(state, tools, model)
    assert 'partial_finalization' not in state.data
    assert state.data['catalog_progress']['stalled'] == 0


def test_empty_catalog_metadata_is_explicit(tmp_path):
    state, tools = fixture(tmp_path, count=0)
    context = context_for(state)
    assert context['source_listing']['at_end']
    assert context['source_listing']['shown'] == 0
    assert context['source_listing']['next_offset'] is None
