"""Repair saved Person time rows using the shared temporal policy, without search."""
import copy
from collections import Counter, defaultdict

from finmy.subject_graph.temporal_policy import normalize_time_field
from .adapter import TIME_FIELDS
from .validation import validate_person_epg


def normalize_person_times(package):
    """Return a repaired copy and audit; preserve IDs, facts, evidence and organization."""
    result = copy.deepcopy(package)
    sets = {s["evidence_set_id"]: s for s in result["evidence_set"]}
    spans = {s["span_id"]: s for s in result["evidence_span"]}
    quotes = defaultdict(list)
    for link in result["evidence_link"]:
        quotes[link["evidence_set_id"], link["field_path"]].append(spans[link["span_id"]]["quote"])
    references = defaultdict(list)
    for rows in result.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            for field, column in TIME_FIELDS.items():
                if row.get(column) and row.get("evidence_set_id") in sets:
                    references[row[column]].append((row["evidence_set_id"], "/" + field))
    changes, counts = [], Counter()
    for time in result["time_value"]:
        before = copy.deepcopy(time)
        field = {"value": time["value"], "evidence_source_contents": [], "reasons": []}
        for sid, path in references[time["time_id"]]:
            meta = (sets[sid].get("field_metadata") or {}).get(path, {})
            field["evidence_source_contents"].extend(quotes[sid, path])
            field["reasons"].extend(meta.get("reasons", []))
        if time.get("window_start") is not None:
            field["time_window"] = {"start": time.get("window_start"), "end": time.get("window_end"),
                "original": time.get("original_text"), "approximate": time.get("is_approximate")}
        normalized = normalize_time_field(field)
        time["value"] = normalized["value"]
        window = normalized.get("time_window")
        if window:
            time.update(window_start=window["start"], window_end=window["end"],
                original_text=window["original"], is_approximate=window["approximate"])
            if not before.get("window_start"):
                time["window_semantics"] = "uncertainty"
        else:
            for key in ("window_start", "window_end", "original_text", "is_approximate", "window_semantics"):
                time.pop(key, None)
        if time == before:
            counts["unchanged"] += 1
            continue
        audit = normalized.get("time_normalization", {"status": "normalized", "original": before["value"],
            "rule": "Canonical scalar formatting under temporal_policy.py."})
        counts[audit["status"]] += 1
        changes.append({"time_id": time["time_id"], "before": before, "after": copy.deepcopy(time), **audit})
        for sid, path in references[time["time_id"]]:
            if sets[sid].get("field_metadata") is None:
                sets[sid]["field_metadata"] = {}
            meta = sets[sid]["field_metadata"].setdefault(path, {})
            meta["time_normalization"] = copy.deepcopy(audit)
            reasons = meta.setdefault("reasons", [])
            for reason in normalized.get("reasons", []):
                if reason not in reasons:
                    reasons.append(reason)
    check = validate_person_epg(result, require_normalized_times=True)
    if not check["valid"]:
        raise ValueError("Invalid repaired Person EPG: " + str(check["errors"][:2]))
    return result, {"policy": "finmy/subject_graph/temporal_policy.py", "model_calls": 0,
                    "counts": dict(counts), "changes": changes}
