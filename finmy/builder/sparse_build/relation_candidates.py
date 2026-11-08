"""Retain global relation proposals and review them with their source owner.

Generation batches are scheduling units, not factual boundaries. A proposal
with known global endpoints is a candidate, even if emitted by another batch.
No proposal reaches the public plan without an explicit owner review decision.
"""

from __future__ import annotations

import copy
import hashlib
import json

from jsonschema import Draft202012Validator

from .completion_errors import IncompleteCompletionError
from .organization_errors import OrganizationValidationError
from .person_organization import PLAN_SCHEMA, _check_temporal_link


RELATION_REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["decisions"],
    "properties": {"decisions": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "decision", "reason"],
        "properties": {
            "candidate_id": {"type": "string", "minLength": 1},
            "decision": {"enum": ["accept", "reject"]},
            "reason": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
    }}},
}
RELATION_REVIEW_INSTRUCTIONS = """Review every supplied relation candidate exactly
once against the complete original facts and sources. All supplied variants of
one (from_activity_id,to_activity_id,relation_type) key must be considered
together; accept at most one variant for that key. Return only candidate_id,
accept/reject and a concise nonempty reason. You cannot edit endpoints, dates,
relation types, descriptions, quotes or any underlying fact. Reject an unsupported
proposal rather than inventing a repair. A generating batch is not evidence.
Cross-batch proposals require the same factual support as all other proposals.
executed_by must connect a decision or instruction to its execution; a meeting
containing a statement, or a person speaking during a meeting, is not executed_by.
Non-temporal links require a quote supporting the link itself, not just its two
endpoints. Do not infer causality from order. Preserve company/personal actors.
Your decisions are model proposals for content review, not proof of entailment."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _key(relation):
    return tuple(relation[name] for name in
                 ("from_activity_id", "to_activity_id", "relation_type"))


def _violation(path, code, message, item=None):
    result = {"path": path, "code": code, "message": message}
    if item is not None:
        result["item"] = copy.deepcopy(item)
    return result


def _raise(phase, assigned_ids, allowed_activity_ids, violations, **extra):
    if violations:
        raise OrganizationValidationError({
            "phase": phase, "assigned_ids": list(assigned_ids),
            "allowed_activity_ids": list(allowed_activity_ids),
            "violations": violations, **extra,
        })


def _source_time_values(package, activity_id):
    """Return original time rows for diagnostics, never normalize their values."""
    activity = next((row for row in package["activity"] if row["activity_id"] == activity_id), {})
    fact = {}
    for key, table, identifier in (("action_id", "action", "action_id"),
                                   ("transaction_id", "financial_transaction", "transaction_id"),
                                   ("context_occurrence_id", "occurrence", "occurrence_id")):
        if activity.get(key):
            fact = next((row for row in package[table] if row[identifier] == activity[key]), {})
            break
    tids = {value for key, value in fact.items() if key.endswith("_time_id") and value}
    return copy.deepcopy([row for row in package["time_value"] if row["time_id"] in tids])


def validate_relation_candidates(payload, assigned_ids, allowed_activity_ids, package):
    """Validate all factual constraints; a known cross-batch source is allowed.

    Invalid responses are rejected as a whole. The caller may retain them in
    diagnostics, but must not salvage their valid-looking subset as candidates.
    """
    schema = {"type": "object", "additionalProperties": False,
              "required": ["activity_relations"],
              "properties": {"activity_relations": PLAN_SCHEMA["properties"]["activity_relations"]}}
    issues = []
    try:
        _canonical(payload)
    except (TypeError, ValueError):
        issues.append(_violation("result", "invalid_json_value", "Relation proposals must contain finite JSON values"))
    shape_errors = list(Draft202012Validator(schema).iter_errors(payload))
    for error in shape_errors:
        path = ".".join(map(str, error.absolute_path)) or "result"
        issues.append(_violation(path, "invalid_shape", error.message))
    # Keep all shape errors, but still check well-shaped rows in the same
    # response. A malformed row must not hide another row's endpoint/time issue.
    if not isinstance(payload, dict) or not isinstance(payload.get("activity_relations"), list):
        _raise("Relations", assigned_ids, allowed_activity_ids, issues)
    allowed = set(allowed_activity_ids)
    row_schema = PLAN_SCHEMA["properties"]["activity_relations"]["items"]
    for index, row in enumerate(payload["activity_relations"]):
        if not Draft202012Validator(row_schema).is_valid(row):
            continue
        path = f"activity_relations[{index}]"
        left, right = row["from_activity_id"], row["to_activity_id"]
        if left not in allowed:
            issues.append(_violation(path, "unknown_from_activity", f"Unknown source Activity: {left}", row))
        if right not in allowed:
            issues.append(_violation(path, "unknown_to_activity", f"Unknown target Activity: {right}", row))
        if left == right:
            issues.append(_violation(path, "self_relation", "A relation needs distinct Activities", row))
        if row["basis"] == "temporal":
            if left in allowed and right in allowed:
                try:
                    _check_temporal_link(package, row)
                except ValueError as error:
                    if row["relation_type"] not in {"precedes", "overlaps"}:
                        code = "invalid_temporal_basis"
                    elif str(error) == "Temporal relation contradicts or overstates the supplied times":
                        code = "temporal_contradicted_or_overstated"
                    else:
                        code = "temporal_unestablished"
                    issue = _violation(path, code, str(error), row)
                    issue["left_time_values"] = _source_time_values(package, left)
                    issue["right_time_values"] = _source_time_values(package, right)
                    issues.append(issue)
        elif not row["description"]["evidence_source_contents"]:
            issues.append(_violation(path, "missing_quote", "A non-temporal relation needs its own supporting source quotation", row))
    _raise("Relations", assigned_ids, allowed_activity_ids, issues)


def validate_relation_review(payload, candidates, assigned_ids, allowed_activity_ids):
    """Require a decision for each immutable candidate, at most one per key."""
    issues = [_violation(".".join(map(str, error.absolute_path)) or "result",
                         "invalid_shape", error.message)
              for error in Draft202012Validator(RELATION_REVIEW_SCHEMA).iter_errors(payload)]
    expected = {candidate["candidate_id"]: candidate for candidate in candidates}
    if issues:
        _raise("RelationsReview", assigned_ids, allowed_activity_ids, issues,
               candidate_ids=list(expected))
    seen, accepted = set(), {}
    for index, decision in enumerate(payload["decisions"]):
        cid = decision["candidate_id"]
        path = f"decisions[{index}]"
        if cid not in expected:
            issues.append(_violation(path, "unknown_candidate", "Candidate is outside this review group", decision))
            continue
        if cid in seen:
            issues.append(_violation(path, "duplicate_decision", "Candidate has more than one decision", decision))
        seen.add(cid)
        if decision["decision"] == "accept":
            key = _key(expected[cid]["relation"])
            if key in accepted:
                issues.append(_violation(path, "conflicting_variants", "At most one variant of a relation key may be accepted", decision))
            accepted[key] = cid
    for cid in expected.keys() - seen:
        issues.append(_violation("decisions", "missing_decision", f"Candidate requires exactly one decision: {cid}"))
    _raise("RelationsReview", assigned_ids, allowed_activity_ids, issues,
           candidate_ids=list(expected))


class RelationCandidatePool:
    """Canonical exact deduplication with provenance and immutable variants."""

    def __init__(self, all_activity_ids, batch_size=20):
        self.activity_ids = list(all_activity_ids)
        self.owners = [(f"RelationsOwner-{index:03d}", self.activity_ids[start:start + batch_size])
                       for index, start in enumerate(range(0, len(self.activity_ids), batch_size), 1)]
        self._owner = {aid: name for name, ids in self.owners for aid in ids}
        self._candidates = {}
        self.audit = {
            "execution_version": 3, "status": "collecting",
            "semantic_support_checked": False, "semantic_approval": False,
            "generation_batches": [], "review_batches": [], "rejected_attempts": [],
        }

    def add(self, payload, batch_name, assigned_ids):
        ids, assigned = [], set(assigned_ids)
        for index, relation in enumerate(payload["activity_relations"]):
            canonical = _canonical(relation)
            cid = "RC_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            cross_batch = relation["from_activity_id"] not in assigned
            if cid not in self._candidates:
                self._candidates[cid] = {
                    "candidate_id": cid, "relation": copy.deepcopy(relation),
                    "key": dict(zip(("from_activity_id", "to_activity_id", "relation_type"), _key(relation))),
                    "owner_batch": self._owner[relation["from_activity_id"]],
                    "origins": [], "cross_batch": False, "decision": None,
                }
            candidate = self._candidates[cid]
            candidate["origins"].append({"batch_name": batch_name,
                                         "assigned_ids": list(assigned_ids),
                                         "item_index": index, "cross_batch": cross_batch})
            candidate["cross_batch"] |= cross_batch
            ids.append(cid)
        self.audit["generation_batches"].append({"batch_name": batch_name,
            "assigned_ids": list(assigned_ids), "candidate_ids": ids, "status": "collected"})

    def rejected(self, phase, name, assigned_ids, payload, error):
        self.audit["rejected_attempts"].append({"phase": phase, "batch_name": name,
            "assigned_ids": list(assigned_ids), "candidate": copy.deepcopy(payload),
            "report": copy.deepcopy(error.report)})

    def groups_by_owner(self):
        for owner, ids in self.owners:
            groups = {}
            for candidate in self._candidates.values():
                if candidate["owner_batch"] == owner:
                    groups.setdefault(_key(candidate["relation"]), []).append(copy.deepcopy(candidate))
            if groups:
                yield owner, list(ids), list(groups.values())

    def decide(self, payload, review_batch):
        for decision in payload["decisions"]:
            candidate = self._candidates[decision["candidate_id"]]
            if candidate["decision"] is not None:
                raise ValueError("Candidate was already reviewed")
            candidate["decision"] = {"decision": decision["decision"],
                                     "reason": decision["reason"], "review_batch": review_batch}
        self.audit["review_batches"].append({"batch_name": review_batch,
                                             "decisions": copy.deepcopy(payload["decisions"])})

    def snapshot(self):
        return copy.deepcopy({**self.audit, "candidates": list(self._candidates.values())})

    def accepted(self):
        if any(candidate["decision"] is None for candidate in self._candidates.values()):
            raise ValueError("Every relation candidate requires an explicit review decision")
        return [copy.deepcopy(candidate["relation"]) for candidate in self._candidates.values()
                if candidate["decision"]["decision"] == "accept"]


def collect_reviewed_relations(package, activity_ids, layout, backgrounds,
                               call, save, is_splittable, *, batch_size=20):
    """Collect every generating batch, then review whole variant groups by owner."""
    pool = RelationCandidatePool(activity_ids, batch_size)

    def persist():
        save(pool.snapshot(), "PersonOrganization-RelationCandidates")

    def checked(phase, name, ids, payload, validator):
        try:
            validator(payload)
        except OrganizationValidationError as error:
            pool.rejected(phase, name, ids, payload, error)
            persist()
            raise

    def generate(ids, name):
        task = {"assigned_ids": ids, "layout": layout,
                "allowed_activity_ids": list(activity_ids), "background_activities": backgrounds}
        try:
            result = call("Relations", task, name,
                lambda value: checked("Relations", name, ids, value,
                    lambda proposal: validate_relation_candidates(proposal, ids, activity_ids, package)))
        except Exception as error:
            if not is_splittable(error) or len(ids) <= 1:
                raise
            midpoint = len(ids) // 2
            generate(ids[:midpoint], name + "-L")
            generate(ids[midpoint:], name + "-R")
            return
        pool.add(result, name, ids)
        persist()

    def review(owner, assigned_ids, groups, name):
        candidates = [candidate for group in groups for candidate in group]
        task = {"assigned_ids": assigned_ids, "layout": layout,
                "allowed_activity_ids": list(activity_ids), "owner_batch": owner,
                "background_activities": backgrounds, "candidates": candidates}
        try:
            result = call("RelationsReview", task, name,
                lambda value: checked("RelationsReview", name, assigned_ids, value,
                    lambda proposal: validate_relation_review(proposal, candidates, assigned_ids, activity_ids)))
        except Exception as error:
            if not is_splittable(error) or len(groups) <= 1:
                raise
            midpoint = len(groups) // 2
            review(owner, assigned_ids, groups[:midpoint], name + "-L")
            review(owner, assigned_ids, groups[midpoint:], name + "-R")
            return
        pool.decide(result, name)
        persist()

    persist()
    try:
        for index, start in enumerate(range(0, len(activity_ids), batch_size), 1):
            generate(activity_ids[start:start + batch_size], f"PersonOrganization-Relations-{index:03d}")
        pool.audit["status"] = "reviewing"
        persist()
        for index, (owner, ids, groups) in enumerate(pool.groups_by_owner(), 1):
            review(owner, ids, groups, f"PersonOrganization-RelationsReview-{index:03d}")
        accepted = pool.accepted()
        pool.audit["status"] = "reviewed_requires_content_review"
        persist()
        return accepted
    except Exception as error:
        pool.audit["status"] = "failed"
        failure = {"error_type": type(error).__name__}
        business_error = (error if isinstance(error, OrganizationValidationError)
                          else error.__cause__ if isinstance(error.__cause__, OrganizationValidationError)
                          else None)
        if business_error is not None:
            failure.update(message=str(business_error), report=business_error.report)
        elif isinstance(error, IncompleteCompletionError):
            failure.update(finish_reason=error.finish_reason,
                           completion_tokens=error.completion_tokens,
                           output_limit=error.output_limit,
                           refusal=error.refusal, tool_calls=error.tool_calls)
        # Transport exception messages may contain endpoints or headers. The
        # type is sufficient here; never copy arbitrary provider text to audit.
        pool.audit["failure"] = failure
        persist()
        raise
