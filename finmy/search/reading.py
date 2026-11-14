"""Question-directed reading of saved text, with original offsets and one read budget."""
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


def targeted_spans(document, query, limit, read_ranges):
    """Rank temporary text windows, then read anchors and nearby context within limit.

    Temporary windows never replace saved parsing or alter original evidence locations.
    No fixed match-count cap. Low-score tails are excluded before accounting for read ranges.
    Previously read matches yield to unread matches; explicit
    location reads remain available for rereading. Lexical matches are navigation hints.
    """
    windows = []
    for i, block in enumerate(document['blocks']):
        for part in pdf_blocks(block['text'], block.get('page', 0)):
            if part['text'].strip():
                windows.append(dict(block=i, start=part['start'], end=part['end'], text=part['text']))
    ranked = rank_blocks({'blocks': list(range(len(windows)))}, {'blocks': windows}, [query], focused=True)
    ranking = ranked[0]['ranking'] if ranked else []
    current = [r for r in read_ranges if r['version'] == document['version']]
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
    return spans, reading
