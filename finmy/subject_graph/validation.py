"""Dependency-free shape, identity, temporal, and evidence checks.

Validation never repairs, pads dates, merges entities, or mutates model output.
Verbatim quote matching establishes provenance, not truth or entailment.
"""
import calendar
import math
import re
from datetime import datetime, timedelta, timezone

from finmy.subject_graph.schema import JSON_SCHEMA

_UNKNOWN = {"", "unknown", "unspecified", "none", "null", "n/a", "na"}
_UTC = timezone.utc


def _value(value):
    return value.get("value") if isinstance(value, dict) else value


def date_interval(value):
    """Read supported precision without replacing an unknown day with the first."""
    value = _value(value)
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"\d{4}", value):
            year = int(value)
            return (datetime(year, 1, 1, tzinfo=_UTC),
                    datetime(year, 12, 31, 23, 59, 59, 999999, tzinfo=_UTC), "year")
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month = map(int, value.split("-"))
            return (datetime(year, month, 1, tzinfo=_UTC),
                    datetime(year, month, calendar.monthrange(year, month)[1],
                             23, 59, 59, 999999, tzinfo=_UTC), "month")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            start = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=_UTC)
            return start, start + timedelta(days=1) - timedelta(microseconds=1), "day"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", value):
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            instant = instant.replace(tzinfo=_UTC) if instant.tzinfo is None else instant.astimezone(_UTC)
            return instant, instant, "datetime"
    except (ValueError, OverflowError):
        pass
    return None


def _pointer(path, key):
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _shape(value, schema, path, errors):
    if "$ref" in schema:
        schema = JSON_SCHEMA["$defs"][schema["$ref"].split("/")[-1]]
    def error(message):
        errors.append({"path": path, "message": message})
    if "const" in schema and value != schema["const"]:
        error("Expected constant " + repr(schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        error("Expected one of " + repr(schema["enum"]))
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        matches = {
            "object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "null": value is None,
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        }
        if not any(matches.get(kind, False) for kind in types):
            error("Expected type " + " or ".join(types))
            return
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append({"path": _pointer(path, key), "message": "Required field is missing"})
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _shape(item, properties[key], _pointer(path, key), errors)
            elif schema.get("additionalProperties") is False:
                errors.append({"path": _pointer(path, key), "message": "Unexpected field"})
            elif isinstance(schema.get("additionalProperties"), dict):
                _shape(item, schema["additionalProperties"], _pointer(path, key), errors)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            error("Array has too few items")
        if schema.get("uniqueItems") and any(item in value[:i] for i, item in enumerate(value)):
            error("Array items must be unique")
        for i, item in enumerate(value):
            if "items" in schema:
                _shape(item, schema["items"], _pointer(path, i), errors)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            error("String is empty")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            error("Invalid identifier")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            error("Number must be finite and within its allowed range")


def validate_subject_graph(graph, source_texts=None, allow_unverified_evidence=False):
    """Return a deterministic report; callers decide whether warnings block use."""
    errors, warnings = [], []
    _shape(graph, JSON_SCHEMA, "", errors)
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    def issue(path, message, warning=False):
        (warnings if warning else errors).append({"path": path, "message": message})

    def unique(rows, key, prefix, global_ids=None):
        found = {} if global_ids is None else global_ids
        for i, row in enumerate(rows):
            identifier = row[key]
            path = _pointer(_pointer(prefix, i), key)
            if identifier in found:
                issue(path, "Duplicate " + key + ": " + identifier)
            else:
                found[identifier] = row
        return found

    def read_date(value, path, nullable=False):
        raw = _value(value)
        if nullable and raw is None:
            return None
        if isinstance(raw, str) and raw.lower().strip() in _UNKNOWN:
            return None
        result = date_interval(value)
        if result is None:
            issue(path, "Invalid date; use supported ISO precision or unknown")
        return result

    def bounds(obj, first, last, path):
        start = read_date(obj[first], path + "/" + first)
        end = read_date(obj[last], path + "/" + last)
        if start and end and start[0] > end[1]:
            issue(path, "Start is after end")
        return start, end

    def within(start, end, outer, path, warning=False):
        low, high = outer
        if start and high and start[0] > high[1] or end and low and end[1] < low[0]:
            issue(path, "Time is wholly outside the containing interval", warning)

    entities = unique(graph["entities"], "entity_id", "/entities")
    events = unique(graph["events"], "event_id", "/events")
    unique(graph["relations"], "relation_id", "/relations")
    subject_id = graph["subject_id"]
    if subject_id not in entities:
        issue("/subject_id", "Subject does not resolve to the entity registry")
    elif entities[subject_id]["entity_type"] != graph["subject_type"]:
        issue("/subject_type", "Subject type disagrees with the subject entity")
    coverage = (read_date(graph["coverage_start"], "/coverage_start", True),
                read_date(graph["coverage_end"], "/coverage_end", True))
    if all(coverage) and coverage[0][0] > coverage[1][1]:
        issue("/coverage_end", "Coverage end is before coverage start")

    participants_by_event = {}
    global_participations, global_actions, global_transactions = {}, {}, {}
    for ei, event in enumerate(graph["events"]):
        path = f"/events/{ei}"
        if event["subject_relevance"]["value"].lower().strip() in _UNKNOWN:
            issue(path + "/subject_relevance", "Event requires an explicit connection to the subject")
        event_bounds = bounds(event, "start_time", "end_time", path)
        within(*event_bounds, coverage, path, warning=True)
        unique(event["participations"], "participation_id", path + "/participations", global_participations)
        unique(event["actions"], "action_id", path + "/actions", global_actions)
        unique(event["transactions"], "transaction_id", path + "/transactions", global_transactions)
        participants = {p["entity_id"] for p in event["participations"]}
        participants_by_event[event["event_id"]] = participants
        for pi, part in enumerate(event["participations"]):
            pp = f"{path}/participations/{pi}"
            if part["entity_id"] not in entities:
                issue(pp + "/entity_id", "Participation entity is missing from registry")
            times = bounds(part, "start_time", "end_time", pp)
            within(*times, event_bounds, pp)
        for ai, action in enumerate(event["actions"]):
            ap = f"{path}/actions/{ai}"
            if action["actor_id"] not in entities or action["actor_id"] not in participants:
                issue(ap + "/actor_id", "Action actor must participate in this event")
            instant = read_date(action["timestamp"], ap + "/timestamp")
            within(instant, instant, event_bounds, ap)
        for ti, transaction in enumerate(event["transactions"]):
            tp = f"{path}/transactions/{ti}"
            for side in ("from_entity_id", "to_entity_id"):
                party = transaction[side]["value"]
                if party != "unknown" and (party not in entities or party not in participants):
                    issue(tp + "/" + side, "Known transaction party must participate in this event; otherwise use unknown")
            instant = read_date(transaction["timestamp"], tp + "/timestamp")
            within(instant, instant, event_bounds, tp)
    for ri, relation in enumerate(graph["relations"]):
        path = f"/relations/{ri}"
        for side in ("from_entity_id", "to_entity_id"):
            if relation[side] not in entities:
                issue(path + "/" + side, "Relation endpoint is missing from registry")
        relation_bounds = bounds(relation, "valid_from", "valid_to", path)
        for i, event_id in enumerate(relation["event_ids"]):
            ep = path + f"/event_ids/{i}"
            if event_id not in events:
                issue(ep, "Relation references a missing event")
                continue
            if not {relation["from_entity_id"], relation["to_entity_id"]}.issubset(participants_by_event[event_id]):
                issue(ep, "Relation endpoints are not both recorded as participants in this referenced event; the link is contextual, not proof of joint participation", warning=True)
            event = events[event_id]
            event_times = (date_interval(event["start_time"]), date_interval(event["end_time"]))
            within(*relation_bounds, event_times, ep)

    if source_texts is not None:
        if not isinstance(source_texts, (list, tuple)) or any(not isinstance(t, str) for t in source_texts):
            issue("/", "source_texts must be a sequence of source strings")
        else:
            subject_name_paths = {f"/entities/{i}/name" for i, e in enumerate(graph["entities"])
                                  if e["entity_id"] == subject_id}
            def evidence(value, path):
                if isinstance(value, dict) and "value" in value:
                    pending = allow_unverified_evidence and value.get("evidence_status") == "needs_review"
                    quotes = value["evidence_source_contents"]
                    for qi, quote in enumerate(quotes):
                        if not quote.strip():
                            issue(path + f"/evidence_source_contents/{qi}", "Evidence quote must contain non-whitespace text", warning=pending)
                        elif not any(quote in source for source in source_texts):
                            issue(path + f"/evidence_source_contents/{qi}", "Evidence quote is absent from supplied sources", warning=pending)
                    configured = path in subject_name_paths and "configured_identity" in value["reasons"]
                    if path != "/title" and not configured and value["value"].lower().strip() not in _UNKNOWN and not quotes:
                        issue(path, "Known factual value requires a source quote", warning=pending)
                elif isinstance(value, dict):
                    for key, item in value.items():
                        evidence(item, _pointer(path, key))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        evidence(item, _pointer(path, i))
            evidence(graph, "")
    def review_notices(value, path):
        if isinstance(value, dict):
            if value.get("evidence_status") == "needs_review":
                issue(path, "Evidence needs review; this fact is not verified", warning=True)
            for key, child in value.items():
                review_notices(child, _pointer(path, key))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                review_notices(child, _pointer(path, i))
    review_notices(graph, "")
    return {"valid": not errors, "errors": errors, "warnings": warnings}
