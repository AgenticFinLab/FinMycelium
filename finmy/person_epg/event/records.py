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


def ground_quote(proposal, samples, evidence_id, allowed_ranges=None):
    """Locate verbatim text. Repeated quotes without a verified hint stay ambiguous."""
    sample = samples[proposal['sample_id']]
    text, quote = sample['content'], proposal['quote']
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError('Evidence requires a nonempty original quote')
    positions = [match.start() for match in re.finditer('(?=' + re.escape(quote) + ')', text)]
    if allowed_ranges is not None:
        positions = [p for p in positions if any(lo <= p and p + len(quote) <= hi for lo, hi in allowed_ranges)]
    for key, before in (('context_before', True), ('context_after', False)):
        hint = proposal.get(key)
        if hint:
            if not isinstance(hint, str):
                raise ValueError('Quote context must be original text')
            positions = [p for p in positions if (text[:p].endswith(hint) if before else text[p + len(quote):].startswith(hint))]
    start = proposal.get('start')
    end = proposal.get('end')
    if type(start) is int and type(end) is int and start in positions and end == start + len(quote):
        positions = [start]
    matched = len(positions) == 1
    return dict(evidence_id=evidence_id, sample_id=sample['sample_id'], source_id=sample['raw_data_id'],
                quote=quote, start=positions[0] if matched else None,
                end=positions[0] + len(quote) if matched else None,
                location_status='matched' if matched else 'ambiguous' if positions else 'unmatched',
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
