"""Carry discovery hypotheses into organization without promoting them to facts."""
from __future__ import annotations

import copy


STORYLINE_GUIDANCE = """candidate_storylines contains pre-search discovery hypotheses,
not extracted facts or source evidence. Use them to preserve continuing experiences
across reports and meeting scenes. Reuse a candidate's event_id/domain_id when the
supplied facts support that same storyline/domain; do not rename its IDs merely
because labels are translated. Do not create an Event solely to satisfy the list.
Omit candidates without supported activities. Merge, split or add storylines when
supplied facts require it, keeping a candidate ID for an unchanged or retained
storyline. Do not manufacture activities, stage transitions, dates or quotes from
candidate summaries, person_connection, scope, terms or questions. All summaries,
assignments and stages still need the existing source-grounded organization checks.
There is no target count of Domains, Events, Activities or Stages."""


def candidate_storylines(plan):
    """Validate only the planning handoff; factual support is checked separately."""
    if plan is None:
        return None
    if not isinstance(plan, dict) or plan.get("version") != "person-storylines-v1":
        raise ValueError("Unsupported storyline discovery plan")
    domains, events = plan.get("domains"), plan.get("events")
    if not isinstance(domains, list) or not isinstance(events, list):
        raise ValueError("Storyline plan needs domain and event lists")
    domain_ids, event_ids = set(), set()
    projected_domains, projected_events = [], []
    for row in domains:
        if not isinstance(row, dict):
            raise ValueError("Storyline Domain must be an object")
        identifier, label = row.get("domain_id"), row.get("label")
        if (not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 128
                or identifier in domain_ids or not isinstance(label, str) or not label.strip()):
            raise ValueError("Storyline Domains need unique IDs and nonempty labels")
        domain_ids.add(identifier)
        projected_domains.append({key: copy.deepcopy(row[key]) for key in
                                  ("domain_id", "label", "summary") if key in row})
    for row in events:
        if not isinstance(row, dict):
            raise ValueError("Storyline Event must be an object")
        identifier, label = row.get("event_id"), row.get("label")
        if (not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 128
                or identifier in event_ids or not isinstance(label, str) or not label.strip()
                or row.get("domain_id") not in domain_ids):
            raise ValueError("Storyline Events need unique IDs, labels and known Domains")
        event_ids.add(identifier)
        projected_events.append({key: copy.deepcopy(row[key]) for key in
            ("event_id", "domain_id", "label", "summary", "person_connection", "scope",
             "event_terms", "questions") if key in row})
    return {"version": plan["version"], "is_source_evidence": False,
            "domains": projected_domains, "events": projected_events}


def align_storyline_ids(layout, candidates):
    """Reuse unambiguous exact-label IDs without adding a model rejection gate.

    Never overwrite another output object's existing ID. Ambiguous, translated,
    merged or split labels remain as proposed and are visible in the audit.
    """
    result = copy.deepcopy(layout)
    changes = {"domain_id_remaps": [], "event_id_remaps": []}
    if candidates is None:
        return result, changes
    for table, key in (("domains", "domain_id"), ("events", "event_id")):
        def identity(row):
            label = " ".join(row["label"].casefold().split())
            return (row["domain_id"], label) if table == "events" else label

        by_label = {}
        for row in candidates[table]:
            label = identity(row)
            by_label.setdefault(label, []).append(row[key])
        output_counts = {}
        for row in result[table]:
            label = identity(row)
            output_counts[label] = output_counts.get(label, 0) + 1
        occupied = {row[key] for row in result[table]}
        mapping = {}
        for row in result[table]:
            label = identity(row)
            matches = by_label.get(label, [])
            if (len(matches) == 1 and output_counts[label] == 1
                    and row[key] != matches[0] and matches[0] not in occupied):
                mapping[row[key]] = matches[0]
                occupied.add(matches[0])
        for old, new in mapping.items():
            changes[key + "_remaps"].append({"from": old, "to": new})
        if key == "domain_id":
            affected = ("domains", "events")
        else:
            affected = ("events", "stages", "memberships")
        for name in affected:
            for row in result.get(name, []):
                if row.get(key) in mapping:
                    row[key] = mapping[row[key]]
    return result, changes


def storyline_resolution(candidates, organization, remaps=None):
    """Audit identity coverage without asserting that omitted candidates are false."""
    candidate_ids = {row["event_id"] for row in candidates["events"]}
    final_ids = {row["event_id"] for row in organization["events"]}
    memberships = organization.get("memberships", [])
    remaps = copy.deepcopy(remaps or {"domain_id_remaps": [], "event_id_remaps": []})
    return {
        "version": "person-storyline-resolution-v1",
        "candidate_is_evidence": False,
        "id_remaps": remaps,
        "id_remap_counts": {key: len(rows) for key, rows in remaps.items()},
        "candidate_event_count": len(candidate_ids),
        "represented_event_count": len(candidate_ids & final_ids),
        "not_represented_event_count": len(candidate_ids - final_ids),
        "semantic_support_checked": False,
        "events": [{"event_id": row["event_id"], "label": row["label"],
                    "status": "represented" if row["event_id"] in final_ids else "not_represented",
                    "activity_ids": [m["activity_id"] for m in memberships
                                     if m["event_id"] == row["event_id"]]}
                   for row in candidates["events"]],
        "additional_event_ids": [row["event_id"] for row in organization["events"]
                                 if row["event_id"] not in candidate_ids],
        "interpretation": "Not represented means the reviewed organization did not retain this candidate ID; it does not prove the event did not happen.",
    }
