"""Deterministic year/topic queries and strict publication-window checks.

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
_TOPICS = {
    "meeting": (r"annual\s+meeting|shareholder\w*\s+meeting|股东大会|股東大會", "annual shareholders meeting transcript 股东大会 实录"),
    "letter": (r"shareholder\w*\s+letter|annual\s+letter|股东信|股東信|致股东|致股東", "shareholder letter full text 致股东信 全文"),
    "interview": (r"interview|访谈|訪談|采访|採訪", "interview transcript 采访 实录"),
    "investment": (r"invest|投资|投資|持仓|持倉|增持|减持|減持", "investment decisions purchases sales 投资 决策"),
    "philanthropy": (r"philanthrop|donat|慈善|捐赠|捐贈", "philanthropy donation 慈善 捐赠"),
    "succession": (r"success(?:ion|or)|接班|继任|繼任", "succession statements 接班人 发言"),
    "visit": (r"visit|访日|訪日|访问|訪問|日本", "visit 访问"),
}


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


def _topic_scope(query):
    """Keep literal topic restrictions; never invent an organization or place."""
    clauses = []
    pattern = r"(?:related\s+to|about|focus(?:ed)?\s+on|visits?\s+to|关于|關於|围绕|圍繞|聚焦|访问|訪問)\s*([^.;。；\n]+)"
    for match in re.finditer(pattern, query or "", re.I):
        clause = re.split(r"\b(?:between|from|during|through)\b|(?<!\d)(?:19|20)\d{2}|[，,]", match[1], maxsplit=1, flags=re.I)[0]
        clause = clause.strip(" ：:，,。;；-")
        if clause:
            clauses.append(clause[:160])
    return " ".join(dict.fromkeys(clauses))


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
    """Plan bounded year/topic queries without using model-generated identity."""
    options = options or {}
    name = subject.get("name", "").strip()
    if not name:
        raise ValueError("Scoped search requires a subject name")
    start, end = search_window(query, subject, options)
    cap = options.get("max_queries", 16)
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ValueError("max_queries must be a positive integer")
    years = list(range(start.year, end.year + 1))
    if len(years) > cap:
        raise ValueError("Publication period has more years than max_queries; increase the query budget or narrow the requested period")
    topics = options.get("topics")
    if topics is None:
        text = " ".join([query or "", " ".join(keywords or [])])
        topics = [key for key, (pattern, _) in _TOPICS.items() if re.search(pattern, text, re.I)]
    elif not isinstance(topics, list) or any(not isinstance(x, str) or not x.strip() for x in topics):
        raise ValueError("topics must be a list of nonempty topic strings")
    topics = list(dict.fromkeys(topics or ["activities"]))
    if len(years) * len(topics) > cap:
        raise ValueError("Requested years and topics exceed max_queries; increase the query budget or narrow the requested scope")
    scope = (options.get("scope") or subject.get("scope") or "").strip()
    # The normal subject scope is boilerplate, not a query constraint. Preserve
    # explicitly configured topic scope (e.g. Occidental Petroleum / OXY).
    if scope.startswith(("Documented activities and experiences across events", "Documented company history and activities across events")):
        scope = ""
    scope = " ".join(dict.fromkeys(filter(None, (scope, _topic_scope(query)))))
    result = []
    # Round-robin years: the budget must never omit the later requested years.
    for topic in topics:
        for year in years:
            low, high = max(start, dt.date(year, 1, 1)), min(end, dt.date(year, 12, 31))
            terms = _TOPICS.get(topic, (None, topic))[1]
            if topic == "visit" and re.search(r"Japan|日本|访日|訪日", " ".join([query or "", " ".join(keywords or [])]), re.I):
                terms += " Japan 日本"
            query_text = (f'"{name.replace(chr(34), "")}" {year} {terms} {scope} '
                          f'published {low.isoformat()} to {high.isoformat()} '
                          f'after:{(low - dt.timedelta(days=1)).isoformat()} '
                          f'before:{(high + dt.timedelta(days=1)).isoformat()}')
            result.append({"query": query_text, "start": low.isoformat(), "end": high.isoformat(),
                           "year": year, "topic": topic})
            if len(result) == cap:
                return result
    return result
