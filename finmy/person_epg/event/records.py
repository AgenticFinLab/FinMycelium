"""Frozen inputs, exact quotes, stable IDs and derived Context views."""
from copy import deepcopy
import hashlib
import json
import re

from .schema import COLLECTION_IDS, FACTS_VERSION
from .evidence_support import evidence_is_located, evidence_statement, merge_citations


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
    source_ids = list(dict.fromkeys(s['raw_data_id'] for s in payload['samples']))
    for source_id in source_ids:
        if source_id not in registry:
            raise ValueError('Unknown source in source_registry: ' + str(source_id))
        record = registry[source_id]
        source = dict(source_id=source_id, title=record.get('title'),
                      url=record.get('source_url') or record.get('url'), origin=record.get('origin'),
                      published_at=record.get('published_at'), retrieved_at=record.get('retrieved_at'))
        for key in ('source_type', 'content_status', 'publisher', 'upstream_source_ids'):
            if record.get(key) is not None:
                source[key] = deepcopy(record[key])
        if not source['url'] and not source['origin']:
            raise ValueError('Each frozen source needs a URL or origin: ' + source_id)
        from jsonschema import Draft202012Validator
        from .schema import schema_for
        problems = list(Draft202012Validator(schema_for('Source')).iter_errors(source))
        if problems:
            raise ValueError('Invalid source metadata: ' + source_id + ': ' + problems[0].message)
        for upstream_id in source.get('upstream_source_ids', []):
            if upstream_id == source_id:
                raise ValueError('A source cannot cite itself as its upstream origin: ' + source_id)
            if upstream_id not in registry:
                raise ValueError('Unknown upstream source: ' + upstream_id)
            if upstream_id not in source_ids:
                source_ids.append(upstream_id)
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


def index_records(package):
    indexes = {name: {record[key]: record for record in package.get(name, [])}
               for name, key in COLLECTION_IDS.items()}
    for name in ('person', 'storyline', 'event'):
        if name in package:
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

    def permitted(start, end):
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


def ground_evidence(proposal, samples, evidence_id, allowed_ranges=None, *, audit=None):
    """Ground every quotation before an Evidence or citation append is adopted.

    ``allowed_ranges`` maps sample IDs to ranges read by this task. The v1
    proposal adapter retains a source-attributed quotation as its statement;
    it does not infer a new factual paraphrase from historical output.
    """
    if not isinstance(proposal, dict):
        raise ValueError('Evidence proposals must be objects')
    citation_fields = {'sample_id', 'quote', 'start', 'end', 'context_before', 'context_after'}
    legacy = 'statement' not in proposal and 'citations' not in proposal
    if legacy:
        if (not {'evidence_id', 'sample_id', 'quote'} <= proposal.keys()
                or proposal.keys() - citation_fields - {'evidence_id'}):
            raise ValueError('Legacy Evidence needs only its ID, sample, quote and location hints')
        citations = [{key: value for key, value in proposal.items() if key != 'evidence_id'}]
    else:
        if set(proposal) != {'evidence_id', 'statement', 'citations'}:
            raise ValueError('Evidence proposals require only evidence_id, statement and citations')
        if not isinstance(proposal['statement'], str) or not proposal['statement'].strip():
            raise ValueError('Evidence requires a nonempty factual statement')
        citations = proposal['citations']
    if not isinstance(citations, list) or not citations:
        raise ValueError('Evidence requires at least one source quotation')
    grounded = []
    for index, citation in enumerate(citations):
        if (not isinstance(citation, dict) or not {'sample_id', 'quote'} <= citation.keys()
                or citation.keys() - citation_fields):
            raise ValueError('Citations contain only sample, exact quote and location hints')
        if not isinstance(citation['sample_id'], str) or citation['sample_id'] not in samples:
            raise ValueError('Citation sample is unknown')
        ranges = None if allowed_ranges is None else allowed_ranges.get(citation['sample_id'], [])
        changes = []
        item = ground_quote(citation, samples, evidence_id, ranges, audit=changes)
        item.pop('evidence_id')
        grounded.append(item)
        if audit is not None:
            for change in changes:
                audit.append({**change, 'field': f'/citations/{index}' + change['field']})
    statement = evidence_statement(grounded[0]) if legacy else proposal['statement']
    if legacy and audit is not None:
        audit.append(dict(field='/statement', rule='legacy_quote_as_source_statement', after=statement))
    return dict(evidence_id=evidence_id, statement=statement, citations=merge_citations([], grounded))


def support_located(supports, package):
    """Structural traceability only; this does not establish semantic entailment."""
    evidence = index_records(package)['evidence']
    if not supports:
        return False
    for support in supports:
        ids = support.get('evidence_ids', [])
        if any(eid not in evidence or not evidence_is_located(evidence[eid]) for eid in ids):
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
