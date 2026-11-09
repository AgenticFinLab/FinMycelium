"""Recompute observed event coverage from accepted activity times.

The canonical event/stage tables deliberately have no date-bound columns. Their
display envelopes are projections of their members. This report records that
projection without rewriting facts, graph coverage or inventing event duration.
Publication dates and dates mentioned inside text are never time inputs here.
"""
from __future__ import annotations

import copy

from finmy.subject_graph.validation import date_interval


def _bound(row, side, activity_id):
    if not row:
        return None
    window = row.get("window_start") is not None and row.get("window_end") is not None
    value = row.get("window_start" if side == "start" else "window_end") if window else row.get("value")
    parsed = date_interval(value)
    if parsed is None:
        return None
    endpoint = {"value": value, "precision": parsed[2], "time_id": row["time_id"],
                "activity_id": activity_id, "original_value": row.get("value"),
                "original_text": row.get("original_text"),
                "is_approximate": bool(row.get("is_approximate")) or parsed[2] in {"year", "month"}
                                  or (window and row.get("window_semantics") == "uncertainty"
                                      and row["window_start"] != row["window_end"]),
                "window_semantics": row.get("window_semantics")}
    return parsed[0 if side == "start" else 1], endpoint


def _summary(records):
    starts = [row["start"] for row in records if row["start"] is not None]
    ends = [row["end"] for row in records if row["end"] is not None]
    return {
        # Preserve source precision, including YYYY and YYYY-MM. Expanded
        # calendar bounds are used solely for comparison, never persisted.
        "start": copy.deepcopy(min(starts, key=lambda item: item[0])[1]) if starts else None,
        "end": copy.deepcopy(max(ends, key=lambda item: item[0])[1]) if ends else None,
        "dated_activity_ids": [row["activity_id"] for row in records
                               if row["start"] is not None or row["end"] is not None],
        "undated_activity_ids": [row["activity_id"] for row in records
                                 if row["start"] is None and row["end"] is None],
        "partial_activity_ids": [row["activity_id"] for row in records
                                 if (row["start"] is None) != (row["end"] is None)],
    }


def _groups(records):
    return {"observed": _summary(records),
            "primary": _summary([row for row in records if row["kind"] != "context"]),
            "context": _summary([row for row in records if row["kind"] == "context"])}


def event_time_coverage(package, event_id):
    """Describe existing event/stage coverage; never use it as an admission gate.

    ``observed`` includes all accepted members. The HTML projects these member
    times into its event envelope within the graph's configured display scope.
    ``primary`` separates actions/transactions from background ``context``. An
    accepted retrospective statement uses its own recorded occurrence time; the
    historical dates in its prose cannot silently move that statement earlier.
    """
    if event_id not in {row["event_id"] for row in package.get("event", [])}:
        raise ValueError("Unknown event for temporal coverage")
    activities = {row["activity_id"]: row for row in package.get("activity", [])}
    actions = {row["action_id"]: row for row in package.get("action", [])}
    transactions = {row["transaction_id"]: row for row in package.get("financial_transaction", [])}
    occurrences = {row["occurrence_id"]: row for row in package.get("occurrence", [])}
    times = {row["time_id"]: row for row in package.get("time_value", [])}
    records = []
    for member in package.get("event_activity", []):
        if member["event_id"] != event_id:
            continue
        activity_id = member["activity_id"]
        activity = activities[activity_id]
        if activity.get("action_id"):
            kind, fact = "action", actions[activity["action_id"]]
        elif activity.get("transaction_id"):
            kind, fact = "transaction", transactions[activity["transaction_id"]]
        else:
            kind, fact = "context", occurrences[activity["context_occurrence_id"]]
        first = fact.get("start_time_id" if kind == "context" else "timestamp_time_id")
        last = fact.get("end_time_id" if kind == "context" else "timestamp_time_id")
        start = _bound(times.get(first), "start", activity_id)
        end = _bound(times.get(last), "end", activity_id)
        # Invalid/reversed ranges are not made into coverage by reordering them.
        if start is not None and end is not None and start[0] > end[0]:
            start = end = None
        records.append({"activity_id": activity_id, "stage_id": member.get("stage_id"),
                        "kind": kind, "start": start, "end": end})
    stages = [{"stage_id": stage["stage_id"],
               **_groups([row for row in records if row["stage_id"] == stage["stage_id"]])}
              for stage in package.get("stage", []) if stage["event_id"] == event_id]
    return {"event_id": event_id, "basis": "accepted_activity_times",
            "interpretation": "Observed coverage, not event start/end or continuous duration.",
            **_groups(records), "stages": stages}


def compare_event_time_coverage(before, after, event_id):
    """Return an audit comparison after a reviewed update is accepted."""
    previous, current = event_time_coverage(before, event_id), event_time_coverage(after, event_id)

    def bounds(record):
        return [(record[group][side] or {}).get("value")
                for group in ("observed", "primary", "context") for side in ("start", "end")]

    return {"before": previous, "after": current, "range_changed": bounds(previous) != bounds(current)}
