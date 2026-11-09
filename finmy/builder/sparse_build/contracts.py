"""Versioned construction checks and lossless prompt projections."""

import calendar
import copy
from datetime import datetime, timezone
import re

from .validation import scalar


CONSTRUCTION_CONTRACT_VERSION = 2
ROLE_RESULTS = {
    "participants": "Results of ParticipantReconstructor",
    "transactions": "Results of TransactionReconstructor",
}
EPISODE_SCOPE_FIELDS = ("episode_id", "name", "index_in_stage", "start_time", "end_time")
UNKNOWN = {None, "", "unknown", "unspecified", "null", "none", "n/a"}


class TemporalScopeError(ValueError):
    """A validly parsed candidate contains facts outside its target Episode.

    Keep every conflicting item for targeted feedback and review. This report
    does not relocate, remove or rewrite any candidate fact.
    """

    def __init__(self, report):
        self.report = copy.deepcopy(report)
        first = self.report["violations"][0]
        super().__init__(
            f"Episode scope: {first['path']}.timestamp {first['timestamp']!r} is outside target bounds"
        )


def compact_values(value):
    """Project verified-field values, retaining all facts, order and identifiers."""
    if isinstance(value, dict):
        if isinstance(value.get("value"), str):
            return value["value"]
        return {key: compact_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [compact_values(item) for item in value]
    return copy.deepcopy(value)


def episode_scope(episode):
    return compact_values({key: episode[key] for key in EPISODE_SCOPE_FIELDS if key in episode})


def stage_scope(stage):
    return {**compact_values({key: stage[key] for key in
                             ("stage_id", "name", "index_in_event", "start_time", "end_time")
                             if key in stage}),
            "episodes": [episode_scope(ep) for ep in stage.get("episodes", [])]}


def _identity_value(value):
    value = scalar(value)
    return " ".join(value.split()).casefold() if isinstance(value, str) else None


def participant_registry(results):
    """Keep canonical ID/name/type bindings; roles may vary between episodes."""
    registry = {}
    for result in results:
        for participant in result.get("ParticipantReconstructor", {}).get("participants", []):
            identifier = participant["participant_id"]
            entry = registry.setdefault(identifier, {"participant_id": identifier})
            for key in ("name", "participant_type"):
                candidate = scalar(participant.get(key))
                if _identity_value(entry.get(key)) in UNKNOWN:
                    entry[key] = candidate
                elif _identity_value(candidate) != _identity_value(entry[key]):
                    raise ValueError(f"Participant identity drift: {identifier}.{key}; reuse canonical binding")
            entry["base_role"] = scalar(participant.get("base_role"))
            entry["attributes"] = compact_values(participant.get("attributes", {}))
    return list(registry.values())


def validate_participant_identity(participants, previous_results):
    return participant_registry([*previous_results, {"ParticipantReconstructor": {"participants": participants}}])


def validate_episode_reuse(payload, target):
    for key, placeholder in ROLE_RESULTS.items():
        if payload.get(key) != placeholder:
            raise ValueError(f"episode.{key}: must equal {placeholder!r}; arrays belong to the preceding role")
    for key in EPISODE_SCOPE_FIELDS:
        if scalar(payload.get(key)) != scalar(target.get(key)):
            raise ValueError(f"Episode scope drift: {key} must match the checked skeleton")


def date_interval(value):
    """Recognize explicit ISO/English dates without inventing finer precision."""
    value = scalar(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    quarter = re.fullmatch(r"(?:(\d{4})-Q([1-4])|Q([1-4])\s+(\d{4}))", value, re.I)
    if quarter:
        year = int(quarter.group(1) or quarter.group(4))
        number = int(quarter.group(2) or quarter.group(3))
        first, last = (number - 1) * 3 + 1, number * 3
        try:
            return (datetime(year, first, 1), datetime(year, last,
                calendar.monthrange(year, last)[1], 23, 59, 59, 999999))
        except ValueError:
            return None
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value)
    if match:
        year, month, day = (int(part) if part else None for part in match.groups())
        try:
            first = datetime(year, month or 1, day or 1)
            last_month = month or 12
            last_day = day or calendar.monthrange(year, last_month)[1]
            return first, datetime(year, last_month, last_day, 23, 59, 59, 999999)
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", value):
        try:
            point = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if point.tzinfo:
                point = point.astimezone(timezone.utc).replace(tzinfo=None)
            return point, point
        except ValueError:
            return None
    # These expressions identify a month, not an exact early/mid/late date.
    month_value = re.sub(r"^(?:early|mid|late|end of|beginning of)\s+", "", value, flags=re.I)
    for fmt in ("%B %Y", "%b %Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            point = datetime.strptime(month_value, fmt)
        except ValueError:
            continue
        return date_interval(point.strftime("%Y-%m-%d" if "%d" in fmt else "%Y-%m"))
    return None


def check_temporal_scope(target, *, participants=(), transactions=()):
    start, end = date_interval(target.get("start_time")), date_interval(target.get("end_time"))
    lower, upper = start[0] if start else None, end[1] if end else None
    if lower and upper and lower > upper:
        raise ValueError("Episode scope: start_time is later than end_time")
    checks, violations = [], []
    items = [(f"participants[{pi}].actions[{ai}]", action,
              {"participant_id": participant.get("participant_id")})
             for pi, participant in enumerate(participants)
             for ai, action in enumerate(participant.get("actions", []))]
    items += [(f"transactions[{ti}]", transaction, {}) for ti, transaction in enumerate(transactions)]
    for path, item, identity in items:
        stamp = scalar(item.get("timestamp"))
        interval = date_interval(stamp)
        status = "unchecked"
        if interval and (lower or upper):
            if (lower and interval[1] < lower) or (upper and interval[0] > upper):
                violations.append({"path": path, "timestamp": stamp,
                                   "item": copy.deepcopy(item), **identity})
            status = "overlaps_known_bounds"
        checks.append({"path": path, "timestamp": stamp, "status": status})
    if violations:
        raise TemporalScopeError({
            "scope": episode_scope(target),
            "bounds": {"start": lower.isoformat() if lower else None,
                       "end": upper.isoformat() if upper else None},
            "violations": violations,
        })
    return {"scope": episode_scope(target), "start_checked": lower is not None,
            "end_checked": upper is not None, "items": checks}


def construction_report(cascade):
    results, episodes, seen_actions, duplicates = [], [], {}, []
    for si, stage in enumerate(cascade["stages"]):
        for ei, episode in enumerate(stage["episodes"]):
            locator = {"stage_index": si, "episode_index": ei, "stage_id": stage["stage_id"],
                       "episode_id": episode["episode_id"]}
            participants = episode["participants"]
            results.append({"ParticipantReconstructor": {"participants": participants}})
            episodes.append({"locator": locator, "participant_ids": [p["participant_id"] for p in participants],
                             **check_temporal_scope(episode, participants=participants,
                                                    transactions=episode["transactions"])})
            for participant in participants:
                for action in participant.get("actions", []):
                    key = (participant["participant_id"], scalar(action.get("name")), scalar(action.get("timestamp")))
                    if key in seen_actions:
                        duplicates.append({"participant_id": key[0], "name": key[1], "timestamp": key[2],
                                           "previous": seen_actions[key], "current": locator})
                    seen_actions[key] = locator
    return {"contract_version": CONSTRUCTION_CONTRACT_VERSION,
            "identity_map": participant_registry(results), "episodes": episodes,
            "repeated_action_candidates": duplicates, "semantic_support_checked": False,
            "time_policy": "Reject only provably disjoint intervals; unknown/unparsed dates remain unchecked."}
