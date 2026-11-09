"""Remove reviewed proposal items and their dependencies, never approve them.

Paths identify complete claims in the original proposal, not arbitrary fields.
The returned subset is still only a candidate: callers must validate its merge
and obtain a fresh semantic review before publishing any of it.
"""
from __future__ import annotations

import copy

from jsonschema import Draft202012Validator

from finmy.runner.event_additions import ADDITIONS_SCHEMA


_KINDS = {"entities": "entity", "stages": "stage", "activities": "activity",
          "details": "detail", "relations": "relation"}


def _validate(proposal):
    error = next(Draft202012Validator(ADDITIONS_SCHEMA).iter_errors(proposal), None)
    if error is not None:
        raise ValueError("Invalid addition schema: " + error.message[:300])
    keys = [row["key"] for name in ("entities", "stages", "activities")
            for row in proposal[name]]
    if len(keys) != len(set(keys)):
        raise ValueError("Local proposal keys must be unique before selecting items")


def proposal_items(proposal):
    """List removable claim paths, in stable original-proposal order.

    Activity paths cover the activity and its nested details; a nested detail
    can also be removed independently. This inventory does not confer approval.
    """
    _validate(proposal)
    items = []
    for name, kind in _KINDS.items():
        for index, row in enumerate(proposal[name]):
            path = f"/{name}/{index}"
            items.append({"path": path, "kind": kind,
                          **({"key": row["key"]} if "key" in row else {})})
            if name == "activities":
                items.extend({"path": f"{path}/details/{detail_index}", "kind": "detail"}
                             for detail_index in range(len(row["details"])))
    return items


def prune_proposal(proposal, rejected_paths):
    """Return a dependency-closed candidate and an audit of original paths.

    Removing a local entity or stage removes activities that require it. Removing
    an activity removes its details and relations. References to removed local
    keys are never reinterpreted as existing graph IDs. Unused proposed entities
    and stages are discarded, since they no longer support a retained activity.
    """
    items = proposal_items(proposal)
    ordered_paths = [item["path"] for item in items]
    known_paths = set(ordered_paths)
    if not isinstance(rejected_paths, list) or any(not isinstance(path, str) for path in rejected_paths):
        raise ValueError("Rejected paths must be an array of complete proposal item paths")
    if set(rejected_paths) - known_paths:
        raise ValueError("Rejected path does not identify a complete proposal item")
    explicit = set(rejected_paths)
    removed, dependencies, orphans = set(explicit), set(), set()

    def discard(path, reason):
        if path not in removed:
            removed.add(path)
            reason.add(path)

    # The current proposal schema has no cycles between entity/stage/activity
    # dependencies. Iterate to a fixed point so each dependent removal is
    # recorded independently, including nested details of removed activities.
    while True:
        previous = len(removed)
        removed_keys = {
            name: {row["key"] for index, row in enumerate(proposal[name])
                   if f"/{name}/{index}" in removed}
            for name in ("entities", "stages", "activities")
        }
        for index, row in enumerate(proposal["activities"]):
            path = f"/activities/{index}"
            if (any(row[field] in removed_keys["entities"]
                    for field in ("actor_id", "from_entity_id", "to_entity_id"))
                    or row["stage_id"] in removed_keys["stages"]):
                discard(path, dependencies)
            if path in removed:
                for detail_index in range(len(row["details"])):
                    discard(f"{path}/details/{detail_index}", dependencies)
        removed_activity_keys = {row["key"] for index, row in enumerate(proposal["activities"])
                                 if f"/activities/{index}" in removed}
        for index, row in enumerate(proposal["details"]):
            if row["activity_id"] in removed_activity_keys:
                discard(f"/details/{index}", dependencies)
        for index, row in enumerate(proposal["relations"]):
            if any(row[field] in removed_activity_keys for field in ("from_activity_id", "to_activity_id")):
                discard(f"/relations/{index}", dependencies)

        retained = [row for index, row in enumerate(proposal["activities"])
                    if f"/activities/{index}" not in removed]
        used_entities = {row[field] for row in retained
                         for field in ("actor_id", "from_entity_id", "to_entity_id")}
        used_stages = {row["stage_id"] for row in retained}
        for name, used in (("entities", used_entities), ("stages", used_stages)):
            for index, row in enumerate(proposal[name]):
                if row["key"] not in used:
                    discard(f"/{name}/{index}", orphans)
        if len(removed) == previous:
            break

    result = {name: [] for name in _KINDS}
    for name in _KINDS:
        for index, row in enumerate(proposal[name]):
            path = f"/{name}/{index}"
            if path in removed:
                continue
            selected = copy.deepcopy(row)
            if name == "activities":
                selected["details"] = [copy.deepcopy(detail) for detail_index, detail in enumerate(row["details"])
                                       if f"{path}/details/{detail_index}" not in removed]
            result[name].append(selected)
    return result, {
        "explicit_removed_paths": [path for path in ordered_paths if path in explicit],
        "dependency_removed_paths": [path for path in ordered_paths if path in dependencies],
        "orphan_removed_paths": [path for path in ordered_paths if path in orphans],
        "remaining_paths": [path for path in ordered_paths if path not in removed],
        "requires_review": True,
    }
