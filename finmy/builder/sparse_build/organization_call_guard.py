"""Bind organization detail projections to facts at the shared inference boundary.

The inference boundary is common to older and current organization schedulers.
Recompute reference keys from factual rows rather than relying on a scheduler's
prompt version. This module never repairs a model's selections or edits facts.
"""
from __future__ import annotations

import copy
import json

from .organization_errors import OrganizationValidationError


REFERENCE_SEPARATOR = "\n\nACTIVITY DETAIL REFERENCE CONTRACT:\n"
_TASK_SEPARATOR = "\n\nBATCH TASK:\n"
_GUIDANCE = """Membership detail_indices select facts.activity_detail.detail_index
keys for the SAME activity_id. They do not index financial_transaction.details,
transaction_instrument, another Activity's details, or rows of a global table.
Use the exact available_detail_indices below, including sparse and zero keys.
A transaction may have financial_transaction.details but no activity_detail rows.
When its allowed list is [], numeric detail_indices are invalid: [] selects no
activity_detail rows; null/omission keeps all existing activity details. Neither
choice deletes the transaction or its financial_transaction.details. Choose the
appropriate display projection explicitly; do not omit the membership, change
its Activity ID, renumber indices, or drop valid selections on other memberships
merely to satisfy validation. Keep all extracted facts and evidence unchanged.
The reference catalog is metadata, not evidence for an Event or a relationship.
"""


def _request_context(user_msg):
    """Recognize the native organization request without rewriting source text."""
    try:
        decoder = json.JSONDecoder()
        request, end = decoder.raw_decode(user_msg.lstrip())
    except (TypeError, ValueError):
        return None
    if not isinstance(request, dict) or not isinstance(request.get("facts"), dict):
        return None
    facts = request["facts"]
    if not all(isinstance(facts.get(key), list) for key in ("activity", "activity_detail")):
        return None
    task = {}
    tail = user_msg.lstrip()[end:]
    if tail.startswith(_TASK_SEPARATOR):
        try:
            task, _ = decoder.raw_decode(tail[len(_TASK_SEPARATOR):])
        except (TypeError, ValueError):
            return None
        if not isinstance(task, dict):
            return None
    if task.get("phase") not in (None, "Assignments", "Relevance"):
        return None
    return facts, task


def _catalog(facts):
    catalog = {row["activity_id"]: [] for row in facts["activity"]}
    for row in facts["activity_detail"]:
        aid = row["activity_id"]
        if aid in catalog and row["detail_index"] not in catalog[aid]:
            catalog[aid].append(row["detail_index"])
    return {aid: sorted(indices) for aid, indices in catalog.items()}


def _check_details(value, catalog, facts, task, phase):
    if not isinstance(value, dict) or not isinstance(value.get("memberships"), list):
        return  # The caller's complete phase/schema validator diagnoses shape.
    allowed = copy.deepcopy(catalog)
    # Relevance and monolithic plans may introduce an occurrence-backed context
    # Activity. Such an Activity has no factual activity_detail keys yet.
    if task.get("phase") != "Assignments":
        occurrences = {row["occurrence_id"] for row in facts.get("occurrence", [])}
        for oid in value.get("background_occurrence_ids", []) or []:
            if isinstance(oid, str) and oid in occurrences:
                allowed.setdefault("C:" + oid, [])
    violations = []
    for member_index, row in enumerate(value["memberships"]):
        if not isinstance(row, dict):
            continue
        aid = row.get("activity_id")
        if not isinstance(aid, str) or aid not in allowed:
            continue  # Preserve the phase validator's activity/scope rules.
        indices = row.get("detail_indices")
        if indices is None or not isinstance(indices, list):
            continue
        for position, index in enumerate(indices):
            if index in allowed[aid]:
                continue
            violations.append({
                "path": f"memberships[{member_index}].detail_indices[{position}]",
                "code": "unknown_activity_detail",
                "message": (f"Activity {aid!r} has no activity_detail index {index!r}; "
                            f"allowed indices: {allowed[aid]}. These are not "
                            "financial_transaction.details array positions. Correct this "
                            "membership's projection without changing its Activity or evidence."),
                "item": copy.deepcopy(row), "activity_id": aid,
                "event_id": row.get("event_id"), "invalid_detail_index": index,
                "allowed_detail_indices": list(allowed[aid]),
            })
    if violations:
        report = {"phase": phase, "violations": violations,
                  "available_detail_indices": {
                      row["activity_id"]: list(allowed[row["activity_id"]])
                      for row in violations}}
        if isinstance(task.get("assigned_ids"), list):
            report["assigned_ids"] = list(task["assigned_ids"])
        raise OrganizationValidationError(report)


def guard_organization_call(system_msg, user_msg, validator, *, phase):
    """Return source-preserving prompt additions and a strict validator wrapper.

    Old scheduler requests lack a detail catalog and old validators return only
    a generic error. Both receive the same exact catalog and per-item diagnostics
    as current requests, without changing the accepted public schema.
    """
    context = _request_context(user_msg)
    if context is None:
        return system_msg, user_msg, validator
    facts, task = context
    catalog = _catalog(facts)
    visible = catalog
    if task.get("phase") == "Assignments":
        visible = {aid: catalog[aid] for aid in task.get("assigned_ids", []) if aid in catalog}
    metadata = {"phase": task.get("phase", phase),
                "available_detail_indices": visible,
                "derived_from": "facts.activity_detail grouped by activity_id"}
    guarded_user = user_msg + REFERENCE_SEPARATOR + json.dumps(
        metadata, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    def checked(value):
        _check_details(value, catalog, facts, task, phase)
        if validator is not None:
            return validator(value)

    return system_msg + "\n\n" + _GUIDANCE, guarded_user, checked
