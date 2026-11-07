"""One additive coverage review of existing evidence; never performs a search."""
import copy
import logging
import re

from finmy.subject_graph.evidence import restore_source_quotes
from finmy.subject_graph.event_sources import _quotes, restrict_event_evidence, select_event_sources
from finmy.subject_graph.validation import date_interval, validate_subject_graph


def _value(field):
    return field.get("value") if isinstance(field, dict) else field


def _key(value):
    return " ".join(str(_value(value)).casefold().split())


def _append_unique(destination, records):
    if not isinstance(records, list):
        raise ValueError("Supplemented fields must be lists")
    for record in records:
        if record not in destination:
            destination.append(copy.deepcopy(record))


def _check_review_flags(value):
    if isinstance(value, dict):
        if "evidence_status" in value:
            raise ValueError("Review flags cannot bypass evidence checks for additions")
        for child in value.values():
            _check_review_flags(child)
    elif isinstance(value, list):
        for child in value:
            _check_review_flags(child)


def _statement_quotes(action):
    label = str(_value(action.get("action_type", "")))
    if not re.search(r"\b(said|says|stated|reported|disclosed|explained|discussed|commented|"
                     r"acknowledged|clarified|announced|described|expressed|corrected)\b|"
                     r"表示|披露|解释|讨论|发言|指出|澄清|宣布", label, re.I):
        return []
    details = action.get("details", [])
    fields = [action.get("action_type"), *(details if isinstance(details, list) else [])]
    quotes = []
    for field in fields:
        if not isinstance(field, dict) or field.get("evidence_status") == "needs_review":
            continue
        for quote in _quotes(field):
            key = re.sub(r"\s+", "", quote).strip("。.!！?？\"“”")
            if len(key) >= 18:
                quotes.append(key)
    return quotes


def repeated_statement(action, graph):
    """Flag same-speaker/day statements sharing a specific evidence passage.

    Similar topics or titles alone are insufficient. Coarse/unknown dates and
    actual purchases versus later explanations are not merged by this check.
    A flag means route details to the existing occurrence or retain for review.
    """
    if not isinstance(action, dict):
        return None
    when = date_interval(action.get("timestamp"))
    anchors = _statement_quotes(action)
    if not when or when[2] not in ("day", "datetime") or not anchors:
        return None
    for event in graph["events"]:
        for other in event["actions"]:
            if other.get("actor_id") != action.get("actor_id") or date_interval(other.get("timestamp")) != when:
                continue
            if any(a in b or b in a for a in anchors for b in _statement_quotes(other)):
                return {"event_id": event["event_id"], "action_id": other["action_id"]}
    return None


def find_statement_duplicates(graph):
    seen, duplicates = {"events": []}, []
    for event in graph["events"]:
        row = {"event_id": event["event_id"], "actions": []}
        seen["events"].append(row)
        for action in event["actions"]:
            match = repeated_statement(action, seen)
            if match:
                duplicates.append({"event_id": event["event_id"], "action_id": action["action_id"],
                                   "possible_duplicate_of": match})
            row["actions"].append(action)
    return duplicates


def validate_review(graph, allocation, sources):
    """Use the same graph, date and assigned-evidence checks for every review edit."""
    report = validate_subject_graph(graph, source_texts=[s["content"] for s in sources],
                                    allow_unverified_evidence=True)
    if not report["valid"]:
        raise ValueError("; ".join(f"{e['path']}: {e['message']}" for e in report["errors"][:3]))
    checked, conflicts = restrict_event_evidence(
        graph, {e["event_id"]: e for e in graph["events"]}, allocation, sources)
    if conflicts or checked != graph:
        raise ValueError("Review edit conflicts with event evidence or dates")


def apply_statement_merges(graph, proposals, event_sources, sources):
    """Apply explicit duplicate-speech decisions from the existing global review.

    A shared quote is only a candidate. The reviewer must identify the surviving
    occurrence; its date, actor and source evidence are checked before any removal.
    Events and transactions are preserved.
    """
    if not isinstance(proposals, list) or len(proposals) > 12:
        raise ValueError("statement_merges must contain at most 12 objects")
    result, allocation = copy.deepcopy(graph), dict(event_sources)
    report = {"accepted": [], "rejected": []}
    for item in proposals:
        try:
            required = {"keep_event_id", "keep_action_id", "remove_event_id", "remove_action_id", "reason"}
            if (not isinstance(item, dict) or set(item) != required
                    or any(not isinstance(v, str) or not v.strip() for v in item.values())):
                raise ValueError("Statement merge requires both event/action IDs and a reason")
            candidate, selected = copy.deepcopy(result), dict(allocation)
            events = {e["event_id"]: e for e in candidate["events"]}
            keep, remove = events[item["keep_event_id"]], events[item["remove_event_id"]]
            kept = next(a for a in keep["actions"] if a["action_id"] == item["keep_action_id"])
            removed = next(a for a in remove["actions"] if a["action_id"] == item["remove_action_id"])
            if kept is removed:
                raise ValueError("Statement merge must identify two different actions")
            if not repeated_statement(removed, {"events": [{"event_id": keep["event_id"], "actions": [kept]}]}):
                raise ValueError("Statements need the same speaker, precise date and shared identifying evidence")
            when = date_interval(kept["timestamp"])
            start, end = date_interval(keep["start_time"]), date_interval(keep["end_time"])
            if (not start or start != end or start[2] != "day"
                    or not start[0] <= when[0] <= when[1] <= end[1]):
                raise ValueError("Surviving event must identify the statement's actual day")
            details = list(removed["details"])
            if _key(kept["action_type"]) != _key(removed["action_type"]):
                details.append(removed["action_type"])
            _check_review_flags(details)
            _append_unique(kept["details"], details)
            remove["actions"].remove(removed)
            selected[keep["event_id"]] = list({s["source_id"]: s for s in
                [*selected.get(keep["event_id"], []), *selected.get(remove["event_id"], [])]}.values())
            validate_review(candidate, selected, sources)
            result, allocation = candidate, selected
            report["accepted"].append({**copy.deepcopy(item), "removed_record": copy.deepcopy(removed)})
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            report["rejected"].append({"record": copy.deepcopy(item),
                                       "reason": str(exc) or "Statement merge target does not exist"})
    return result, allocation, report


def apply_coverage_additions(graph, proposal, event_sources, sources, max_events, excluded_records=()):
    """Validate each event's additions atomically; preserve all existing records.

    Failed additions remain in the review trace. They cannot trigger search, a
    repair loop, or changes to old facts/dates. New events use explicit source IDs.
    """
    if (not isinstance(proposal, dict)
            or set(proposal) != {"event_additions", "missing_events"}
            or not all(isinstance(proposal[k], list) for k in proposal)):
        raise ValueError("Expected event_additions and missing_events lists")
    groups = [(False, item) for item in proposal["event_additions"]]
    groups += [(True, item) for item in proposal["missing_events"]]
    if len(groups) > 12:
        raise ValueError("Coverage review exceeded 12 event groups")
    result, allocation = copy.deepcopy(graph), dict(event_sources)
    review = {"status": "no_additions", "accepted": [], "rejected": [], "quote_restoration": []}
    for is_new, item in groups:
        raw_item = copy.deepcopy(item)
        try:
            if not isinstance(item, dict):
                raise ValueError("An event supplement must be an object")
            # Check exact superseded claims even when a proposed action gets a new ID.
            def reintroduces(value, old):
                if isinstance(value, dict):
                    ignore = {"action_id", "transaction_id"}
                    if {k: v for k, v in value.items() if k not in ignore} == {
                            k: v for k, v in old.items() if k not in ignore}:
                        return True
                    return any(reintroduces(v, old) for v in value.values())
                return isinstance(value, list) and any(reintroduces(v, old) for v in value)
            _check_review_flags(item)
            allowed_sources = (select_event_sources({}, sources, item.get("source_ids", []))
                               if is_new else allocation.get(item.get("event_id"), []))
            item, changes = restore_source_quotes(item, [s["content"] for s in allowed_sources])
            if any((is_new or row["event_id"] == item.get("event_id"))
                   and reintroduces(item, row["record"]) for row in excluded_records):
                raise ValueError("Supplement reintroduces a claim corrected during event review")
            if changes:
                review["quote_restoration"].append({"event_id": item.get("event", item).get("event_id"),
                                                    "source_ids": [s["source_id"] for s in allowed_sources],
                                                    "changes": changes})
            candidate = copy.deepcopy(result)
            selected = dict(allocation)
            if is_new:
                if set(item) != {"event", "source_ids"} or not isinstance(item["event"], dict):
                    raise ValueError("A missing event requires event and source_ids")
                event = copy.deepcopy(item["event"])
                eid = event.get("event_id")
                source_ids = item["source_ids"]
                if (not isinstance(source_ids, list) or not source_ids
                        or any(not isinstance(s, str) or s not in {v['source_id'] for v in sources}
                               for s in source_ids)):
                    raise ValueError("Missing event has invalid source IDs")
                if len(candidate["events"]) >= max_events:
                    raise ValueError("Event limit reached")
                if any(e["event_id"] == eid or
                       (_key(e["title"]), _key(e["start_time"])) ==
                       (_key(event.get("title")), _key(event.get("start_time")))
                       for e in candidate["events"]):
                    raise ValueError("Event already exists")
                for action in event.get("actions", []):
                    match = repeated_statement(action, result)
                    if match:
                        raise ValueError(f"Possible repeated statement: {match['event_id']}/{match['action_id']}; supplement that occurrence instead")
                candidate["events"].append(event)
                selected[eid] = select_event_sources(event, sources, source_ids)
            else:
                allowed = {"event_id", "descriptions", "participations", "actions",
                           "transactions", "action_details"}
                if not set(item) <= allowed:
                    raise ValueError("Only additive event fields are allowed")
                eid = item.get("event_id")
                event = next((e for e in candidate["events"] if e["event_id"] == eid), None)
                if event is None:
                    raise ValueError("Unknown target event")
                for key in ("descriptions", "participations", "actions", "transactions"):
                    rows = item.get(key, [])
                    if key == "actions" and isinstance(rows, list):
                        for action in rows:
                            match = repeated_statement(action, result) if isinstance(action, dict) else None
                            if match:
                                raise ValueError(f"Possible repeated statement: {match['event_id']}/{match['action_id']}; append action_details instead")
                            if isinstance(action, dict) and any(
                                (a.get("actor_id"), _key(a.get("action_type")), _key(a.get("timestamp"))) ==
                                (action.get("actor_id"), _key(action.get("action_type")), _key(action.get("timestamp")))
                                for a in event["actions"]):
                                raise ValueError("Action already exists; append its details instead")
                    _append_unique(event[key], rows)
                details = item.get("action_details", [])
                if not isinstance(details, list):
                    raise ValueError("action_details must be a list")
                for entry in details:
                    if not isinstance(entry, dict) or set(entry) != {"action_id", "details"}:
                        raise ValueError("Invalid action detail supplement")
                    action = next((a for a in event["actions"] if a["action_id"] == entry["action_id"]), None)
                    if action is None:
                        raise ValueError("Unknown action for detail supplement")
                    _append_unique(action["details"], entry["details"])
            if not isinstance(eid, str) or not eid.strip():
                raise ValueError("Missing event ID")
            quotes = list(_quotes(item))
            if not quotes or any(not any(q in s["content"] for s in selected.get(eid, [])) for q in quotes):
                raise ValueError("Supplement evidence is absent from this event's assigned sources")
            validate_review(candidate, selected, sources)
            if candidate == result:
                raise ValueError("No new content")
            result, allocation = candidate, selected
            review["accepted"].append({"event_id": eid, "new_event": is_new})
        except (ValueError, KeyError, TypeError) as exc:
            review["rejected"].append({"record": raw_item, "reason": str(exc)})
    review["status"] = "supplemented" if review["accepted"] else "candidates_rejected" if groups else "no_additions"
    logging.info("Coverage review: %s event supplement(s) accepted; %s rejected. No search performed.",
                 len(review["accepted"]), len(review["rejected"]))
    return result, allocation, review
