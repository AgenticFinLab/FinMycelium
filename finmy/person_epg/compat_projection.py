"""Read-only display projection from Person EPG 3.0 to SubjectGraph 1.0.

This is deliberately separate from the strict legacy round-trip adapter.  It
accepts nullable v3 columns and restores evidence wrappers without requiring the
metadata produced by ``from_subject_graph``.  Organizational rows stay in the
canonical Person EPG; the projection must never be used to save that package.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict

from finmy.subject_graph.validation import date_interval, outside_coverage, validate_subject_graph

from .validation import validate_person_epg


_LEGACY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")
_UNKNOWN = {"", "unknown", "unspecified", "none", "null", "n/a", "na"}


def _pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _ordered(rows):
    # Python's stable sort preserves the original tie order.
    return sorted(rows, key=lambda row: row.get("sort_order", 0))


def _identifiers(values, prefix):
    """Keep usable IDs, mapping only values the old contract cannot represent."""
    values = list(dict.fromkeys(values))
    used = {value for value in values if _LEGACY_ID.fullmatch(value)}
    result = {}
    for value in values:
        if _LEGACY_ID.fullmatch(value):
            result[value] = value
            continue
        base = prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
        candidate, suffix = base, 0
        while candidate in used:
            suffix += 1
            candidate = f"{base}_{suffix}"
        used.add(candidate)
        result[value] = candidate
    return result


def project_person_epg(package):
    """Return a validated legacy display graph without mutating ``package``.

    Unknown roles are emitted only for identities already in the occurrence's
    participant set.  A scene with no recorded participant cannot be represented
    by the old contract and raises an error rather than adding the focal person.
    The validation performed here checks display structure, not source support.
    """
    report = validate_person_epg(package)
    if not report["valid"]:
        error = report["errors"][0]
        raise ValueError(f"Invalid Person EPG at {error['path']}: {error['message']}")

    metadata = {row["evidence_set_id"]: row.get("field_metadata") or {}
                for row in package["evidence_set"]}
    spans = {row["span_id"]: row for row in package["evidence_span"]}
    links = defaultdict(list)
    for row in package["evidence_link"]:
        links[(row["evidence_set_id"], row["field_path"])].append(row)
    times = {row["time_id"]: row for row in package["time_value"]}

    def field(row, value, path, *, alternatives=()):
        sid = row.get("evidence_set_id")
        fields = metadata.get(sid, {})
        if not isinstance(fields, dict):
            fields = {}
        chosen = next((candidate for candidate in (path, *alternatives)
                       if candidate in fields or (sid, candidate) in links), path)
        info = fields.get(chosen, {})
        if not isinstance(info, dict):
            info = {}
        quotes = [spans[link["span_id"]]["quote"] for link in
                  sorted(links.get((sid, chosen), []), key=lambda item: item["quote_order"])]
        reasons = info.get("reasons", [])
        reasons = copy.deepcopy(reasons) if isinstance(reasons, list) and all(
            isinstance(reason, str) for reason in reasons) else []
        if value is None:
            value = "unknown"
        elif not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        result = {"value": value, "evidence_source_contents": quotes, "reasons": reasons}
        confidence = info.get("confidence")
        if "confidence" in info and (confidence is None or
                type(confidence) in (int, float) and 0 <= confidence <= 1):
            result["confidence"] = confidence
        # Unlocated evidence remains usable for display, explicitly unverified.
        if info.get("evidence_status") == "needs_review" or any(
                spans[link["span_id"]].get("document_id") is None
                for link in links.get((sid, chosen), [])):
            result["evidence_status"] = "needs_review"
        elif not quotes and value.lower().strip() not in _UNKNOWN:
            result["evidence_status"] = "needs_review"
        window = info.get("time_window")
        if isinstance(window, dict) and set(window) == {"start", "end", "original", "approximate"}:
            result["time_window"] = copy.deepcopy(window)
        return result

    def time_field(row, name, column):
        time = times.get(row.get(column))
        result = field(row, time["value"] if time else "unknown", "/" + name,
                       alternatives=("/" + column,))
        if time and time.get("window_start") is not None:
            result["time_window"] = {
                "start": time["window_start"], "end": time["window_end"],
                "original": time["original_text"], "approximate": time["is_approximate"],
            }
        if result["value"].lower().strip() not in _UNKNOWN and date_interval(result) is None:
            original = result["value"]
            result["value"] = "unknown"
            result["reasons"].append(
                "Legacy display cannot locate this time expression; the Person EPG retains it: " + original)
            result["evidence_status"] = "needs_review"
        return result

    def text_list(row, name):
        values = row.get(name) or []
        # Open JSON columns can hold a single structured value. Keep its content
        # visible as text rather than iterating dictionary keys or string letters.
        if not isinstance(values, list):
            values = [values]
        return [field(row, value, "/" + name + "/" + str(index))
                for index, value in enumerate(values)]

    entity_ids = _identifiers((r["entity_id"] for r in package["entity"]), "DISPLAY_ENTITY_")
    occurrence_ids = _identifiers((r["occurrence_id"] for r in package["occurrence"]), "DISPLAY_OCC_")
    action_ids = _identifiers((r["action_id"] for r in package["action"]), "DISPLAY_ACTION_")
    transaction_ids = _identifiers((r["transaction_id"] for r in package["financial_transaction"]), "DISPLAY_TX_")
    relation_ids = _identifiers((r["relation_id"] for r in package["entity_relation"]), "DISPLAY_REL_")
    participation_ids = _identifiers((r["participation_id"] for r in package["participation"]), "DISPLAY_PART_")
    used_participation_ids = set(participation_ids.values())
    graph = package["graph"]
    output = {
        "schema_version": "subject-graph-1.0",
        "graph_id": _identifiers([graph["graph_id"]], "DISPLAY_GRAPH_")[graph["graph_id"]],
        "subject_id": entity_ids[graph["subject_entity_id"]],
        "subject_type": graph["subject_type"],
        "coverage_start": graph.get("coverage_start"),
        "coverage_end": graph.get("coverage_end"),
        "title": field(graph, graph["title"], "/title"),
        "descriptions": text_list(graph, "descriptions"),
        "entities": [], "events": [], "relations": [],
    }
    for row in _ordered(package["entity"]):
        attrs = row.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {"source_attributes": attrs}
        output["entities"].append({
            "entity_id": entity_ids[row["entity_id"]], "name": field(row, row["name"], "/name"),
            "entity_type": row["entity_type"],
            "aliases": [a["alias"] for a in _ordered(package["entity_alias"])
                        if a["entity_id"] == row["entity_id"]],
            "attributes": {key: field(row, value, "/attributes/" + _pointer(key))
                           for key, value in attrs.items()},
        })

    action_activity = {r["action_id"]: r["activity_id"] for r in package["activity"]
                       if r.get("action_id") is not None}
    details = defaultdict(list)
    for row in package["activity_detail"]:
        details[row["activity_id"]].append(row)
    for row in _ordered(package["occurrence"]):
        oid = row["occurrence_id"]
        participants = [p["entity_id"] for p in package["occurrence_participant"]
                        if p["occurrence_id"] == oid]
        if not participants:
            raise ValueError(f"Cannot project occurrence {oid}: no recorded participant")
        event = {
            "event_id": occurrence_ids[oid], "title": field(row, row["title"], "/title"),
            "start_time": time_field(row, "start_time", "start_time_id"),
            "end_time": time_field(row, "end_time", "end_time_id"),
            "subject_relevance": field(row, row["subject_relevance"], "/subject_relevance"),
            "descriptions": text_list(row, "descriptions"),
            "participations": [], "actions": [], "transactions": [],
        }
        for part in _ordered(package["participation"]):
            if part["occurrence_id"] == oid:
                event["participations"].append({
                    "participation_id": participation_ids[part["participation_id"]],
                    "entity_id": entity_ids[part["entity_id"]],
                    "role": field(part, part["role"], "/role"),
                    "start_time": time_field(part, "start_time", "start_time_id"),
                    "end_time": time_field(part, "end_time", "end_time_id"),
                })
        represented = {part["entity_id"] for part in event["participations"]}
        for eid in participants:
            if entity_ids[eid] in represented:
                continue
            key = json.dumps([oid, eid], ensure_ascii=False)
            pid = "DISPLAY_PART_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
            while pid in used_participation_ids:
                pid += "_"
            used_participation_ids.add(pid)
            event["participations"].append({
                "participation_id": pid, "entity_id": entity_ids[eid],
                "role": {"value": "unknown", "evidence_source_contents": [],
                         "reasons": ["Only occurrence membership is recorded; no role was supplied."]},
                "start_time": field({}, "unknown", "/start_time"),
                "end_time": field({}, "unknown", "/end_time"),
            })
        for action in _ordered(package["action"]):
            if action["occurrence_id"] != oid:
                continue
            event["actions"].append({
                "action_id": action_ids[action["action_id"]], "actor_id": entity_ids[action["actor_id"]],
                "action_type": field(action, action["action_type"], "/action_type"),
                "timestamp": time_field(action, "timestamp", "timestamp_time_id"),
                "details": [field(d, d["value"], "/value") for d in
                            sorted(details[action_activity.get(action["action_id"])],
                                   key=lambda d: d["detail_index"])],
            })
        for tx in _ordered(package["financial_transaction"]):
            if tx["occurrence_id"] != oid:
                continue
            transaction = {
                "transaction_id": transaction_ids[tx["transaction_id"]],
                "name": field(tx, tx["name"], "/name"),
                "timestamp": time_field(tx, "timestamp", "timestamp_time_id"),
                "details": text_list(tx, "details"),
                "instruments": [field(i, i["description"], "/description") for i in
                                sorted(package["transaction_instrument"], key=lambda i: i["ordinal"])
                                if i["transaction_id"] == tx["transaction_id"]],
            }
            for side in ("from_entity_id", "to_entity_id"):
                transaction[side] = field(tx, entity_ids.get(tx.get(side), "unknown"), "/" + side)
            event["transactions"].append(transaction)
        output["events"].append(event)
    for row in _ordered(package["entity_relation"]):
        output["relations"].append({
            "relation_id": relation_ids[row["relation_id"]],
            "from_entity_id": entity_ids[row["from_entity_id"]],
            "to_entity_id": entity_ids[row["to_entity_id"]],
            "relation_type": field(row, row["relation_type"], "/relation_type"),
            "valid_from": time_field(row, "valid_from", "valid_from_time_id"),
            "valid_to": time_field(row, "valid_to", "valid_to_time_id"),
            "event_ids": [occurrence_ids[r["occurrence_id"]] for r in _ordered(package["relation_occurrence"])
                          if r["relation_id"] == row["relation_id"]],
        })
    # v3 may retain dated context outside the requested period, while the old
    # validator forbids every out-of-coverage event. Its display envelope must
    # therefore be unbounded for display; the requested scope stays in the v3
    # graph and is also stated explicitly in display metadata below.
    original_scope = (output["coverage_start"], output["coverage_end"])
    if any(outside_coverage(event, *original_scope) for event in output["events"]):
        output["coverage_start"] = output["coverage_end"] = None
        output["descriptions"].append({
            "value": ("Legacy display includes retained background outside the requested period "
                      f"{original_scope[0]} to {original_scope[1]}. "
                      "The canonical Person EPG retains the original requested scope."),
            "evidence_source_contents": [],
            "reasons": ["Display metadata; coverage is null in this projection so dated background remains visible."],
        })
    report = validate_subject_graph(output, allow_unverified_evidence=True)
    if not report["valid"]:
        error = report["errors"][0]
        raise ValueError(f"Person EPG cannot be represented in the legacy view at {error['path']}: {error['message']}")
    return output
