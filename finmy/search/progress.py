"""Observable research progress; neither language hints nor counters verify facts."""
import re
from decimal import Decimal

NO_PROGRESS_WARNING = 3
NO_PROGRESS_LIMIT = 6


def query_read_feedback(state, sid, query, *, question=None):
    """Block a third similar read when neither preceding read gained a mark."""
    from .budget import tokens
    from .topic import SYNONYMS

    entry = state.data['sources'][sid]
    question_names = {question} if question else set()
    for check in state.data.get('fact_checks', []):
        names = {check['question'], *check.get('replaces', [])}
        if question in names:
            question_names.update(names)
    aliases = {word: min(group) for group in SYNONYMS for word in group}
    terms = lambda text: {aliases.get(word, word) for word in tokens(text)}
    current = terms(query)
    attempts = entry.get('query_read_attempts', [])
    failed = []
    for attempt in reversed(attempts):
        if attempt['version'] != entry.get('version'):
            continue
        previous = terms(attempt['query'])
        numbers = [{Decimal(n.replace(',', '')) for n in re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', q)}
                   for q in (query, attempt['query'])]
        negation = [bool(re.search(r'\b(?:not|no|never|without|unless|only)\b|n[\'’]t\b|不|未|无', q, re.I))
                    for q in (query, attempt['query'])]
        same_question = bool(question and attempt.get('question') in question_names)
        if ((question and attempt.get('question') and not same_question)
                or (not same_question and ((numbers[0] - numbers[1] and numbers[1] - numbers[0])
                    or negation[0] != negation[1]
                    or len(current & previous) / max(1, len(current | previous)) < .55))):
            continue
        added = [p for p in state.data.get('priority_passages', [])
                 if p['source_id'] == sid and p['version'] == attempt['version']
                 and [p['block'], p['start'], p['end']] not in attempt['marks']]
        if any(p['block'] == span['block'] and p['start'] < span['end'] and p['end'] > span['start']
               for p in added for span in attempt['ranges']):
            break
        failed.append(attempt['query'])
    if len(failed) < 2:
        return None
    return dict(source_id=sid, version=entry['version'], status=entry['status'], spans=[],
        reading=dict(mode='bm25', query=query, match_status='no_evidence_gain', attempted_queries=failed),
        progress=dict(new_chars=0, returned_chars=0,
            hint='Two similar reads of this version produced no new located evidence marks. '
                 'Mark useful returned originals now, use another source, or read an explicit new location; '
                 'rewording the same query is deferred. New questions and new versions remain readable.'))


def record_query_read(state, sid, query, result, *, question=None):
    if (result.get('operation_deferred') or not result.get('version')
            or result.get('status') not in {'success', 'partial'}):
        return
    entry = state.data['sources'][sid]
    previous = (entry.get('query_read_attempts') or [{}])[-1]
    if query is None:
        # A cursor continuation belongs to the same question unless explicitly changed.
        query = previous.get('query','')
        question = question or previous.get('question')
    attempt = dict(query=query, version=result['version'],
        ranges=[{k:s[k] for k in ('block', 'start', 'end')} for s in result.get('spans', [])],
        marks=[[p['block'], p['start'], p['end']] for p in state.data.get('priority_passages', [])
               if p['source_id'] == sid and p['version'] == result['version']])
    if question:
        attempt['question'] = question
    entry['query_read_attempts'] = (entry.get('query_read_attempts', []) + [attempt])[-2:]


def provider_observations(state):
    result = []
    for provider in state.config.providers:
        queries, candidates, chinese, inspected, failed = [], set(), set(), set(), set()
        for sid, source in state.data['sources'].items():
            for discovery in source.get('discoveries', []):
                if discovery.get('provider') != provider:
                    continue
                candidates.add(sid)
                query = discovery.get('query', '')
                if query and query not in queries:
                    queries.append(query)
                hints = ' '.join(str(x or '') for x in (source.get('title'), discovery.get('snippet'), discovery.get('summary')))
                if any('\u4e00' <= c <= '\u9fff' for c in hints):
                    chinese.add(sid)
                if any(r['version'] == source.get('version') and r['end'] > r['start']
                       for r in source.get('read_ranges', [])):
                    inspected.add(sid)
                if source.get('status') == 'fetch_failed':
                    failed.add(sid)
        chinese_query = any('\u4e00' <= c <= '\u9fff' for q in queries for c in q)
        row = dict(provider=provider, queries=queries, candidates=len(candidates),
                   chinese_hints=len(chinese), chinese_query_tried=chinese_query,
                   inspected=len(inspected), fetch_failed=len(failed))
        if chinese and not chinese_query:
            row['hint'] = ('Chinese leads have returned without a Chinese query attempt. '
                'If relevant gaps remain, consider a Chinese expression or aliases for this provider; '
                'language presence is not an evidence-quality score.')
        result.append(row)
    return result


def record_progress(state, operation, feedback, *, new_sources=0, new_marks=0, reviewed_chars=0):
    if operation == 'finish':
        return
    new_chars = feedback.get('progress', {}).get('new_chars', 0)
    version_changed = feedback.get('progress', {}).get('source_version_changed', False)
    previous = state.data.get('research_progress', {}).get('consecutive_no_gain', 0)
    count = 0 if new_chars or new_sources or new_marks or reviewed_chars or version_changed else previous + 1
    progress = dict(consecutive_no_gain=count, new_chars=new_chars,
                    new_sources=new_sources, new_priority_marks=new_marks)
    if version_changed:
        progress['source_version_changed'] = True
    if reviewed_chars:
        progress['reviewed_chars'] = reviewed_chars
    if count >= NO_PROGRESS_WARNING:
        progress['hint'] = ('Repeated operations added no original text, candidate or validated priority mark. '
            'Do not replay the same bodies to recover missing information. Follow a new source, '
            'unread location or targeted query, or finish with unresolved gaps.')
    state.data['research_progress'] = progress
    state.trace(dict(action='research_progress', operation=operation, **progress))
