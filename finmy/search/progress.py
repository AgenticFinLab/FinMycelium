"""Observable research progress; neither language hints nor counters verify facts."""

NO_PROGRESS_WARNING = 3
NO_PROGRESS_LIMIT = 6


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


def record_progress(state, operation, feedback, *, new_sources=0, new_marks=0):
    if operation == 'finish':
        return
    new_chars = feedback.get('progress', {}).get('new_chars', 0)
    previous = state.data.get('research_progress', {}).get('consecutive_no_gain', 0)
    count = 0 if new_chars or new_sources or new_marks else previous + 1
    progress = dict(consecutive_no_gain=count, new_chars=new_chars,
                    new_sources=new_sources, new_priority_marks=new_marks)
    if count >= NO_PROGRESS_WARNING:
        progress['hint'] = ('Repeated operations added no original text, candidate or validated priority mark. '
            'Do not replay the same bodies to recover missing information. Follow a new source, '
            'unread location or targeted query, or finish with unresolved gaps.')
    state.data['research_progress'] = progress
    state.trace(dict(action='research_progress', operation=operation, **progress))
