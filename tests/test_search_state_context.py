"""First-presentation review contracts and the original source-ledger context."""
from copy import deepcopy

import jsonschema
import pytest

from finmy.search.agent import context_for, execute_action, run_agent, model_context
from finmy.search.inspection import context_passages, pending_passages
from finmy.search.state import SearchState
from test_search_candidate_review import setup, saved, finish, offline


def test_first_presentation_declares_decisions_and_advances_in_one_call(tmp_path):
    state, tools = setup(tmp_path)
    sid, doc = saved(tools, 'interview', 'Ada Vale approved Orion.\n\nSubscribe to the newsletter.')
    tools.read_source(sid, location={'block': 0})
    state.data['priority_passages'] = []
    calls = []
    def decide(context):
        calls.append(context)
        review = context['evidence_review']
        assert 'read_state' not in str(review)
        rows = list(context_passages(context))
        assert review['phase'] == 'review_then_act'
        assert set(review['required_passage_ids']) == {r['passage_id'] for r in rows}
        assert not state.data.get('passage_reviews')  # Preparing a prompt is not a committed read.
        useful = [r for r in rows if 'approved' in r['text']]
        action = finish([sid], priority_passages=[{k: r[k] for k in
            ('source_id', 'version', 'block', 'start', 'end')} for r in useful],
            passage_exclusions={r['passage_id']: 'Newsletter boilerplate.' for r in rows if r not in useful})
        jsonschema.validate(action, review['response_schema'])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'action': 'read_source', 'source': sid}, review['response_schema'])
        return action
    run_agent(state, tools, decide)
    assert len(calls) == 1 and state.data['usage']['model'] == 1
    assert state.data['status'] == 'finished' and not pending_passages(state)
    assert tools.sources.document(sid) == doc


def test_all_sources_keep_metadata_and_marks_without_question_filtering(tmp_path):
    state, tools = setup(tmp_path)
    for i in range(12):
        sid, _ = saved(tools, f'source-{i}', f'Ada Vale approved Orion district {i}.', read=True)
        state.data['sources'][sid]['acquisition_attempts'] = {
            'one': dict(status='kept_cached', reason='Acquisition detail ' * 20)}
    state.save()
    before = deepcopy(state.data)
    context = context_for(state)
    assert len(context['sources']) == 12
    for source in context['sources']:
        sid = source['source_id']
        assert source['acquisition'] == before['sources'][sid]['acquisition_attempts']['one']
        assert source['priority_passages'] == [p for p in before['priority_passages'] if p['source_id'] == sid]
    assert context['allowed_actions'] == ['search', 'read_source', 'finish']
    assert 'state_access' not in context
    assert state.data == before
    assert SearchState(tmp_path, 'case').data == before


def test_supported_details_and_provider_queries_are_not_shortened(tmp_path):
    state, tools = setup(tmp_path)
    detail = 'Ada approved Orion subject to local consent. ' * 20
    state.data['fact_checks'] = [dict(question='What condition applied?', status='supported',
                                    source_ids=[], detail=detail)]
    for i in range(4):
        sid, _ = saved(tools, f'query-{i}', f'Orion district {i}.', read=True)
        state.data['sources'][sid]['discoveries'] = [dict(provider='exa', query=f'Orion query {i}')]
    context = context_for(state)
    assert context['fact_checks'][0]['detail'] == detail
    assert 'detail_truncated' not in context['fact_checks'][0]
    provider = next(p for p in context['provider_observations'] if p['provider'] == 'exa')
    assert provider['queries'] == [f'Orion query {i}' for i in range(4)]
