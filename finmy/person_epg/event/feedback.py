"""Small, deterministic scopes for repairing rejected fact operations."""
from copy import deepcopy

from .proposals import FIELDS, validate_envelope
from .schema import COLLECTION_IDS


def reserved_records(issues):
    """Keep IDs of rejected proposals stable when the final repair reuses them."""
    result = {}
    def walk(value):
        if isinstance(value, dict):
            for collection, key in {**COLLECTION_IDS, 'context_refs': 'context_ref_id'}.items():
                if isinstance(value.get(key), str):
                    result.setdefault(collection, set()).add(value[key])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for issue in issues:
        walk(issue.get('proposal'))
    return {c: sorted(ids) for c, ids in result.items()}


def correction_scope(role, report, package, handled=frozenset()):
    """Later hierarchy/association work retains its existing final repair round."""
    allowed = {}
    if role == 'extraction':
        for issue in report['rejected']:
            proposal = issue.get('proposal')
            records = proposal if isinstance(proposal, list) else [dict(collection='entities', record=proposal)] \
                if issue['item'].startswith('entities:') and isinstance(proposal, dict) else []
            for item in records:
                collection, record = item.get('collection'), item.get('record')
                if collection in FIELDS[role] and isinstance(record, dict):
                    oid = record.get(COLLECTION_IDS[collection])
                    if isinstance(oid, str) and (collection, oid) not in handled:
                        allowed.setdefault(collection, set()).add(oid)
    elif role == 'consolidation':
        for issue in report['rejected']:
            for ref in issue['refs']:
                if isinstance(ref, dict) and ref.get('collection') in FIELDS['extraction']:
                    collection, oid = ref['collection'], ref.get('object_id')
                    if (collection, oid) not in handled and any(r[COLLECTION_IDS[collection]] == oid for r in package[collection]):
                        allowed.setdefault(collection, set()).add(oid)
    return {c: sorted(ids) for c, ids in allowed.items()}


def correction_issues(issues, allowed):
    """Only the prompt projection is narrowed; the original rejection stays intact."""
    projected = deepcopy(issues)
    for issue in projected:
        if isinstance(issue.get('proposal'), list):
            issue['proposal'] = [item for item in issue['proposal'] if isinstance(item, dict)
                and isinstance(item.get('record'), dict) and item['record'].get(COLLECTION_IDS.get(item.get('collection')))
                in allowed.get(item.get('collection'), [])]
    return projected


def validate_correction(role, value, allowed):
    validate_envelope(role, value)
    if role == 'extraction':
        for collection in FIELDS[role]:
            for record in value[collection]:
                if not isinstance(record, dict) or record.get(COLLECTION_IDS[collection]) not in allowed.get(collection, []):
                    raise ValueError('Correction may only return rejected records with their assigned IDs: ' + collection)
    elif role == 'consolidation':
        for decision in value['decisions']:
            if not isinstance(decision, dict) or not isinstance(decision.get('input_refs'), list):
                raise ValueError('Correction needs decisions on the remaining assigned candidates')
            for ref in decision['input_refs']:
                if not isinstance(ref, dict) or ref.get('object_id') not in allowed.get(ref.get('collection'), []):
                    raise ValueError('Correction cannot reconsider an already adopted decision')


def unresolved_report(records, outstanding):
    result = dict(accepted=[], accepted_items=[], rejected=[], pending=[], reported_pending=[])
    for record in records:
        report = outstanding(record)
        for key in result:
            for item in report.get(key, []):
                if item not in result[key]:
                    result[key].append(deepcopy(item))
    return result
