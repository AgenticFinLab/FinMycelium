"""Located finish checks over saved originals, independent of domain."""
from .sources import SourceStore, canonical_url
from .state import digest


def selection_ranges(state, entry):
    if 'ranges' in entry:
        return entry['ranges']
    doc = SourceStore(state).document(entry['source_id'],entry['version'])
    return [dict(block=b,start=0,end=len(doc['blocks'][b]['text'])) for b in entry['blocks']]


def question_attempts(state, check):
    """Reuse accepted actions, including a question's explicit rename history."""
    names = {check['question'], *check.get('replaces', [])}
    return [a for a in state.data.get('actions', [])
            if a.get('action') in {'search', 'read_source'}
            and (a.get('question') in names or
                 not a.get('question') and (a.get('query') in names or a.get('gap') in names))]


def research_steps(state, checks=None):
    """One question-driven route for ordinary decisions and a proposed finish.

    These are navigation suggestions, never evidence judgments or tool execution.
    Candidate text is presented only by the normal, budgeted decision context.
    """
    from .retrieval import cached_candidates
    from .progress import query_read_feedback
    checks = state.data.get('fact_checks', []) if checks is None else checks
    steps = []
    for check in checks:
        if check['status'] == 'supported':
            continue
        question = check['question']
        attempts = question_attempts(state, check)
        candidates = cached_candidates(state, dict(question=question, fact_checks=checks),
                                       max_chars=min(1600, state.config.max_read_chars))
        candidate = next((c for c in candidates if not query_read_feedback(
            state, c['source_id'], question, question=question)), None)
        if candidate:
            span = candidate['spans'][-1]
            steps.append(dict(question=question,
                remedy='read_source' if candidate['reading_status']=='cached_unread' else 'review_passage',
                source=candidate['source_id'], version=candidate['version'],
                location=dict(block=span['block'], offset=span['start']),
                reason='Check this candidate against the question; cite useful shown support in fact_checks.'))
        elif not any(a['action']=='search' for a in attempts) and (
                state.data['usage']['search'] < state.config.max_search_requests
                and len(state.data['read_sources']) < state.config.max_read_sources):
            steps.append(dict(question=question, remedy='search',
                reason='No usable cached match; this task question has no recorded targeted search.'))
        if len(steps) == 3:
            break
    return steps


def delivery_steps(state, issues):
    """Route known missing citations by location; do not reopen general search."""
    from .evidence import validate_passage, UninspectedPassage
    from .reading import unread_ranges
    steps = []
    for issue in issues:
        if not issue['evidence']:
            steps.append(dict(question=issue['question'],remedy='correct_citation',
                              reason='Supply the supporting original location or retain the gap.'))
        for ref in issue['evidence']:
            step = dict(question=issue['question'],evidence=ref)
            try:
                mark = validate_passage(state,ref)
            except UninspectedPassage as exc:
                step.update(remedy='read_source',reason=str(exc),source=ref['source_id'],
                            location=dict(block=ref['block'],offset=ref['start']))
            except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:
                step.update(remedy='correct_citation',reason=str(exc))
            else:
                marks = [m for m in state.data.get('priority_passages',[]) if
                         m['source_id']==mark['source_id'] and m['version']==mark['version']]
                marked = not any(unread_ranges(mark['block'],mark['start'],mark['end'],marks))
                step.update(remedy='revise_selection' if marked else 'mark_passage',
                            reason='Support was marked but omitted; inspect exclusions, duplicates and the material limit.'
                            if marked else 'Support is already inspected; mark this location without reading it again.')
            steps.append(step)
    return steps


def saved_gap_evidence(state, questions, *, max_chars, selected=None):
    """Return whole saved ranges relevant to gap wording, within the existing allowance."""
    import json
    import re
    from .budget import rank_blocks
    from .reading import unread_ranges
    store, documents, passages, seen = SourceStore(state), {}, [], set()
    delivered = {e['source_id']:e for e in selected} if selected is not None else None
    for mark in state.data.get('priority_passages', []):
        sid, version = mark['source_id'], mark['version']
        if state.data['sources'][sid].get('version') != version:
            continue
        if delivered is not None:
            entry = delivered.get(sid)
            if (not entry or entry['version'] != version or any(unread_ranges(
                    mark['block'], mark['start'], mark['end'], selection_ranges(state, entry)))):
                continue
        key = (sid, version)
        if key not in documents:
            documents[key] = store.document(sid, version)
        text = documents[key]['blocks'][mark['block']]['text'][mark['start']:mark['end']]
        if not text or text in seen:
            continue
        seen.add(text)
        passages.append(dict(source_id=sid, version=version, block=mark['block'],
                             start=mark['start'], end=mark['end'], text=text))
    # A known quantity in one clause must not drown out the missing fact in another.
    queries = [part for question in questions for part in re.split(r'[;；]|\.\s+',question) if part.strip()]
    ranked = rank_blocks({'blocks':list(range(len(passages)))}, {'blocks':passages}, queries)
    queues = [[i for i,score in row['ranking'] if score > 0] for row in ranked]
    order = dict.fromkeys(i for rank in range(max(map(len,queues),default=0))
                         for queue in queues for i in queue[rank:rank+1])
    result = []
    for i in order:
        trial = result + [passages[i]]
        if len(json.dumps(trial,ensure_ascii=False)) + 32 <= max_chars:
            result = trial  # Never truncate a saved sentence to fit the review.
    return result


def review_before_finish(state, issues, *, gaps=(), selected=None):
    """Repair citations or compare free-form gaps with saved support once."""
    if (state.data.get('finalization_trigger')
            or state.data['usage']['model'] >= state.config.max_model_calls):
        return None
    if not issues:
        names = {q for c in state.data.get('fact_checks', [])
                 for q in [c['question'], *c.get('replaces', [])]}
        notes = [g for g in gaps if not any(g == q or g.startswith(q+':') for q in names)]
        if (not notes or state.data.get('finish_gap_review') is not None
                or not saved_gap_evidence(state,notes,max_chars=3200,selected=selected)):
            return None
        feedback = dict(kind='finish_gap_review', operation_deferred=True, gaps=notes,
            hint='Compare these proposed gaps with saved_gap_evidence. Preserve facts and '
                 'announced quantities already present; distinguish missing confirmation of '
                 'completion. Correct fact_checks and gaps together, then finish. '
                 'Do not search or reread solely to restate saved evidence.')
        state.data['finish_gap_review'] = state.data['feedback'] = feedback
        state.save()
        state.trace(dict(action='finish_gap_review', **feedback))
        return feedback
    if state.data.get('finish_delivery_review') is not None:
        return None
    feedback = dict(kind='finish_delivery_review', operation_deferred=True,
        delivery_issues=list(issues), next_steps=delivery_steps(state, issues),
        hint='Repair these exact citations or retain their gaps. No general candidate rescan is needed.')
    state.data['finish_delivery_review'] = state.data['feedback'] = feedback
    state.save()
    state.trace(dict(action='finish_delivery_review', **feedback))
    return feedback


def delivered_checks(checks, selected, *, state=None):
    """Validate located citations against delivered intervals, without a model."""
    from .reading import unread_ranges
    delivered = {e['source_id']:e for e in selected}
    result, issues = [], []
    for original in checks:
        check = dict(original)
        if check['status'] != 'supported':
            result.append(check)
            continue
        refs = check.get('evidence')
        missing_refs = []
        if refs is None:
            # Older callers cite only sources. Preserve that contract and label its
            # limited resolution instead of inventing supporting coordinates.
            valid = all(sid in delivered for sid in check['source_ids'])
            check['citation_status'] = 'source_only'
        else:
            valid = bool(refs)
            for ref in refs:
                entry = (delivered.get(ref['source_id'], {}) if isinstance(ref,dict)
                         and isinstance(ref.get('source_id'),str) else {})
                if not entry or ref['source_id'] not in check['source_ids']:
                    missing_refs.append(ref)
                    continue
                b,a,z = (ref.get(k) for k in ('block','start','end'))
                ranges = selection_ranges(state,entry) if state is not None else entry.get('ranges',[])
                if not (ref.get('version',entry['version']) == entry['version']
                         and all(type(v) is int for v in (b,a,z)) and 0 <= a < z
                         and not any(unread_ranges(b,a,z,ranges))):
                    missing_refs.append(ref)
            valid = valid and not missing_refs
            check['citation_status'] = 'delivered' if valid else 'not_delivered'
        if not valid:
            issues.append(dict(question=check['question'],source_ids=check['source_ids'],
                               evidence=missing_refs,reason='Supporting original was not delivered'))
            check.update(status='missing',detail='Supporting original was not delivered.',
                         citation_status='not_delivered')
        result.append(check)
    return result,issues


def delivered_person_evidence(person, checks, issues, *, derive=False):
    """Build a linked personal assessment from the same delivered fact checks."""
    if not person:
        return person
    result = dict(person)
    if derive:
        aliases = {q:c['question'] for c in checks for q in c.get('replaces',[])}
        result['questions'] = list(dict.fromkeys(aliases.get(q,q) for q in person.get('questions',[])))
        person = result
    if 'questions' in person:
        by_question = {c['question']:c for c in checks}
        linked = [by_question.get(q,dict(question=q,status='missing')) for q in person['questions']]
        supported = [c['detail'] for c in linked if c['status']=='supported']
        missing = [c['question'] for c in linked if c['status']!='supported']
        result['detail'] = ' '.join(supported)
        if derive:
            result['status'] = 'supported' if linked and not missing else (
                'unattempted' if person['status']=='unattempted' and not linked else 'limited')
        if missing or not linked:
            result.update(status='unattempted' if person['status']=='unattempted' and not linked else 'limited',
                          detail=(result['detail']+' Unresolved personal evidence: '
                          + '; '.join(missing or ['No fact checks were linked.'])).strip())
    elif issues:
        # Old checkpoints have no links. Do not carry their unchecked narrative
        # forward when a cited original has just failed delivery validation.
        result.update(status='limited',detail='Personal assessment requires review against delivered originals. '
                      + 'Unresolved: ' + '; '.join(i['question'] for i in issues))
    return result


def check_gaps(checks, notes=()):
    """Derive factual gaps once; retain acquisition and other operational notes."""
    names = {q for c in checks for q in [c['question'], *c.get('replaces', [])]}
    gaps = [g for g in notes if not any(g == q or g.startswith(q+':') for q in names)]
    gaps += [c['question']+': '+c['status']+'; '+c['detail'] for c in checks if c['status']!='supported']
    return list(dict.fromkeys(gaps))


def lead_reviews(state, decisions=None):
    """Derive lead readiness from actual inspection, saved decisions and access state."""
    decisions = {} if decisions is None else decisions
    if not isinstance(decisions, dict) or any(not isinstance(v,str) or not v.strip() for v in decisions.values()):
        raise ValueError('source_lead_decisions maps source IDs or seed URLs to concrete reasons')
    seeds = [(url, canonical_url(url)) for url in state.data['task'].get('seed_urls', [])]
    by_url = {entry['url']: sid for sid, entry in state.data['sources'].items()}
    valid = {key for url, canonical in seeds for key in (url, canonical, by_url.get(canonical)) if key}
    if any(key not in valid for key in decisions):
        raise ValueError('source_lead_decisions must identify an explicitly supplied seed URL or its source ID')
    # Retain explicit decisions from older checkpoints too. Inspection and access
    # failure are always recomputed from the current version, never from this log.
    saved = {canonical_url(row['url']): row['reason']
             for row in state.data.get('source_lead_review', [])
             if row.get('status') == 'skipped' and row.get('reason')}
    saved.update(state.data.get('source_lead_decisions', {}))
    rows = []
    for url, canonical in seeds:
        sid = by_url.get(canonical)
        entry = state.data['sources'].get(sid, {})
        read = any(r['version']==entry.get('version') and r['end']>r['start'] for r in entry.get('read_ranges', []))
        reason = decisions.get(sid) or decisions.get(url) or decisions.get(canonical) or saved.get(canonical)
        status = 'read' if read else 'skipped' if reason else 'unresolved'
        if status == 'unresolved':
            if entry.get('status') == 'fetch_failed' or (entry.get('version')
                    and entry.get('status') not in {'success', 'partial'}):
                status, reason = 'unavailable', 'Source acquisition failed: ' + entry['status']
            elif sid not in state.data['read_sources'] and len(state.data['read_sources']) >= state.config.max_read_sources:
                reason = 'Not inspected: read-source budget exhausted.'
        rows.append(dict(url=url,source_id=sid,status=status,reason=reason))
    return rows


def record_lead_decisions(state, decisions):
    rows = lead_reviews(state, decisions)  # Validate before changing the saved ledger.
    state.data['source_lead_decisions'] = {canonical_url(r['url']): r['reason']
        for r in rows if r['status'] in {'read', 'skipped'} and r['reason']}
    state.save()


def require_source_leads(state):
    """A voluntary finish must resolve supplied leads through the normal read loop."""
    if state.data.get('finalization_trigger') or state.data['usage']['model'] >= state.config.max_model_calls:
        return None
    pending = [r for r in lead_reviews(state) if r['status'] == 'unresolved'
        and (r['source_id'] in state.data['read_sources']
             or len(state.data['read_sources']) < state.config.max_read_sources)]
    if not pending:
        return None
    return dict(kind='source_leads_pending', operation_deferred=True, pending_count=len(pending),
        next_steps=[dict(action='read_source', source=r['source_id'] or r['url'],
                         location=dict(block=0, offset=0)) for r in pending[:3]],
        hint='Explicitly supplied sources remain uninspected. Read these leads, or supply '
             'source_lead_decisions with concrete skip reasons in finish. A saved body is not an inspection.')


def _validate_check(state, check, previous, updated):
    """Validate one update and its rename dependencies before changing the ledger."""
    if (not isinstance(check,dict)
            or set(check)-{'question','status','source_ids','detail','evidence','citation_status','replaces'}
            or not {'question','status','source_ids','detail'} <= set(check)
            or check['status'] not in {'supported','planned','missing','conflicting'}
            or not isinstance(check['question'],str) or not check['question'].strip()
            or not isinstance(check['detail'],str) or not check['detail'].strip()
            or not isinstance(check['source_ids'],list)):
        raise ValueError('Each fact check needs question, status, inspected source_ids, detail')
    if 'evidence' in check and not isinstance(check['evidence'],list):
        raise ValueError('Fact-check evidence must be a list of original passage locations')
    replaces = check.get('replaces',[])
    if (not isinstance(replaces,list) or any(not isinstance(q,str) or not q.strip() for q in replaces)
            or check['question'] in replaces):
        raise ValueError('replaces must name other saved questions being merged into this check')
    if any(q not in previous and q not in previous.get(check['question'],{}).get('replaces',[]) for q in replaces):
        raise ValueError('replaces must refer to a saved question')
    if any(q in updated for q in replaces):
        raise ValueError('Do not replace a question that is also updated in this action')
    for sid in check['source_ids']:
        entry=state.data['sources'].get(sid,{}) if isinstance(sid,str) else {}
        if not any(r['version']==entry.get('version') and r['end']>r['start'] for r in entry.get('read_ranges',[])):
            raise ValueError('Fact checks must cite inspected source IDs')
    if check['status']=='supported' and not check['source_ids']:
        raise ValueError('A supported fact requires an inspected source')


def record_checks(state, checks, *, mark_support=False):
    """Keep valid fact updates even when a different update is malformed."""
    previous = {c['question']:c for c in state.data.get('fact_checks', [])}
    accepted, rejected = [], []
    if not isinstance(checks, list):
        rejected.append(dict(index=None, reason='fact_checks must be a list'))
    else:
        updated = {c['question'] for c in checks if isinstance(c, dict) and isinstance(c.get('question'), str)}
        for index, check in enumerate(checks):
            try:
                _validate_check(state, check, previous, updated)
                accepted.append(check)
            except (ValueError, TypeError, KeyError) as exc:
                rejected.append(dict(index=index, question=check.get('question') if isinstance(check, dict) else None,
                                     reason=str(exc)))
    report = dict(accepted=len(accepted), rejected=rejected)
    state.data.setdefault('evidence_feedback', {})['fact_checks'] = report
    if checks:
        state.trace(dict(action='fact_checks', **report))
    merged = dict(previous)
    for check in accepted:
        check = dict(check)
        check.pop('citation_status',None)  # Delivery status is computed, never model supplied.
        # Keep explicit merge history for idempotent retries and checkpoint replay.
        replaces = previous.get(check['question'],{}).get('replaces',[]) + check.get('replaces',[])
        replaces = list(dict.fromkeys(replaces + [q for old in replaces
                         for q in previous.get(old,{}).get('replaces',[])]))
        if replaces:
            check['replaces'] = replaces
        for question in replaces:
            merged.pop(question,None)
        if mark_support and 'evidence' not in check:
            prior = previous.get(check['question'], {})
            check['evidence'] = (prior.get('evidence', []) if
                prior.get('source_ids') == check['source_ids'] else [])
        if 'evidence' in check:
            check['evidence'] = [dict(ref,version=ref.get('version') or
                state.data['sources'][ref['source_id']].get('version'))
                if isinstance(ref,dict) and isinstance(ref.get('source_id'),str)
                and ref['source_id'] in state.data['sources'] else ref for ref in check['evidence']]
        merged[check['question']] = check
    state.data['fact_checks'] = list(merged.values())
    if mark_support:
        # Explicitly selected useful originals survive even if the question is
        # still planned, missing or conflicting. Saving text does not promote a fact.
        # The existing location/version/inspection validator remains authoritative.
        from .evidence import record_passages
        from .reading import unread_ranges
        marks = state.data.get('priority_passages', [])
        # Preserve short keys; hash the full long question to avoid truncation collisions.
        refs = [dict(ref, fact_ids=[c['question'] if len(c['question']) <= 120
                                   else 'question:' + digest(c['question'])],
                     reason=ref.get('reason',c['question']))
                for c in state.data['fact_checks']
                for ref in c.get('evidence',[]) if isinstance(ref,dict)
                and ref.get('source_id') in c['source_ids']
                and (not all(type(ref.get(k)) is int for k in ('block','start','end')) or
                     any(unread_ranges(ref['block'],ref['start'],ref['end'],[m for m in marks
                         if m['source_id']==ref['source_id'] and m['version']==ref.get('version')])))]
        if refs:
            state.data['evidence_feedback']['support_passages'] = record_passages(state, refs)
    return state.data['fact_checks']


def finish_review(state, action):
    rows = lead_reviews(state, action.get('source_lead_decisions'))
    state.data['source_lead_review'] = rows
    gaps = list(action['gaps'])
    if state.data.get('person_evidence',{}).get('status') == 'unattempted':
        gaps.append('Requested personal participation: unattempted.')
        if action['reason'] == 'supported':
            action['reason'] = 'low_gain'
    for row in rows:
        if row['status'] != 'read':
            gaps.append('Source lead '+row['url']+': '+(row['reason'] or 'not inspected; no skip reason supplied'))
    checks = state.data.get('fact_checks', [])
    action['fact_checks'] = checks
    rejected = state.data.get('evidence_feedback', {}).get('fact_checks', {}).get('rejected', [])
    for row in rejected:
        gaps.append('Fact update rejected: ' + str(row.get('question') or row.get('index')) + ': ' + row['reason'])
    if rejected and action['reason'] == 'supported':
        action['reason'] = 'low_gain'
    if action['reason']=='supported' and (any(r['status'] in {'unresolved', 'unavailable'} for r in rows)
                                         or any(c['status']!='supported' for c in checks)):
        action['reason']='low_gain'
    action['gaps']=check_gaps(checks,gaps)
