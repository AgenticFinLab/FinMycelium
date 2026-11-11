"""Dependency-free shape, identity, temporal, and evidence checks.

Validation never repairs, pads dates, merges entities, or mutates model output.
Verbatim quote matching establishes provenance, not truth or entailment.
"""
import calendar
import math
import re
from datetime import datetime, timedelta, timezone


_UNKNOWN = {"", "unknown", "unspecified", "none", "null", "n/a", "na"}
_UTC = timezone.utc


def _value(value):
    return value.get("value") if isinstance(value, dict) else value


def date_interval(value):
    """Read supported precision without replacing an unknown day with the first."""
    if isinstance(value, dict) and "time_window" in value:
        window = value["time_window"]
        if not isinstance(window, dict):
            return None
        start, end = date_interval(window.get("start")), date_interval(window.get("end"))
        if start and end and start[0] <= end[1]:
            return start[0], end[1], "day" if start == end and start[2] == "day" else "range"
        return None
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
