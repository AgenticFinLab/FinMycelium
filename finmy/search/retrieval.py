"""Optional BM25 passage retrieval; scores never become delivery marks."""
from datetime import date
import re
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


def passage_windows(document, width):
    """Bound cached and explicit reads alike; Chinese full stops need no whitespace."""
    from .topic import windows
    for window in windows(document):
        text=document['blocks'][window['block']]['text']
        start=window['start']
        while start<window['end']:
            end=min(start+width,window['end'])
            if end<window['end']:
                boundaries=list(re.finditer(r'[。！？]|[.!?](?=\s)',text[start:end]))
                if boundaries:end=start+boundaries[-1].end()
            yield dict(window,start=start,end=end,text=text[start:end])
            start=end


class RetrievalSession:
    def __init__(self, state):
        self.state, self.options = state, state.config.retrieval

    def rank(self, document, query, *, source_id='', metadata=None):
        from .budget import rank_blocks
        options = self.options; mode = options.get('mode', 'topic'); k = options.get('top_k', 24)
        if mode != 'bm25':
            raise ValueError('Use existing topic reader for topic mode')
        width = options.get('window_chars', 1600)
        items = passage_windows(document,width)
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
    match_status = 'matched' if spans else 'no_match'
    if replayed:
        match_status = 'already_read'
    reading = dict(mode=record['mode'], query=query, match_status=match_status,
                   replayed=replayed, ranking=record,
                   note='Candidates only; validated explicit marks control final delivery.')
    if spans:
        reading['preview_location'] = {k:spans[0][k] for k in ('block', 'start', 'end')}
    return spans, reading


def mentions(text, phrase):
    """Latin names can adjoin Chinese prose without adjoining a Latin word."""
    text,phrase = ' '.join(text.casefold().split()),' '.join(phrase.casefold().split())
    if not phrase.isascii():
        return phrase in text
    return bool(re.search(r'(?<![a-z0-9_])'+re.escape(phrase)+r'(?![a-z0-9_])',text))


def cached_candidates(state, action, selected=None, *, unread_only=False, max_chars=3200):
    """Local BM25 navigation; an explicit question disables broad discovery groups."""
    from .sources import SourceStore
    from .budget import rank_blocks, tokens
    from .coverage import normalized, overlap
    from .evidence import sentence_bounds
    from .metadata import source_metadata
    from .reading import unread_ranges
    from .topic import plan_for, words

    plan = state.data.get('retrieval_plan') or plan_for(state.data['task'])
    people = list(dict.fromkeys(plan['focal_people'] + [alias for p in plan['focal_people'] if p.split()
                  for alias in (p.split()[-1],' '.join((p.split()[0],p.split()[-1])) if len(p.split())>1 else p)]))
    names = plan['entities'] + people
    person_pattern = '(?:'+'|'.join(re.escape(p) for p in people)+')'
    acts = r'(?:said|says|stated|explained|told|decided|approved|declined|stipulated|promised|表示|决定|要求)'
    attribution = re.compile(r'\b'+person_pattern+r'\b\s+(?:(?:has|had|also|personally)\s+)?'+acts+
        r'\b|\b'+acts+r'\s+'+person_pattern+r'\b|^\s*'+person_pattern+r'\s*[:：]|'
        +person_pattern+r'\s*(?:表示|决定|要求)',re.I)
    if not names:
        return []
    store, candidates, known = SourceStore(state), [], []
    candidate_texts, inspected_texts = set(), set()
    marks = [m for m in state.data.get('priority_passages', [])
             if state.data['sources'].get(m['source_id'], {}).get('version') == m['version']]
    if selected is None:
        selected = [dict(source_id=m['source_id'], version=m['version'], ranges=[m]) for m in marks
                    if m['source_id'] not in action.get('source_exclusions', {})]
    for entry in selected:
        doc = store.document(entry['source_id'], entry['version'])
        known.extend(doc['blocks'][r['block']]['text'][r['start']:r['end']] for r in entry.get('ranges', [dict(block=b,start=0,end=len(doc['blocks'][b]['text'])) for b in entry.get('blocks',[])]))
    known_texts = [normalized(text) for text in known]
    condition = re.compile(r'\b(?:unless|stipulat\w*|conditional|contingent|prerequisite)\b|'
        r'\bonly (?:if|after)\b|\bif\b.{0,180}\b(?:would|will|could|do|did)\s+not\b|'
        r'\bwould not\b.{0,180}\bif\b|只有|除非|前提|条件|要求|才会|不得|禁止',re.I|re.S)
    for sid, entry in state.data['sources'].items():
        version = entry.get('version')
        if not version or entry['status'] not in {'success', 'partial'}:
            continue
        doc = store.document(sid, version)
        current = [r for r in entry.get('read_ranges', []) if r['version'] == version]
        inspected_texts.update(normalized(doc['blocks'][r['block']]['text'][r['start']:r['end']]) for r in current)
        from .inspection import excluded_ranges
        own_marks = [m for m in marks if m['source_id'] == sid] + excluded_ranges(state,sid,version)
        metadata = source_metadata(entry, doc)
        scope = dict(doc.get('metadata', {}).get('evidence_scope', {}))
        if metadata.get('published_at'):
            scope['published_at'] = metadata['published_at']
        for window in passage_windows(doc,min(1600,state.config.max_read_chars)):
            plain=normalized(window['text'].lstrip('#> '))
            title=normalized(entry['title'])
            if window['heading'] or (plain and title and plain in title):
                continue
            if metadata_conflict(state.data['task'].get('retrieval_constraints', {}),
                    dict(scope, **doc['blocks'][window['block']].get('evidence_scope', {})),
                    state.config.publication_start, state.config.publication_end):
                continue
            # Subtract selected marks, not the whole source's visited flag.
            for a,b in unread_ranges(window['block'],window['start'],window['end'],
                                     own_marks + (current if unread_only else [])):
                left,right = sentence_bounds(doc['blocks'][window['block']],a,b)
                # Expansion stays inside the same paragraph; it never propagates aliases
                # across a report or reinstates already-read text in a decision preview.
                if not unread_only:
                    a,b = max(window['start'],left),min(window['end'],right)
                text = doc['blocks'][window['block']]['text'][a:b]
                if (not text.strip() or text.rstrip().rstrip('\"”’').endswith(('?', '？'))
                        or len(text) > min(1600,state.config.max_read_chars)):
                    continue
                fingerprint = normalized(text)
                if fingerprint in candidate_texts or any(fingerprint in old for old in known_texts):
                    continue
                personal = any(mentions(text, n) for n in people)
                speech = personal and bool(attribution.search(text))
                process = personal and bool(re.search(
                    r'\b(?:approach\w*|negotiat\w*|propos\w*|introduc\w*|contact\w*|decid\w*|commit\w*)\b|接洽|提议|决定|承诺',text,re.I))
                conditional = personal and any(any(mentions(text[max(0,m.start()-100):m.end()],p) for p in people)
                    or bool(re.search(r'\bI\b',text[max(0,m.start()-100):m.end()])) for m in condition.finditer(text))
                candidate_texts.add(fingerprint)
                candidates.append(dict(source_id=sid,version=version,block=window['block'],start=a,end=b,
                    text=text,personal=personal,condition=conditional,speech=speech,process=process,
                    unread=bool(list(unread_ranges(window['block'],a,b,current)))))
    if unread_only:
        candidates = [c for c in candidates if normalized(c['text']) not in inspected_texts]
    all_indexes = list(range(len(candidates)))
    checks = action.get('fact_checks', state.data.get('fact_checks', []))
    questions = [c['question'] for c in checks if c['status'] != 'supported']
    # A rendered ledger gap is the same question, not a second retrieval request.
    questions += [g for g in action.get('gaps', []) if not any(
        g == c['question'] or g.startswith(c['question']+':') for c in checks)]
    active = action.get('query')
    variants = list(dict.fromkeys(([active] if active else []) + list(action.get('provider_queries',{}).values())))
    groups = []
    if people:
        groups.append(([i for i,c in enumerate(candidates) if c['condition']],
                       'Focal-person conditions','condition'))
    # Interleave the current question with personal evidence and task facets.
    # A stale question cannot monopolize every candidate slot.
    if not variants and questions:
        variants.append(questions.pop(0))
    groups += [(all_indexes,q,'question') for q in variants]
    if people:
        groups.append(([i for i,c in enumerate(candidates) if c['personal'] and (c['speech'] or c['condition'] or c['process'])],
                       'Focal-person actions, statements and conditions','personal'))
    groups += [(all_indexes,q,'question') for q in questions]
    if unread_only or not checks:
        groups += [(all_indexes,q,'question') for q in plan['facets']]
    if action.get('question'):
        groups = [(all_indexes, action['question'], 'question')]
    seen_queries = set()
    chosen, locations = [], set()
    new_sources, remaining = set(), min(max_chars,state.config.max_read_chars)
    for indexes,query,kind in groups:
        key = tuple(sorted(tokens(query)))
        if key in seen_queries:
            continue
        seen_queries.add(key)
        if kind in {'personal','condition'}:
            ranking = [(i,1) for i in indexes]
        else:
            # Name-only matches do not answer a missing fact; scope is verified by the model.
            name_terms = set(tokens(' '.join(names)))
            focus = ' '.join(sorted(words(query) - name_terms))
            ranks = rank_blocks({'blocks':indexes},{'blocks':candidates},[focus],focused=True,query_coverage=True)
            ranking = ranks[0]['ranking'] if ranks else []
        # Compare copied wording only after lexical selection, not for every
        # paragraph in every annual report once the name gate is removed.
        for index,_ in ranking:
            row=candidates[index]
            if 'novelty' not in row:
                row['novelty']=1-overlap(row['text'],known)
        group_sources = set()
        for index,score in sorted(ranking,key=lambda r:(candidates[r[0]]['novelty'] < .5,
                                  not candidates[r[0]]['unread'], -r[1],
                                  not (candidates[r[0]]['condition'] or candidates[r[0]]['process']),
                                  -candidates[r[0]]['novelty'] if kind=='question' else 0,r[0])):
            row = candidates[index]
            sid = row['source_id']
            location = (sid,row['block'],row['start'],row['end'])
            if (sid in group_sources or location in locations or len(row['text']) > remaining
                    or any(normalized(row['text']) in old for old in known_texts)):
                continue
            if (sid not in state.data['read_sources'] and sid not in new_sources
                    and len(state.data['read_sources'])+len(new_sources) >= state.config.max_read_sources):
                continue
            spans = [dict(block=row['block'],start=row['start'],end=row['end'],text=row['text'],
                          read_location=dict(block=row['block'],offset=row['start']))]
            if row['start'] and not any(mentions(row['text'],e) for e in plan['entities']):
                block = store.document(sid,row['version'])['blocks'][row['block']]
                _,end = sentence_bounds(block,0,1)
                prefix = block['text'][:end]
                if (end <= row['start'] and end <= 600 and end+len(row['text']) <= remaining
                        and any(mentions(prefix,e) for e in plan['entities'])):
                    spans.insert(0,dict(block=row['block'],start=0,end=end,text=prefix,
                                       read_location=dict(block=row['block'],offset=0)))
            if row['block'] and row['start'] == 0:
                previous = store.document(sid,row['version'])['blocks'][row['block']-1]['text']
                if (len(previous) <= 400 and previous.rstrip().rstrip('"”’').endswith(('?', '？'))
                        and len(previous)+len(row['text']) <= remaining):
                    spans.insert(0,dict(block=row['block']-1,start=0,end=len(previous),text=previous,
                                        read_location=dict(block=row['block']-1,offset=0)))
            chosen.append(dict(source_id=sid,version=row['version'],query=query,spans=spans,
                               reading_status='cached_unread' if row['unread'] else 'read_unmarked'))
            locations.add(location); known.append(row['text']); known_texts.append(normalized(row['text']))
            if sid not in state.data['read_sources']:
                new_sources.add(sid)
            remaining -= sum(len(s['text']) for s in spans)
            group_sources.add(sid)
            if len(group_sources) >= 1 or len(chosen) == 3:
                break
        if len(chosen) == 3:
            break
    return chosen
