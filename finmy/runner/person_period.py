"""Person-period inputs shared by the UI and compact CLI request.

Keep year/month/day precision in the scope. A single date token is a point at
that precision, not an invented day or an inferred whole-biography request.
"""
from __future__ import annotations

import re
import unicodedata

from finmy.reconstruction_scope import date_bounds


_DATE = r"\d{4}(?:-\d{1,2}(?:-\d{1,2})?)?"
_CHINESE_DATE = re.compile(r"(\d{4})年(?:(\d{1,2})月(?:(\d{1,2})[日号])?)?")
_RANGE = re.compile(rf"({_DATE})\s*(?:to|至|到|[~～〜–—-])\s*({_DATE})", re.I)


def _date_token(value):
    parts = value.split("-")
    normalized = parts[0] + "".join("-" + str(int(part)).zfill(2) for part in parts[1:])
    date_bounds(normalized)
    return normalized


def parse_person_period(value):
    """Return (start, end) for a date point or an inclusive date range."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a period, such as 2023, 2023-05, or 2022–2023.")
    text = unicodedata.normalize("NFKC", value).strip()
    text = _CHINESE_DATE.sub(
        lambda match: "-".join(part for part in match.groups() if part is not None), text)
    if re.fullmatch(_DATE, text):
        start = end = _date_token(text)
    else:
        match = _RANGE.fullmatch(text)
        if not match:
            raise ValueError("Use a year, month or date, or a range such as 2022–2023 / 2022-01-01 to 2023-12-31.")
        start, end = (_date_token(part) for part in match.groups())
    if date_bounds(start)[0] > date_bounds(end)[1]:
        raise ValueError("The start of the period must not be after its end.")
    return start, end


def period_text(subject):
    """Render a saved scope for the two-field form without losing precision."""
    start, end = subject.get("coverage_start"), subject.get("coverage_end")
    if not isinstance(start, str) or not isinstance(end, str):
        return ""
    text = start if start == end else start + " – " + end
    try:
        parse_person_period(text)
    except ValueError:
        return ""
    return text


def compact_person_request(request):
    """Read `name period`; return None for a longer natural-language request.

    Invalid date-shaped compact requests raise instead of silently falling back
    to a stale configured person's scope.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Provide a person and period, e.g. Buffett 2022–2023.")
    # The boundary before a four-digit year also supports 巴菲特2022至2023.
    match = re.fullmatch(r"\s*(.+?)\s*[,，:]?\s*(\d{4}.*)\s*", request)
    if not match:
        return None
    name, candidate = match.groups()
    name = name.strip().rstrip(",，:").strip()
    # Do not interpret prose after a year as a compact input. A fully declared
    # person scope remains available to callers of the natural-language CLI.
    if re.search(r"[^\d\s\-–—~～〜至到年月日号tToO]", candidate):
        return None
    if not name or not re.search(r"[^\d\s,，:\-–—]", name):
        raise ValueError("A nonempty person name is required before the period.")
    start, end = parse_person_period(candidate)
    return name, start, end
