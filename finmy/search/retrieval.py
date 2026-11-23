"""Optional BM25 passage retrieval; scores never become delivery marks."""
from datetime import date
from .state import digest

MODES = {'topic', 'bm25'}
OPTIONS = {'mode', 'top_k', 'window_chars'}


def validate_options(options):
    if not isinstance(options, dict) or set(options) - OPTIONS:
        raise ValueError('Retrieval accepts only mode, top_k and window_chars')
    if options.get('mode', 'topic') not in MODES:
        raise ValueError('Retrieval mode must be topic or bm25')
    for k in ('top_k', 'window_chars'):
        if k in options and (type(options[k]) is not int or options[k] < 1):
            raise ValueError(k + ' must be a positive integer')


def _day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def metadata_conflict(expected, actual, publication_start=None, publication_end=None):
    """Only explicit known mismatches filter; missing/ambiguous values survive.

    evidence_scope is explicit structured metadata, never inferred from a company
    mention, source URL, publication year or filename.
    """
    for key in ('entity_id', 'event_id'):
        left, right = expected.get(key), actual.get(key)
        if isinstance(left, str) and left and isinstance(right, str) and right and left != right:
            return key
    a, b = _day(actual.get('activity_start')), _day(actual.get('activity_end'))
    x, y = _day(expected.get('activity_start')), _day(expected.get('activity_end'))
    if a and b and a <= b and x and y and x <= y and (b < x or a > y):
        return 'activity_period'
    published = _day(actual.get('published_at'))
    if published and ((publication_start and published < _day(publication_start)) or
                      (publication_end and published > _day(publication_end))):
        return 'publication_filter'
    return None


class RetrievalSession:
    def __init__(self, state):
        self.state, self.options = state, state.config.retrieval

    def rank(self, document, query, *, source_id='', metadata=None):
        from .topic import windows
        from .budget import rank_blocks
        options = self.options; mode = options.get('mode', 'topic'); k = options.get('top_k', 24)
        if mode != 'bm25':
            raise ValueError('Use existing topic reader for topic mode')
        items = []
        width = options.get('window_chars', 1600)
        for w in windows(document):
            for start in range(w['start'], w['end'], width):
                end = min(start+width, w['end'])
                items.append(dict(w, start=start, end=end, text=document['blocks'][w['block']]['text'][start:end]))
        candidates = []; rejected = []
        expected = self.state.data['task'].get('retrieval_constraints', {})
        base = dict(document.get('metadata', {}).get('evidence_scope', {}))
        if metadata and metadata.get('published_at'):
            base['published_at'] = metadata['published_at']
        for w in items:
            scope = dict(base, **document['blocks'][w['block']].get('evidence_scope', {}))
            conflict = metadata_conflict(expected, scope, self.state.config.publication_start, self.state.config.publication_end)
            if conflict:
                rejected.append(dict(block=w['block'], start=w['start'], end=w['end'], reason=conflict)); continue
            uid = digest(dict(source=source_id, version=document['version'], block=w['block'], start=w['start'], end=w['end']))[:24]
            candidates.append(dict(id=uid, block=w['block'], start=w['start'], end=w['end'], text=w['text'],
                metadata=scope))
        rows = rank_blocks({'blocks':list(range(len(candidates)))}, {'blocks':candidates}, [query])
        lexical = [candidates[i]['id'] for i, _ in rows[0]['ranking'][:k]] if rows else []
        lookup = {c['id']: c for c in candidates}
        result = [lookup[uid] for uid in lexical]
        record = dict(mode=mode, bm25_ids=lexical, ranked_ids=lexical,
                      metadata_exclusions=rejected,
                      source_id=source_id, version=document['version'], query=query)
        self.state.trace(dict(action='passage_retrieval', **record))
        return result, record


def read_retrieved(session, document, query, limit, read_ranges, *, source_id='', metadata=None):
    from .reading import unread_ranges
    ranked, record = session.rank(document, query, source_id=source_id, metadata=metadata)
    current = [r for r in read_ranges if r['version'] == document['version']]
    def take(covered):
        chosen = []; remaining = limit
        for row in ranked:
            for start, end in unread_ranges(row['block'], row['start'], row['end'], covered+chosen):
                if remaining <= 0: break
                end = min(end, start+remaining)
                chosen.append(dict(block=row['block'], start=start, end=end)); remaining -= end-start
        return chosen
    chosen = take(current); replayed = False
    if not chosen and ranked:
        chosen = take([]); replayed = bool(chosen)
    spans = [dict(r, text=document['blocks'][r['block']]['text'][r['start']:r['end']],
                  locator={k:v for k,v in document['blocks'][r['block']].items() if k != 'text'}) for r in chosen]
    reading = dict(mode=record['mode'], query=query, match_status='matched' if spans else 'no_match',
                   replayed=replayed, ranking=record,
                   note='Candidates only; validated explicit marks control final delivery.')
    if spans:
        reading['preview_location'] = {k:spans[0][k] for k in ('block', 'start', 'end')}
    return spans, reading
