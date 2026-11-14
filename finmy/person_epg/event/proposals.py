"""Scoped model proposals become validated program-owned records, never global writes."""
from copy import deepcopy

from jsonschema import Draft202012Validator

from .records import fingerprint, ground_quote, index_records, pointer
from .schema import COLLECTION_IDS, FACTS_SCHEMA, FACTS_VERSION, GRAPH_VERSION, schema_for
from .validation import check_graph, covers, record_temporal_conflicts, SupportIndex

FIELDS = {
    'extraction': ('entities', 'actions', 'contexts', 'relation_candidates'),
    'consolidation': ('decisions',),
    'organization': ('stages', 'phases', 'assignments', 'split_proposals'),
    'relations': ('contexts', 'relations', 'phase_context_updates', 'action_context_updates'),
}
ID_FIELDS = {v: k for k, v in COLLECTION_IDS.items()}
ID_FIELDS.update(from_action_id='actions', to_action_id='actions', on_behalf_of='entities')
LIST_REFS = {'entity_refs': 'entities', 'evidence_ids': 'evidence'}


def validate_envelope(role, value):
    required = set(FIELDS[role]) | {'evidence', 'pending'}
    optional = {'note', 'event_overview'} if role == 'organization' else {'note'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ValueError('Expected only role fields: ' + ', '.join(sorted(required | optional)))
    if any(not isinstance(value[k], list) for k in required):
        raise ValueError('All role result lists must be arrays')
    if 'note' in value and not isinstance(value['note'], str):
        raise ValueError('note must be a string')


def reference(collection, object_id):
    return dict(collection=collection, object_id=object_id, field='')


def replace_references(value, mappings):
    """Rewrite typed references only; never replace substrings in evidence or prose."""
    if isinstance(value, list):
        return [replace_references(v, mappings) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == 'lineage':
            result[key] = deepcopy(item)  # Historical input/output IDs are immutable.
            continue
        collection = ID_FIELDS.get(key)
        if key == 'object_id':
            collection = value.get('collection')
        if key == 'context_ref_id':
            collection = 'context_refs'
        if collection and isinstance(item, str):
            result[key] = mappings.get(collection, {}).get(item, item)
        elif key in LIST_REFS and isinstance(item, list):
            result[key] = [mappings.get(LIST_REFS[key], {}).get(x, x) if isinstance(x, str) else x for x in item]
        else:
            result[key] = replace_references(item, mappings)
    return result


def _errors(package, payload):
    return {fingerprint(i): i for i in check_graph(package, payload, complete=False)['issues'] if i['severity'] == 'error'}


class ProposalError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('; '.join(f"{i['code']} {i['object_type']}:{i['object_id']}{i['field']}: {i['message']}"
                                 for i in issues[:4]))


def merge_aliases(current, proposed):
    """A canonical identity is immutable; alias additions are not identity edits."""
    if ({k: v for k, v in current.items() if k != 'aliases'} !=
            {k: v for k, v in proposed.items() if k != 'aliases'}):
        raise ValueError('Canonical entity ID, name and type cannot be overwritten')
    aliases = proposed.get('aliases', [])
    if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
        raise ValueError('Entity aliases must be strings')
    current['aliases'] = list(dict.fromkeys([*current.get('aliases', []), *aliases]))


def preserve_known_fields(originals, target, decision, package):
    """Keep known conditional facts, or require an explicit supported correction."""
    support_index = SupportIndex(package)
    for old in originals:
        paths = []
        if 'actor' in old:
            paths += ['/actor/' + key for key in ('entity_id', 'capacity', 'role', 'on_behalf_of') if key in old['actor']]
            if 'object' in old:
                # Wording may change; the known object and its entity identities remain.
                if 'object' not in target:
                    paths.append('/object')
                if old['object'].get('entity_refs'):
                    paths.append('/object/entity_refs')
        if old.get('entity_refs'):
            paths.append('/entity_refs')
        for field in paths:
            before = pointer(old, field)
            try:
                after = pointer(target, field)
            except (KeyError, IndexError, TypeError, ValueError):
                after = None
            if before == after or (isinstance(before, list) and isinstance(after, list) and all(x in after for x in before)):
                continue
            new_support = [s for s in target.get('support', []) if s not in old.get('support', [])
                           and covers(s['target'], field) and support_index.valid(s)]
            retained_alternative = any(covers(c['target'], field) and any(
                a['value'] == before and a['support'] and all(support_index.valid(s) for s in a['support'])
                for a in c['alternatives']) for c in target.get('conflicts', []))
            explicit_gap = any(covers(g['target'], field) for g in target.get('gaps', []))
            corrected = bool(decision['evidence_ids'] and ((after is not None and new_support)
                             or (retained_alternative and (after is not None or explicit_gap))))
            if not corrected:
                raise ValueError('Known field cannot disappear or change without a supported correction: ' + field)


def preserve_context_refs(previous, proposed):
    """Adopted association IDs retain their meaning and known applicability.

    Additional support or previously unknown metadata may be supplied. A different
    role/applicability is a distinct association, not an overwrite of an adopted ID.
    Action-specific baseline exceptions use the existing exclusion mechanism.
    """
    if not previous:
        return
    if any(not isinstance(r, dict) or not isinstance(r.get('context_ref_id'), str) for r in proposed):
        raise ValueError('Context associations require records and stable IDs')
    by_id = {r['context_ref_id']: r for r in proposed}
    fields = ('context_id', 'relation_type', 'entity_id', 'role', 'interaction_type', 'qualification')
    for old in previous:
        updated = by_id.get(old['context_ref_id'])
        if updated is None:
            raise ValueError('An adopted Context association cannot be silently removed; retain it or use a supported baseline exclusion')
        if any(key in old and updated.get(key) != old[key] for key in fields):
            raise ValueError('Retain known Context association fields; use a distinct association for different meaning')


class Receiver:
    def __init__(self, package, payload, id_map, namespace, read_ranges=None, reserved=None):
        self.package, self.payload = deepcopy(package), payload
        self.ids, self.namespace = id_map, namespace
        self.read_ranges = read_ranges
        self.reserved = reserved or {}
        self.report = dict(accepted=[], accepted_items=[], rejected=[], pending=[], reported_pending=[])

    def reject(self, label, reason, refs=None, evidence_ids=None):
        item = dict(refs=refs or [], reason=str(reason), evidence_ids=evidence_ids or [])
        self.report['rejected'].append(dict(item=label, **item))
        self.report['pending'].append(item)

    def apply(self, label, change, refs=None, proposal=None):
        candidate = deepcopy(self.package)
        before = _errors(candidate, self.payload)
        try:
            change(candidate)
            introduced = [v for k, v in _errors(candidate, self.payload).items() if k not in before]
            if introduced:
                raise ProposalError(introduced)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            self.reject(label, exc, refs)
            self.report['rejected'][-1]['issues'] = deepcopy(getattr(exc, 'issues', []))
            if proposal is not None:
                self.report['rejected'][-1]['proposal'] = deepcopy(proposal)
            return False
        self.package = candidate
        self.report['accepted'].append(label)
        self.report['accepted_items'].append(dict(item=label, refs=deepcopy(refs or [])))
        return True

    def prepare(self, role, response):
        validate_envelope(role, response)
        response = deepcopy(response)
        indexes = index_records(self.package)
        mappings = {k: {} for k in (*COLLECTION_IDS, 'context_refs')}

        def allocate(collection, record):
            if not isinstance(record, dict):
                return
            key = COLLECTION_IDS[collection]
            temporary = record.get(key)
            if isinstance(temporary, str) and temporary.strip():
                mappings[collection][temporary] = (temporary if temporary in indexes[collection] or temporary in self.reserved.get(collection, [])
                    else self.ids.assign(collection, temporary, self.namespace))

        for collection in COLLECTION_IDS:
            for record in response.get(collection, []):
                allocate(collection, record)
        for decision in response.get('decisions', []) + response.get('split_proposals', []):
            if not isinstance(decision, dict):
                continue
            outputs = decision.get('outputs')
            for output in outputs if isinstance(outputs, list) else []:
                if (isinstance(output, dict) and isinstance(output.get('collection'), str)
                        and output['collection'] in COLLECTION_IDS):
                    allocate(output['collection'], output.get('record'))

        known_context_refs = {r['context_ref_id'] for collection, key in [('phases', 'baseline_context_refs'), ('actions', 'delta_context_refs')]
                              for record in self.package.get(collection, []) for r in record.get(key, [])}

        def associations(value):
            if isinstance(value, list):
                for item in value:
                    associations(item)
            elif isinstance(value, dict):
                rid = value.get('context_ref_id')
                if 'context_id' in value and isinstance(rid, str) and rid.strip():
                    mappings['context_refs'][rid] = rid if rid in known_context_refs or rid in self.reserved.get('context_refs', []) else self.ids.assign('context_refs', rid, self.namespace)
                for item in value.values():
                    associations(item)
        associations(response)
        samples = {s['sample_id']: s for s in self.payload['samples']}
        for proposal in response['evidence']:
            try:
                if (not isinstance(proposal, dict) or not {'evidence_id', 'sample_id', 'quote'} <= proposal.keys()
                        or proposal.keys() - {'evidence_id', 'sample_id', 'quote', 'start', 'end', 'context_before', 'context_after'}):
                    raise ValueError('Evidence proposals contain only temporary ID, sample, exact quote and location hints')
                temporary = proposal['evidence_id']
                eid = self.ids.assign('evidence', temporary, self.namespace)
                ranges = None if self.read_ranges is None else self.read_ranges.get(proposal['sample_id'], [])
                grounded = ground_quote(proposal, samples, eid, ranges)
                duplicate = next((e for e in self.package['evidence'] if all(e[k] == grounded[k]
                    for k in ('sample_id', 'quote', 'start', 'end', 'location_status', 'sample_sha256'))), None)
                if duplicate:
                    eid = duplicate['evidence_id']
                elif temporary in indexes['evidence']:
                    raise ValueError('Existing Evidence cannot be overwritten')
                else:
                    self.package['evidence'].append(grounded)
                mappings['evidence'][temporary] = eid
            except (ValueError, KeyError, TypeError) as exc:
                self.reject('evidence', exc)
        response = replace_references(response, mappings)
        for item in response['pending']:
            errors = list(Draft202012Validator(schema_for('Pending')).iter_errors(item))
            if errors:
                self.reject('pending', errors[0].message)
            else:
                self.report['pending'].append(item)
                self.report['reported_pending'].append(deepcopy(item))
        return response

    def add_records(self, records, collection, *, existing=False):
        """Dependency order is resolved by the caller; independent records are isolated."""
        key = COLLECTION_IDS[collection]
        for record in records:
            label = collection + ':' + str(record.get(key)) if isinstance(record, dict) else collection + ':invalid'

            def change(package):
                if not isinstance(record, dict) or key not in record:
                    raise ValueError('Missing record ID')
                current = index_records(package)[collection].get(record[key])
                if current:
                    if collection == 'entities':
                        merge_aliases(current, record)
                        return
                    if current != record:
                        raise ValueError('This role cannot overwrite an existing record')
                    return
                if collection == 'actions' and record.get('phase_id') is not None:
                    raise ValueError('Extraction cannot assign Phase')
                package[collection].append(deepcopy(record))
            self.apply(label, change, [reference(collection, record[key])] if isinstance(record, dict)
                       and isinstance(record.get(key), str) else [], proposal=record)

    def extract(self, response):
        response = self.prepare('extraction', response)
        self.add_records(response['entities'], 'entities')
        records = [(c, r) for c in ('actions', 'contexts', 'relation_candidates') for r in response[c]]
        ids = {(c, r[COLLECTION_IDS[c]]): n for n, (c, r) in enumerate(records)
               if isinstance(r, dict) and isinstance(r.get(COLLECTION_IDS[c]), str)}
        links = {n: set() for n in range(len(records))}

        def refs(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    collection = value.get('collection') if key == 'object_id' else ID_FIELDS.get(key)
                    if collection and isinstance(child, str):
                        yield collection, child
                    yield from refs(child)
            elif isinstance(value, list):
                for child in value:
                    yield from refs(child)
        for n, (_, record) in enumerate(records):
            for key in refs(record):
                if key in ids and ids[key] != n:
                    links[n].add(ids[key])
                    links[ids[key]].add(n)
        remaining = set(links)
        while remaining:
            component, stack = set(), [min(remaining)]
            while stack:
                n = stack.pop()
                if n not in component:
                    component.add(n)
                    stack.extend(links[n] - component)
            remaining -= component

            def change(package):
                for n in sorted(component):
                    collection, record = records[n]
                    key = COLLECTION_IDS[collection]
                    if not isinstance(record, dict) or key not in record:
                        raise ValueError('Missing candidate ID')
                    if record[key] in index_records(package)[collection]:
                        raise ValueError('Extraction cannot overwrite an existing candidate')
                    if collection == 'actions' and record.get('phase_id') is not None:
                        raise ValueError('Extraction cannot assign hierarchy')
                    package[collection].append(deepcopy(record))
            self.apply('candidates:' + ','.join(map(str, sorted(component))), change,
                       [reference(records[n][0], records[n][1][COLLECTION_IDS[records[n][0]]]) for n in sorted(component)
                        if isinstance(records[n][1], dict) and isinstance(records[n][1].get(COLLECTION_IDS[records[n][0]]), str)],
                       proposal=[dict(collection=records[n][0], record=records[n][1]) for n in sorted(component)])
        if not any(response[c] for c in FIELDS['extraction']) and not response.get('note') and not response['pending']:
            self.reject('empty_extraction', 'Explain why this body range contains no in-scope facts, or record pending work')
        return self.finish()

    def decision(self, package, decision, assigned, consumed):
        required = {'operation', 'input_refs', 'outputs', 'reason', 'evidence_ids'}
        if not isinstance(decision, dict) or set(decision) != required:
            raise ValueError('Decision fields differ from the contract')
        operation, refs, outputs = decision['operation'], decision['input_refs'], decision['outputs']
        if not isinstance(refs, list) or not refs or not isinstance(outputs, list) or not isinstance(decision['reason'], str) or not decision['reason'].strip():
            raise ValueError('Decision needs input refs, output list and reason')
        if any(list(Draft202012Validator(schema_for('StepRef')).iter_errors(r)) for r in refs):
            raise ValueError('Decision input references must follow the ObjectRef contract')
        if (not isinstance(decision['evidence_ids'], list)
                or any(not isinstance(e, str) for e in decision['evidence_ids'])):
            raise ValueError('Decision evidence IDs must be strings')
        inputs = [(r['collection'], r['object_id']) for r in refs]
        if any(r.get('field') != '' for r in refs) or len(set(inputs)) != len(inputs) or not set(inputs) <= assigned or set(inputs) & consumed:
            raise ValueError('Decision consumes unassigned, duplicate or previously handled candidates')
        indexes = index_records(package)
        originals = [indexes[c][oid] for c, oid in inputs]
        if any(e not in indexes['evidence'] or indexes['evidence'][e]['location_status'] != 'matched' for e in decision['evidence_ids']):
            raise ValueError('Decision evidence is not located')
        if any(not isinstance(o, dict) or set(o) != {'collection', 'record'}
               or not isinstance(o['collection'], str)
               or o['collection'] not in ('entities', 'actions', 'contexts', 'relation_candidates')
               or not isinstance(o['record'], dict)
               or not isinstance(o['record'].get(COLLECTION_IDS[o['collection']]), str) for o in outputs):
            raise ValueError('Each output needs collection and record')
        output_ids = [(o['collection'], o['record'][COLLECTION_IDS[o['collection']]]) for o in outputs]
        names = {'entities': 'Entity', 'actions': 'Action', 'contexts': 'Context', 'relation_candidates': 'Candidate'}
        for output in outputs:
            schema = {'$defs': FACTS_SCHEMA['$defs'], '$ref': '#/$defs/' + names[output['collection']]}
            error = next(Draft202012Validator(schema).iter_errors(output['record']), None)
            if error is not None:
                raise ValueError('Invalid proposed fact: ' + error.message)
        if len(set(output_ids)) != len(output_ids):
            raise ValueError('Duplicate output IDs')
        if operation in ('keep', 'pending', 'exclude', 'split') and len(inputs) != 1:
            raise ValueError('This operation consumes exactly one candidate')
        if operation == 'keep':
            if len(outputs) > 1 or (outputs and output_ids != inputs):
                raise ValueError('keep preserves collection and ID')
        elif operation == 'merge':
            if len(inputs) < 2 or len({c for c, _ in inputs}) != 1 or len(outputs) != 1 or output_ids[0] not in inputs:
                raise ValueError('merge needs same-collection candidates and one surviving input ID')
        elif operation == 'split':
            if len(outputs) < 2 or any(c != inputs[0][0] or oid in indexes[c] for c, oid in output_ids):
                raise ValueError('split needs at least two new same-collection records')
            if any(not isinstance(output['record'].get('support'), list) or not output['record']['support']
                   or any(list(Draft202012Validator(schema_for('Support')).iter_errors(s)) for s in output['record']['support'])
                   for output in outputs):
                raise ValueError('Every split result requires its own support')
            if any(ref['collection'] in ('stages', 'phases', 'relations') for output in outputs
                   for support in output['record']['support'] for ref in support.get('premise_refs', [])):
                raise ValueError('Split facts require source-level support, not the hierarchy being constructed')
        elif operation == 'exclude':
            if outputs and (inputs[0][0] != 'actions' or any(c != 'contexts' for c, _ in output_ids)):
                raise ValueError('exclude may only reclassify an Action into supported Context')
        elif operation == 'pending':
            if outputs:
                raise ValueError('pending cannot replace the unresolved candidate')
        else:
            raise ValueError('Unknown consolidation operation')
        if operation in ('keep', 'merge') and outputs:
            target = outputs[0]['record']
            preserve_known_fields(originals, target, decision, package)
            for old in originals:
                for field in ('support', 'conflicts'):
                    if any(item not in target.get(field, []) for item in old.get(field, [])):
                        raise ValueError('keep/merge must preserve prior support and conflicts')
        if any(c == 'entities' and oid == package['person']['person_id'] for c, oid in inputs):
            if operation != 'keep' or (outputs and outputs[0]['record'] != originals[0]):
                raise ValueError('Confirmed person identity is immutable')
        if operation == 'pending':
            package['pending'].append(dict(refs=refs, reason=decision['reason'], evidence_ids=decision['evidence_ids']))
        elif outputs or operation == 'exclude':
            for c, oid in inputs:
                package[c] = [r for r in package[c] if r[COLLECTION_IDS[c]] != oid]
            for output in outputs:
                package[output['collection']].append(deepcopy(output['record']))
            if operation == 'merge':
                collection, survivor = output_ids[0]
                remapped = replace_references(package, {collection: {oid: survivor for _, oid in inputs}})
                package.clear()
                package.update(remapped)
            elif operation in ('split', 'exclude'):
                collection, old_id = inputs[0]
                if collection == 'actions':
                    for relation in package.get('relation_candidates', []):
                        for field in ('from_action_id', 'to_action_id'):
                            if relation[field] == old_id:
                                relation[field] = None
                                relation.setdefault('gaps', []).append(dict(target='/' + field,
                                    reason='Original Action was split or excluded; the endpoint needs confirmation.'))
                                package['pending'].append(dict(refs=[reference('relation_candidates', relation['candidate_id'])],
                                    reason='Resolve endpoint after ' + operation, evidence_ids=[]))
        package['lineage'].append(dict(operation=operation, input_refs=refs,
            output_refs=[reference(c, oid) for c, oid in output_ids] if outputs else refs if operation in ('keep', 'pending') else [],
            reason=decision['reason'], step_id=self.namespace))
        return set(inputs)

    def consolidate(self, response, assigned):
        response = self.prepare('consolidation', response)
        consumed = set()
        for number, decision in enumerate(response['decisions']):
            handled = set()

            def change(package):
                handled.update(self.decision(package, decision, assigned, consumed))
            refs = decision.get('input_refs', []) if isinstance(decision, dict) else []
            if self.apply('decision:' + str(number), change, refs if isinstance(refs, list) else [], proposal=decision):
                consumed.update(handled)
        for collection, oid in sorted(assigned - consumed):
            self.reject('unhandled_candidate', 'Candidate lacks an accepted decision', [reference(collection, oid)])
        return self.finish()

    def organize(self, response, *, assigned=None):
        response = self.prepare('organization', response)
        allowed = set(index_records(self.package)['actions']) if assigned is None else set(assigned)
        if response['split_proposals']:
            lineage = []

            def joint(package):
                facts = {k: deepcopy(v) for k, v in package.items() if k not in ('stages', 'phases', 'relations')}
                facts.update(schema_version=FACTS_VERSION, relation_candidates=[], pending=[], lineage=[])
                consumed, generated = set(), set()
                for decision in response['split_proposals']:
                    if (not isinstance(decision, dict) or decision.get('operation') != 'split'
                            or not isinstance(decision.get('input_refs'), list)
                            or any(not isinstance(r, dict) or r.get('collection') != 'actions' for r in decision['input_refs'])):
                        raise ValueError('Organization permits only Action splits')
                    consumed.update(self.decision(facts, decision, {('actions', aid) for aid in allowed}, consumed))
                    generated.update(o['record']['action_id'] for o in decision['outputs'])
                package['actions'] = facts['actions']
                for collection in ('stages', 'phases'):
                    for record in response[collection]:
                        key = COLLECTION_IDS[collection]
                        if not isinstance(record, dict) or key not in record:
                            raise ValueError('Hierarchy record is invalid')
                        if collection == 'phases' and record.get('baseline_context_refs'):
                            raise ValueError('Organization leaves baseline Context to the next role')
                        previous = index_records(package)[collection].get(record[key])
                        if previous is not None and previous != record:
                            raise ValueError('A split cannot overwrite unrelated accepted hierarchy')
                        if previous is None:
                            package[collection].append(deepcopy(record))
                seen = set()
                for assignment in response['assignments']:
                    if not isinstance(assignment, dict) or set(assignment) != {'action_id', 'phase_id', 'support'}:
                        raise ValueError('Invalid split assignment')
                    aid = assignment['action_id']
                    if (aid in seen or aid not in allowed | generated or ('actions', aid) in consumed
                            or not isinstance(assignment['support'], list) or not assignment['support'] or any(not isinstance(s, dict) or s.get('target') != '/phase_id' for s in assignment['support'])):
                        raise ValueError('Every new Action needs one supported assignment')
                    action = index_records(package)['actions'][aid]
                    action['phase_id'] = assignment['phase_id']
                    action['support'] = [s for s in action['support'] if s['target'] != '/phase_id'] + deepcopy(assignment['support'])
                    seen.add(aid)
                if not generated <= seen:
                    raise ValueError('A split and all new assignments must be adopted together')
                if 'event_overview' in response:
                    overview = response['event_overview']
                    if (not isinstance(overview, dict) or not {'time', 'summary', 'support'} <= overview.keys()
                            or overview.keys() - {'time', 'summary', 'support', 'gaps', 'conflicts'}):
                        raise ValueError('Overview cannot change confirmed identity')
                    package['event'].update(deepcopy(overview))
                lineage.extend(facts['lineage'])
            if self.apply('joint_split_organization', joint, proposal=response):
                self.report['lineage'] = lineage
                return self.finish()
        split_assignments, split_inputs = set(), set()
        for collection in ('stages', 'phases'):
            if collection == 'phases':
                for phase in response[collection]:
                    if isinstance(phase, dict) and phase.get('baseline_context_refs'):
                        self.reject('phase', 'Organization must leave baseline Context empty')
                        phase = None
                response[collection] = [p for p in response[collection] if not isinstance(p, dict) or not p.get('baseline_context_refs')]
            self.add_records(response[collection], collection)
        # Split, reference changes and all new assignments are one checked operation.
        for number, decision in enumerate(response['split_proposals']):
            outputs = decision.get('outputs') if isinstance(decision, dict) else None
            produced = {o['record']['action_id'] for o in outputs if isinstance(o, dict)
                        and isinstance(o.get('record'), dict) and isinstance(o['record'].get('action_id'), str)} if isinstance(outputs, list) else set()
            split_assignments.update(produced - set(index_records(self.package)['actions']))
            consumed = set()

            def split(package):
                if (not isinstance(decision, dict) or decision.get('operation') != 'split'
                        or not isinstance(decision.get('input_refs'), list)
                        or any(not isinstance(r, dict) or r.get('collection') != 'actions' for r in decision['input_refs'])):
                    raise ValueError('Organization permits only supported Action splitting')
                facts = {k: deepcopy(v) for k, v in package.items() if k not in ('stages', 'phases', 'relations')}
                facts.update(schema_version=FACTS_VERSION, relation_candidates=[], pending=[], lineage=[])
                consumed.update(self.decision(facts, decision, {('actions', aid) for aid in allowed}, split_inputs))
                assignments = [a for a in response['assignments'] if isinstance(a, dict) and a.get('action_id') in produced]
                if len(assignments) != len(produced) or {a['action_id'] for a in assignments} != produced:
                    raise ValueError('Every split Action needs one assignment in the same response')
                for assignment in assignments:
                    if set(assignment) != {'action_id', 'phase_id', 'support'} or not isinstance(assignment['support'], list) or not assignment['support'] or any(not isinstance(s, dict) or s.get('target') != '/phase_id' for s in assignment['support']):
                        raise ValueError('Split assignments need /phase_id support')
                    action = index_records(facts)['actions'][assignment['action_id']]
                    action['phase_id'] = assignment['phase_id']
                    action['support'] += deepcopy(assignment['support'])
                package['actions'] = facts['actions']
            if self.apply('split:' + str(number), split):
                split_inputs.update(consumed)
                self.report.setdefault('lineage', []).append(dict(operation='split', input_refs=decision['input_refs'],
                    output_refs=[reference('actions', aid) for aid in sorted(produced)], reason=decision['reason'], step_id=self.namespace))
        handled = set()
        for item in response['assignments']:
            if isinstance(item, dict) and isinstance(item.get('action_id'), str) and item['action_id'] in split_assignments:
                continue
            def change(package):
                if not isinstance(item, dict) or set(item) != {'action_id', 'phase_id', 'support'}:
                    raise ValueError('Assignment fields differ from the contract')
                aid = item['action_id']
                if aid not in allowed or aid in handled or aid in split_assignments:
                    raise ValueError('Assignment is outside this task or belongs to an unaccepted split')
                if not isinstance(item['support'], list) or not item['support'] or any(not isinstance(s, dict) or s.get('target') != '/phase_id' for s in item['support']):
                    raise ValueError('Assignment needs explicit /phase_id support')
                action = index_records(package)['actions'][aid]
                action['phase_id'] = item['phase_id']
                action['support'] = [s for s in action['support'] if s['target'] != '/phase_id'] + deepcopy(item['support'])
            if self.apply('assignment:' + str(item.get('action_id')) if isinstance(item, dict) else 'assignment', change,
                          [reference('actions', item['action_id'])] if isinstance(item, dict) and isinstance(item.get('action_id'), str) else []):
                handled.add(item['action_id'])
        for aid in allowed - handled - {oid for _, oid in split_inputs}:
            self.reject('unassigned_action', 'Action lacks an accepted Phase assignment', [reference('actions', aid)])
        if 'event_overview' in response:
            def overview(package):
                value = response['event_overview']
                if not isinstance(value, dict) or not {'time', 'summary', 'support'} <= value.keys() or value.keys() - {'time', 'summary', 'support', 'gaps', 'conflicts'}:
                    raise ValueError('Event overview cannot change identity or scope')
                package['event'].update(deepcopy(value))
            self.apply('event_overview', overview)
        return self.finish()

    def relate(self, response, *, action_ids=None, phase_ids=None):
        response = self.prepare('relations', response)
        indexes = index_records(self.package)
        allowed_actions = set(indexes['actions']) if action_ids is None else set(action_ids)
        allowed_phases = set(indexes['phases']) if phase_ids is None else set(phase_ids)
        # A new Context and every association referring to it are accepted atomically.
        contexts, duplicate_contexts = {}, set()
        for context in response['contexts']:
            if not isinstance(context, dict) or not isinstance(context.get('context_id'), str):
                self.reject('context', 'Context requires an object and an ID')
                continue
            cid = context['context_id']
            if cid in contexts:
                duplicate_contexts.add(cid)
                self.reject('context:' + cid, 'Duplicate Context ID within one response')
            contexts[cid] = context
        for cid in duplicate_contexts:
            contexts.pop(cid)
        updates = [('phases', u) for u in response['phase_context_updates']] + [('actions', u) for u in response['action_context_updates']]
        usable = []
        for collection, update in updates:
            fields = ('baseline_context_refs',) if collection == 'phases' else ('delta_context_refs', 'baseline_context_exclusions')
            if not isinstance(update, dict) or any(not isinstance(update.get(k), list) for k in fields):
                self.reject('context_update', 'Context association and exclusion fields must be arrays')
            else:
                usable.append((collection, update))
        updates = usable
        remaining = list(range(len(updates)))
        used_contexts, handled = set(), set()
        while remaining:
            group = {remaining.pop(0)}
            needed = set()
            changed = True
            while changed:
                changed = False
                for n in list(group):
                    collection, update = updates[n]
                    if isinstance(update, dict):
                        key = 'baseline_context_refs' if collection == 'phases' else 'delta_context_refs'
                        needed.update(r.get('context_id') for r in update.get(key, []) if isinstance(r, dict) and isinstance(r.get('context_id'), str))
                for n in list(remaining):
                    collection, update = updates[n]
                    key = 'baseline_context_refs' if collection == 'phases' else 'delta_context_refs'
                    refs = {r.get('context_id') for r in update.get(key, []) if isinstance(r, dict) and isinstance(r.get('context_id'), str)} if isinstance(update, dict) else set()
                    if refs & needed & contexts.keys():
                        group.add(n)
                        remaining.remove(n)
                        changed = True
            touched = []

            def change(package):
                for cid in needed & contexts.keys():
                    existing = index_records(package)['contexts'].get(cid)
                    if existing and existing != contexts[cid]:
                        raise ValueError('Relations cannot overwrite existing Context content')
                    if not existing:
                        package['contexts'].append(deepcopy(contexts[cid]))
                for n in sorted(group):
                    collection, update = updates[n]
                    key = COLLECTION_IDS[collection]
                    fields = {'baseline_context_refs'} if collection == 'phases' else {'delta_context_refs', 'baseline_context_exclusions'}
                    if not isinstance(update, dict) or set(update) != fields | {key}:
                        raise ValueError('Context update cannot modify other fields')
                    oid = update[key]
                    allowed = allowed_phases if collection == 'phases' else allowed_actions
                    if oid not in allowed or (collection, oid) in handled or (collection, oid) in touched:
                        raise ValueError('Context update is outside the assigned task or duplicated')
                    record = index_records(package)[collection][oid]
                    for field in fields - {'baseline_context_exclusions'}:
                        preserve_context_refs(record.get(field, []), update[field])
                    record.update({f: deepcopy(update[f]) for f in fields})
                    touched.append((collection, oid))
            refs = [reference(c, u[COLLECTION_IDS[c]]) for n in sorted(group) for c, u in [updates[n]]
                    if isinstance(u.get(COLLECTION_IDS[c]), str)]
            proposal = dict(contexts=[contexts[cid] for cid in sorted(needed) if cid in contexts],
                phase_context_updates=[deepcopy(updates[n][1]) for n in sorted(group) if updates[n][0] == 'phases'],
                action_context_updates=[deepcopy(updates[n][1]) for n in sorted(group) if updates[n][0] == 'actions'])
            if self.apply('context_updates:' + ','.join(map(str, sorted(group))), change, refs, proposal=proposal):
                used_contexts.update(needed)
                handled.update(touched)
        for cid in contexts.keys() - used_contexts:
            self.reject('context:' + str(cid), 'New Context has no accepted association; preserve it as pending',
                        [reference('contexts', cid)])
            self.report['rejected'][-1]['proposal'] = deepcopy(contexts[cid])
        for record in response['relations']:
            def relation(package):
                if not isinstance(record, dict) or record.get('from_action_id') not in allowed_actions:
                    raise ValueError('Relation source is outside the assigned action batch')
                previous = index_records(package)['relations'].get(record['relation_id'])
                if previous:
                    if previous != record:
                        raise ValueError('An accepted relation cannot be silently overwritten')
                else:
                    package['relations'].append(deepcopy(record))
                record_temporal_conflicts(package)
            refs = [reference('actions', record['from_action_id'])] if isinstance(record, dict) and record.get('from_action_id') in allowed_actions else []
            if isinstance(record, dict) and isinstance(record.get('relation_id'), str):
                refs.append(reference('relations', record['relation_id']))
            self.apply('relation:' + str(record.get('relation_id')) if isinstance(record, dict) else 'relation', relation, refs, proposal=record)
        for collection, allowed in [('phases', allowed_phases), ('actions', allowed_actions)]:
            for oid in allowed:
                if (collection, oid) not in handled:
                    self.reject('missing_context_update', 'Assigned Context fields were not completed', [reference(collection, oid)])
        return self.finish()

    def finish(self):
        if self.package.get('schema_version') == FACTS_VERSION:
            for item in self.report['pending']:
                if item not in self.package['pending']:
                    self.package['pending'].append(deepcopy(item))
        return self.package, self.report


def exact_deduplicate(facts, payload):
    """Only identical semantic records; keep all support and explicit differences."""
    facts = deepcopy(facts)
    for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
        key, seen = COLLECTION_IDS[collection], {}
        for record in list(facts[collection]):
            identity = fingerprint({k: v for k, v in record.items() if k not in (key, 'support', 'gaps', 'conflicts')})
            if identity not in seen:
                seen[identity] = record
                continue
            survivor = seen[identity]
            if record[key] == facts['person']['person_id']:
                continue
            previous = deepcopy(facts)
            previous_errors = _errors(previous, payload)
            for field in ('support', 'gaps', 'conflicts'):
                for item in record.get(field, []):
                    if item not in survivor.get(field, []):
                        survivor.setdefault(field, []).append(deepcopy(item))
            old, new = record[key], survivor[key]
            facts[collection] = [r for r in facts[collection] if r[key] != old]
            facts = replace_references(facts, {collection: {old: new}})
            facts['lineage'].append(dict(operation='merge', input_refs=[reference(collection, new), reference(collection, old)],
                output_refs=[reference(collection, new)], reason='Identical semantic fields; retain all evidence and conflicts.', step_id='exact_deduplicate'))
            if any(error not in previous_errors for error in _errors(facts, payload)):
                facts = previous
            seen[identity] = index_records(facts)[collection][new]
    return facts


def graph_from_facts(facts):
    result = {k: deepcopy(v) for k, v in facts.items() if k not in ('relation_candidates', 'pending', 'lineage')}
    result.update(schema_version=GRAPH_VERSION, stages=[], phases=[], relations=[])
    return result
