"""Single-range queries and strict publication-window checks.

Search operators are only hints to providers. Call publication_allowed on every
result before fetching it; unknown dates do not silently pass the window.
"""
import calendar
import datetime as dt
import re

from finmy.reconstruction_scope import date_bounds


_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTH_WORD = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_DATES = re.compile(
    rf"\b{_MONTH_WORD}\.?\s+(?:\d{{1,2}},?\s+)?(?:19|20)\d{{2}}\b"
    rf"|(?<!\d)(?:19|20)\d{{2}}(?:年\s*\d{{1,2}}月(?:\s*\d{{1,2}}日)?"
    rf"|[-/]\d{{1,2}}(?:[-/]\d{{1,2}})?|\s+{_MONTH_WORD}\.?)?(?!\d)",
    re.I,
)


def publication_bounds(value):
    """Parse an explicit publication date; do not infer dates from URL/title."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Full ISO dates may carry a time/timezone; their local publication date is
    # preserved, rather than moving an item across a boundary via UTC conversion.
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T ].*)?", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            day = dt.date(year, month, day)
            return day, day
        except ValueError:
            return None
    normalized = re.sub(r"\s+", "", text).replace("年", "-").replace("月", "-").replace("日", "").rstrip("-")
    normalized = normalized.replace("/", "-")
    if re.fullmatch(r"\d{4}(?:-\d{1,2}){0,2}", normalized):
        try:
            pieces = normalized.split("-")
            return date_bounds("-".join([pieces[0]] + [p.zfill(2) for p in pieces[1:]]))
        except ValueError:
            return None
    match = re.fullmatch(rf"({_MONTH_WORD})\.?\s+(?:(\d{{1,2}}),?\s+)?(\d{{4}})", text, re.I)
    if match:
        month, day, year = match.groups()
        return publication_bounds(f"{year}-{_MONTHS[month.lower()]:02d}" + (f"-{int(day):02d}" if day else ""))
    match = re.fullmatch(rf"(\d{{4}})\s+({_MONTH_WORD})\.?", text, re.I)
    if match:
        return publication_bounds(f"{match[1]}-{_MONTHS[match[2].lower()]:02d}")
    return None


def publication_allowed(value, start, end, allow_undated=False):
    """Accept only date intervals fully contained in the requested window."""
    bounds = publication_bounds(value)
    if bounds is None:
        return bool(allow_undated), "publication_date_unknown"
    low, high = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if bounds[0] >= low and bounds[1] <= high:
        return True, "publication_in_scope"
    return False, "publication_out_of_scope_or_imprecise"


def _request_dates(query):
    matches = list(_DATES.finditer(query or ""))
    # Prefer an actual requested range, not an unrelated historical year later
    # in the instructions. E.g. "2022–2023; compare with his 2019 letter".
    for first, last in zip(matches, matches[1:]):
        connector = query[first.end():last.start()]
        if re.fullmatch(r"\s*年?\s*(?:through|to|until|[-–—~～至到])\s*", connector, re.I):
            return [publication_bounds(first.group()), publication_bounds(last.group())]
        if re.fullmatch(r"\s+and\s+", connector, re.I) and re.search(r"between\s*$", query[:first.start()], re.I):
            return [publication_bounds(first.group()), publication_bounds(last.group())]
    if len(matches) == 1:
        return [publication_bounds(matches[0].group())] * 2
    if matches:
        raise ValueError("Ambiguous publication period: specify a date range such as 2022–2023 or configure publication_start/publication_end")
    return []


def search_window(query, subject, options=None):
    """Explicit configuration wins; otherwise read dates from the request."""
    options = options or {}
    first = options.get("publication_start") or subject.get("coverage_start")
    last = options.get("publication_end") or subject.get("coverage_end")
    extracted = [] if first and last else _request_dates(query or "")
    extracted = [value for value in extracted if value is not None]
    lo = publication_bounds(first) if first else (extracted[0] if extracted else None)
    hi = publication_bounds(last) if last else (extracted[-1] if extracted else None)
    if lo is None or hi is None:
        raise ValueError("Scoped search needs a publication period: include years/dates in the description or configure publication_start/publication_end.")
    start, end = lo[0], hi[1]
    if start > end:
        raise ValueError("Search publication_start must not be after publication_end")
    return start, end


def plan_search(query, keywords, subject, options=None):
    """One original request over the full publication window, per provider.

    Legacy topics/max_queries settings do not split or restrict the request.
    """
    options = options or {}
    name = subject.get("name", "").strip()
    if not name:
        raise ValueError("Scoped search requires a subject name")
    start, end = search_window(query, subject, options)
    scope = (options.get("scope") or subject.get("scope") or "").strip()
    if scope.startswith(("Documented activities and experiences across events", "Documented company history and activities across events")):
        scope = ""
    keyword_text = keywords if isinstance(keywords, str) else " ".join(keywords or [])
    terms = [f'"{name.replace(chr(34), "")}"', query or "", keyword_text, scope]
    return [{"query": " ".join(term.strip() for term in terms if term.strip()),
             "start": start.isoformat(), "end": end.isoformat()}]
