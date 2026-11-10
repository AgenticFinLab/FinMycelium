"""Interrupted research keeps model-selected originals without resetting quotas."""
import copy
import json

import pytest

from finmy.search.agent import context_for, run_agent
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import QueryLimitError, SearchTools


ACTIVISION_QUERY = 'Buffett Berkshire Activision stake 2022 annual meeting arbitrage comments'


def fixture(tmp_path, *, calls=24):
    state = SearchState(tmp_path, 'event', task={
        'target_type': 'event', 'target_name': 'Activision investment',
        'query_text': 'Buffett 2022–2023: Activision investment and rationale'},
        config=SearchConfig(providers=['bocha', 'baidu'], max_model_calls=calls))
    store = SourceStore(state)
    ids = []
    for name, body in [('purchase', 'Berkshire disclosed an Activision position.'),
                       ('rationale', 'The merger remained subject to approval.')]:
        sid = store.register('https://example.test/' + name, title=name)
        store.save_raw(sid, body.encode(), 'txt')
        store.read(sid)
        ids.append(sid)
    unread = store.register('https://example.test/unread', title='Unread candidate')
    store.save_raw(unread, b'Unreviewed text must not be included.', 'txt')
    state.save()
    tools = SearchTools(state, transport=lambda *args: pytest.fail('Unexpected provider call'),
                        fetcher=lambda *args: pytest.fail('Unexpected fetch'))
    return state, tools, ids, unread


def selection(ids, *, reason='supported'):
    return dict(action='finish', source_ids=ids, reason=reason,
                gaps=['The final disposal date remains unresolved.'])


def chosen(state):
    payload = json.loads((state.run_dir / 'builder_input.json').read_text())
    return [row['raw_data_id'] for row in payload['samples']]


def test_three_rejected_actions_switch_to_selection_instead_of_discarding_read_sources(tmp_path):
    state, tools, ids, unread = fixture(tmp_path)
    def legacy_query(query):
        assert query == ACTIVISION_QUERY
        raise QueryLimitError('baidu', 73, 72)
    tools.search = legacy_query
    contexts = []
    def model(context):
        contexts.append(copy.deepcopy(context))
        if len(contexts) <= 3:
            return dict(action='search', query=ACTIVISION_QUERY)
        assert context['phase'] == 'finalize'
        assert context['allowed_actions'] == ['finish']
        assert context['eligible_source_ids'] == ids
        assert unread not in context['eligible_source_ids']
        assert context['interrupted_research']['required_reason'] == 'insufficient'
        return selection(ids[:1])
    run_agent(state, tools, model)
    assert state.data['status'] == 'insufficient'
    assert state.data['usage'] == dict(search=0, model=4)
    assert chosen(state) == ids[:1]  # Other inspected material is not selected automatically.
    record = json.loads((state.run_dir / 'selection.json').read_text())
    assert record['reason'] == 'insufficient'
    assert any('repeated_invalid_action' in gap for gap in record['gaps'])


def test_saved_legacy_failure_gets_direct_finalization_without_repeating_search(tmp_path):
    state, tools, ids, unread = fixture(tmp_path)
    state.data.update(status='failed', stop_reason='repeated_invalid_action',
                      invalid_actions=3, usage=dict(search=2, model=6),
                      feedback=dict(error='QueryLimitError', query_units=73, query_max_units=72))
    state.save()
    originals = {p: p.read_bytes() for p in state.root.rglob('raw')}
    restored = SearchState(tmp_path, 'event')
    calls = []
    def model(context):
        calls.append(context)
        assert context['phase'] == 'finalize'
        assert context['remaining']['model'] == 18
        return selection(ids)
    run_agent(restored, SearchTools(restored, transport=tools.transport), model)
    assert len(calls) == 1
    assert restored.data['usage'] == dict(search=2, model=7)
    assert restored.data['status'] == 'insufficient'
    assert chosen(restored) == ids
    assert originals == {p: p.read_bytes() for p in originals}


def test_recovery_is_bounded_and_does_not_fabricate_selection(tmp_path):
    state, tools, ids, _ = fixture(tmp_path)
    run_agent(state, tools, lambda context: 'not json')
    assert state.data['status'] == 'failed'
    assert state.data['stop_reason'] == 'partial_finalization_failed'
    assert state.data['usage']['model'] == 5  # Three research errors + two reserved finish attempts.
    assert not (state.run_dir / 'builder_input.json').exists()
    run_agent(state, tools, lambda context: pytest.fail('Retry cannot reset recovery allowance'))
    assert state.data['usage']['model'] == 5


def test_invalid_final_selection_preserves_only_valid_model_selected_subset(tmp_path):
    state, tools, ids, unread = fixture(tmp_path)
    calls = []
    def model(context):
        calls.append(context)
        if len(calls) <= 3:
            return 'not json'
        return selection([ids[0], unread, 'invented'])
    run_agent(state, tools, model)
    assert state.data['status'] == 'insufficient'
    assert state.data['usage']['model'] == 5
    assert state.data['stop_reason'] == 'partial_handoff_recovered'
    assert chosen(state) == ids[:1]


def test_recovery_never_exceeds_original_task_model_limit(tmp_path):
    state, tools, ids, unread = fixture(tmp_path, calls=4)
    # Replay a legacy failure with exactly one model call left.
    state.data.update(status='failed', stop_reason='repeated_invalid_action', invalid_actions=3)
    state.data['usage']['model'] = 3
    run_agent(state, tools, lambda context: selection([ids[0], unread]))
    assert state.data['usage']['model'] == 4
    assert state.data['status'] == 'insufficient'
    assert chosen(state) == ids[:1]
