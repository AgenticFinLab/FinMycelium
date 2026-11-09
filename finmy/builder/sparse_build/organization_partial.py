"""Isolate relevance proposals by item; unresolved metadata never changes facts."""
import copy
import re
from collections import defaultdict
from jsonschema import Draft202012Validator

PENDING_RELEVANCE = {
    'value': 'Person relevance review pending.',
    'evidence_source_contents': [],
    'reasons': ['Execution status only; no claim of personal involvement has been accepted.'],
}


def pending_relevance(value):
    return value == PENDING_RELEVANCE


def partition_relevance(payload, ids, layout, package, prior_memberships):
    from .person_organization import PLAN_SCHEMA, _require_quotes
    from .organization_batches import _memberships
    original = copy.deepcopy(payload)
    audit = []
    def note(kind, row, **extra):
        audit.append({'status': kind, 'item': copy.deepcopy(row), **extra})
    def rows(key):
        value = original.get(key, [])
        if not isinstance(value, list):
            note('invalid_array', {key: value})
            return []
        return value
    if not isinstance(original, dict):
        original = {}
        note('invalid_response_shape', payload)
    allowed = set(ids)
    activity_ids = {row['activity_id'] for row in package['activity']}
    existing_contexts = {row.get('context_occurrence_id') for row in package['activity']}
    by_occurrence = defaultdict(list)
    relevance_schema = PLAN_SCHEMA['properties']['occurrence_relevance']['items']
    for row in rows('occurrence_relevance'):
        if (not isinstance(row, dict) or not isinstance(row.get('occurrence_id'), str)
                or row['occurrence_id'] not in allowed):
            note('out_of_scope_relevance', row)
            continue
        try:
            Draft202012Validator(relevance_schema).validate(row)
            if not pending_relevance(row['subject_relevance']):
                _require_quotes(row['subject_relevance'], 'subject_relevance')
            by_occurrence[row['occurrence_id']].append(row)
        except Exception as error:
            # JSON-schema/value validation only: the candidate remains in the audit.
            from jsonschema import ValidationError
            if not isinstance(error, (ValueError, ValidationError)):
                raise
            note('invalid_relevance', row, reason=str(error).splitlines()[0])
    issues = rows('occurrence_issues')
    affected = {oid for oid in ids for issue in issues
                if isinstance(issue, str) and re.search(r'(?<![\w:])' + re.escape(oid) + r'(?![\w:])', issue)}
    relevance, pending = [], []
    for oid in ids:
        variants = []
        for row in by_occurrence[oid]:
            if row not in variants:
                variants.append(row)
        if oid not in affected and len(variants) == 1 and not pending_relevance(variants[0]['subject_relevance']):
            relevance.append(copy.deepcopy(variants[0]))
        else:
            pending.append(oid)
            relevance.append({'occurrence_id': oid, 'subject_relevance': copy.deepcopy(PENDING_RELEVANCE)})
            note('pending_relevance', {'occurrence_id': oid, 'candidates': variants})
    backgrounds = []
    for oid in rows('background_occurrence_ids'):
        if isinstance(oid, str) and oid in allowed and oid not in existing_contexts and 'C:'+oid not in activity_ids:
            if oid not in backgrounds:
                backgrounds.append(oid)
        else:
            note('invalid_background', oid)
    created = {'C:'+oid for oid in backgrounds}
    member_schema = PLAN_SCHEMA['properties']['memberships']['items']
    by_key = defaultdict(list)
    for row in rows('memberships'):
        aid = row.get('activity_id') if isinstance(row, dict) else None
        if not isinstance(aid, str) or aid not in created:
            prior = [m for m in prior_memberships if m.get('activity_id') == aid]
            note('cross_phase_deferred' if isinstance(aid, str) and aid in activity_ids else 'invalid_membership_reference', row,
                 existing_memberships=copy.deepcopy(prior))
            continue
        try:
            Draft202012Validator(member_schema).validate(row)
            _memberships([row], created, layout, package, phase='Relevance')
        except Exception as error:
            from jsonschema import ValidationError
            if not isinstance(error, (ValueError, ValidationError)):
                raise
            note('invalid_background_membership', row, reason=str(error).splitlines()[0])
            continue
        key = (row['event_id'], aid)
        if row not in by_key[key]:
            by_key[key].append(row)
    members = []
    for variants in by_key.values():
        if len(variants) == 1:
            members.append(copy.deepcopy(variants[0]))
        else:
            note('conflicting_background_memberships', variants)
    kept = {m['activity_id'] for m in members}
    for oid in backgrounds:
        if 'C:'+oid not in kept:
            note('background_without_valid_membership', oid)
    for issue in issues:
        note('occurrence_review_requested', issue)
    result = {'occurrence_relevance': relevance,
              'background_occurrence_ids': [oid for oid in backgrounds if 'C:'+oid in kept],
              'memberships': members, 'occurrence_issues': []}
    if pending:
        result['pending_occurrence_ids'] = pending
    return result, {'original': original, 'items': audit, 'pending_occurrence_ids': pending,
                    'facts_modified': False, 'semantic_approval': False}
