"""Restore formatting-only quote differences to exact source spans.

No fuzzy matching, case folding, word deletion, or number normalization.
The validator still checks the restored quotes against unmodified sources.
"""
import copy
import re

_PUNCTUATION = str.maketrans({'，': ',', '：': ':', '；': ';', '！': '!', '？': '?',
                             '（': '(', '）': ')', '“': '"', '”': '"', '‘': "'", '’': "'"})


def _han(char):
    return '\u3400' <= char <= '\u9fff' or '\U00020000' <= char <= '\U0003134f'


def _canonical(text, join_words=False):
    chars, spans = [], []
    i = 0
    while i < len(text):
        start = i
        char = text[i]
        if char.isspace():
            while i < len(text) and text[i].isspace():
                i += 1
            # HTML extraction often inserts whitespace around Chinese links.
            if (start and _han(text[start - 1])) or (i < len(text) and _han(text[i])):
                continue
            if (join_words and start and i < len(text)
                    and text[start - 1].isascii() and text[start - 1].isalpha()
                    and text[i].isascii() and text[i].isalpha()):
                continue
            char = ' '
        else:
            i += 1
            char = char.translate(_PUNCTUATION)
        chars.append(char)
        spans.append((start, i))
    return ''.join(chars), spans


def _source_runs(text):
    """Map contiguous budget excerpts to their untouched positions in the input.

    Only valid adjacent offsets may cross a wrapper. Gaps, reversed ranges and
    malformed lengths stay separate; markers are never blindly stripped.
    """
    markers = list(re.finditer(r"(?m)^\[Source chars (\d+):(\d+)\]\n", text))
    if not markers or "Verbatim source excerpts follow; gaps are omitted." not in text[:markers[0].start()]:
        return [(text, list(range(len(text))))]
    runs = [(text[:markers[0].start()], list(range(markers[0].start())))]
    previous_end = None
    for i, marker in enumerate(markers):
        left, right = map(int, marker.groups())
        start = marker.end()
        stop = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        end = start + right - left
        suffix = "\n\n" if i + 1 < len(markers) else "\n"
        if right <= left or end > stop or text[end:stop] != suffix:
            runs.append((text[marker.start():stop], list(range(marker.start(), stop))))
            previous_end = None
            continue
        value, positions = text[start:end], list(range(start, end))
        if previous_end == left:
            prior, offsets = runs[-1]
            runs[-1] = (prior + value, offsets + positions)
        else:
            runs.append((value, positions))
        previous_end = right
    return runs


def _source_index(source, join_words=False):
    indexed = []
    for text, offsets in _source_runs(source):
        canonical, spans = _canonical(text, join_words)
        indexed.append((canonical, [(offsets[a], offsets[b - 1] + 1) for a, b in spans]))
    return indexed


def restore_source_quotes(graph, source_texts):
    """Return a copy and change log, replacing only formatting-equivalent quotes."""
    result = copy.deepcopy(graph)
    indexed = [_source_index(source) for source in source_texts]
    compact_index = None
    changes = []

    def walk(value, path):
        nonlocal compact_index
        if isinstance(value, dict):
            quotes = value.get('evidence_source_contents')
            if isinstance(quotes, list):
                for qi, quote in enumerate(quotes):
                    if not isinstance(quote, str) or not quote.strip():
                        continue
                    if any(quote in source for source in source_texts):
                        continue
                    # Long contextual passages can repair PDF word-space loss.
                    # Short strings ("nowhere"/"now here") and digit spacing cannot.
                    modes = [False]
                    if len(re.findall(r"[A-Za-z]+", quote)) >= 6 and len(quote) >= 60:
                        modes.append(True)
                    restored_match = None
                    for compact in modes:
                        key, _ = _canonical(quote, compact)
                        if not key.strip():
                            continue
                        if compact and compact_index is None:
                            compact_index = [_source_index(source, True) for source in source_texts]
                        matches = []
                        for si, regions in enumerate(compact_index if compact else indexed):
                            for canonical, spans in regions:
                                position = canonical.find(key)
                                while position >= 0:
                                    start, end = spans[position][0], spans[position + len(key) - 1][1]
                                    matches.append((si, start, end, source_texts[si][start:end]))
                                    position = canonical.find(key, position + 1)
                        # Ambiguous compact matches stay unresolved, not guessed.
                        if matches and (not compact or len({m[3] for m in matches}) == 1):
                            restored_match = matches[0]
                            break
                    if restored_match:
                        si, start, end, restored = restored_match
                        quotes[qi] = restored
                        changes.append({'path': path + f'/evidence_source_contents/{qi}',
                                        'before': quote, 'after': restored, 'source_index': si,
                                        'start': start, 'end': end})
            for name, child in value.items():
                walk(child, path + '/' + name.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, path + '/' + str(i))

    walk(result, '')
    return result, changes


def review_fields(graph):
    """Return paths of facts explicitly marked as awaiting evidence review."""
    paths = []
    def walk(value, path):
        if isinstance(value, dict):
            if value.get('evidence_status') == 'needs_review':
                paths.append(path)
            for key, child in value.items():
                walk(child, path + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, path + '/' + str(i))
    walk(graph, '')
    return paths


def flag_evidence_issues(graph, source_texts):
    """Mark only evidence failures; structural/reference errors remain blocking."""
    from finmy.subject_graph.validation import validate_subject_graph
    result = copy.deepcopy(graph)
    def clear(value):
        if isinstance(value, dict):
            value.pop('evidence_status', None)
            for child in value.values():
                clear(child)
        elif isinstance(value, list):
            for child in value:
                clear(child)
    clear(result)
    errors = validate_subject_graph(result, source_texts)['errors']
    evidence_messages = {'Evidence quote is absent from supplied sources',
                         'Evidence quote must contain non-whitespace text',
                         'Known factual value requires a source quote'}
    if any(error['message'] not in evidence_messages for error in errors):
        return result, []
    for error in errors:
        path = error['path'].split('/evidence_source_contents/')[0]
        field = result
        for key in path.strip('/').split('/'):
            key = key.replace('~1', '/').replace('~0', '~')
            field = field[int(key)] if isinstance(field, list) else field[key]
        field['evidence_status'] = 'needs_review'
        field['confidence'] = None
    return result, errors
