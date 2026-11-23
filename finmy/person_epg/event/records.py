"""Frozen inputs, exact quotes, stable IDs and derived Context views."""
from copy import deepcopy
import hashlib
import json
import re

from .schema import COLLECTION_IDS, FACTS_VERSION


def sha256(data):
    if not isinstance(data, bytes):
        raise TypeError('Hash exact bytes, not a JSON value or an implicitly encoded string')
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def prompt_json(value):
    """Compact model input; durable artifacts retain their readable serialization."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    """json-canonical-v1; deliberately distinct from on-disk artifact hashes."""
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8'))


def unknown_time(text=None):
    return dict(text=text, kind='unknown', start=None, end=None,
                start_precision='unknown', end_precision='unknown')


def validate_input(payload):
    from ..input import validate_input as validate_identity
    from finmy.generic import DataSample, UserQueryInput
    identity = validate_identity(payload)
    query = payload['user_query']
    if not isinstance(query.get('query_text'), str) or not query['query_text'].strip():
        raise ValueError('query_text must preserve the original research request')
    if not isinstance(query.get('key_words'), list) or any(not isinstance(k, str) for k in query['key_words']):
        raise ValueError('key_words must be a list of strings')
    try:
        UserQueryInput(**query)
        for sample in payload['samples']:
            DataSample(**sample)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid query or sample fields') from exc
    source_records(payload)  # Known metadata is checked before creating a run.
    return identity


def source_records(payload):
    registry = payload['user_query']['extras']['source_registry']
    sources = []
    for source_id in dict.fromkeys(s['raw_data_id'] for s in payload['samples']):
        record = registry[source_id]
        source = dict(source_id=source_id, title=record.get('title'),
                      url=record.get('source_url') or record.get('url'), origin=record.get('origin'),
                      published_at=record.get('published_at'), retrieved_at=record.get('retrieved_at'))
        for key in ('source_type', 'content_status'):
            if record.get(key) is not None:
                source[key] = record[key]
        if not source['url'] and not source['origin']:
            raise ValueError('Each frozen source needs a URL or origin: ' + source_id)
        from jsonschema import Draft202012Validator
        from .schema import schema_for
        problems = list(Draft202012Validator(schema_for('Source')).iter_errors(source))
        if problems:
            raise ValueError('Invalid source metadata: ' + source_id + ': ' + problems[0].message)
        sources.append(source)
    return sources


def seed_facts(payload):
    identity = validate_input(payload)
    person_id, event_id = identity['person_id'], identity['event_id']
    return dict(schema_version=FACTS_VERSION,
                person=dict(person_id=person_id, name=identity['person_name'], aliases=identity.get('aliases', []), event_ids=[event_id]),
                storyline=dict(storyline_id=identity['storyline_id'], person_id=person_id, name=identity['storyline_name']),
                event=dict(event_id=event_id, person_id=person_id, storyline_id=identity['storyline_id'],
                           name=identity['event_name'], scope=deepcopy(identity['scope'])),
                entities=[dict(entity_id=person_id, name=identity['person_name'], type='person', aliases=identity.get('aliases', []))],
                actions=[], contexts=[], relation_candidates=[], sources=source_records(payload),
                evidence=[], pending=[], lineage=[])


def pointer(value, path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ValueError('Invalid JSON Pointer')
    for part in path.split('/')[1:]:
        if re.search(r'~(?![01])', part):
            raise ValueError('Invalid JSON Pointer escape')
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise ValueError('Invalid array index')
            value = value[int(key)]
        else:
            value = value[key]
    return value


def index_records(package, *, partial=False):
    indexes = {name: {record[key]: record for record in package.get(name, []) if not partial or key in record}
               for name, key in COLLECTION_IDS.items()}
    for name in ('person', 'storyline', 'event'):
        if name in package and (not partial or name + '_id' in (package[name] or {})):
            indexes[name] = {package[name][name + '_id']: package[name]}
    return indexes


def resolve_ref(package, reference):
    return pointer(index_records(package)[reference['collection']][reference['object_id']], reference['field'])


class IdMap:
    """Program IDs are stable for one task response and survive serialization."""
    def __init__(self, mapping=None):
        self.mapping = deepcopy(mapping or {})

    def assign(self, collection, temporary, namespace):
        if not isinstance(temporary, str) or not temporary.strip():
            raise ValueError('Objects need a nonempty temporary ID')
        key = json.dumps([namespace, collection, temporary], ensure_ascii=False)
        if key not in self.mapping:
            prefix = {'entities': 'ENT', 'actions': 'ACT', 'contexts': 'CTX', 'relations': 'REL',
                      'stages': 'STG', 'phases': 'PHS', 'evidence': 'EVD',
                      'relation_candidates': 'CAN', 'context_refs': 'CREF'}[collection]
            self.mapping[key] = prefix + '-' + sha256(key.encode('utf-8'))[:20]
        return self.mapping[key]


def _whitespace_view(text):
    """Collapse whitespace runs while retaining each output character's raw span."""
    chars, spans = [], []
    for match in re.finditer(r"\s+|[^\s]+", text):
        if match.group().isspace():
            chars.append(' ')
            spans.append((match.start(), match.end()))
        else:
            chars.extend(match.group())
            spans.extend((i, i + 1) for i in range(match.start(), match.end()))
    return ''.join(chars), spans


_HANDOFF_HEADER = re.compile(
    r'\[source=(?P<source>\S+) version=\S+ (?:status=[^\]\n]+|'
    r'block=\d+ chars=(?P<start>\d+):(?P<end>\d+))\]\n')
_PUBLICATION_LINE = re.compile(
    r'Publication date \(source/provider metadata\): \d{4}-\d{2}-\d{2}\n|'
    r'Publication date: (?:conflicted|unverified) \(see source metadata\)\n')
_RETRIEVAL_LINE = re.compile(r'Retrieved at: \d{4}-\d{2}-\d{2}(?:T[^\n ]+)?\n')
_ASSEMBLY_LINE = re.compile(
    r'^(?:\[\.\.\. omitted original blocks (?:(?:before|after) \d+|\d+:\d+) \.\.\.\]|'
    r'\[original block \d+ chars \d+:\d+\])(?:\n|$)', re.MULTILINE)


def _body_ranges(sample, source=None):
    """Ranges in the unchanged sample, using the two public Search handoff formats."""
    text = sample['content']
    header = _HANDOFF_HEADER.match(text)
    if not header or header['source'] != sample['raw_data_id']:
        return ((0, len(text)),)
    source = source or {}
    url_end = text.find('\n', header.end())
    if url_end == -1:
        return ()
    title_start = url_end + 1
    title = source.get('title')
    if title and text.startswith(title + '\n', title_start):
        start = title_start + len(title) + 1
    else:
        title_end = text.find('\n', title_start)
        if title_end == -1:
            return ()
        start = title_end + 1

    if header['start'] is not None:
        # Exact excerpts end with the declared source slice, even for multiline titles.
        width = int(header['end']) - int(header['start'])
        excerpt_start = len(text) - width
        if width > 0 and excerpt_start >= start and text[excerpt_start - 1] == '\n':
            return ((excerpt_start, len(text)),)
        return ()

    # Only these optional lines in the generated prefix have metadata semantics.
    line = _PUBLICATION_LINE.match(text, start)
    if line:
        start = line.end()
    line = _RETRIEVAL_LINE.match(text, start)
    if line:
        start = line.end()

    spans = []
    for marker in _ASSEMBLY_LINE.finditer(text, start):
        if start < marker.start():
            spans.append((start, marker.start()))
        start = marker.end()
    if start < len(text):
        spans.append((start, len(text)))
    return tuple(spans)


def evidence_samples(payload):
    """Index citable spans privately; frozen samples and their hashes stay intact."""
    registry = payload['user_query']['extras']['source_registry']
    return {s['sample_id']: dict(s, _body_ranges=_body_ranges(s, registry[s['raw_data_id']]))
            for s in payload['samples']}


def in_source_body(sample, start, end):
    spans = sample.get('_body_ranges')
    if spans is None:
        spans = _body_ranges(sample)
    return any(lo <= start < end <= hi for lo, hi in spans)


def ground_quote(proposal, samples, evidence_id, allowed_ranges=None, *, audit=None):
    """Exact first; uniquely located whitespace-equivalent text keeps raw bytes.

    No punctuation, case, word-boundary or semantic substitutions are performed.
    Bad hints cannot override a unique permitted match or select among repetitions.
    """
    sample = samples[proposal['sample_id']]
    text, quote = sample['content'], proposal['quote']
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError('Evidence requires a nonempty original quote')
    for key in ('context_before', 'context_after'):
        if proposal.get(key) is not None and not isinstance(proposal[key], str):
            raise ValueError('Quote context must be original text')

    outside_body = False

    def permitted(start, end):
        nonlocal outside_body
        if not in_source_body(sample, start, end):
            outside_body = True
            return False
        return allowed_ranges is None or any(lo <= start and end <= hi for lo, hi in allowed_ranges)

    positions = [(m.start(), m.start() + len(quote)) for m in re.finditer('(?=' + re.escape(quote) + ')', text)
                 if permitted(m.start(), m.start() + len(quote))]
    if not positions:
        view, spans = _whitespace_view(text)
        normalized, _ = _whitespace_view(quote)
        normalized = normalized.strip()
        for match in re.finditer('(?=' + re.escape(normalized) + ')', view):
            start, end = spans[match.start()][0], spans[match.start() + len(normalized) - 1][1]
            if permitted(start, end):
                positions.append((start, end))
    if not positions and outside_body:
        raise ValueError('Quote has no permitted occurrence in the source body. '
                         'Search handoff metadata and assembly markers cannot serve as Evidence.')
    candidates = positions
    for key, before in (('context_before', True), ('context_after', False)):
        hint = proposal.get(key)
        if hint:
            candidates = [(lo, hi) for lo, hi in candidates
                          if (text[:lo].endswith(hint) if before else text[hi:].startswith(hint))]
    offsets = (proposal.get('start'), proposal.get('end'))
    if all(type(x) is int for x in offsets) and offsets in candidates:
        candidates = [offsets]
    # A unique permitted raw span is authoritative. Conflicting hints on repeated
    # text are not enough to choose a location and remain ambiguous.
    if not candidates:
        candidates = positions
    matched = len(candidates) == 1
    start, end = candidates[0] if matched else (None, None)
    raw_quote = text[start:end] if matched else quote
    if matched and audit is not None:
        if raw_quote != quote:
            audit.append(dict(field='/quote', rule='unique_whitespace_equivalent', before=quote, after=raw_quote))
        if offsets != (None, None) and offsets != (start, end):
            audit.append(dict(field='/start,/end', rule='unique_permitted_span',
                              before=list(offsets), after=[start, end]))
        for key, before in (('context_before', True), ('context_after', False)):
            hint = proposal.get(key)
            if hint and not (text[:start].endswith(hint) if before else text[end:].startswith(hint)):
                audit.append(dict(field='/' + key, rule='ignored_conflicting_hint_for_unique_span'))
    return dict(evidence_id=evidence_id, sample_id=sample['sample_id'], source_id=sample['raw_data_id'],
                quote=raw_quote, start=start, end=end,
                location_status='matched' if matched else 'ambiguous' if candidates else 'unmatched',
                sample_sha256=sha256(text.encode('utf-8')))


def support_located(supports, package):
    """Structural traceability only; this does not establish semantic entailment."""
    evidence = index_records(package)['evidence']
    if not supports:
        return False
    for support in supports:
        ids = support.get('evidence_ids', [])
        if any(eid not in evidence or evidence[eid]['location_status'] != 'matched' for eid in ids):
            return False
        if support.get('mode') in ('O', 'A'):
            if not ids:
                return False
        elif support.get('mode') == 'I' and support.get('reason'):
            refs = support.get('premise_refs', [])
            if not ids and not refs:
                return False
            try:
                for reference in refs:
                    resolve_ref(package, reference)
            except (KeyError, IndexError, ValueError, TypeError):
                return False
        else:
            return False
    return True


def compose_context(package, action_id):
    """Derive baseline minus supported exclusions plus delta; never mutate facts."""
    indexes = index_records(package)
    action = indexes['actions'][action_id]
    phase = indexes['phases'].get(action.get('phase_id'), {})
    baseline = {r['context_ref_id']: r for r in phase.get('baseline_context_refs', [])}
    excluded, unresolved, problems = [], [], []
    for item in action.get('baseline_context_exclusions', []):
        rid = item['context_ref_id']
        if (rid not in baseline or rid in excluded or not support_located(item.get('support'), package)
                or any(s.get('target') not in ('/context_ref_id', '/reason') for s in item.get('support', []))):
            problems.append(dict(code='CONTEXT_EXCLUSION_INVALID', context_ref_id=rid))
            unresolved.append(rid)
        elif (baseline[rid].get('conflicts') or baseline[rid].get('gaps') or action.get('conflicts')
              or indexes['contexts'].get(baseline[rid]['context_id'], {}).get('conflicts')):
            problems.append(dict(code='CONTEXT_EXCLUSION_CONFLICT', context_ref_id=rid))
            unresolved.append(rid)
        else:
            excluded.append(rid)
    groups = {}
    for reference in [r for rid, r in baseline.items() if rid not in excluded] + action.get('delta_context_refs', []):
        identity = {k: reference.get(k) for k in ('context_id', 'relation_type', 'entity_id', 'role', 'interaction_type', 'qualification')}
        # Unknowns or conflicts are never treated as wildcard-equivalent associations.
        key = fingerprint(identity) if not reference.get('gaps') and not reference.get('conflicts') else reference['context_ref_id']
        if key not in groups:
            groups[key] = dict(reference=deepcopy(reference), contributing_ref_ids=[])
        group = groups[key]
        group['contributing_ref_ids'].append(reference['context_ref_id'])
        for support in reference['support']:
            if support not in group['reference']['support']:
                group['reference']['support'].append(deepcopy(support))
        context = indexes['contexts'].get(reference['context_id'])
        if (not context or reference.get('gaps') or reference.get('conflicts') or context.get('conflicts')
                or context.get('perspective') == 'unknown' or context.get('time', {}).get('kind') == 'unknown'):
            unresolved.append(reference['context_ref_id'])
    return dict(associations=list(groups.values()), excluded_ref_ids=excluded,
                unresolved_ref_ids=list(dict.fromkeys(unresolved)), issues=problems)
