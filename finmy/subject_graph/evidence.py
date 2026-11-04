"""Restore formatting-only quote differences to exact source spans.

No fuzzy matching, case folding, word deletion, or number normalization.
The validator still checks the restored quotes against unmodified sources.
"""
import copy

_PUNCTUATION = str.maketrans({'，': ',', '：': ':', '；': ';', '！': '!', '？': '?',
                             '（': '(', '）': ')', '“': '"', '”': '"', '‘': "'", '’': "'"})


def _han(char):
    return '\u3400' <= char <= '\u9fff' or '\U00020000' <= char <= '\U0003134f'


def _canonical(text):
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
            char = ' '
        else:
            i += 1
            char = char.translate(_PUNCTUATION)
        chars.append(char)
        spans.append((start, i))
    return ''.join(chars), spans


def restore_source_quotes(graph, source_texts):
    """Return a copy and change log, replacing only formatting-equivalent quotes."""
    result = copy.deepcopy(graph)
    indexed = [_canonical(source) for source in source_texts]
    changes = []

    def walk(value, path):
        if isinstance(value, dict):
            quotes = value.get('evidence_source_contents')
            if isinstance(quotes, list):
                for qi, quote in enumerate(quotes):
                    if not isinstance(quote, str) or not quote.strip():
                        continue
                    if any(quote in source for source in source_texts):
                        continue
                    key, _ = _canonical(quote)
                    if not key.strip():
                        continue
                    for si, (canonical, spans) in enumerate(indexed):
                        position = canonical.find(key)
                        if position < 0:
                            continue
                        start, end = spans[position][0], spans[position + len(key) - 1][1]
                        restored = source_texts[si][start:end]
                        quotes[qi] = restored
                        changes.append({'path': path + f'/evidence_source_contents/{qi}',
                                        'before': quote, 'after': restored, 'source_index': si,
                                        'start': start, 'end': end})
                        break
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
