"""Non-mutating shape, identity, evidence and temporal checks for person Events."""
from collections import defaultdict, deque
from datetime import date

from jsonschema import Draft202012Validator, FormatChecker

from .records import compose_context, index_records, pointer, sha256, source_records
from .schema import COLLECTION_IDS, FACTS_SCHEMA, FACTS_VERSION, GRAPH_SCHEMA, PARTIAL_SCHEMA


def interval(record):
    time = record.get('time', record)
    if not time.get('start') or not time.get('end'):
        return None
    try:
        return date.fromisoformat(time['start']), date.fromisoformat(time['end'])
    except (ValueError, TypeError):
        return None


def has_time_conflict(record):
    return any(c['target'] in ('', '/time') or c['target'].startswith('/time/') for c in record.get('conflicts', []))


def covers(target, field, *, root=False):
    """JSON Pointer ancestry, without treating description support as every field."""
    return target == field or bool(target and field.startswith(target + '/')) or (root and target == '')


def field_conflicted(package, collection, oid, field):
    record = index_records(package).get(collection, {}).get(oid, {})
    for conflict in record.get('conflicts', []):
        if covers(conflict['target'], field, root=True) or covers(field, conflict['target']):
            return True
    for index in index_records(package).values():
        for owner in index.values():
            for conflict in owner.get('conflicts', []):
                for ref in conflict.get('related_refs', []):
                    if ref['collection'] == collection and ref['object_id'] == oid and (
                            covers(ref['field'], field, root=True) or covers(field, ref['field'])):
                        return True
    return False


def located_evidence(evidence, indexes, samples=None):
    if (not evidence or evidence.get('location_status') != 'matched'
            or evidence.get('source_id') not in indexes['sources']):
        return False
    start, end = evidence.get('start'), evidence.get('end')
    if type(start) is not int or type(end) is not int or not 0 <= start < end or end - start != len(evidence['quote']):
        return False
    if samples is not None:
        sample = samples.get(evidence['sample_id'])
        return bool(sample and sample['raw_data_id'] == evidence['source_id']
                    and end <= len(sample['content']) and sample['content'][start:end] == evidence['quote']
                    and evidence['sample_sha256'] == sha256(sample['content'].encode('utf-8')))
    return True


class SupportIndex:
    """Deterministic provenance eligibility; no semantic entailment scoring."""
    def __init__(self, package, payload=None):
        self.package = package
        self.records = index_records(package)
        self.samples = {s['sample_id']: s for s in payload['samples']} if payload is not None else None

    def supported(self, collection, oid, field, seen=frozenset(), *, respect_conflicts=True):
        node = (collection, oid, field)
        if node in seen:
            return False
        record = self.records.get(collection, {}).get(oid)
        if record is None or (respect_conflicts and field_conflicted(self.package, collection, oid, field)):
            return False
        if any(covers(g['target'], field, root=True) for g in record.get('gaps', [])):
            return False
        try:
            pointer(record, field)
        except (KeyError, IndexError, TypeError, ValueError):
            return False
        if field == '/time':
            return all(self.supported(collection, oid, '/time/' + side, seen) for side in ('start', 'end'))
        # Relations are single propositions, including their endpoints and type.
        root = collection in ('relations', 'relation_candidates') or field in ('', '/description', '/summary')
        return any(covers(s['target'], field, root=root) and self.valid(s, seen | {node})
                   for s in record.get('support', []))

    def valid(self, support, seen=frozenset()):
        evidence = support.get('evidence_ids', [])
        premises = support.get('premise_refs', [])
        if any(not located_evidence(self.records['evidence'].get(eid), self.records, self.samples) for eid in evidence):
            return False
        if support['mode'] in ('O', 'A'):
            return bool(evidence)
        return bool(support.get('reason') and (evidence or premises)
                    and all(self.supported(r['collection'], r['object_id'], r['field'], seen) for r in premises))

    def time_ready(self, collection, oid):
        record = self.records.get(collection, {}).get(oid, {})
        bounds = interval(record)
        return bool(bounds and bounds[0] < bounds[1] and self.supported(collection, oid, '/time'))

    def derived(self, relation):
        a, b = (self.records['actions'].get(relation[k], {}) for k in ('from_action_id', 'to_action_id'))
        if not all(self.time_ready('actions', relation[k]) for k in ('from_action_id', 'to_action_id')):
            return False
        ia, ib = interval(a), interval(b)
        if relation['type'] == 'precedes':
            valid = ia[1] <= ib[0]
        elif relation['type'] == 'overlaps':
            valid = a['time']['kind'] == b['time']['kind'] == 'duration' and max(ia[0], ib[0]) < min(ia[1], ib[1])
        else:
            return False
        supports = [s for s in relation['support'] if s['mode'] == 'I' and self.valid(s)]
        premises = {(r['collection'], r['object_id'], r['field']) for s in supports for r in s.get('premise_refs', [])}
        required = {('actions', relation[k], '/time') for k in ('from_action_id', 'to_action_id')}
        return valid and required <= premises


def critical_fields(collection, record):
    """Only explicit field contracts, not a requirement to annotate every scalar."""
    fields = []
    if collection == 'actions':
        fields = ['/description', '/actor/entity_id', '/actor/capacity']
        fields += ['/actor/' + key for key in ('role', 'on_behalf_of') if key in record['actor']]
        if record.get('phase_id') is not None:
            fields.append('/phase_id')
        fields += ['/object/description'] if 'object' in record else ['/object']
        if record.get('object', {}).get('entity_refs'):
            fields.append('/object/entity_refs')
    elif collection in ('stages', 'phases'):
        fields = ['/description', '/boundary_reason']
    elif collection == 'event' and 'summary' in record:
        fields = ['/summary']
    elif collection in ('relations', 'relation_candidates'):
        fields = ['/from_action_id', '/to_action_id', '/type']
    if collection in ('actions', 'stages', 'phases', 'event') and 'time' in record:
        fields += ['/time/start', '/time/end']
    return fields


def reachable(edges, start, end):
    seen, queue = set(), deque([start])
    while queue:
        current = queue.popleft()
        if current == end:
            return True
        if current not in seen:
            seen.add(current)
            queue.extend(edges.get(current, ()))
    return False


def order_view(package, payload=None):
    """Preserve raw claims; exclude every conflicting edge, not an arbitrary cycle cut."""
    support = SupportIndex(package, payload)
    actions = {a['action_id']: a for a in package.get('actions', [])}
    candidates = [r for r in package.get('relations', [])
                  if r['type'] == 'precedes' and r['basis'] in ('observed', 'asserted', 'derived')
                  and r['from_action_id'] in actions and r['to_action_id'] in actions]
    declared, conflicted_times = set(), {aid for aid, action in actions.items() if has_time_conflict(action)}
    for conflict in package.get('event', {}).get('conflicts', []):
        for reference in conflict.get('related_refs', []):
            if reference['collection'] == 'relations':
                declared.add(reference['object_id'])
            if reference['collection'] == 'actions' and reference['field'].startswith('/time'):
                conflicted_times.add(reference['object_id'])
    edges = defaultdict(set)
    conflicts, excluded = [], {}
    eligible = []
    for relation in candidates:
        rid = relation['relation_id']
        # Detect cycles in supported raw claims before removing disputed edges.
        # Filtering one declared edge first would silently cut an otherwise raw cycle.
        if not all(support.supported('relations', rid, '/' + key, respect_conflicts=False)
                   for key in ('from_action_id', 'to_action_id', 'type')):
            excluded[rid] = ['unsupported_or_conflicted_relation']
        elif relation['basis'] == 'derived' and not support.derived(relation):
            excluded[rid] = ['invalid_time_premise']
        else:
            eligible.append(relation)
            edges[relation['from_action_id']].add(relation['to_action_id'])
    cycle_ids = {r['relation_id'] for r in eligible if reachable(edges, r['to_action_id'], r['from_action_id'])}
    if cycle_ids:
        conflicts.append(dict(relation_ids=sorted(cycle_ids), reason='Raw precedence claims form a cycle.'))
    for relation in candidates:
        rid, a, b = relation['relation_id'], actions[relation['from_action_id']], actions[relation['to_action_id']]
        ia, ib = interval(a), interval(b)
        contradiction = support.time_ready('actions', a['action_id']) and support.time_ready('actions', b['action_id']) and (
            ia[0] >= ib[1] or (a['time']['kind'] == b['time']['kind'] == 'duration' and ia[1] > ib[0]))
        reasons = excluded.get(rid, [])
        if contradiction:
            conflicts.append(dict(relation_ids=[rid], reason='Precedence contradicts supported action intervals.'))
            reasons.append('known_time_conflict')
        if rid in cycle_ids:
            reasons.append('precedence_cycle')
        if rid in declared or relation.get('conflicts'):
            reasons.append('declared_conflict')
        if a['action_id'] in conflicted_times or b['action_id'] in conflicted_times:
            reasons.append('unresolved_time_premise')
        if reasons:
            excluded[rid] = reasons
    usable = [r for r in candidates if r['relation_id'] not in excluded]
    return dict(relation_ids=[r['relation_id'] for r in usable], excluded=excluded,
                conflicts=conflicts, declared_relation_ids=sorted(declared))


def record_temporal_conflicts(package):
    """Record program-detected contradictions without deleting either source claim."""
    view = order_view(package)
    indexes = index_records(package)
    for conflict in view['conflicts']:
        ids = conflict['relation_ids']
        if set(ids) <= set(view['declared_relation_ids']):
            continue
        related = [dict(collection='relations', object_id=rid, field='') for rid in ids]
        action_ids = {indexes['relations'][rid][key] for rid in ids for key in ('from_action_id', 'to_action_id')}
        related += [dict(collection='actions', object_id=aid, field='/time') for aid in sorted(action_ids)]
        alternatives = [dict(value=dict(relation_ids=ids), support=[dict(target='/value', mode='I', evidence_ids=[],
            premise_refs=related[:len(ids)], reason='Retain these original relation claims without resolving the contradiction.')]),
            dict(value=dict(constraint='Precedence must be acyclic and consistent with known action times.'),
                 support=[dict(target='/value', mode='I', evidence_ids=[], premise_refs=related,
                               reason=conflict['reason'])])]
        package['event'].setdefault('conflicts', []).append(dict(target='', alternatives=alternatives,
            reason=conflict['reason'], related_refs=related))
    return package


def check_graph(package, payload=None, *, complete=True):
    """Return protocol errors separately from review warnings and unperformed checks."""
    issues = []
    facts = isinstance(package, dict) and package.get('schema_version') == FACTS_VERSION
    artifact = 'facts' if facts else 'graph'

    def issue(code, message, collection='event', object_id=None, field='', severity='error', evidence_ids=None):
        if object_id is None:
            event = package.get('event', {}) if isinstance(package, dict) else {}
            object_id = event.get('event_id', 'unknown') if isinstance(event, dict) else 'unknown'
        item = dict(code=code, severity=severity, artifact=artifact, object_type=collection,
                    object_id=object_id, field=field, message=message)
        if evidence_ids:
            item['evidence_ids'] = evidence_ids
        issues.append(item)

    def result(order=None):
        errors = [dict(path=i['field'], message=i['message']) for i in issues if i['severity'] == 'error']
        return dict(valid=not errors, errors=errors, issues=issues, order=order,
                    summary=dict(errors=len(errors), warnings=sum(i['severity'] == 'warning' for i in issues),
                                 checked=['shape', 'identity', 'references', 'field_support_coverage', 'known_time_constraints', 'context_links']
                                 + (['quote_locations', 'source_mapping'] if payload else []),
                                 not_checked=['semantic_support', 'real_world_completeness']
                                 + ([] if payload else ['quote_locations'])))

    schema = FACTS_SCHEMA if facts else GRAPH_SCHEMA if complete else PARTIAL_SCHEMA
    shape_errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(package))
    if shape_errors:
        for error in shape_errors:
            path = '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in error.absolute_path)
            issue('SCHEMA_INVALID', error.message, field=path)
        report = result()
        report['summary']['checked'] = ['shape']
        report['summary']['not_checked'] += ['identity', 'references', 'field_support_coverage', 'known_time_constraints', 'context_links']
        return report

    indexes = index_records(package)
    for collection, key in COLLECTION_IDS.items():
        if len(indexes[collection]) != len(package.get(collection, [])):
            issue('DUPLICATE_ID', 'IDs must be unique within their collection.', collection)
    person, storyline, event = package['person'], package['storyline'], package['event']
    if (event['person_id'] != person['person_id'] or storyline['person_id'] != person['person_id']
            or event['storyline_id'] != storyline['storyline_id'] or person['event_ids'] != [event['event_id']]):
        issue('IDENTITY_MISMATCH', 'The graph must describe exactly one fixed person/storyline/event.')
    if person['person_id'] not in indexes['entities'] or indexes['entities'][person['person_id']]['type'] != 'person':
        issue('FOCAL_ENTITY_MISSING', 'The focal person must have a person Entity with the same ID.')
    if payload:
        expected = payload['user_query']['extras']['person_event']
        for record, pairs in [(person, [('person_id', 'person_id'), ('name', 'person_name')]),
                              (storyline, [('storyline_id', 'storyline_id'), ('name', 'storyline_name')]),
                              (event, [('event_id', 'event_id'), ('name', 'event_name'), ('scope', 'scope')])]:
            if any(record[k] != expected[v] for k, v in pairs):
                issue('INPUT_IDENTITY_CHANGED', 'Confirmed identity, names or scope changed.')
        expected_sources = {s['source_id']: s for s in source_records(payload)}
        if set(expected_sources) != set(indexes['sources']):
            issue('SOURCE_METADATA_CHANGED', 'Every frozen input source must remain represented.', 'sources')
        for sid, source in indexes['sources'].items():
            if sid not in expected_sources or source != expected_sources[sid]:
                issue('SOURCE_METADATA_CHANGED', 'Source metadata must retain its frozen input value.', 'sources', sid)

    def foreign(collection, target, owner, oid, field):
        if target not in indexes.get(collection, {}):
            issue('REFERENCE_MISSING', 'Referenced object is absent: ' + str(target), owner, oid, field)
            return False
        return True

    samples = {s['sample_id']: s for s in payload['samples']} if payload else {}
    support_index = SupportIndex(package, payload)
    for eid, evidence in indexes['evidence'].items():
        foreign('sources', evidence['source_id'], 'evidence', eid, '/source_id')
        if evidence['location_status'] == 'matched' and (
                type(evidence['start']) is not int or type(evidence['end']) is not int
                or not 0 <= evidence['start'] < evidence['end']
                or evidence['end'] - evidence['start'] != len(evidence['quote'])):
            issue('QUOTE_LOCATION_INVALID', 'Matched Unicode offsets must span exactly the nonempty quote.', 'evidence', eid)
            if type(evidence['start']) is not int or type(evidence['end']) is not int:
                continue
        if payload:
            sample = samples.get(evidence['sample_id'])
            if not sample or sample['raw_data_id'] != evidence['source_id']:
                issue('QUOTE_SOURCE_INVALID', 'Evidence does not belong to a frozen sample/source.', 'evidence', eid)
                continue
            if evidence['sample_sha256'] != sha256(sample['content'].encode('utf-8')):
                issue('SAMPLE_HASH_MISMATCH', 'Evidence hash does not match the exact frozen text.', 'evidence', eid)
            if evidence['location_status'] == 'matched' and evidence['end'] > len(sample['content']):
                issue('QUOTE_LOCATION_INVALID', 'Quote offsets exceed the frozen sample.', 'evidence', eid)
            if evidence['location_status'] == 'matched' and sample['content'][evidence['start']:evidence['end']] != evidence['quote']:
                issue('QUOTE_MISMATCH', 'Quote is not the exact original text at the retained offsets.', 'evidence', eid)
        if evidence['location_status'] != 'matched':
            issue('QUOTE_UNLOCATED', 'This candidate quote is not valid located support.', 'evidence', eid, severity='warning')

    dependencies = defaultdict(set)

    def inspect(value, collection, oid, location=''):
        if isinstance(value, list):
            for n, item in enumerate(value):
                inspect(item, collection, oid, location + '/' + str(n))
        elif isinstance(value, dict):
            if 'support' in value:
                modes = defaultdict(set)
                for support in value['support']:
                    target = location + support['target']
                    try:
                        pointer(value, support['target'])
                    except (KeyError, IndexError, ValueError, TypeError):
                        issue('SUPPORT_TARGET_INVALID', 'Support target is absent from its owner.', collection, oid, target)
                    modes[support['target']].add(support['mode'])
                    for eid in support['evidence_ids']:
                        if foreign('evidence', eid, collection, oid, target) and indexes['evidence'][eid]['location_status'] != 'matched':
                            issue('SUPPORT_UNLOCATED', 'Unlocated quotes cannot count as valid support.', collection, oid, target, evidence_ids=[eid])
                    for reference in support.get('premise_refs', []):
                        if foreign(reference['collection'], reference['object_id'], collection, oid, target):
                            try:
                                pointer(indexes[reference['collection']][reference['object_id']], reference['field'])
                            except (KeyError, IndexError, ValueError, TypeError):
                                issue('PREMISE_FIELD_INVALID', 'Premise field is absent.', collection, oid, target)
                            node = (collection, oid, target)
                            dependency = (reference['collection'], reference['object_id'], reference['field'])
                            if node[:2] == dependency[:2] and (not dependency[2] or target == dependency[2] or target.startswith(dependency[2] + '/')):
                                issue('SUPPORT_SELF_REFERENCE', 'A claim cannot support itself through its owner.', collection, oid, target)
                            dependencies[node].add(dependency)
                if any({'O', 'A'} <= kinds for kinds in modes.values()):
                    issue('SUPPORT_MODE_MIXED', 'Separate record-content and world-assertion claims.', collection, oid, location)
                if not value['support'] and not value.get('gaps') and not value.get('conflicts'):
                    issue('SUPPORT_OR_GAP_REQUIRED', 'A semantic record requires support or an explicit Gap.', collection, oid, location)
            for conflict in value.get('conflicts', []):
                for reference in conflict.get('related_refs', []):
                    if foreign(reference['collection'], reference['object_id'], collection, oid, location):
                        try:
                            pointer(indexes[reference['collection']][reference['object_id']], reference['field'])
                        except (KeyError, IndexError, ValueError, TypeError):
                            issue('CONFLICT_FIELD_INVALID', 'Conflict field is absent.', collection, oid, location)
            for key, item in value.items():
                if key not in ('support', 'gaps'):
                    inspect(item, collection, oid, location + '/' + key.replace('~', '~0').replace('/', '~1'))

    for collection, index in indexes.items():
        for oid, record in index.items():
            inspect(record, collection, oid)
            for field in critical_fields(collection, record):
                root = collection in ('relations', 'relation_candidates') or field in ('/description', '/summary')
                covered = any(covers(s['target'], field, root=root) for s in record.get('support', []))
                gap = any(covers(g['target'], field, root=root) for g in record.get('gaps', []))
                conflict = field_conflicted(package, collection, oid, field)
                if not (covered or gap or conflict):
                    issue('FIELD_SUPPORT_OR_GAP_REQUIRED', 'This critical field needs its own support, Gap or Conflict.', collection, oid, field)
            if record.get('conflicts'):
                issue('SOURCE_CONFLICT', 'Unresolved source claims are retained for review.', collection, oid, severity='warning')
            if 'time' in record:
                time = record['time']
                known = interval(record)
                if known and known[0] >= known[1]:
                    issue('TIME_INTERVAL_INVALID', 'Time intervals are half open with start < end.', collection, oid, '/time')
                for side in ('start', 'end'):
                    if time[side] is None and time[side + '_precision'] != 'unknown':
                        issue('TIME_PRECISION_INVALID', 'An unknown endpoint has unknown precision.', collection, oid, '/time/' + side)
                if not known:
                    issue('TIME_NOT_VERIFIED', 'Incomplete endpoints: no interval inference was made.', collection, oid, '/time', 'info')
    # A premise that references an object/parent field also depends on its supported
    # child claims. Exact-pointer edges alone miss circular whole-object inference.
    claims = list(dependencies)
    for node, parents in list(dependencies.items()):
        expanded = set(parents)
        for parent in parents:
            expanded.update(claim for claim in claims if claim[:2] == parent[:2]
                            and (claim[2] == parent[2] or claim[2].startswith(parent[2] + '/')))
        dependencies[node] = expanded
    for node, parents in dependencies.items():
        if any(reachable(dependencies, parent, node) for parent in parents):
            issue('SUPPORT_CYCLE', 'Inference premises contain circular support.', *node)

    def contains(parent, child, collection, oid, *, overlap=False):
        a, b = interval(parent), interval(child)
        if a and b and not has_time_conflict(parent) and not has_time_conflict(child):
            valid = max(a[0], b[0]) < min(a[1], b[1]) if overlap else a[0] <= b[0] and b[1] <= a[1]
            if not valid:
                issue('HIERARCHY_TIME_CONFLICT', 'Child time is incompatible with its assigned parent.', collection, oid, '/time')

    for sid, stage in indexes['stages'].items():
        if stage['event_id'] != event['event_id']:
            issue('STAGE_EVENT_MISMATCH', 'Stage belongs to another Event.', 'stages', sid, '/event_id')
        if 'time' in event:
            contains(event, stage, 'stages', sid)
        if complete and not facts and not any(p['stage_id'] == sid for p in package['phases']):
            issue('STAGE_WITHOUT_PHASE', 'A complete Stage requires at least one Phase.', 'stages', sid)
    ref_ids = set()

    def context_refs(owner, collection, oid, key, register=True):
        for reference in owner.get(key, []):
            rid = reference['context_ref_id']
            if register and rid in ref_ids:
                issue('DUPLICATE_CONTEXT_REF', 'Context association IDs must be unique.', collection, oid, '/' + key)
            if register:
                ref_ids.add(rid)
            if not foreign('contexts', reference['context_id'], collection, oid, '/' + key):
                continue
            context = indexes['contexts'][reference['context_id']]
            for required in (('entity_id', 'role') if reference['relation_type'] == 'participation'
                             else ('entity_id',) if reference['relation_type'] == 'knowledge-source' else ()):
                if required not in reference and not any(g['target'] in ('', '/' + required) for g in reference.get('gaps', [])):
                    issue('CONTEXT_ROLE_MISSING', 'A participation/knowledge association needs its entity/role or Gap.', collection, oid, '/' + key)
            if 'entity_id' in reference:
                foreign('entities', reference['entity_id'], collection, oid, '/' + key)
            if reference['relation_type'] in ('condition', 'trigger', 'knowledge-source'):
                if context['perspective'] == 'post_hoc':
                    issue('POST_HOC_CONTEXT', 'Later information cannot be an earlier decision input.', collection, oid, '/' + key)
                a, c = interval(owner), interval(context)
                if a and c and not has_time_conflict(owner) and not has_time_conflict(context) and c[0] >= a[1]:
                    issue('FUTURE_CONTEXT', 'This input context only occurs after its target.', collection, oid, '/' + key)
                if context['perspective'] in ('world', 'unknown') and not reference.get('gaps'):
                    issue('KNOWLEDGE_REVIEW', 'World facts alone do not prove knowledge at the action time.', collection, oid, '/' + key, 'warning')

    for pid, phase in indexes['phases'].items():
        if foreign('stages', phase['stage_id'], 'phases', pid, '/stage_id'):
            contains(indexes['stages'][phase['stage_id']], phase, 'phases', pid)
        context_refs(phase, 'phases', pid, 'baseline_context_refs')
        categories = {indexes['contexts'][r['context_id']]['category'] for r in phase['baseline_context_refs'] if r['context_id'] in indexes['contexts']}
        if categories != {'environment', 'relations', 'person_state'}:
            issue('BASELINE_CONTEXT_GAP', 'Not all baseline context categories have evidence; retain the missing categories as a Gap.', 'phases', pid, '/baseline_context_refs', 'warning')
    for aid, action in indexes['actions'].items():
        foreign('entities', action['actor']['entity_id'], 'actions', aid, '/actor/entity_id')
        if 'on_behalf_of' in action['actor']:
            foreign('entities', action['actor']['on_behalf_of'], 'actions', aid, '/actor/on_behalf_of')
        if action['actor']['entity_id'] != person['person_id']:
            issue('ATTRIBUTION_REVIEW', 'Verify documented attribution of the executor to the focal person.', 'actions', aid, '/actor', 'warning')
        for eid in action.get('object', {}).get('entity_refs', []):
            foreign('entities', eid, 'actions', aid, '/object/entity_refs')
        if not facts:
            if action['phase_id'] is None:
                issue('ACTION_PHASE_MISSING', 'Action assignment is incomplete.', 'actions', aid, '/phase_id')
            elif foreign('phases', action['phase_id'], 'actions', aid, '/phase_id'):
                contains(indexes['phases'][action['phase_id']], action, 'actions', aid,
                         overlap=action['time']['kind'] != 'duration')
            context_refs(action, 'actions', aid, 'delta_context_refs')
            composed = compose_context(package, aid)
            inherited = [entry['reference'] for entry in composed['associations']
                         if entry['reference']['context_ref_id'] not in {r['context_ref_id'] for r in action.get('delta_context_refs', [])}]
            context_refs({**action, 'effective_context_refs': inherited}, 'actions', aid, 'effective_context_refs', register=False)
            for problem in composed['issues']:
                issue(problem['code'], 'Baseline exclusion is not valid for this Action: ' + problem['context_ref_id'],
                      'actions', aid, '/baseline_context_exclusions')
    for cid, context in indexes['contexts'].items():
        for eid in context['entity_refs']:
            foreign('entities', eid, 'contexts', cid, '/entity_refs')
    for collection in ('stages', 'phases'):
        groups = defaultdict(list)
        for record in package.get(collection, []):
            if interval(record) and not has_time_conflict(record):
                groups[record.get('stage_id') if collection == 'phases' else event['event_id']].append(record)
        for records in groups.values():
            ordered = sorted(records, key=lambda r: interval(r))
            if records != ordered:
                issue('HIERARCHY_ORDER', 'Known sibling times must be ordered.', collection)
            for a, b in zip(ordered, ordered[1:]):
                if interval(a)[1] > interval(b)[0]:
                    issue('SIBLING_TIME_OVERLAP', 'Known sibling stages/phases must not overlap.', collection, b[COLLECTION_IDS[collection]], '/time')

    for collection in ('relations', 'relation_candidates'):
        for rid, relation in indexes[collection].items():
            for key in ('from_action_id', 'to_action_id'):
                if relation[key] is not None:
                    foreign('actions', relation[key], collection, rid, '/' + key)
            if collection == 'relation_candidates':
                for key in ('from_action_id', 'to_action_id', 'type'):
                    if relation[key] is None and not any(covers(g['target'], '/' + key) for g in relation.get('gaps', [])):
                        issue('CANDIDATE_GAP_REQUIRED', 'An unknown candidate endpoint/type requires a corresponding Gap.', collection, rid, '/' + key)
            if relation['from_action_id'] and relation['from_action_id'] == relation['to_action_id']:
                issue('SELF_RELATION', 'An action relation requires two different actions.', collection, rid)
            if relation.get('basis') == 'derived' and not support_index.derived(relation):
                issue('DERIVED_RELATION_INVALID', 'Derived temporal relations need supported consistent intervals and their time premises.', collection, rid)
    order = order_view(package, payload)
    declared = set(order['declared_relation_ids'])
    for conflict in order['conflicts']:
        if not set(conflict['relation_ids']) <= declared:
            issue('TEMPORAL_CONFLICT_UNRECORDED', conflict['reason'] + ' Record every involved relation in event.conflicts.related_refs.')
        else:
            issue('TEMPORAL_CONFLICT_RETAINED', conflict['reason'], severity='warning')
    usable = defaultdict(set)
    for relation in package.get('relations', []):
        if relation['relation_id'] in order['relation_ids']:
            usable[relation['from_action_id']].add(relation['to_action_id'])
    for relation in package.get('relations', []):
        a, b = relation['from_action_id'], relation['to_action_id']
        if relation['type'] == 'order_unknown' and relation['relation_id'] not in declared and (reachable(usable, a, b) or reachable(usable, b, a)):
            issue('ORDER_UNKNOWN_CONTRADICTION', 'A supported precedence path already establishes order.', 'relations', relation['relation_id'])
    return result(order)
