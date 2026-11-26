"""Bound a Stage/Phase support correction and replay its original dependent proposals."""
from collections import defaultdict
from copy import deepcopy

from .proposals import validate_envelope
from .records import fingerprint
from .schema import COLLECTION_IDS


def rejected_records(rejected, label, owner, key):
    """Leave competing original proposals for one ID to review."""
    groups = defaultdict(list)
    for issue in rejected:
        record = issue.get('proposal')
        if isinstance(record, dict) and isinstance(record.get(key), str) and issue['item'] == f'{label}:{record[key]}':
            groups[record[key]].append(issue)
    for oid, issues in groups.items():
        if len({fingerprint(i['proposal']) for i in issues}) != 1:
            continue
        details = [e for i in issues for e in i.get('issues', [])]
        if not details or any(e.get('object_type') != owner or e.get('object_id') != oid for e in details):
            continue
        yield oid, issues[0]['proposal'], {(e['code'], e['field']) for e in details}, issues


class HierarchyCorrection:
    def __init__(self, rejected, graph):
        self.roots = {}
        self.children = {}
        self.assignments = {}
        self.receipts = set()
        present_stages = {s['stage_id'] for s in graph['stages']}
        present_phases = {p['phase_id'] for p in graph['phases']}
        unassigned = {a['action_id'] for a in graph['actions'] if a.get('phase_id') is None}
        # Classify in parent order, independent of the order of validation receipts.
        for collection, present in (('stages', present_stages), ('phases', present_phases)):
            for oid, item, errors, issues in rejected_records(rejected, collection, collection, COLLECTION_IDS[collection]):
                if oid in present:
                    continue
                if collection == 'phases' and ('REFERENCE_MISSING', '/stage_id') in errors:
                    parent = item['stage_id']
                    if parent not in present_stages and parent not in self.roots.get('stages', {}):
                        continue
                    errors.remove(('REFERENCE_MISSING', '/stage_id'))
                    if not errors:
                        self.children[oid] = item
                if errors:
                    if errors != {('SUPPORT_MODE_MIXED', '')}:
                        continue
                    modes = defaultdict(set)
                    for support in item['support']:
                        modes[support['target']].add(support['mode'])
                    targets = sorted(k for k, kinds in modes.items() if {'A', 'O'} <= kinds)
                    if not targets:
                        continue
                    self.roots.setdefault(collection, {})[oid] = dict(record=item, targets=targets)
                self.receipts.update(map(fingerprint, issues))
        for aid, item, errors, issues in rejected_records(rejected, 'assignment', 'actions', 'action_id'):
            if errors == {('REFERENCE_MISSING', '/phase_id')} and aid in unassigned and item['phase_id'] in self.phase_ids:
                self.assignments[aid] = item
                self.receipts.update(map(fingerprint, issues))

    @property
    def phase_ids(self):
        return set(self.roots.get('phases', {})) | self.children.keys()

    def resolved(self, issue, accepted):
        if issue['item'] == 'unassigned_action':
            return any('assignment:' + r['object_id'] in accepted for r in issue['refs'] if r['collection'] == 'actions')
        return issue['item'] in accepted and fingerprint(issue) in self.receipts

    def expand(self, value):
        """Validate the model's field-level edits and restore immutable fields and dependencies."""
        validate_envelope('organization', value)
        if value['assignments'] or value['split_proposals'] or value['evidence'] or 'event_overview' in value:
            raise ValueError('Hierarchy correction can only change the listed support fields')
        result = deepcopy(value)
        for collection in ('stages', 'phases'):
            key = COLLECTION_IDS[collection]
            result[collection] = []
            seen = set()
            for patch in value[collection]:
                if not isinstance(patch, dict) or set(patch) != {key, 'support'}:
                    raise ValueError(f'Hierarchy correction requires only {key} and support')
                oid = patch[key]
                if not isinstance(oid, str) or oid in seen or oid not in self.roots.get(collection, {}):
                    raise ValueError('Hierarchy correction needs one of the rejected IDs once')
                seen.add(oid)
                root = self.roots[collection][oid]
                support = patch['support']
                if (not isinstance(support, list) or not all(isinstance(s, dict) and isinstance(s.get('target'), str)
                                                            for s in support)
                        or {s['target'] for s in support} != set(root['targets'])):
                    raise ValueError('Only replace support for the specified mixed targets')
                record = deepcopy(root['record'])
                record['support'] = [s for s in record['support'] if s['target'] not in root['targets']] + support
                result[collection].append(record)
        stages = {s['stage_id'] for s in result['stages']}
        result['phases'].extend(p for p in self.children.values() if p['stage_id'] in stages)
        phases = {p['phase_id'] for p in result['phases']}
        result['assignments'] = [a for a in self.assignments.values() if a['phase_id'] in phases]
        return result
