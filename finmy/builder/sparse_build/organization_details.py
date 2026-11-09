"""Expose exact per-Activity detail keys and diagnose invalid display selections."""
from __future__ import annotations

import copy
import hashlib
import json

from .organization_errors import OrganizationValidationError


def detail_reference_catalog(package, activity_ids=None):
    """Stable selection identities independent of detail array/order positions."""
    allowed = set(activity_ids) if activity_ids is not None else {r['activity_id'] for r in package['activity']}
    spans = {r['span_id']: r.get('quote', '') for r in package.get('evidence_span', [])}
    evidence = {}
    for row in package.get('evidence_link', []):
        evidence.setdefault(row['evidence_set_id'], set()).add(spans.get(row['span_id'], ''))
    catalog = {aid: [] for aid in allowed}
    for row in package['activity_detail']:
        aid = row['activity_id']
        if aid not in allowed:
            continue
        identity = {'activity_id': aid, 'value': row['value'],
                    'quotes': sorted(evidence.get(row.get('evidence_set_id'), set()))}
        key = 'DETAIL_' + hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                                   separators=(',', ':')).encode()).hexdigest()[:24]
        catalog[aid].append({'detail_ref': key, 'detail_index': row['detail_index'], 'value': row['value']})
    return catalog


def resolve_detail_references(row, catalog):
    """Map one model selection to today's public indices without changing facts."""
    result = copy.deepcopy(row)
    if 'detail_refs' not in result:
        return result
    selected = result.pop('detail_refs')
    if selected is None:
        resolved = None
    else:
        if not isinstance(selected, list) or any(not isinstance(ref, str) for ref in selected):
            raise ValueError('detail_refs must be a list of stable strings or null')
        entries = catalog.get(result.get('activity_id'), [])
        known = {item['detail_ref'] for item in entries}
        if not set(selected) <= known:
            raise ValueError('Unknown stable detail reference for this Activity')
        resolved = sorted({item['detail_index'] for item in entries if item['detail_ref'] in selected})
    if 'detail_indices' in result and result['detail_indices'] != resolved:
        raise ValueError('detail_refs and detail_indices disagree')
    result['detail_indices'] = resolved
    return result


def detail_index_catalog(package, activity_ids=None):
    """List real keys, including empty lists; never infer indexes from other tables."""
    ids = (list(activity_ids) if activity_ids is not None else
           [row["activity_id"] for row in package["activity"]])
    indices = {aid: set() for aid in ids}
    for row in package["activity_detail"]:
        if row["activity_id"] in indices:
            indices[row["activity_id"]].add(row["detail_index"])
    return {aid: sorted(values) for aid, values in indices.items()}


def validate_detail_selections(rows, catalog, *, phase, assigned_ids=None):
    """Validate already schema-checked memberships without repairing their meaning."""
    violations = []
    for membership_index, row in enumerate(rows):
        aid = row["activity_id"]
        allowed = catalog.get(aid, [])
        for position, index in enumerate(row.get("detail_indices") or []):
            if index not in allowed:
                violations.append({
                    "path": f"memberships[{membership_index}].detail_indices[{position}]",
                    "code": "unknown_activity_detail",
                    "message": (f"Activity {aid!r} in Event {row['event_id']!r} has no "
                                f"activity_detail index {index!r}; allowed indices: {allowed}. "
                                "Copy only this Activity's facts.activity_detail.detail_index keys; "
                                "transaction details, instrument ordinals and global row positions "
                                "are not activity_detail keys."),
                    "item": copy.deepcopy(row), "activity_id": aid,
                    "event_id": row["event_id"], "invalid_detail_index": index,
                    "allowed_detail_indices": list(allowed),
                })
    if violations:
        report = {"phase": phase, "violations": violations,
                  "available_detail_indices": {
                      row["activity_id"]: list(catalog.get(row["activity_id"], [])) for row in rows}}
        if assigned_ids is not None:
            report["assigned_ids"] = sorted(assigned_ids)
        raise OrganizationValidationError(report)
