"""Evidence-located, append-only additions to one existing person event.

The model proposes claims, never interchange rows or globally allocated IDs.
This module validates structure and verbatim quote locations, not entailment;
callers must review relevance, duplicate meaning and conflicts before merging.
An invalid proposal is rejected atomically. Existing rows are never rewritten.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal

from jsonschema import Draft202012Validator
from finmy.person_epg.validation import validate_person_epg


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _array(items, maximum=100):
    return {"type": "array", "items": items, "maxItems": maximum}


_TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
_KEY = {"type": "string", "minLength": 1, "maxLength": 128}
_NULLABLE_KEY = {"anyOf": [_KEY, {"type": "null"}]}
_NULLABLE_TEXT = {"anyOf": [_TEXT, {"type": "null"}]}
_CITATIONS = {**_array(_object({"document_id": _KEY, "quote": _TEXT}), 12), "minItems": 1}
_DETAIL = _object({"value": _TEXT, "citations": _CITATIONS})
_RELATIONS = ["precedes", "overlaps", "executed_by", "explains", "responds_to", "context_for"]
ADDITIONS_SCHEMA = _object({
    "entities": _array(_object({"key": _KEY, "name": _TEXT,
        "entity_type": {"type": "string", "minLength": 1, "maxLength": 64}, "citations": _CITATIONS}), 40),
    "stages": _array(_object({"key": _KEY, "label": _TEXT,
        "summary": _NULLABLE_TEXT, "boundary_reason": _NULLABLE_TEXT, "citations": _CITATIONS}), 20),
    "activities": _array(_object({"key": _KEY, "kind": {"enum": ["action", "transaction", "context"]},
        "title": _TEXT, "actor_id": _NULLABLE_KEY, "from_entity_id": _NULLABLE_KEY,
        "to_entity_id": _NULLABLE_KEY, "time": _NULLABLE_KEY, "stage_id": _NULLABLE_KEY,
        "details": _array(_DETAIL, 30), "citations": _CITATIONS}), 80),
    "details": _array(_object({"activity_id": _KEY, "value": _TEXT, "citations": _CITATIONS}), 100),
    "relations": _array(_object({"from_activity_id": _KEY, "to_activity_id": _KEY,
        "relation_type": {"enum": _RELATIONS}, "description": _NULLABLE_TEXT,
        "citations": _CITATIONS}), 100),
})


def empty_additions():
    return {key: [] for key in ADDITIONS_SCHEMA["properties"]}


def _normal(value):
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()[:24]


def _numbers(value):
    # Compare explicit magnitudes as well as digits (million != billion).
    scales = {"thousand": 1000, "million": 1000000, "billion": 1000000000,
              "万": 10000, "亿": 100000000, "bn": 1000000000}
    values = []
    for match in re.finditer(r"(\d+(?:[.,]\d+)*)\s*(thousand\b|million\b|billion\b|bn\b|万|亿)?", value, re.I):
        try:
            number = Decimal(match.group(1).replace(",", ""))
            number *= scales.get((match.group(2) or "").lower(), 1)
            values.append(str(number.normalize()))
        except Exception:
            values.append(match.group(0))
    return tuple(sorted(set(values)))


def _source_time(value, rows):
    """Normalize only an explicit, quoted absolute date, retaining precision."""
    if value is None:
        return None
    if not any(value in row["quote"] for row in rows):
        raise ValueError("Activity time must occur verbatim in its cited passage")
    raw = value.strip()
    normalized = re.sub(r"年|月", "-", raw).removesuffix("日").rstrip("-")
    if re.fullmatch(r"\d{4}(?:-\d{1,2}){0,2}", normalized):
        parts = [int(part) for part in normalized.split("-")]
        date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        return f"{parts[0]:04d}" + (f"-{parts[1]:02d}" if len(parts) > 1 else "") + (f"-{parts[2]:02d}" if len(parts) > 2 else "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", raw):
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return raw
    months = {name: index for index, name in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
    months.update({name[:3]: index for name, index in list(months.items())})
    cleaned = raw.casefold().replace(",", "").replace(".", "")
    forward = re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", cleaned)
    backward = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})", cleaned)
    partial = re.fullmatch(r"([a-z]+)\s+(\d{4})", cleaned)
    if forward and forward[1] in months:
        return date(int(forward[3]), months[forward[1]], int(forward[2])).isoformat()
    if backward and backward[2] in months:
        return date(int(backward[3]), months[backward[2]], int(backward[1])).isoformat()
    if partial and partial[1] in months:
        date(int(partial[2]), months[partial[1]], 1)
        return f"{int(partial[2]):04d}-{months[partial[1]]:02d}"
    raise ValueError("Unsupported or relative date; leave the activity time null")


def merge_event_additions(package, event_id, proposal, sources):
    """Return ``(package, report)``; every pre-existing row remains identical.

    Local entity/stage/activity keys resolve only within this proposal. Existing
    entity IDs can be used as actors; existing stage/activity IDs must belong to
    the target event. Citations refer to caller-owned source IDs and exact text.
    A successful location check does not constitute semantic verification.
    """
    original = copy.deepcopy(package)
    report = {"event_id": event_id, "status": "rejected", "added": {},
              "skipped_duplicates": 0, "semantic_improvement_verified": False}
    try:
        initial_check = validate_person_epg(original)
        if not initial_check["valid"]:
            raise ValueError("Initial person EPG is invalid")
        if event_id not in {row["event_id"] for row in original["event"]}:
            raise ValueError("Unknown target event")
        errors = list(Draft202012Validator(ADDITIONS_SCHEMA).iter_errors(proposal))
        if errors:
            raise ValueError("Invalid addition schema: " + errors[0].message[:300])
        result = copy.deepcopy(original)
        source_map = {row["document_id"]: row for row in original["source_document"]}
        supplied = {}
        for source in sources:
            if (not isinstance(source, dict) or not isinstance(source.get("document_id"), str)
                    or not source["document_id"] or len(source["document_id"]) > 128
                    or not isinstance(source.get("content"), str)):
                raise ValueError("Invalid source document")
            sid = source["document_id"]
            existing = supplied.get(sid, source_map.get(sid))
            if existing is not None and existing["content"] != source["content"]:
                raise ValueError("Source document ID collision")
            supplied[sid] = source
        source_map.update(supplied)
        used_source_ids = set()
        entities = {row["entity_id"]: row for row in result["entity"]}
        target_members = {row["activity_id"]: row for row in result["event_activity"]
                          if row["event_id"] == event_id}
        target_stages = {row["stage_id"]: row for row in result["stage"] if row["event_id"] == event_id}
        local_entities, local_stages, local_activities = {}, {}, {}
        reserved = set()
        for table in ("entity", "stage", "activity"):
            reserved.update(row[table + "_id"] for row in result[table])
        for table in ("entities", "stages", "activities"):
            for row in proposal[table]:
                if row["key"] in reserved:
                    raise ValueError("Local keys must be unique and must not shadow existing IDs")
                reserved.add(row["key"])
        existing_ids = {row[key] for rows in result.values() if isinstance(rows, list)
                        for row in rows if isinstance(row, dict) for key in row
                        if key.endswith("_id") and isinstance(row[key], str)}

        def new_id(kind, value):
            candidate = "EF_" + kind + "_" + _digest([event_id, value])
            # Normal deduplication happens before allocating IDs. A collision is
            # never permission to overwrite an existing fact.
            if candidate in existing_ids:
                index = 1
                while candidate + "_" + str(index) in existing_ids:
                    index += 1
                candidate += "_" + str(index)
            existing_ids.add(candidate)
            return candidate

        def order(table):
            return max((row.get("sort_order", -1) for row in result[table]), default=-1) + 1

        spans_by_location = {(row.get("document_id"), row.get("char_start"), row.get("char_end")): row["span_id"]
                             for row in result["evidence_span"] if row.get("document_id") is not None}

        def citations(rows):
            located = []
            for citation in rows:
                sid, quote = citation["document_id"], citation["quote"]
                if not quote.strip() or sid not in source_map:
                    raise ValueError("Unknown citation source or empty quote")
                text = source_map[sid]["content"]
                start = text.find(quote)
                if start < 0:
                    raise ValueError("Citation quote is not verbatim source text")
                located.append((sid, start, start + len(quote), quote))
            return list(dict.fromkeys(located))

        # Validate every supplied citation, including rows later deduplicated.
        for rows in proposal.values():
            for row in rows:
                citations(row["citations"])
                for detail in row.get("details", []):
                    citations(detail["citations"])

        def evidence(rows, paths):
            located = citations(rows)
            set_id = new_id("ES", [located, paths, len(result["evidence_set"])])
            result["evidence_set"].append({"evidence_set_id": set_id})
            for i, (sid, start, end, quote) in enumerate(located):
                used_source_ids.add(sid)
                location = sid, start, end
                span_id = spans_by_location.get(location)
                if span_id is None:
                    span_id = new_id("SPAN", location)
                    result["evidence_span"].append({"span_id": span_id, "document_id": sid,
                        "char_start": start, "char_end": end, "quote": quote})
                    spans_by_location[location] = span_id
                for path in dict.fromkeys(paths):
                    result["evidence_link"].append({"evidence_set_id": set_id,
                        "field_path": path, "quote_order": i, "span_id": span_id})
            return set_id

        for row in proposal["entities"]:
            same = next((entity for entity in entities.values()
                         if _normal(entity["name"]) == _normal(row["name"])
                         and _normal(entity["entity_type"]) == _normal(row["entity_type"])), None)
            if same:
                local_entities[row["key"]] = same["entity_id"]
                report["skipped_duplicates"] += 1
                continue
            eid = new_id("ENTITY", row["key"])
            entity = {"entity_id": eid, "name": row["name"], "entity_type": row["entity_type"],
                "sort_order": order("entity"), "evidence_set_id": evidence(row["citations"], ["/name", "/entity_type"])}
            result["entity"].append(entity)
            entities[eid] = entity
            local_entities[row["key"]] = eid

        def entity_id(value, required=False):
            value = local_entities.get(value, value)
            if value is None and not required:
                return None
            if value not in entities:
                raise ValueError("Unknown activity entity reference")
            return value

        for row in proposal["stages"]:
            same = next((stage for stage in target_stages.values()
                         if _normal(stage["label"]) == _normal(row["label"])), None)
            if same:
                local_stages[row["key"]] = same["stage_id"]
                report["skipped_duplicates"] += 1
                continue
            sid = new_id("STAGE", row["key"])
            stage = {"event_id": event_id, "stage_id": sid, "label": row["label"],
                "summary": row["summary"], "boundary_reason": row["boundary_reason"],
                "sort_order": max((s.get("sort_order", -1) for s in target_stages.values()), default=-1) + 1,
                "evidence_set_id": evidence(row["citations"], ["/label", "/summary", "/boundary_reason"])}
            result["stage"].append(stage)
            target_stages[sid] = stage
            local_stages[row["key"]] = sid

        def stage_id(value):
            value = local_stages.get(value, value)
            if value is not None and value not in target_stages:
                raise ValueError("Stage must belong to the target event")
            return value

        actions = {row["action_id"]: row for row in result["action"]}
        transactions = {row["transaction_id"]: row for row in result["financial_transaction"]}
        occurrences = {row["occurrence_id"]: row for row in result["occurrence"]}
        times = {row["time_id"]: row["value"] for row in result["time_value"]}
        span_map = {row["span_id"]: row for row in result["evidence_span"]}
        existing_citations = {}
        for link in result["evidence_link"]:
            span = span_map.get(link["span_id"], {})
            if span.get("document_id") is not None:
                existing_citations.setdefault(link["evidence_set_id"], set()).add(
                    (span["document_id"], span["quote"]))
        fingerprints = {}
        transaction_quotes = {}
        for activity in result["activity"]:
            if activity.get("action_id"):
                fact = actions[activity["action_id"]]
                signature = ("action", _normal(fact["action_type"]), fact["actor_id"], None,
                             _normal(times.get(fact.get("timestamp_time_id"))))
            elif activity.get("transaction_id"):
                fact = transactions[activity["transaction_id"]]
                signature = ("transaction", _normal(fact["name"]), fact.get("from_entity_id"), fact.get("to_entity_id"),
                             _normal(times.get(fact.get("timestamp_time_id"))))
                quote_key = (tuple(sorted(existing_citations.get(fact.get("evidence_set_id"), set()))),
                             signature[1], signature[2], signature[3], signature[4])
                if quote_key[0]:
                    transaction_quotes[quote_key] = (activity["activity_id"], _numbers(json.dumps(fact.get("details", []))))
            else:
                fact = occurrences[activity["context_occurrence_id"]]
                signature = ("context", _normal(fact["title"]), None, None,
                             _normal(times.get(fact.get("start_time_id"))))
            fingerprints[signature] = activity["activity_id"]

        def add_detail(activity_id, value, rows):
            existing = [row for row in result["activity_detail"] if row["activity_id"] == activity_id]
            if any(_normal(row["value"]) == _normal(value) for row in existing):
                report["skipped_duplicates"] += 1
                return
            index = max((row["detail_index"] for row in existing), default=-1) + 1
            result["activity_detail"].append({"activity_id": activity_id, "detail_index": index,
                "value": value, "evidence_set_id": evidence(rows, ["/value"])})
            if target_members[activity_id]["detail_mode"] == "selected":
                result["event_activity_detail"].append({"event_id": event_id,
                    "activity_id": activity_id, "detail_index": index})

        for row in proposal["activities"]:
            kind = row["kind"]
            normalized_time = _source_time(row["time"], row["citations"])
            actor = entity_id(row["actor_id"], required=kind == "action")
            sender = entity_id(row["from_entity_id"])
            recipient = entity_id(row["to_entity_id"])
            if (kind != "transaction" and (sender is not None or recipient is not None)) or (kind == "transaction" and actor is not None):
                raise ValueError("Activity fields mix incompatible fact kinds")
            sid = stage_id(row["stage_id"])
            signature = (kind, _normal(row["title"]), actor if kind == "action" else sender if kind == "transaction" else None,
                         recipient if kind == "transaction" else None, _normal(normalized_time))
            same = fingerprints.get(signature)
            quote_key = (tuple(sorted((c["document_id"], c["quote"]) for c in row["citations"])),
                         _normal(row["title"]), sender, recipient, _normal(normalized_time))
            numeric = _numbers(json.dumps([d["value"] for d in row["details"]], ensure_ascii=False))
            if kind == "transaction" and quote_key in transaction_quotes:
                previous_id, previous_numeric = transaction_quotes[quote_key]
                if numeric != previous_numeric:
                    raise ValueError("Conflicting numeric transaction claims reuse the same source quote")
                same = previous_id
            if same:
                if same not in target_members:
                    member = {"event_id": event_id, "activity_id": same, "stage_id": sid,
                        "display_title": row["title"], "detail_mode": "all",
                        "sort_order": max((m["sort_order"] for m in target_members.values()), default=-1) + 1}
                    result["event_activity"].append(member)
                    target_members[same] = member
                local_activities[row["key"]] = same
                report["skipped_duplicates"] += 1
                for detail in row["details"]:
                    add_detail(same, detail["value"], detail["citations"])
                continue
            aid = new_id("ACTIVITY", row["key"])
            oid = new_id("OCC", row["key"])
            tid = None
            if normalized_time is not None:
                tid = new_id("TIME", [row["key"], normalized_time])
                result["time_value"].append({"time_id": tid, "value": normalized_time})
            evidence_id = evidence(row["citations"], ["/title", "/subject_relevance", "/start_time", "/end_time",
                "/action_type" if kind == "action" else "/name", "/timestamp"])
            occurrence = {"occurrence_id": oid, "title": row["title"], "subject_relevance": "event_context" if kind == "context" else "documented_activity",
                "start_time_id": tid, "end_time_id": tid, "descriptions": [],
                "evidence_set_id": evidence_id, "sort_order": order("occurrence")}
            result["occurrence"].append(occurrence)
            participants = {x for x in (actor, sender, recipient) if x is not None}
            result["occurrence_participant"].extend({"occurrence_id": oid, "entity_id": eid} for eid in sorted(participants))
            activity = {"activity_id": aid, "action_id": None, "transaction_id": None, "context_occurrence_id": None}
            if kind == "action":
                fid = new_id("ACTION", row["key"])
                result["action"].append({"action_id": fid, "occurrence_id": oid, "actor_id": actor,
                    "action_type": row["title"], "timestamp_time_id": tid,
                    "evidence_set_id": evidence_id, "sort_order": order("action")})
                activity["action_id"] = fid
            elif kind == "transaction":
                fid = new_id("TX", row["key"])
                paths = ["/name", "/timestamp"]
                tx_evidence_id = evidence(row["citations"], paths)
                # Separate detail evidence links retain field-level provenance.
                for i, detail in enumerate(row["details"]):
                    location_rows = citations(detail["citations"])
                    for j, (doc_id, start, end, quote) in enumerate(location_rows):
                        used_source_ids.add(doc_id)
                        location = doc_id, start, end
                        span_id = spans_by_location.get(location)
                        if span_id is None:
                            span_id = new_id("SPAN", location)
                            result["evidence_span"].append({"span_id": span_id, "document_id": doc_id,
                                "char_start": start, "char_end": end, "quote": quote})
                            spans_by_location[location] = span_id
                        result["evidence_link"].append({"evidence_set_id": tx_evidence_id,
                            "field_path": "/details/" + str(i), "quote_order": j, "span_id": span_id})
                result["financial_transaction"].append({"transaction_id": fid, "occurrence_id": oid,
                    "name": row["title"], "from_entity_id": sender, "to_entity_id": recipient,
                    "timestamp_time_id": tid, "details": [d["value"] for d in row["details"]],
                    "evidence_set_id": tx_evidence_id, "sort_order": order("financial_transaction")})
                activity["transaction_id"] = fid
                transaction_quotes[quote_key] = (aid, numeric)
            else:
                activity["context_occurrence_id"] = oid
            result["activity"].append(activity)
            member = {"event_id": event_id, "activity_id": aid, "stage_id": sid,
                "display_title": row["title"], "detail_mode": "all",
                "sort_order": max((m["sort_order"] for m in target_members.values()), default=-1) + 1}
            result["event_activity"].append(member)
            target_members[aid] = member
            local_activities[row["key"]] = aid
            fingerprints[signature] = aid
            for detail in row["details"]:
                add_detail(aid, detail["value"], detail["citations"])

        def activity_id(value):
            value = local_activities.get(value, value)
            if value not in target_members:
                raise ValueError("Activity reference must belong to target event")
            return value

        for row in proposal["details"]:
            aid = activity_id(row["activity_id"])
            add_detail(aid, row["value"], row["citations"])
        relation_keys = {(r["from_activity_id"], r["to_activity_id"], r["relation_type"])
                         for r in result["activity_relation"]}
        for row in proposal["relations"]:
            source, destination = activity_id(row["from_activity_id"]), activity_id(row["to_activity_id"])
            if source == destination:
                raise ValueError("Activity relation cannot link a fact to itself")
            key = source, destination, row["relation_type"]
            if key in relation_keys:
                report["skipped_duplicates"] += 1
                continue
            result["activity_relation"].append({"link_id": new_id("LINK", key),
                "from_activity_id": source, "to_activity_id": destination,
                "relation_type": row["relation_type"], "description": row["description"], "basis": "source",
                "evidence_set_id": evidence(row["citations"], ["/description", "/relation_type"])})
            relation_keys.add(key)

        original_sources = {row["document_id"] for row in original["source_document"]}
        for sid in sorted(used_source_ids - original_sources):
            source = source_map[sid]
            timestamp = source.get("published_at")
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    timestamp = None
            except (AttributeError, ValueError):
                timestamp = None
            result["source_document"].append({"document_id": sid, "content": source["content"],
                "title": source.get("title"), "source_url": source.get("source_url"), "published_at": timestamp})
        checked = validate_person_epg(result)
        if not checked["valid"]:
            raise ValueError("Merged person EPG invalid: " + json.dumps(checked["errors"][:2], ensure_ascii=False))
        for key, value in original.items():
            if isinstance(value, list):
                if result[key][:len(value)] != value:
                    raise ValueError("An original row was modified")
            elif result[key] != value:
                raise ValueError("Original graph metadata was modified")
        report["added"] = {key: len(result[key]) - len(value) for key, value in original.items() if isinstance(value, list)}
        report["status"] = "merged" if any(report["added"].values()) else "no_changes"
        report["original_rows_preserved"] = True
        return result, report
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        report["reason"] = str(exc)[:600]
        return original, report
