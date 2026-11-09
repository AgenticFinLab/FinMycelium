"""Private, exact projections of an already validated person organization.

This module does not extract facts, classify semantic roles or repair a plan.
Themes are organizational hypotheses, not independent evidence for a link.
All hints are advisory: their presence never rejects a plan or requires a quota
of stages, backgrounds, actors or connected activities.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict


ORGANIZATION_CONTEXT_POLICY_IDENTITY = {
    "version": 2,
    "facts": "immutable_ids_and_exact_detail_projection",
    "themes": "hypotheses_not_evidence",
    "diagnostics": "advisory_no_quotas_no_forced_connectivity",
}


def activity_catalog(package):
    """Global identities and factual titles, without repeated source documents."""
    actions = {r['action_id']: r for r in package['action']}
    transactions = {r['transaction_id']: r for r in package['financial_transaction']}
    occurrences = {r['occurrence_id']: r for r in package['occurrence']}
    times = {r['time_id']: r for r in package['time_value']}
    entities = {r['entity_id']: r.get('name') for r in package['entity']}
    details = defaultdict(list)
    for row in package['activity_detail']:
        details[row['activity_id']].append({'detail_index': row['detail_index'], 'value': row['value']})
    result = []
    for activity in package['activity']:
        if activity.get('action_id'):
            row = actions[activity['action_id']]
            kind, title, actors = 'action', row['action_type'], [row['actor_id']]
        elif activity.get('transaction_id'):
            row = transactions[activity['transaction_id']]
            kind, title = 'transaction', row['name']
            actors = [row.get('from_entity_id'), row.get('to_entity_id')]
        else:
            row = occurrences[activity['context_occurrence_id']]
            kind, title, actors = 'context', row['title'], []
        oid = row['occurrence_id']
        result.append({'activity_id': activity['activity_id'], 'kind': kind, 'title': title,
                       'occurrence_id': oid, 'occurrence_title': occurrences[oid]['title'],
                       'actors': [{'entity_id': eid, 'name': entities.get(eid)} for eid in actors if eid],
                       'times': [times[value] for key, value in row.items()
                                 if key.endswith('_time_id') and value in times],
                       'details': details[activity['activity_id']]})
    return result


def field_evidence(package, row, field):
    """Reconstruct an existing verifiable field; never invent a quotation."""
    esid = row.get('evidence_set_id')
    evidence = next((r for r in package['evidence_set'] if r['evidence_set_id'] == esid), {})
    metadata = (evidence.get('field_metadata') or {}).get('/' + field, {})
    spans = {r['span_id']: r for r in package['evidence_span']}
    links = sorted((r for r in package['evidence_link']
                    if r['evidence_set_id'] == esid and r['field_path'] == '/' + field),
                   key=lambda r: r.get('quote_order', 0))
    return {'value': row.get(field),
            'evidence_source_contents': list(dict.fromkeys(spans[r['span_id']]['quote'] for r in links)),
            'reasons': copy.deepcopy(metadata.get('reasons') or [])}


def scoped_organization_request(package, subject, activity_ids, *, occurrence_ids=(), catalog=None):
    """Send the complete evidence closure of this task, plus a global ID index.

    Documents in the closure remain verbatim. Unbound quotes are resolved against
    all stored documents, so older saved graphs retain their original evidence.
    No character cap or arbitrary first-N document selection is applied here.
    """
    from .organization_details import detail_index_catalog, detail_reference_catalog
    selected = set(activity_ids)
    activities = [r for r in package['activity'] if r['activity_id'] in selected]
    action_ids = {r.get('action_id') for r in activities}
    transaction_ids = {r.get('transaction_id') for r in activities}
    actions = [r for r in package['action'] if r['action_id'] in action_ids]
    transactions = [r for r in package['financial_transaction'] if r['transaction_id'] in transaction_ids]
    oids = set(occurrence_ids) | {r['occurrence_id'] for r in actions + transactions}
    oids.update(r['context_occurrence_id'] for r in activities if r.get('context_occurrence_id'))
    facts = {
        'entity': package['entity'], 'entity_alias': package['entity_alias'],
        'occurrence': [r for r in package['occurrence'] if r['occurrence_id'] in oids],
        'occurrence_participant': [r for r in package['occurrence_participant'] if r['occurrence_id'] in oids],
        'participation': [r for r in package['participation'] if r.get('occurrence_id') in oids],
        'action': actions, 'financial_transaction': transactions,
        'transaction_instrument': [r for r in package['transaction_instrument'] if r['transaction_id'] in transaction_ids],
        'activity': activities,
        'activity_detail': [r for r in package['activity_detail'] if r['activity_id'] in selected],
        'time_value': package['time_value'],
        'relation_occurrence': [r for r in package['relation_occurrence'] if r['occurrence_id'] in oids],
    }
    relids = {r['relation_id'] for r in facts['relation_occurrence']}
    facts['entity_relation'] = [r for r in package['entity_relation'] if r['relation_id'] in relids]
    tids = {value for key, rows in facts.items() if key != 'time_value' for r in rows
            for field, value in r.items() if field.endswith('_time_id') and value}
    facts['time_value'] = [r for r in package['time_value'] if r['time_id'] in tids]
    eids = {package['graph']['subject_entity_id']}
    for key, rows in facts.items():
        if key in {'entity', 'entity_alias'}:
            continue
        for row in rows:
            eids.update(value for field, value in row.items()
                        if field in {'entity_id', 'actor_id', 'from_entity_id', 'to_entity_id',
                                     'source_entity_id', 'target_entity_id'} and value)
    facts['entity'] = [r for r in package['entity'] if r['entity_id'] in eids]
    facts['entity_alias'] = [r for r in package['entity_alias'] if r['entity_id'] in eids]
    # Entity/time catalogs are small metadata; their unrelated sources should not
    # pull the whole input corpus into every placement batch.
    esids = {r.get('evidence_set_id') for key, rows in facts.items()
             if key not in {'entity', 'entity_alias', 'time_value'} for r in rows}
    facts['evidence_set'] = [r for r in package['evidence_set'] if r['evidence_set_id'] in esids]
    facts['evidence_link'] = [r for r in package['evidence_link'] if r['evidence_set_id'] in esids]
    span_ids = {r['span_id'] for r in facts['evidence_link']}
    facts['evidence_span'] = [r for r in package['evidence_span'] if r['span_id'] in span_ids]
    docids = {r.get('document_id') for r in facts['evidence_span']}
    unbound = [r['quote'] for r in facts['evidence_span'] if not r.get('document_id') and r.get('quote')]
    facts['source_document'] = [r for r in package['source_document'] if r['document_id'] in docids
                               or any(q in r.get('content', '') for q in unbound)]
    return copy.deepcopy({'subject': subject, 'graph': package['graph'], 'facts': facts,
                          'global_activity_index': catalog if catalog is not None else activity_catalog(package),
                          'source_catalog': [{k: r[k] for k in ('document_id', 'title', 'url') if k in r}
                                             for r in package['source_document']],
                          'available_detail_indices': detail_index_catalog(facts),
                          'available_detail_refs': {aid: [{'detail_ref': row['detail_ref'], 'value': row['value']}
                                                          for row in rows]
                                                    for aid, rows in detail_reference_catalog(facts).items()}})


def _unique(values):
    return list(dict.fromkeys(value for value in values if value is not None))


def _components(ids, relations):
    """Report undirected components only; this is not a causality score."""
    neighbors = {aid: set() for aid in ids}
    for relation in relations:
        left, right = relation["from_activity_id"], relation["to_activity_id"]
        if left in neighbors and right in neighbors:
            neighbors[left].add(right)
            neighbors[right].add(left)
    seen, components = set(), []
    for aid in ids:
        if aid in seen:
            continue
        pending, component = [aid], set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            component.add(current)
            pending.extend(neighbors[current] - seen)
        components.append([item for item in ids if item in component])
    return components


def build_organization_context(package, plan):
    """Return an independent deterministic view of the current validated plan.

``package`` is the original immutable fact package. A newly selected background
is resolved through ``plan.background_occurrence_ids`` before C: activities have
been materialized. Missing or invalid references fail rather than being guessed;
the caller must run the existing organization validator first.
"""
    actions = {row["action_id"]: row for row in package["action"]}
    transactions = {row["transaction_id"]: row for row in package["financial_transaction"]}
    occurrences = {row["occurrence_id"]: row for row in package["occurrence"]}
    activities = {row["activity_id"]: row for row in package["activity"]}
    for oid in plan.get("background_occurrence_ids", []):
        activities.setdefault("C:" + oid, {"activity_id": "C:" + oid, "context_occurrence_id": oid})
    details, participants, relation_ids = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in package["activity_detail"]:
        details[row["activity_id"]].append(row)
    for row in package["occurrence_participant"]:
        participants[row["occurrence_id"]].append(row["entity_id"])
    for row in package["relation_occurrence"]:
        relation_ids[row["occurrence_id"]].append(row["relation_id"])
    relevance = {row["occurrence_id"]: row["subject_relevance"]
                 for row in plan.get("occurrence_relevance", [])}
    by_event, by_activity = defaultdict(list), defaultdict(list)
    for membership in plan["memberships"]:
        by_event[membership["event_id"]].append(membership)
        by_activity[membership["activity_id"]].append(membership)
    hints = []

    def hint(code, message, **locators):
        hints.append({"code": code, "message": message, **locators})

    def projection(member):
        aid = member["activity_id"]
        activity = activities[aid]
        if activity.get("action_id"):
            kind, table, key = "action", "action", "action_id"
            row = actions[activity[key]]
            title = row["action_type"]
            actors = {"actor_id": row["actor_id"]}
        elif activity.get("transaction_id"):
            kind, table, key = "transaction", "financial_transaction", "transaction_id"
            row = transactions[activity[key]]
            title = row["name"]
            actors = {"from_entity_id": row.get("from_entity_id"),
                      "to_entity_id": row.get("to_entity_id")}
        else:
            kind, table, key = "context", "occurrence", "context_occurrence_id"
            row = occurrences[activity[key]]
            title = row["title"]
            actors = {"participant_entity_ids": _unique(participants[row["occurrence_id"]])}
        oid = row["occurrence_id"]
        all_details = sorted(details[aid], key=lambda item: item["detail_index"])
        selection = member.get("detail_indices")
        selected = (all_details if selection is None else
                    [item for item in all_details if item["detail_index"] in selection])
        return {
            "activity_id": aid, "stage_id": member.get("stage_id"), "kind": kind,
            "display_title": member.get("display_title") or title,
            "fact_ref": {"table": table, "id": activity[key]},
            **actors, "occurrence_id": oid,
            "time_refs": {name: value for name, value in row.items()
                          if name.endswith("_time_id")},
            "detail_mode": "all" if selection is None else "selected",
            "detail_indices": selection,
            "selected_details": selected,
            "evidence_set_ids": _unique([row.get("evidence_set_id"),
                                          occurrences[oid].get("evidence_set_id"),
                                          *(item.get("evidence_set_id") for item in selected)]),
            "entity_relation_ids": _unique(relation_ids[oid]),
            "subject_relevance": relevance.get(oid),
        }

    themes = []
    relations = plan.get("activity_relations", [])
    domain_events = Counter(event["domain_id"] for event in plan["events"])
    if len(plan["domains"]) > 1 and all(domain_events[domain["domain_id"]] == 1 for domain in plan["domains"]):
        hint("one_event_per_domain", "Check whether Domains and Events express different levels; this pattern can be legitimate.")
    for domain in plan["domains"]:
        if not domain_events[domain["domain_id"]]:
            hint("unused_domain", "No Event is assigned to this Domain.", domain_id=domain["domain_id"])
    domain_labels = {row["domain_id"]: " ".join(row["label"].casefold().split()) for row in plan["domains"]}
    for event in plan["events"]:
        eid = event["event_id"]
        members = [projection(member) for member in by_event[eid]]
        ids = [member["activity_id"] for member in members]
        stages = []
        for stage in plan["stages"]:
            if stage["event_id"] != eid:
                continue
            stage_ids = [member["activity_id"] for member in members
                         if member["stage_id"] == stage["stage_id"]]
            stages.append({**stage, "activity_ids": stage_ids})
            if not stage_ids:
                hint("unused_stage", "No Activity is assigned to this Stage.", event_id=eid, stage_id=stage["stage_id"])
            if not stage.get("summary"):
                hint("missing_stage_summary", "Consider a sourced progress summary if it adds meaning; do not invent one.",
                     event_id=eid, stage_id=stage["stage_id"])
        if not ids:
            hint("unused_event", "No Activity is assigned to this Event.", event_id=eid)
        if " ".join(event["label"].casefold().split()) == domain_labels[event["domain_id"]]:
            hint("matching_domain_event_labels", "Domain and Event labels are identical; check whether both levels are useful.", event_id=eid)
        internal = [row for row in relations if row["from_activity_id"] in ids and row["to_activity_id"] in ids]
        crossing = [row for row in relations if (row["from_activity_id"] in ids) != (row["to_activity_id"] in ids)]
        components = _components(ids, internal)
        # No relations before generation is normal. Report connectivity as data,
        # not a missing-evidence finding or a reason to manufacture a link.
        themes.append({**event, "stages": stages, "activities": members,
                       "internal_relations": internal, "cross_theme_relations": crossing,
                       "relation_components": components})
    for aid, members in by_activity.items():
        if len(members) > 1 and all(row.get("detail_indices") is None for row in members):
            hint("shared_activity_all_details", "All memberships show every detail; check each theme's relevance without changing the fact.",
                 activity_id=aid, event_ids=[row["event_id"] for row in members])
    for row in plan.get("unassigned_reasons", []):
        hint("unassigned_activity", "The Activity is retained but has no theme membership.", activity_id=row["activity_id"])
    context = {
        "organization_context_version": ORGANIZATION_CONTEXT_POLICY_IDENTITY['version'],
        "semantic_support_checked": False,
        "interpretation": "Derived organization is not source evidence. Hints and connectivity are advisory, not quotas or semantic approval.",
        "subject_entity_id": package["graph"]["subject_entity_id"],
        "domains": plan["domains"], "themes": themes,
        "unassigned_reasons": plan.get("unassigned_reasons", []),
        "occurrence_issues": plan.get("occurrence_issues", []),
        "quality_hints": hints,
        "summary": {"theme_count": len(themes), "stage_count": len(plan["stages"]),
                    "membership_count": len(plan["memberships"]),
                    "assigned_activity_count": len(by_activity),
                    "unassigned_activity_count": len(plan.get("unassigned_reasons", [])),
                    "relation_count": len(relations)},
    }
    return copy.deepcopy(context)
