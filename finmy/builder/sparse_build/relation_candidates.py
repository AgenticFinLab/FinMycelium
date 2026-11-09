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
            "decision": {"enum": ["accept", "reject", "reverse"]},
            "reason": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
    }}},
}
RELATION_REVIEW_INSTRUCTIONS = """Review every supplied relation candidate exactly
once against the complete original facts and sources. All supplied variants of
one (from_activity_id,to_activity_id,relation_type) key must be considered
together; accept at most one variant for that key. Return only candidate_id,
accept/reject/reverse and a concise nonempty reason. reverse swaps ONLY the two
endpoints of an otherwise supported non-temporal relation. You cannot edit dates,
relation types, descriptions, quotes or any underlying fact. Reject an unsupported
proposal rather than inventing a repair. A generating batch is not evidence.
Read the proposed edge as an explicit sentence: FROM [relation] TO. For
responds_to, FROM is the response and TO the earlier request/question/proposal.
Approval responds_to application, never application responds_to approval. If
your reason describes the opposite direction, choose reverse, not accept.
Reject temporal reversal; it needs a separately validated temporal proposal.
Cross-batch proposals require the same factual support as all other proposals.
executed_by must connect a decision or instruction to its execution; a meeting
containing a statement, or a person speaking during a meeting, is not executed_by.
Non-temporal links require a quote supporting the link itself, not just its two
endpoints. Do not infer causality from order. Preserve company/personal actors.
Use organization_context to inspect the selected details and final memberships
across scenes, stages and themes. These are organizational hypotheses, not source
evidence. Shared membership or a diagnostic hint does not establish a relation.
Detail selection controls display only; consult the complete underlying facts
and sources when evaluating a relation, including details not selected for display.
Consider cross-theme links on their evidence; never force a connected chain or
accept a candidate merely to improve coverage or connectivity.
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
        if decision["decision"] in {"accept", "reverse"}:
            relation = copy.deepcopy(expected[cid]["relation"])
            if decision["decision"] == "reverse":
                if relation["relation_type"] in {"precedes", "overlaps"}:
                    issues.append(_violation(path, "temporal_reversal", "Temporal relations require a new checked proposal"))
                relation["from_activity_id"], relation["to_activity_id"] = relation["to_activity_id"], relation["from_activity_id"]
            key = _key(relation)
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
            "execution_version": 4, "status": "collecting",
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
        accepted = {}
        for candidate in self._candidates.values():
            decision = candidate["decision"]["decision"]
            if decision not in {"accept", "reverse"}:
                continue
            relation = copy.deepcopy(candidate["relation"])
            if decision == "reverse":
                relation["from_activity_id"], relation["to_activity_id"] = relation["to_activity_id"], relation["from_activity_id"]
            accepted.setdefault(_key(relation), relation)
        return list(accepted.values())



CANONICAL_RELATION_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['candidates'],
    'properties': {'candidates': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['relation', 'assessment'],
        'properties': {
            'relation': PLAN_SCHEMA['properties']['activity_relations']['items'],
            'assessment': {
                'type': 'object', 'additionalProperties': False,
                'required': ['supported', 'evidence_scope', 'from_role', 'to_role', 'reason', 'needs_review', 'duplicate_fact'],
                'properties': {
                    'supported': {'type': 'boolean'},
                    'evidence_scope': {'enum': ['relation', 'endpoints_only']},
                    'from_role': {'type': 'string', 'minLength': 1},
                    'to_role': {'type': 'string', 'minLength': 1},
                    'reason': {'type': 'string', 'minLength': 1},
                    'needs_review': {'type': 'boolean'}, 'duplicate_fact': {'type': 'boolean'},
                    'response_activity_id': {'type': 'string'}, 'trigger_activity_id': {'type': 'string'},
                },
            },
        },
    }}},
}
CANONICAL_RELATION_INSTRUCTIONS = '''Propose only supported relations involving the assigned_ids source Activities.
A target may be any known global canonical Activity; inspect its factual context.
Do not connect duplicate reports of one fact using overlaps/explains: flag a
suspected duplicate instead. Identity repair is upstream, not a new edge.
For each candidate, assess the relation itself against the original source:
supported, evidence_scope (relation vs endpoints_only), the two semantic roles,
and a concrete reason. A quotation mentioning both endpoints does not establish
causality, execution or response. Mark needs_review for genuine ambiguity.
For responds_to explicitly identify response_activity_id and trigger_activity_id:
a vote or approval responds to the earlier request/proposal, never the reverse.
For executed_by, FROM is a decision/instruction and TO is its implementation;
for explains, FROM is an explanation and TO is what it explains. A meeting
containing a speech does not establish execution. Use temporal basis only when
activity times establish the relation, preserving uncertain windows. Empty
candidates is legitimate; do not create connectivity or relationship quotas.'''
CANONICAL_REVIEW_SCHEMA = copy.deepcopy(RELATION_REVIEW_SCHEMA)
CANONICAL_REVIEW_SCHEMA['properties']['decisions']['items']['properties'].update({
    'response_activity_id': {'type': 'string'}, 'trigger_activity_id': {'type': 'string'},
})
CANONICAL_REVIEW_INSTRUCTIONS = RELATION_REVIEW_INSTRUCTIONS + '''
Only disputed candidates and directional semantic claims require this review.
For responds_to, also return response_activity_id and trigger_activity_id from
the candidate endpoints; these semantic roles determine the final direction.
Do not accept a relation supported only by separately quoted endpoint facts.
A duplicate-fact suspicion is not resolved by accepting an overlap edge.'''


def _same_fact_candidate(package, left, right):
    """Conservative duplicate suspicion, never an automatic fact merge."""
    activities = {r['activity_id']: r for r in package['activity']}
    left_id, right_id = left, right
    left, right = activities[left], activities[right]
    for table, key in (('action', 'action_id'), ('financial_transaction', 'transaction_id')):
        if not left.get(key) or not right.get(key):
            continue
        rows = {r[key]: r for r in package[table]}
        a, b = rows[left[key]], rows[right[key]]
        fields = ('actor_id', 'action_type') if key == 'action_id' else ('from_entity_id', 'to_entity_id', 'name')
        times = {r['time_id']: r for r in package['time_value']}
        ta, tb = times.get(a.get('timestamp_time_id')), times.get(b.get('timestamp_time_id'))
        def normalized(row):
            return {k: v for k, v in (row or {}).items() if k not in {'time_id', 'evidence_set_id'}}
        details = lambda aid: sorted(r['value'] for r in package['activity_detail'] if r['activity_id'] == aid)
        if details(left_id) != details(right_id):
            return False
        if key == 'transaction_id':
            def instruments(tid):
                return sorted(_canonical({k: v for k, v in r.items()
                                           if k not in {'transaction_id', 'ordinal', 'evidence_set_id'}})
                              for r in package['transaction_instrument'] if r['transaction_id'] == tid)
            if instruments(a[key]) != instruments(b[key]):
                return False
        return (all(a.get(k) == b.get(k) for k in fields) and bool(ta) and bool(tb)
                and normalized(ta) == normalized(tb))
    return False


def _original_quotes(package, relation):
    quotes = relation['description']['evidence_source_contents']
    return all(any(quote in r.get('content', '') for r in package['source_document']) for quote in quotes)


def normalize_response_direction(relation, assessment):
    """Assemble response direction from declared semantic roles, not prose regex."""
    row = copy.deepcopy(relation)
    if row['relation_type'] == 'responds_to':
        response, trigger = assessment.get('response_activity_id'), assessment.get('trigger_activity_id')
        if response == trigger or {response, trigger} != {row['from_activity_id'], row['to_activity_id']}:
            raise ValueError('responds_to needs distinct response and trigger endpoint roles')
        row['from_activity_id'], row['to_activity_id'] = response, trigger
    return row


def collect_canonical_relations(package, plan, call, save, *, batch_size=20):
    """One semantic proposal pass; review conflicts and directional claims only.

    Citation presence is only a grounding check. Each proposal contains an
    explicit semantic assessment; direction-sensitive claims get an independent
    review with both endpoint evidence closures before acceptance.
    """
    from .organization_batches import _splittable
    activity_ids = [r['activity_id'] for r in package['activity']]
    pool = RelationCandidatePool(activity_ids, batch_size)
    pool.audit.update(execution_version=6, review_policy='semantic_disputes_and_directional_relations')
    assessments = {}
    membership_events = {}
    for row in plan['memberships']:
        membership_events.setdefault(row['activity_id'], set()).add(row['event_id'])
    def persist():
        save(pool.snapshot(), 'PersonOrganization-RelationCandidates')
    def generation(ids, name):
        event_ids = set().union(*(membership_events.get(aid, set()) for aid in ids))
        scope_ids = [aid for aid in activity_ids if aid in ids or membership_events.get(aid, set()) & event_ids]
        task = {'assigned_ids': ids, 'allowed_activity_ids': activity_ids,
                'events': [r for r in plan['events'] if r['event_id'] in event_ids],
                'memberships': [r for r in plan['memberships'] if r['event_id'] in event_ids]}
        def check(value):
            if not isinstance(value, dict) or not isinstance(value.get('candidates'), list):
                raise ValueError('Relation response needs a candidates array')
            accepted = []
            schema = CANONICAL_RELATION_SCHEMA['properties']['candidates']['items']
            for candidate in value['candidates']:
                try:
                    if not Draft202012Validator(schema).is_valid(candidate):
                        raise ValueError('Invalid candidate/semantic assessment shape')
                    row, assessment = candidate['relation'], candidate['assessment']
                    validate_relation_candidates({'activity_relations': [row]}, ids, activity_ids, package)
                    if not {row['from_activity_id'], row['to_activity_id']} & set(ids):
                        raise ValueError('Both relation endpoints are outside this generation task')
                    if not _original_quotes(package, row):
                        raise ValueError('Relation quote is not present in the original sources')
                    if not assessment['supported'] or assessment['evidence_scope'] != 'relation':
                        raise ValueError('Assessment does not establish the relation itself')
                    if assessment['duplicate_fact'] or _same_fact_candidate(package, row['from_activity_id'], row['to_activity_id']):
                        raise ValueError('Possible duplicate fact requires upstream identity review, not an edge')
                    row = normalize_response_direction(row, assessment)
                    accepted.append({'relation': row, 'assessment': assessment})
                except (ValueError, TypeError, KeyError) as error:
                    entry = {'batch': name, 'candidate': copy.deepcopy(candidate), 'reason': str(error)}
                    if entry not in pool.audit['rejected_attempts']:
                        pool.audit['rejected_attempts'].append(entry)
            value['candidates'] = accepted
        try:
            result = call('Relations', task, scope_ids, check, name,
                          schema=CANONICAL_RELATION_SCHEMA, instructions=CANONICAL_RELATION_INSTRUCTIONS)
        except (ValueError, RuntimeError, TimeoutError) as error:
            if _splittable(error) and len(ids) > 1:
                midpoint = len(ids)//2
                generation(ids[:midpoint], name+'-L'); generation(ids[midpoint:], name+'-R')
                return
            pool.audit.setdefault('unreviewed_batches', []).append({'phase': 'Relations', 'batch': name, 'error_type': type(error).__name__})
            persist(); return
        for candidate in result['candidates']:
            row = candidate['relation']
            pool.add({'activity_relations': [row]}, name, ids)
            cid = 'RC_' + hashlib.sha256(_canonical(row).encode('utf-8')).hexdigest()
            assessments[cid] = candidate['assessment']
        persist()
    for index, start in enumerate(range(0, len(activity_ids), batch_size), 1):
        generation(activity_ids[start:start+batch_size], f'PersonOrganization-Relations-{index:03d}')
    # Keep every variant, including reversed proposals, in the same review task.
    # Scheduling ownership must not separate claims about the same pair.
    pair_groups = {}
    position = {aid: index for index, aid in enumerate(activity_ids)}
    for candidate in pool.snapshot()['candidates']:
        row = candidate['relation']
        key = (*sorted((row['from_activity_id'], row['to_activity_id'])), row['relation_type'])
        pair_groups.setdefault(key, []).append(candidate)
    scheduled = {}
    for key, group in pair_groups.items():
        owner = min(position[key[0]], position[key[1]]) // batch_size
        scheduled.setdefault(owner, []).append(group)
    for index, (owner, groups) in enumerate(sorted(scheduled.items()), 1):
        assigned_ids = activity_ids[owner*batch_size:(owner+1)*batch_size]
        disputed = []
        for group in groups:
            for candidate in group:
                row = candidate['relation']; assessment = assessments[candidate['candidate_id']]
                opposite = any(other['relation']['from_activity_id'] == row['to_activity_id']
                               and other['relation']['to_activity_id'] == row['from_activity_id']
                               and other['relation']['relation_type'] == row['relation_type']
                               for other in pool.snapshot()['candidates'])
                requires_review = (len(group) > 1 or opposite or assessment['needs_review'] or row['basis'] == 'inferred'
                                   or row['relation_type'] in {'responds_to', 'explains', 'executed_by'})
                if requires_review:
                    candidate['assessment'] = assessment
                    disputed.append(candidate)
                else:
                    pool.decide({'decisions': [{'candidate_id': candidate['candidate_id'], 'decision': 'accept',
                        'reason': 'Generation assessed relation-level support; references and original quotations validated.'}]}, 'semantic_proposal')
        if not disputed:
            continue
        name = f'PersonOrganization-RelationsReview-{index:03d}'
        scope_ids = list(dict.fromkeys(aid for c in disputed for aid in
                                      (c['relation']['from_activity_id'], c['relation']['to_activity_id'])))
        task = {'assigned_ids': assigned_ids, 'allowed_activity_ids': activity_ids, 'candidates': disputed,
                'memberships': [r for r in plan['memberships'] if r['activity_id'] in scope_ids]}
        by_id = {c['candidate_id']: c for c in disputed}
        def checked(value):
            if not isinstance(value, dict) or not isinstance(value.get('decisions'), list):
                raise ValueError('Relation review needs a decisions array')
            accepted = {}
            pending = set(value.get('pending_candidate_ids', []))
            for decision in value['decisions']:
                cid = decision.get('candidate_id') if isinstance(decision, dict) else None
                if cid not in by_id or not Draft202012Validator(CANONICAL_REVIEW_SCHEMA['properties']['decisions']['items']).is_valid(decision):
                    continue
                if cid in accepted and accepted[cid] != decision:
                    accepted[cid] = {'candidate_id': cid, 'decision': 'reject', 'reason': 'Conflicting review decisions.'}
                    continue
                relation = by_id[cid]['relation']
                if decision['decision'] != 'reject' and relation['relation_type'] == 'responds_to':
                    try:
                        oriented = normalize_response_direction(relation, decision)
                    except ValueError:
                        continue
                    decision = copy.deepcopy(decision)
                    decision['decision'] = ('accept' if oriented['from_activity_id'] == relation['from_activity_id'] else 'reverse')
                else:
                    decision = {k: decision[k] for k in ('candidate_id', 'decision', 'reason')}
                if decision['decision'] == 'reverse' and relation['basis'] == 'temporal':
                    decision = {'candidate_id': cid, 'decision': 'reject', 'reason': 'Cannot reverse a validated temporal relation.'}
                accepted[cid] = decision
            final_keys = {}
            for cid, decision in accepted.items():
                if decision['decision'] == 'reject':
                    continue
                row = copy.deepcopy(by_id[cid]['relation'])
                if decision['decision'] == 'reverse':
                    row['from_activity_id'], row['to_activity_id'] = row['to_activity_id'], row['from_activity_id']
                final_keys.setdefault(_key(row), []).append(cid)
            for variants in final_keys.values():
                if len(variants) > 1:
                    pending.update(variants)
                    for cid in variants:
                        accepted[cid] = {'candidate_id': cid, 'decision': 'reject',
                                         'reason': 'Multiple accepted variants for one relation; all withheld pending a consistent decision.'}
            pending.update(cid for cid in by_id if cid not in accepted)
            value['pending_candidate_ids'] = sorted(pending)
            value['decisions'] = [accepted.get(cid, {'candidate_id': cid, 'decision': 'reject',
                                         'reason': 'Review unavailable for this candidate; withheld, not semantically rejected.'}) for cid in by_id]
        try:
            result = call('RelationsReview', task, scope_ids, checked, name,
                          schema=CANONICAL_REVIEW_SCHEMA, instructions=CANONICAL_REVIEW_INSTRUCTIONS)
        except (ValueError, RuntimeError, TimeoutError) as error:
            pool.audit.setdefault('unreviewed_batches', []).append({'phase': 'RelationsReview', 'batch': name, 'error_type': type(error).__name__})
            result = {'decisions': [{'candidate_id': cid, 'decision': 'reject', 'reason': 'Semantic review unavailable; candidate withheld.'} for cid in by_id]}
        if result.get('pending_candidate_ids'):
            pool.audit.setdefault('pending_candidate_ids', []).extend(result['pending_candidate_ids'])
        pool.decide(result, name); persist()
    pool.audit['status'] = ('partial_requires_content_review' if pool.audit.get('unreviewed_batches') or pool.audit.get('pending_candidate_ids')
                            else 'reviewed_requires_content_review')
    persist()
    return pool.accepted()
