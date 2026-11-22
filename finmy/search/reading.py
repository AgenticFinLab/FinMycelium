"""Question-directed reading of saved text, with original offsets and one read budget."""
import json
import re

from .budget import MIN_RELATIVE_SCORE, rank_blocks, tokens
from .sources import pdf_blocks


def unread_ranges(block, start, end, read_ranges):
    """Subtract overlapping read intervals; returned offsets stay in the original block."""
    cursor = start
    for item in sorted((r for r in read_ranges if r['block'] == block), key=lambda r: r['start']):
        left, right = max(start, item['start']), min(end, item['end'])
        if right <= left or right <= cursor:
            continue
        if left > cursor:
            yield cursor, left
        cursor = max(cursor, right)
    if cursor < end:
        yield cursor, end


def read_coverage(document, ranges):
    current = [r for r in ranges if r['version'] == document['version']]
    saved = sum(len(b['text']) for b in document['blocks'])
    unread = sum(end-start for i, b in enumerate(document['blocks'])
                 for start, end in unread_ranges(i, 0, len(b['text']), current))
    return saved, saved-unread


def bound_replayed_text(entry, result, *, priority_key):
    """Keep one verification replay per covered range and source annotation state.

    Track source versions and intervals, not keywords or consecutive operations.
    Reading another source cannot reset this guard. Newly inspected text always
    passes; valid new annotations on this source allow another verification.
    Saved originals, read coverage and evidence locations are never removed.
    """
    spans = result.get('spans', [])
    version = result.get('version')
    if not spans or not version:
        return
    guard = entry.get('replay_guard')
    if not guard or guard['version'] != version or guard['priority_key'] != priority_key:
        guard = dict(version=version, priority_key=priority_key, ranges=[])
        entry['replay_guard'] = guard
    if result['progress']['new_chars']:
        return
    covered = guard['ranges']
    if any(list(unread_ranges(s['block'], s['start'], s['end'], covered)) for s in spans):
        # Compact the ranges that actually received a verification replay.
        combined = covered + [{k:s[k] for k in ('block','start','end')} for s in spans]
        merged = []
        for span in sorted(combined, key=lambda s:(s['block'],s['start'])):
            if (merged and merged[-1]['block'] == span['block']
                    and merged[-1]['end'] >= span['start']):
                merged[-1]['end'] = max(merged[-1]['end'], span['end'])
            else:
                merged.append(dict(span))
        guard['ranges'] = merged
        return
    reading = result.setdefault('reading', {})
    reading.update(match_status='already_read', replayed=False, replay_suppressed=True,
                   note='Repeated original text is omitted; saved evidence remains available.')
    reading.pop('preview_location', None)
    result['progress'].update(
        suppressed_chars=result['progress']['returned_chars'], returned_chars=0,
        hint='These original ranges were already read and replayed for verification in this version. '
             'The repeated body is omitted; it is not missing or inaccessible. Use saved read_evidence '
             'to mark passages, choose an unread range or another source, or retain the gap. '
             'Changing keywords or returning after another source does not reset this record.')
    result['spans'] = []


def targeted_spans(document, query, limit, read_ranges, *, replay=True, topic_plan=None):
    """Rank temporary text windows, then read anchors and nearby context within limit.

    Temporary windows never replace saved parsing or alter original evidence locations.
    No fixed match-count cap. Low-score tails are excluded before accounting for read ranges.
    Previously read matches yield to unread matches; explicit
    location reads remain available for rereading. Lexical matches are navigation hints.
    """
    if topic_plan:
        from .topic_reading import read_topic
        return read_topic(document, query, limit, read_ranges, topic_plan, replay=replay)
    current = [r for r in read_ranges if r['version'] == document['version']]
    saved_chars = sum(len(b['text']) for b in document['blocks'])
    if 0 < saved_chars <= limit:
        # A short notice/interview should not lose qualifications just because the
        # query used different words. Return unread saved text, still with offsets.
        spans = []
        for i, block in enumerate(document['blocks']):
            for start, end in unread_ranges(i, 0, len(block['text']), current):
                spans.append(dict(block=i, start=start, end=end, text=block['text'][start:end],
                                  locator={k:v for k,v in block.items() if k != 'text'}))
        cached = not spans
        if cached and replay:
            spans = [dict(block=i, start=0, end=len(b['text']), text=b['text'],
                          locator={k:v for k,v in b.items() if k != 'text'})
                     for i,b in enumerate(document['blocks']) if b['text']]
        reading = dict(mode='full_saved_text', query=query,
                       match_status='already_read' if cached else 'not_ranked',
                       replayed=cached and bool(spans),
                       note='All saved text fits one read; no lexical filtering. '
                            'This is not full-page acquisition or factual verification; '
                            'Already-read originals may be returned again for verification.')
        if spans:
            terms = set(tokens(query))
            preview = next((s for s in spans if terms.intersection(tokens(s['text']))), spans[0])
            reading['preview_location'] = {k:preview[k] for k in ('block', 'start', 'end')}
        return spans, reading

    windows = []
    for i, block in enumerate(document['blocks']):
        for part in pdf_blocks(block['text'], block.get('page', 0)):
            if part['text'].strip():
                windows.append(dict(block=i, start=part['start'], end=part['end'], text=part['text']))
    ranked = rank_blocks({'blocks': list(range(len(windows)))}, {'blocks': windows}, [query], focused=True)
    ranking = ranked[0]['ranking'] if ranked else []
    chosen = []
    remaining = limit
    preview = None
    terms = tokens(query)

    def add(index, *, anchor):
        nonlocal remaining, preview
        window = windows[index]
        # Context may repeat a previous read, but never duplicates text in this response.
        covered = current + chosen if anchor else chosen
        for start, end in unread_ranges(window['block'], window['start'], window['end'], covered):
            if not remaining:
                break
            if end-start > remaining:
                if not anchor:
                    continue
                # An unusually long indivisible block must not hide a late match.
                text = document['blocks'][window['block']]['text']
                hits = [m.start() for term in terms for m in re.finditer(re.escape(term), text[start:end], re.I)]
                if hits:
                    start = min(end-remaining, max(start, start+min(hits)-min(200, remaining//4)))
                end = start+remaining
            item = dict(block=window['block'], start=start, end=end)
            chosen.append(item)
            remaining -= end-start
            if anchor and preview is None:
                preview = item.copy()

    for index, _ in ranking:
        window = windows[index]
        if not list(unread_ranges(window['block'], window['start'], window['end'], current + chosen)):
            continue
        add(index, anchor=True)
        for neighbor in (index-1, index+1):
            if 0 <= neighbor < len(windows):
                add(neighbor, anchor=False)
        if not remaining:
            break
    spans = []
    for item in sorted(chosen, key=lambda r: (r['block'], r['start'])):
        block = document['blocks'][item['block']]
        spans.append(dict(item, text=block['text'][item['start']:item['end']],
                          locator={k:v for k,v in block.items() if k != 'text'}))
    unread_matches = sum(bool(list(unread_ranges(windows[i]['block'], windows[i]['start'], windows[i]['end'], current+chosen)))
                         for i, _ in ranking)
    reading = dict(mode='query', query=query,
                   match_status='matched' if spans else 'already_read' if ranking else 'no_match',
                   matching_windows=len(ranking), unread_matching_windows=unread_matches,
                   min_relative_score=MIN_RELATIVE_SCORE,
                   note='Relevant lexical matches only, not all word hits or a coverage verdict. Refine terms or read an explicit location when needed.')
    if preview is not None:
        reading['preview_location'] = preview
    if not spans and ranking and replay:
        # Revisit saved matches rather than sending an empty tool response. Only
        # replay previously inspected intervals; do not claim unseen text was read.
        candidates, _ = targeted_spans(document, query, limit, [], replay=False)
        for candidate in candidates:
            covered = []
            for r in current:
                if r['block'] != candidate['block']:
                    continue
                start, end = max(r['start'],candidate['start']), min(r['end'],candidate['end'])
                for left,right in unread_ranges(r['block'],start,end,covered):
                    item = dict(block=r['block'],start=left,end=right)
                    covered.append(item)
                    spans.append(dict(item,text=document['blocks'][r['block']]['text'][left:right],
                                      locator=candidate['locator']))
        reading['replayed'] = bool(spans)
        if spans:
            reading['preview_location'] = {k:spans[0][k] for k in ('block','start','end')}
    return spans, reading


def located_preview(document, ranges, queries, limit, priorities=()):
    """Bounded original excerpts, including locations, never an LLM summary.

    The bound includes serialized metadata. Short inspected documents fit whole;
    larger ones use the actual reading questions. Priority annotations only reorder
    text already inspected in the current source version.
    """
    if limit < 160:
        return []
    current = [r for r in ranges if r['version'] == document['version']]
    candidates, seen = [], []
    for r in sorted(current,key=lambda x:(x['block'],x['start'])):
        for start,end in unread_ranges(r['block'],r['start'],r['end'],seen):
            item = dict(block=r['block'],start=start,end=end)
            seen.append(item)
            text = document['blocks'][r['block']]['text'][start:end]
            # Virtual windows handle older, page-sized PDF blocks without changing
            # their original block IDs or offsets.
            for window in pdf_blocks(text,0):
                if window['text'].strip():
                    candidates.append(dict(block=r['block'],start=start+window['start'],
                                           end=start+window['end'],text=window['text']))
    if not candidates:
        return []
    ranking = rank_blocks({'blocks':list(range(len(candidates)))},
                          {'blocks':candidates},queries)
    scores = {}
    for group in ranking:
        maximum = max((s for _,s in group['ranking']),default=1)
        for i,score in group['ranking']:
            scores[i] = max(scores.get(i,0),score/maximum)
    def key(i):
        c = candidates[i]
        marked = any(p['block']==c['block'] and p['start']<c['end'] and p['end']>c['start']
                     for p in priorities)
        return (not marked,-scores.get(i,0),i)
    output = []
    for i in sorted(range(len(candidates)),key=key):
        c = dict(candidates[i])
        c['read_location'] = dict(block=c['block'],offset=c['start'])
        overhead = len(json.dumps(output+[dict(c,text='')],ensure_ascii=False))
        room = limit-overhead
        if room < 80:
            continue
        if len(c['text'])>room:
            c['text'] = c['text'][:room]
            c['end'] = c['start']+len(c['text'])
        while c['text'] and len(json.dumps(output+[c],ensure_ascii=False))>limit:
            c['text'] = c['text'][:-1];c['end']-=1
        if c['text']:
            output.append(c)
    return sorted(output,key=lambda c:(c['block'],c['start']))
