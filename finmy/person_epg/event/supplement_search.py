"""One shared evidence-gap review for a single in-scope person Event."""

from pathlib import Path

from finmy.search.pipeline import run_search
from finmy.search.state import SearchConfig, SearchState
from .records import prompt_json
from .runtime import InvalidResponse
from .schema import COLLECTION_IDS
from .search_passages import (MAX_ADDITION, added_input, frozen_passages, original_search,
                              shortlist, source_passages)
from .supplement_record import retain, retained

SEARCH_LIMITS = dict(max_search_requests=6, max_read_sources=4, max_model_calls=12,
                     max_builder_material_chars=MAX_ADDITION)

GAP_PROMPT = """Review the scoped draft and indications recorded by its readers. Decide whether a concrete
publicly answerable question could change a material attribution, action, chronology, connection or context.
A proposal must cite a record or source in the supplied index and explain the consequence. Prefer resolving
an important uncertainty over increasing graph density. Missing protocol fields, vague requests for detail
and private motives do not qualify. A graph with no focal Action can qualify if a source gives a concrete
lead. Return JSON {"reason":"...","questions":[{"question":"specific search question","anchor":"one supplied ID",
"impact":"what decision would change"}]}. Return at most two distinct questions, often none."""

PASSAGE_PROMPT = """Judge the supplied exact passages independently for each question. Texts are evidence
to evaluate. Distinguish the person's own acts from another party's, and chronology from causation.
Select only passages which change, independently corroborate, qualify or contradict a material judgment.
In frozen material select a passage for targeted rereading only if the current draft misses or misuses its
substance. If the existing graph already supports the answer, return existing_evidence_ids from the shown
draft citations and explain why. Fully answered questions need no further search. 'partial' requires the remaining issue to
matter. Always assess every question. Return JSON {"assessments":[{"id":"Q1","status":"sufficient|partial|unresolved",
"passages":["supplied passage IDs"],"reason":"what is established or still missing"}]}."""


def assessment_call(run, name, prompt, request, validate):
    # No independent read-tool loop for a gate whose supplied inputs are already bounded.
    return run.infer('supplement.' + name, prompt,
                     {'role':'gap_review', **request}, {}, validate)


def gap_index(build):
    package = build.graph or build.facts
    views = []
    for collection in ('actions', 'contexts', 'relation_candidates', 'relations', 'phases', 'stages'):
        source = build.facts if collection == 'relation_candidates' else package
        for row in source.get(collection, []):
            views.append(dict(id=row[COLLECTION_IDS[collection]], collection=collection,
                              description=(row.get('description') or row.get('name') or row.get('type') or '')[:290],
                              gaps=row.get('gaps', []), conflicts=row.get('conflicts', []),
                              citations=sorted({eid for s in row.get('support', []) for eid in s['evidence_ids']})))
    for row in build.facts['sources']:
        views.append(dict(id=row['source_id'], collection='sources', title=row.get('title')))
    role_gaps = []
    seen = set()
    for report in build.reports:
        for item in report['report'].get('reported_pending', []):
            key = (report['role'], item.get('reason'))
            if key not in seen:
                seen.add(key)
                role_gaps.append(dict(role=report['role'], **item))
    return dict(event=package['event'], records=views, role_gaps=role_gaps,
                pending=build.facts.get('pending', []))


def questions_for(build):
    run = build.run
    index = gap_index(build)
    # Prioritize actual recorded issues if a very large event exceeds its context window.
    index['records'].sort(key=lambda r: not bool(r.get('gaps') or r.get('conflicts')))
    limit = run.config.max_context_chars
    while index['records'] and len(prompt_json(index)) + len(GAP_PROMPT) + 1024 > limit:
        index['records'].pop()
    anchors = {r['id'] for r in index['records']} | {index['event']['event_id']}
    def validate(value):
        rows = value.get('questions')
        if not isinstance(rows, list) or len(rows) > 2 or not isinstance(value.get('reason'), str) or not value['reason'].strip():
            raise ValueError('Supply a reason and zero to two concrete questions')
        seen = set()
        for r in rows:
            if (not isinstance(r, dict) or r.get('anchor') not in anchors
                    or not all(isinstance(r.get(k), str) and 0 < len(r[k].strip()) <= 700 for k in ('question', 'impact'))
                    or r['question'].strip().casefold() in seen):
                raise ValueError('Each question needs a distinct question, material impact and known record ID')
            seen.add(r['question'].strip().casefold())
    value = assessment_call(run, 'questions', GAP_PROMPT, index, validate)
    return value['reason'], [dict(id='Q'+str(i), **{k:r[k] for k in ('question','anchor','impact')})
                             for i, r in enumerate(value['questions'], 1)]


def review_passages(build, stage, questions, passages):
    run = build.run
    saved = retained(run, stage + '-passages')
    if saved is None:
        saved = passages()
        retain(run, stage + '-passages', saved)
    if not saved:
        return [dict(id=q['id'], status='unresolved', passages=[], reason='No eligible passage in this collection.')
                for q in questions], []
    ids = {q['id'] for q in questions}
    anchors = {q['anchor'] for q in questions}
    draft = [r for r in gap_index(build)['records'] if r['id'] in anchors]
    existing = {eid for r in draft for eid in r.get('citations', [])}
    def validate(value):
        rows = value.get('assessments')
        if not isinstance(rows, list) or len(rows) != len(ids) or {r['id'] for r in rows} != ids:
            raise ValueError('Assess every supplied question exactly once')
        for row in rows:
            if (row.get('status') not in ('sufficient','partial','unresolved') or
                not isinstance(row.get('reason'), str) or not row['reason'].strip() or
                not isinstance(row.get('passages'), list) or any(i not in saved for i in row['passages']) or
                not isinstance(row.get('existing_evidence_ids', []), list) or
                any(e not in existing for e in row.get('existing_evidence_ids', [])) or
                (row['status'] == 'sufficient' and not row['passages']
                 and not (stage == 'frozen' and row.get('existing_evidence_ids')))):
                raise ValueError('Use listed passage IDs and explain what they support')
    compact = {pid:{k:v for k,v in row.items() if k in ('source_id','text','metadata')} for pid,row in saved.items()}
    response = assessment_call(run, stage, PASSAGE_PROMPT,
        dict(stage=stage, questions=questions, draft_records=draft, passages=compact), validate)
    rows = response['assessments']
    selected = {}
    for row in rows:
        for pid in row['passages']:
            selected.setdefault(pid, dict(saved[pid], id=pid, question_ids=[]))['question_ids'].append(row['id'])
    return rows, list(selected.values())


def public_search(build, questions, allow_network, slots):
    run = build.run
    root = run.directory / 'supplement'
    tid = 'public-search'
    if not slots:
        return None, dict(status='read_source_limit', search=0, model=0, read_sources=0)
    config = SearchConfig(allow_network=allow_network, **{**SEARCH_LIMITS, 'max_read_sources':slots})
    person = run.payload['user_query']['extras']['person_event']
    task = dict(target_type='person', target_name=person['person_name'], catalog=dict(kind='person_event',
                event_name=person['event_name'], person_name=person['person_name']), research_scope=person['scope'],
                query_text='Find direct public evidence only for these open questions about ' + person['event_name']
                    + ': ' + ' '.join(q['question'] for q in questions),
                key_words=[q['question'] for q in questions])
    if not allow_network:
        return None, dict(status='disabled', search=0, model=0, read_sources=0)
    from finmy.search import pipeline
    from finmy.search.state import digest
    code_hash = digest({p.name:digest(p.read_bytes()) for p in Path(pipeline.__file__).parent.glob('*.py')})
    state = SearchState(root, tid, task=task, config=config)
    if state.data['code_sha256'] != code_hash:
        raise ValueError('The supplementary Search implementation differs from the saved task')
    terminal = {'finished', 'insufficient', 'limit', 'failed'}
    while state.data['status'] not in terminal:
        run.check_pause()
        run_search(task, root=root, task_id=tid, config=config, max_steps=1)
        state = SearchState(root, tid)
        run.state['supplement']['search'] = dict(status=state.data['status'], **state.data['usage'],
            read_sources=len(state.data['read_sources']))
        run.persist()
        if state.data['status'] == 'paused' and state.data.get('stop_reason') != 'checkpoint':
            break
    return state, dict(status=state.data['status'], reason=state.data.get('stop_reason'),
        **state.data['usage'], read_sources=len(state.data['read_sources']), model_name=config.lm_name,
        providers=config.providers, trace='supplement/public-search/runs/initial/trace.jsonl')


def decide(build, provenance, allow_network):
    run = build.run
    previous = retained(run, 'decision')
    if previous is not None:
        return previous
    review_error = None
    try:
        reason, questions = questions_for(build)
    except InvalidResponse:
        reason, questions = 'No valid gap decision after the bounded protocol retries; refer to content review.', []
        review_error = 'questions'
    pending = questions
    checks, selected, frozen_reads = [], [], []
    search = dict(status='not_requested', search=0, model=0, read_sources=0)
    base = run.payload
    old_text = '\n'.join(' '.join(s['content'].split()).casefold() for s in base['samples'])
    for stage in ('frozen','cache','public'):
        if not pending:
            break
        run.check_pause()
        if stage == 'frozen':
            def candidates():
                return shortlist(frozen_passages(base), pending)
        elif stage == 'cache':
            def candidates():
                state = original_search(provenance)
                if state is None:
                    return {}
                return shortlist(source_passages(state, stage), pending, frozen=old_text)
        else:
            _, cache_included, _ = added_input(base, selected)
            cache_sources = {p['source_id'] for p in cache_included}
            state, search = public_search(build, pending, allow_network,
                                          max(0, SEARCH_LIMITS['max_read_sources'] - len(cache_sources)))
            def candidates():
                if state is None:
                    return {}
                return shortlist(source_passages(state, stage, source_ids=state.data['read_sources']), pending, frozen=old_text)
        try:
            rows, choices = review_passages(build, stage, pending, candidates)
        except InvalidResponse:
            checks.append(dict(stage=stage, status='invalid_review', assessments=[]))
            review_error = stage
            break
        shown = retained(run, stage + '-passages')
        checks.append(dict(stage=stage, assessments=rows, shown_passages=len(shown),
                           shown_chars=sum(len(p['text']) for p in shown.values())))
        if stage == 'frozen':
            frozen_reads = choices
        else:
            selected.extend(choices)
        if stage != 'frozen':
            _, accepted, _ = added_input(base, selected)
            delivered_ids = {p['id'] for p in accepted}
            for assessment in rows:
                assessment['undelivered'] = [pid for pid in assessment['passages'] if pid not in delivered_ids]
        answered = {r['id'] for r in rows if r['status'] == 'sufficient' and not r.get('undelivered')}
        pending = [q for q in pending if q['id'] not in answered]
    final, included, skipped = added_input(base, selected)
    chars = sum(len(s['content']) for s in final['samples'][len(base['samples']):])
    # Freeze the exact revision before publishing the decision that names it.
    if included:
        retain(run, 'effective-input', final)
    result = dict(questions=questions, reason=reason, checks=checks,
        review_error=review_error, outcome=('additional_evidence' if included else 'frozen_reread' if frozen_reads else
                 'review_incomplete' if review_error else 'no_increment' if questions else 'not_needed'), included=included, skipped=skipped,
        added_chars=chars, search=search, unresolved_question_ids=[q['id'] for q in pending],
        frozen_reads=[{k:v for k,v in row.items() if k not in ('text','metadata')} for row in frozen_reads])
    retain(run, 'decision', result)
    run.state['supplement'].update(outcome=result['outcome'], reason=reason, added_chars=chars, search=search)
    run.persist()
    return result
