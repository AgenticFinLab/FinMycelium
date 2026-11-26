"""Compare the original research scope with the same persisted question ledger."""
from .review import question_attempts, research_steps


REVIEW_HINT = (
    'Compare the ORIGINAL task and research_scope with the actual answers in fact_checks, '
    'not just their supported flags. For each important part of the task, distinguish '
    'what was established from what remains unexplored. One example does not exhaust an '
    'open-ended question about reasons, conditions or participation. Separate negotiated '
    'terms from the person\'s decision preconditions, and announced events from confirmed '
    'outcomes when the task requires them. Add only important task-derived questions or '
    'questions motivated by a concrete source lead; do not invent a universal checklist. '
    'Return scope_review: {"summary":"Coverage, limits and why the research can stop", '
    '"followups":[{"question":"One unresolved fact", "reason":"Why the task or a '
    'source lead requires checking it"}]}. An empty followups list needs a substantive '
    'summary of coverage. Keep existing support; narrow an answered broad check and '
    'record its unresolved parts separately. Use normal search/read_source actions for '
    'followups within the remaining budget.'
)


def _record_review(state, value):
    if (not isinstance(value, dict) or set(value) != {'summary', 'followups'}
            or not isinstance(value['summary'], str) or not value['summary'].strip()
            or not isinstance(value['followups'], list)):
        raise ValueError('scope_review needs a nonempty summary and a followups list')
    for row in value['followups']:
        if (not isinstance(row, dict) or set(row) != {'question', 'reason'}
                or any(not isinstance(row[k], str) or not row[k].strip()
                       for k in ('question', 'reason'))):
            raise ValueError('Each scope followup needs a question and its task/source-based reason')
    checks = state.data.setdefault('fact_checks', [])
    by_name = {name: check for check in checks
               for name in [check['question'], *check.get('replaces', [])]}
    followups = []
    for row in value['followups']:
        question, reason = row['question'].strip(), row['reason'].strip()
        check = by_name.get(question)
        if check is None:
            check = dict(question=question, status='missing', source_ids=[],
                         evidence=[], detail=reason)
            checks.append(check)
            by_name[question] = check
        elif check['status'] == 'supported':
            # A new unresolved part reopens the question, preserving its originals.
            check.update(status='missing', detail=check['detail'] + ' Unresolved: ' + reason)
            check.pop('citation_status', None)
        followup = dict(question=check['question'], reason=reason)
        if followup not in followups:
            followups.append(followup)
    state.data['scope_review'] = dict(summary=value['summary'].strip(), followups=followups)
    state.trace(dict(action='task_scope_review', **state.data['scope_review']))
    state.save()


def review_task_scope(state, action):
    """Require one explicit scope assessment, with bounded opportunities for followup.

    No model or retrieval tool is invoked here. Forced finalization always proceeds,
    and missing assessments become gaps rather than a claim of complete research.
    """
    if not state.data.get('retrieval_plan'):
        return None  # Preserve the historical document-selection protocol.
    forced = bool(state.data.get('finalization_trigger')
                  or state.data['usage']['model'] >= state.config.max_model_calls)
    error = None
    if 'scope_review' in action:
        try:
            _record_review(state, action['scope_review'])
        except ValueError as exc:
            error = str(exc)
    if error or not state.data.get('scope_review'):
        if not forced and not state.data.get('scope_review_requested'):
            state.data['scope_review_requested'] = True
            state.save()
            return dict(kind='task_scope_review', operation_deferred=True,
                        hint=REVIEW_HINT, error=error)
        action['gaps'].append('Task-scope coverage was not assessed.' + (' ' + error if error else ''))
        if action['reason'] == 'supported':
            action['reason'] = 'low_gain'
        return None

    # All unresolved facts stay in fact_checks even if a later review omits them.
    # Give newly identified questions one navigation turn; it is not an invented
    # search attempt, and a persistent inability to investigate remains a gap.
    names = {row['question'] for row in state.data['scope_review']['followups']}
    offered = set(state.data.get('scope_followups_offered', []))
    unresolved = [c for c in state.data.get('fact_checks', [])
                  if names.intersection([c['question'], *c.get('replaces', [])])
                  and c['status'] != 'supported'
                  and not offered.intersection([c['question'], *c.get('replaces', [])])
                  and not question_attempts(state, c)]
    if not forced and unresolved:
        steps = research_steps(state, unresolved)
        if steps:
            state.data['scope_followups_offered'] = list(dict.fromkeys(
                state.data.get('scope_followups_offered', []) + [s['question'] for s in steps]))
            state.save()
            return dict(kind='task_scope_followups', operation_deferred=True, next_steps=steps,
                        hint='These important questions were identified by the scope review. '
                             'Investigate through the normal research loop, or retain an explicit '
                             'gap explaining why further work is unavailable or low yield. '
                             'An answered sibling question does not resolve them.')
    return None
