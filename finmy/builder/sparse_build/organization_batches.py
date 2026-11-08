"""Bound output size without truncating sources or changing the final contract.

Each call sees the same complete factual request. Only its output responsibility
is partitioned. Accepted pieces remain proposals until the merged plan passes
the existing full organization validator.
"""

from __future__ import annotations

import copy
import json

from jsonschema import Draft202012Validator

from .completion_errors import IncompleteCompletionError
from .organization_context import (
    ORGANIZATION_CONTEXT_POLICY_IDENTITY, build_organization_context,
)
from .person_organization import (
    ORGANIZATION_SYSTEM_PROMPT, PLAN_SCHEMA,
    _require_quotes, _require_valid, _unique, organization_request,
    validate_organization,
)
from .relation_candidates import (
    RELATION_REVIEW_INSTRUCTIONS, RELATION_REVIEW_SCHEMA,
    collect_reviewed_relations, validate_relation_candidates,
)


ORGANIZATION_EXECUTION_VERSION = 4
ACTIVITY_BATCH_SIZE = 20
OCCURRENCE_BATCH_SIZE = 5
TASK_SEPARATOR = "\n\nBATCH TASK:\n"

_PHASE_FIELDS = {
    "Layout": ("domains", "events", "stages"),
    "LayoutReview": ("domains", "events", "stages"),
    "Assignments": ("memberships", "unassigned_reasons"),
    "Relevance": ("occurrence_relevance", "background_occurrence_ids",
                  "memberships", "occurrence_issues"),
    "Relations": ("activity_relations",),
    "RelationsReview": ("decisions",),
}
_PHASE_INSTRUCTIONS = {
    "Layout": """Propose only Domains, Events and Stages over the complete supplied
facts. Do not output memberships or relevance yet. Every Event must be useful
for at least one supplied Activity; do not create empty speculative experiences.
Follow supported personal experiences across scenes and sources. Domains group
related experiences; do not merely repeat Event labels as broader categories.
Use stages only for documented changes in involvement, not one per occurrence
or document. Include useful evidence-backed progress summaries. This is the
candidate layout; a single LayoutReview precedes fixed downstream assignments.""",
    "LayoutReview": """Review candidate_layout against the complete supplied
facts and sources, then return the complete corrected Domains, Events and Stages
using the same layout contract. If no correction is needed, return it unchanged.
Check for scene containers mistaken for continuing experiences, duplicated or
fragmented themes, Domain labels that merely repeat an Event, and stage boundaries
based only on date/document/session rather than changes in involvement. Combine
or separate themes only when supplied facts justify doing so. Keep a useful
evidence-backed stage summary when it explains progress beyond the label.
There is no target number of Domains, Events or Stages; a single Event in a Domain
or an Event without stages can be appropriate. Every Event must accommodate at
least one supplied Activity. Never create actions, actors, occurrences, dates or
evidence, and do not copy a reference example's structure. Existing facts are
immutable. Return only the reviewed layout, not memberships, links or a new graph.
This is one bounded review, not a recursive redesign. Later phases use the
returned Event and Stage IDs exactly.""",
    "Assignments": """Assign every assigned_ids Activity to one or more supplied
Events, or give exactly one unassigned_reasons entry. Never both. Multiple Event
memberships for one Activity are allowed. Only these assigned_ids may appear in
this response. Reuse the fixed layout IDs. Do not add background activities here.
Choose detail_indices for each Event separately, especially for cross-theme
memberships; do not mechanically copy all details into every Event. None/omitted
means all details and [] means intentionally display none. Selection must not
rewrite or delete factual details. Use display_title when a supported concise
title clarifies the Activity's role in this Event; omit it when it merely repeats
the original title. Do not drop an Activity to save space. Existing background
activities, if any, are assigned here as ordinary IDs.""",
    "Relevance": """Return subject_relevance exactly once for each assigned_ids
occurrence, including occurrences whose activities were unassigned. Preserve
actual actors and support indirect relevance with source quotes. Select useful
background occurrences only from assigned_ids, and only when no context Activity
already exists. Select a background when it explains a supported experience;
neither duplicate every scene nor infer the person's knowledge from public
information. Preserve the distinction between personal action, company execution
and external context. For every newly selected background, return at least one
membership for C:<occurrence_id> using the fixed layout. No other memberships or
occurrence IDs may be returned. Existing context activities were assigned in the
Assignments phase. If a scene needs reconstruction, report occurrence_issues;
do not manufacture relevance or silently change the scene.""",
    "Relations": """Consider supported Activity relations across the ENTIRE
request, including relations between different occurrences, Events and batches.
Use organization_context to understand the reviewed themes, fixed memberships,
stage placement and selected details. It is derived organizational context, not
new source evidence or permission to alter facts. Check supported connections
across scenes and roles within a theme, and across themes when warranted. An
unconnected node or a short chain alone is not a missing relation; never force
connectivity, causality or a prescribed process pattern.
Generate from_activity_id entries belonging to assigned_ids. to_activity_id may be ANY
allowed_activity_ids entry, even outside this batch. Do not limit targets to this
batch. Include each justified relation once; an empty list is allowed when none
is supported. Non-temporal relations require their own exact supporting quotes.
Temporal relations must follow the existing precise time rules. Do not invent
links or infer causality from sequence. executed_by must connect a decision or
instruction to its execution; it does not mean a meeting contains a statement.
Every proposal is a candidate for later owner review, not an accepted link.
Do not repeat memberships or relevance.""",
    "RelationsReview": RELATION_REVIEW_INSTRUCTIONS,
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _phase_schema(phase):
    if phase == "RelationsReview":
        return copy.deepcopy(RELATION_REVIEW_SCHEMA)
    properties = {name: copy.deepcopy(PLAN_SCHEMA["properties"][name])
                  for name in _PHASE_FIELDS[phase]}
    # An assignment batch may be entirely unassigned; relevance may select no
    # backgrounds. The final contract still requires a nonempty membership set.
    if "memberships" in properties:
        properties["memberships"].pop("minItems", None)
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


_COMMON_PROMPT = ORGANIZATION_SYSTEM_PROMPT.split("\nPrivate JSON contract:", 1)[0]
_BATCH_SYSTEM_PROMPT = (
    _COMMON_PROMPT
    + "\n\nExecution is partitioned into validated phases. The BATCH TASK below "
    "defines this call's exact output fields and assigned IDs. The complete "
    "facts are shared context, not permission to output another batch's items. "
    "Return only the phase contract, never the full plan. Use compact JSON."
)
ORGANIZATION_BATCH_PROMPT_IDENTITY = {
    "execution_version": ORGANIZATION_EXECUTION_VERSION,
    "activity_batch_size": ACTIVITY_BATCH_SIZE,
    "occurrence_batch_size": OCCURRENCE_BATCH_SIZE,
    "small_run": "activities<=20 and occurrences<=5; length falls back to phases",
    "length_policy": "only length without refusal/tools; binary split until singleton; layout fails",
    "layout_review_policy": "one full-contract review before fixed assignments on phased execution; small complete-plan execution retains one call",
    "organization_context_policy": ORGANIZATION_CONTEXT_POLICY_IDENTITY,
    "relation_policy": "collect all generation batches; globally valid cross-batch sources become candidates; canonical exact dedup retains origins; retain key variants; owner review decides every candidate; at most one accepted variant per key; review length splits whole key groups only; reject audit retained; semantic approval remains false",
    "task_separator": TASK_SEPARATOR,
    "system": _BATCH_SYSTEM_PROMPT,
    "instructions": _PHASE_INSTRUCTIONS,
    "schemas": {phase: _phase_schema(phase) for phase in _PHASE_FIELDS},
}


def _shape(payload, phase):
    _json(payload)
    errors = list(Draft202012Validator(_phase_schema(phase)).iter_errors(payload))
    if errors:
        error = errors[0]
        raise ValueError(f"Organization {phase} {'/'.join(map(str, error.absolute_path))}: {error.message}")


def _validate_layout(payload):
    _shape(payload, "Layout")
    domains = _unique(payload["domains"], lambda row: row["domain_id"], "domain")
    events = _unique(payload["events"], lambda row: row["event_id"], "event")
    _unique(payload["stages"], lambda row: (row["event_id"], row["stage_id"]), "stage")
    for event in payload["events"]:
        if event["domain_id"] not in domains:
            raise ValueError("Organization Layout: Event references unknown Domain")
        _require_quotes(event["summary"], "event summary")
    for stage in payload["stages"]:
        if stage["event_id"] not in events:
            raise ValueError("Organization Layout: Stage references unknown Event")
        _require_quotes(stage["boundary_reason"], "stage boundary")
        if stage.get("summary") is not None:
            _require_quotes(stage["summary"], "stage summary")


def _memberships(rows, allowed, layout, package):
    _unique(rows, lambda row: (row["event_id"], row["activity_id"]), "membership")
    event_ids = {row["event_id"] for row in layout["events"]}
    stage_ids = {(row["event_id"], row["stage_id"]) for row in layout["stages"]}
    details = {(row["activity_id"], row["detail_index"]) for row in package["activity_detail"]}
    for row in rows:
        eid, aid, sid = row["event_id"], row["activity_id"], row.get("stage_id")
        if aid not in allowed:
            raise ValueError(f"Organization membership Activity is outside assigned_ids: {aid}")
        if eid not in event_ids or (sid is not None and (eid, sid) not in stage_ids):
            raise ValueError("Organization membership references unknown Event or Stage")
        if any((aid, index) not in details for index in (row.get("detail_indices") or [])):
            raise ValueError("Organization membership references unknown activity detail")


def _validate_assignments(payload, ids, layout, package):
    _shape(payload, "Assignments")
    allowed = set(ids)
    _memberships(payload["memberships"], allowed, layout, package)
    assigned = {row["activity_id"] for row in payload["memberships"]}
    unassigned = _unique(payload["unassigned_reasons"], lambda row: row["activity_id"], "unassigned reason")
    if unassigned != allowed - assigned:
        raise ValueError("Organization Assignments must cover every assigned ID by memberships or an unassigned reason, never both")


def _validate_relevance(payload, ids, layout, package):
    _shape(payload, "Relevance")
    if payload["occurrence_issues"]:
        raise ValueError("Occurrence reconstruction required: " + "; ".join(payload["occurrence_issues"]))
    relevant = _unique(payload["occurrence_relevance"], lambda row: row["occurrence_id"], "occurrence relevance")
    if relevant != set(ids):
        raise ValueError("Organization Relevance must cover every assigned occurrence exactly once")
    for row in payload["occurrence_relevance"]:
        _require_quotes(row["subject_relevance"], "subject_relevance")
    backgrounds = set(payload["background_occurrence_ids"])
    existing = {row.get("context_occurrence_id") for row in package["activity"]}
    if not backgrounds <= set(ids):
        raise ValueError("Organization background occurrence is outside assigned_ids")
    if backgrounds & existing:
        raise ValueError("Existing background Activities belong to Assignments, not new background selection")
    activity_ids = {row["activity_id"] for row in package["activity"]}
    created = {"C:" + oid for oid in backgrounds}
    if created & activity_ids:
        raise ValueError("Background Activity ID collides with an existing fact")
    _memberships(payload["memberships"], created, layout, package)
    if {row["activity_id"] for row in payload["memberships"]} != created:
        raise ValueError("Every selected background Activity must have a membership")


def _validate_relations(payload, ids, allowed, package):
    validate_relation_candidates(payload, ids, allowed, package)


def _splittable(error):
    return (isinstance(error, IncompleteCompletionError)
            and error.finish_reason == "length"
            and not error.refusal and not error.tool_calls)


def organize_person_plan(package, cascade, subject, output_language, infer, save):
    """Generate a complete v1 plan through bounded v4 execution.

    ``infer(system, user, savename, validator)`` must use the caller's common
    attempt/call budget and propagate incomplete completions. No partial JSON
    from an incomplete response is parsed here. ``save(data, name)`` stores
    accepted intermediate proposals; the caller owns the final Result artifact.
    """
    _require_valid(package)
    request = organization_request(package, cascade, subject, include_context_activities=True)
    request["output_language"] = output_language
    # Mark existing context IDs explicitly. Their facts/details and reachable
    # evidence are also retained above, without prior memberships or relevance.
    contexts = [copy.deepcopy(row) for row in package["activity"]
                if row.get("context_occurrence_id") is not None]
    if contexts:
        request["existing_context_activities"] = contexts
        context_ids = {row["activity_id"] for row in contexts}
        request["existing_context_activity_details"] = [
            copy.deepcopy(row) for row in package["activity_detail"]
            if row["activity_id"] in context_ids
        ]
    prefix = _json(request)
    activity_ids = [row["activity_id"] for row in package["activity"]]
    occurrence_ids = [row["occurrence_id"] for row in package["occurrence"]]
    if len(activity_ids) <= ACTIVITY_BATCH_SIZE and len(occurrence_ids) <= OCCURRENCE_BATCH_SIZE:
        try:
            result = infer(ORGANIZATION_SYSTEM_PROMPT, json.dumps(request, ensure_ascii=False), "PersonOrganization",
                           lambda value: validate_organization(value, package))
            validate_organization(result, package)
            save(build_organization_context(package, result), "PersonOrganization-Context")
            return result
        except IncompleteCompletionError as error:
            if not _splittable(error):
                raise

    def call(phase, task, name, validator):
        task = {"phase": phase, "instructions": _PHASE_INSTRUCTIONS[phase],
                "response_schema": _phase_schema(phase), **task}
        result = infer(_BATCH_SYSTEM_PROMPT, prefix + TASK_SEPARATOR + _json(task), name, validator)
        validator(result)
        save(copy.deepcopy(result), name + "-Plan")
        return result

    layout = call("Layout", {}, "PersonOrganization-Layout", _validate_layout)
    layout = call("LayoutReview", {"candidate_layout": copy.deepcopy(layout)},
                  "PersonOrganization-LayoutReview", _validate_layout)
    plan = {**copy.deepcopy(layout), "memberships": [], "occurrence_relevance": [],
            "background_occurrence_ids": [], "activity_relations": [],
            "occurrence_issues": [], "unassigned_reasons": []}

    def batches(phase, ids, size, validate, extra=None):
        def one(assigned, name):
            task = {"assigned_ids": assigned, "layout": layout, **(extra or {})}
            try:
                return [call(phase, task, name, lambda value: validate(value, assigned))]
            except IncompleteCompletionError as error:
                if not _splittable(error) or len(assigned) <= 1:
                    raise
                midpoint = len(assigned) // 2
                return one(assigned[:midpoint], name + "-L") + one(assigned[midpoint:], name + "-R")
        for index, start in enumerate(range(0, len(ids), size), 1):
            yield from one(ids[start:start + size], f"PersonOrganization-{phase}-{index:03d}")

    for result in batches("Assignments", activity_ids, ACTIVITY_BATCH_SIZE,
                          lambda value, ids: _validate_assignments(value, ids, layout, package)):
        plan["memberships"].extend(result["memberships"])
        plan["unassigned_reasons"].extend(result["unassigned_reasons"])
    for result in batches("Relevance", occurrence_ids, OCCURRENCE_BATCH_SIZE,
                          lambda value, ids: _validate_relevance(value, ids, layout, package)):
        for key in ("memberships", "occurrence_relevance", "background_occurrence_ids"):
            plan[key].extend(result[key])

    # Validate all assignments/relevance globally before spending calls on links.
    validate_organization(plan, package)
    organization_context = build_organization_context(package, plan)
    save(copy.deepcopy(organization_context), "PersonOrganization-Context")
    backgrounds = [{"activity_id": "C:" + oid, "context_occurrence_id": oid}
                   for oid in plan["background_occurrence_ids"]]
    relation_package = {**package, "activity": [*package["activity"], *backgrounds]}
    all_ids = activity_ids + [row["activity_id"] for row in backgrounds]
    plan["activity_relations"] = collect_reviewed_relations(
        relation_package, all_ids, layout, backgrounds, call, save, _splittable,
        batch_size=ACTIVITY_BATCH_SIZE, organization_context=organization_context)
    validate_organization(plan, package)
    save(build_organization_context(package, plan), "PersonOrganization-FinalContext")
    return plan
