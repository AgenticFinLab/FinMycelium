"""Task coverage cannot be inferred from a fully supported self-generated question list."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.progress import record_progress
from finmy.search.review import record_checks
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_evidence_routing import check
from test_search_integrated_review import mark


def assessment(*questions):
    return dict(summary='Local consent is established; investigate the remaining decision preconditions '
                        'requested by the original task before considering this direction complete.',
                followups=[dict(question=q, reason='The task asks for the conditions of Ada\'s decision; '
                                'the existing consent evidence does not establish this separate condition.')
                           for q in questions])


def initial_support(tmp_path, **options):
    state, tools = setup(tmp_path, **options)
    text = 'Ada Vale required local consent before approving the Orion program.'
    sid, _ = saved(tools, 'conditions', text, read=True)
    q = 'What conditions did Ada impose on the Orion program?'
    record_checks(state, [check(q, sid, mark(sid, 0, text), detail='Local consent was required.')])
    return state, tools, sid, text, q


def test_supported_checks_alone_defer_finish_and_request_original_task_review(tmp_path):
    state, tools, sid, _, _ = initial_support(tmp_path)
    action = finish([sid])
    action.pop('scope_review')
    response = execute_action(state, tools, action)
    assert response['kind'] == 'task_scope_review' and response['operation_deferred']
    assert not (state.run_dir / 'builder_input.json').exists()
    assert all(c['status'] == 'supported' for c in state.data['fact_checks'])
    state.save()
    resumed = SearchState(tmp_path, 'case')
    context = context_for(resumed)
    assert context['task'] == state.data['task']
    assert context['task_scope_review']['required_before_finish']
    assert 'ORIGINAL task' in context['task_scope_review']['hint']
    assert resumed.data['usage'] == {'model': 0, 'search': 0}


def test_scope_followup_returns_to_search_and_preserves_existing_answer(tmp_path):
    state, tools, sid, text, broad = initial_support(tmp_path, providers=['exa'])
    followup = 'Was a funding guarantee a precondition for Ada approving Orion?'
    narrow = 'Did Ada require local consent for Orion?'
    old = deepcopy(state.data['fact_checks'][0]['evidence'])
    response = execute_action(state, tools, finish([sid], scope_review=assessment(followup),
        fact_checks=[dict(check(narrow, sid, mark(sid, 0, text), detail='Local consent was required.'),
                          replaces=[broad])]))
    assert response['kind'] == 'task_scope_followups'
    assert response['next_steps'][0]['question'] == followup
    assert state.data['fact_checks'][0]['evidence'] == old
    assert state.data['fact_checks'][0]['status'] == 'supported'
    assert state.data['fact_checks'][1]['status'] == 'missing'
    assert not (state.run_dir / 'builder_input.json').exists()

    state.save()
    state = SearchState(tmp_path, 'case')
    extra = 'Ada Vale said she would approve Orion only if the funding guarantee remained in force.'
    requests = []
    def transport(provider, payload, config):
        requests.append(payload)
        return {'results': [dict(url='https://example.org/guarantee', title='Orion funding condition', text=extra)]}
    tools = SearchTools(state, transport=transport, fetcher=lambda _: pytest.fail('Use returned originals'))
    tools.sources.can_complete_partial = False
    calls = []
    def decide(context):
        calls.append(context)
        if len(calls) == 1:
            return dict(action='search', question=followup, query='Ada Orion funding guarantee condition',
                        gap='The task requests decision conditions; only consent has been established.')
        source = next(c for c in context['cached_evidence'] if any(s['text'] == extra for s in c['spans']))
        span = next(s for s in source['spans'] if s['text'] == extra)
        action = finish([sid], fact_checks=[check(followup, source['source_id'],
            dict(source_id=source['source_id'], **{k: span[k] for k in ('block', 'start', 'end')}),
            detail='Ada made approval conditional on a funding guarantee.')])
        action.pop('scope_review')  # Reuse the saved assessment, with its followup now answered.
        return action
    run_agent(state, tools, decide, max_steps=2)
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'supported'
    assert len(calls) == 2 and len(requests) == 1
    body = (state.run_dir / 'builder_input.json').read_text()
    assert text in body and extra in body
    assert all(c['citation_status'] == 'delivered' for c in state.data['fact_checks'])


def test_reopened_question_keeps_evidence_and_review_omission_cannot_erase_gap(tmp_path):
    state, tools, sid, text, broad = initial_support(tmp_path)
    evidence = deepcopy(state.data['fact_checks'][0]['evidence'])
    execute_action(state, tools, finish([sid], scope_review=assessment(broad)))
    check = state.data['fact_checks'][0]
    assert check['status'] == 'missing' and check['evidence'] == evidence
    assert 'Local consent was required.' in check['detail']
    execute_action(state, tools, finish([sid], scope_review=assessment()))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    report = json.loads((state.run_dir / 'selection.json').read_text())
    assert any(broad in gap for gap in report['gaps'])
    assert text in (state.run_dir / 'builder_input.json').read_text()


def test_complete_inline_review_needs_no_extra_call(tmp_path):
    state, tools, sid, _, _ = initial_support(tmp_path)
    calls = []
    def decide(context):
        calls.append(context)
        return finish([sid], scope_review=dict(summary='For this bounded consent question, the '
            'located statement answers the task; no unresolved task requirement or source lead remains.', followups=[]))
    run_agent(state, tools, decide)
    assert len(calls) == 1 and state.data['stop_reason'] == 'supported'
    assert state.data['scope_review']['followups'] == []


@pytest.mark.parametrize('review', [None, {}, {'summary': 'Checked.', 'followups': ['Bad shape']}])
def test_missing_or_invalid_review_is_bounded_and_cannot_claim_complete_scope(tmp_path, review):
    state, tools, sid, _, _ = initial_support(tmp_path)
    action = finish([sid])
    action.pop('scope_review')
    if review is not None:
        action['scope_review'] = review
    run_agent(state, tools, lambda _: deepcopy(action))
    assert state.data['status'] == 'finished' and state.data['usage']['model'] == 2
    assert state.data['stop_reason'] == 'low_gain'
    assert 'Task-scope coverage was not assessed' in str(state.data['feedback']['gaps'])


def test_forced_finalization_keeps_unreviewed_scope_as_gap_without_extra_call(tmp_path):
    state, tools, sid, text, _ = initial_support(tmp_path, max_model_calls=1)
    action = finish([sid])
    action.pop('scope_review')
    run_agent(state, tools, lambda _: action)
    assert state.data['usage']['model'] == 1 and state.data['status'] == 'finished'
    assert state.data['stop_reason'] == 'low_gain'
    assert text in (state.run_dir / 'builder_input.json').read_text()


def test_forced_finalization_records_new_scope_gap_without_attempting_search(tmp_path):
    state, tools, sid, text, _ = initial_support(tmp_path, max_model_calls=1)
    question = 'Was a funding guarantee required before approving Orion?'
    run_agent(state, tools, lambda _: finish([sid], scope_review=assessment(question)))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    assert state.data['usage'] == {'model': 1, 'search': 0}
    assert question in str(state.data['feedback']['gaps'])
    assert text in (state.run_dir / 'builder_input.json').read_text()


def test_invalid_review_cannot_partially_register_followups_or_lose_support(tmp_path):
    state, tools, sid, _, _ = initial_support(tmp_path)
    checks = deepcopy(state.data['fact_checks'])
    passages = deepcopy(state.data['priority_passages'])
    review = assessment('Was a funding guarantee required?')
    review['followups'].append(dict(question=[], reason='Malformed question'))
    response = execute_action(state, tools, finish([sid], scope_review=review))
    assert response['kind'] == 'task_scope_review' and response['error']
    assert state.data['fact_checks'] == checks
    assert state.data['priority_passages'] == passages
    assert 'scope_review' not in state.data


def test_scope_review_does_not_count_as_a_failed_read(tmp_path):
    state, _, _, _, _ = initial_support(tmp_path)
    state.data['research_progress'] = dict(consecutive_no_gain=2)
    for kind in ('task_scope_review', 'task_scope_followups'):
        record_progress(state, 'review_passages', dict(kind=kind, operation_deferred=True))
    assert state.data['research_progress']['consecutive_no_gain'] == 2


@pytest.mark.parametrize('attempted', [False, True])
def test_renaming_followup_preserves_attempt_and_navigation_history(tmp_path, attempted):
    state, tools, sid, _, _ = initial_support(tmp_path)
    old = 'Did Ada need a funding guarantee for Orion?'
    new = 'Was a funding guarantee required before approving Orion?'
    execute_action(state, tools, finish([sid], scope_review=assessment(old)))
    if attempted:
        state.data.setdefault('actions', []).append(dict(action='search', question=old,
                                                        query='Orion funding guarantee'))
    record_checks(state, [dict(check(new, status='missing', detail='No confirming original found.'), replaces=[old])])
    action = finish([sid])
    action.pop('scope_review')
    response = execute_action(state, tools, action)
    assert not response.get('operation_deferred')
    assert state.data['stop_reason'] == 'low_gain'
    assert new in str(response['gaps'])
