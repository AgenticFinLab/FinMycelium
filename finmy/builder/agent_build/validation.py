"""Deterministic checks and conservative, evidence-backed transaction deduplication.

Dates and inferred facts are never rewritten. Partial dates represent intervals.
Removed copies remain in the report; no additional fields enter the cascade schema.
"""

import calendar
import copy
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal


_UTC = timezone.utc
_UNKNOWN = {"", "unknown", "unspecified", "none", "null", "n/a", "na"}
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")
_BACKGROUND = re.compile(
    r"cumulative|so far|this year|now owns?|ownership reached|control of|"
    r"total holding|in 20\d\d|累计|目前持有", re.I
)
_TYPE_ALIASES = {"stock purchase": "share purchase"}


def _value(field):
    return field.get("value") if isinstance(field, dict) else field


def _text(field):
    value = _value(field)
    return str(value).strip() if value is not None else ""


def _norm(field):
    return " ".join(unicodedata.normalize("NFKC", _text(field)).casefold().split())


def _known(field):
    return _norm(field) not in _UNKNOWN


def _evidence_norm(text):
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", _norm(text))
    return " ".join(re.sub(r"[^\w.%$€£]+", " ", text).split())


def _date_interval(field):
    """Return (lower, upper, precision), or None; no guessed calendar dates."""
    text = _text(field)
    try:
        if re.fullmatch(r"\d{4}", text):
            year = int(text)
            return (datetime(year, 1, 1, tzinfo=_UTC),
                    datetime(year, 12, 31, 23, 59, 59, 999999, tzinfo=_UTC), "year")
        if re.fullmatch(r"\d{4}-\d{2}", text):
            year, month = map(int, text.split("-"))
            return (datetime(year, month, 1, tzinfo=_UTC),
                    datetime(year, month, calendar.monthrange(year, month)[1],
                             23, 59, 59, 999999, tzinfo=_UTC), "month")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=_UTC)
            return day, day + timedelta(days=1) - timedelta(microseconds=1), "day"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", text):
            instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
            # Transaction timestamps are UTC in the existing schema.
            instant = instant.replace(tzinfo=_UTC) if instant.tzinfo is None else instant.astimezone(_UTC)
            return instant, instant, "datetime"
    except (ValueError, OverflowError):
        pass
    return None


def _issue(issues, code, path, message, **extra):
    issues.append(dict(code=code, path=path, message=message, **extra))


def _read_date(field, path, issues):
    interval = _date_interval(field)
    if interval is None:
        _issue(issues, "invalid_time" if _known(field) else "unknown_time", path,
               "Date cannot be resolved without guessing.", value=_value(field))
    return interval


def _bounds(obj, path, issues):
    start = _read_date(obj.get("start_time"), path + "/start_time", issues)
    end = _read_date(obj.get("end_time"), path + "/end_time", issues)
    if not start or not end:
        return None
    if start[0] > end[1]:
        _issue(issues, "invalid_time_range", path, "Start is after end.")
        return None
    return start[0], end[1]


def _list(obj, key, path, issues):
    value = obj.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        _issue(issues, "invalid_collection", path + "/" + key, "Expected a list.")
        return []
    return value


def _participants(episode):
    """Only unambiguous, named local participants can identify a transaction."""
    result = {}
    for participant in episode.get("participants", []) or []:
        if not isinstance(participant, dict):
            continue
        identifier = _text(participant.get("participant_id"))
        identity = (_norm(participant.get("name")), _norm(participant.get("participant_type")))
        if identifier in result or not identifier or not all(identity):
            result[identifier] = None
        else:
            result[identifier] = identity
    return result


def _collect(cascade):
    issues, records = [], []
    event_bounds = _bounds(cascade, "", issues)
    for si, stage in enumerate(_list(cascade, "stages", "", issues)):
        spath = "/stages/" + str(si)
        if not isinstance(stage, dict):
            _issue(issues, "invalid_stage", spath, "Expected a stage object.")
            continue
        stage_bounds = _bounds(stage, spath, issues)
        if event_bounds and stage_bounds and not (event_bounds[0] <= stage_bounds[0] and stage_bounds[1] <= event_bounds[1]):
            _issue(issues, "stage_out_of_event", spath, "Stage extends beyond event bounds.")
        for ei, episode in enumerate(_list(stage, "episodes", spath, issues)):
            epath = spath + "/episodes/" + str(ei)
            if not isinstance(episode, dict):
                _issue(issues, "invalid_episode", epath, "Expected an Episode object.")
                continue
            bounds = _bounds(episode, epath, issues)
            if stage_bounds and bounds and not (stage_bounds[0] <= bounds[0] and bounds[1] <= stage_bounds[1]):
                _issue(issues, "episode_out_of_stage", epath, "Episode extends beyond its Stage bounds.")
            local_participants = _list(episode, "participants", epath, issues)
            ids = {_text(p.get("participant_id")) for p in local_participants if isinstance(p, dict)}
            identities = _participants(dict(participants=local_participants))
            for identifier, identity in identities.items():
                if identity is None:
                    _issue(issues, "ambiguous_participant_identity", epath + "/participants",
                           "Duplicate or incomplete participant identity; automatic matching disabled.", participant_id=identifier)
            for key in ("transactions", "participant_relations"):
                for index, item in enumerate(_list(episode, key, epath, issues)):
                    path = epath + "/" + key + "/" + str(index)
                    if not isinstance(item, dict):
                        _issue(issues, "invalid_record", path, "Expected an object.")
                        continue
                    for side in ("from_participant_id", "to_participant_id"):
                        identifier = _text(item.get(side))
                        if not _known(identifier) or identifier not in ids:
                            _issue(issues, "missing_participant_reference", path + "/" + side,
                                   "Reference does not resolve to a local Episode participant.", value=identifier)
                    if key != "transactions":
                        continue
                    date = _read_date(item.get("timestamp"), path + "/timestamp", issues)
                    if bounds and date:
                        if date[1] < bounds[0] or date[0] > bounds[1]:
                            _issue(issues, "transaction_out_of_bounds", path,
                                   "Transaction date is outside its Episode; record retained for review.")
                        elif date[0] < bounds[0] or date[1] > bounds[1]:
                            _issue(issues, "transaction_boundary_uncertain", path,
                                   "Partial transaction date overlaps but is not contained by its Episode.")
                    records.append(dict(transaction=item, episode=episode, episode_path=epath,
                                        path=path, bounds=bounds, date=date, identities=identities))
    return records, issues


def _numbers(text):
    return tuple(sorted(str(Decimal(n.replace(",", ""))) for n in _NUMBER.findall(_text(text))))


def _snippets(field):
    if not isinstance(field, dict):
        return []
    evidence = field.get("evidence_source_contents", [])
    return [s for s in evidence if isinstance(s, str)] if isinstance(evidence, list) else []


def _details(transaction):
    details = transaction.get("details", [])
    return [d for d in details if isinstance(d, dict)] if isinstance(details, list) else []


def _anchors(transaction):
    """Numeric event details, excluding recognisable cumulative holding summaries."""
    anchors = []
    for detail in _details(transaction):
        text = _text(detail)
        numbers = _numbers(text)
        if not numbers or _BACKGROUND.search(text):
            continue
        snippets = [_evidence_norm(s) for s in _snippets(detail) if _numbers(s)]
        if snippets:
            anchors.append((numbers, snippets, text))
    return anchors


def _shared_anchor(left, right):
    for numbers, snippets, text in _anchors(left):
        for other_numbers, other_snippets, other_text in _anchors(right):
            if numbers != other_numbers:
                continue
            amounts, other_amounts = _quantities(text), _quantities(other_text)
            # A bare number, date, or matching paragraph cannot establish that
            # two quantities share a unit (USD 100 is not 100 shares/EUR 100).
            if not amounts.keys() & other_amounts.keys() or _quantity_conflict(amounts, other_amounts):
                continue
            for a in snippets:
                for b in other_snippets:
                    smaller = a if len(a) <= len(b) else b
                    if len(smaller) >= 24 and (a in b or b in a) and set(_numbers(smaller)) & set(numbers):
                        return smaller
    return None


def _quantities(text):
    """Extract explicit signed quantities; unfamiliar units disable matching."""
    quantities = {}
    number = r"(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*(?P<scale>thousand|million|billion)?"
    multiplier = {None: 1, "thousand": 1000, "million": 1000000, "billion": 1000000000}
    patterns = [(r"(?P<sign>[-+]?)\s*(?:\$|usd\s*)\s*" + number, "currency:USD"),
                (r"(?P<sign>[-+]?)\s*(?:€|eur\s*)\s*" + number, "currency:EUR"),
                (r"(?P<sign>[-+]?)\s*(?:£|gbp\s*)\s*" + number, "currency:GBP"),
                (r"(?P<sign>[-+]?)\s*(?:¥|cny\s*|rmb\s*)\s*" + number, "currency:CNY"),
                (number + r"\s+(?:[a-z]+\s+){0,3}(?:shares?)\b", "shares"),
                (number + r"\s*%", "percent")]
    for pattern, unit in patterns:
        for match in re.finditer(pattern, text.lower()):
            amount = Decimal(match.group("number").replace(",", "")) * multiplier[match.group("scale")]
            if match.groupdict().get("sign") == "-":
                amount = -amount
            quantities.setdefault(unit, set()).add(amount)
    return quantities


def _quantity_conflict(left, right):
    left_currencies = {key for key in left if key.startswith("currency:")}
    right_currencies = {key for key in right if key.startswith("currency:")}
    return (bool(left_currencies and right_currencies and left_currencies != right_currencies)
            or any(left[key] != right[key] for key in left.keys() & right.keys()))


def _amounts(transaction):
    """Comparable explicit quantities used only to veto conflicting matches."""
    quantities = {}
    for _, _, text in _anchors(transaction):
        for unit, values in _quantities(text).items():
            quantities.setdefault(unit, set()).update(values)
    return quantities


def _aggregate(transaction):
    """Multiple explicit trade dates indicate a summary, not one execution."""
    dates = set()
    pattern = re.compile(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}\b|\d{1,2}月\d{1,2}日|\b\d{4}-\d{2}-\d{2}\b", re.I)
    for detail in _details(transaction):
        text = _text(detail)
        if (_BACKGROUND.search(text) or re.search(r"approv|regulat|as of", text, re.I)
                or not re.search(r"shares?|purchas|bought|sold|transfer|payment|paid|购买|收购", text, re.I)):
            continue
        dates.update(_norm(m.group()) for m in pattern.finditer(text))
    return len(dates) > 1


def _identity(record):
    transaction = record["transaction"]
    result = []
    for side in ("from_participant_id", "to_participant_id"):
        identifier = _text(transaction.get(side))
        entity = record["identities"].get(identifier)
        if not _known(identifier) or not entity or any(x in _UNKNOWN for x in entity):
            return None
        result.append((identifier, entity))
    return tuple(result)


def _instruments(transaction):
    instruments = transaction.get("instruments")
    if not isinstance(instruments, list) or not instruments or not all(_known(x) for x in instruments):
        return None
    return tuple(sorted(_norm(x) for x in instruments))


def _match(left, right, *, allow_same_episode=False):
    if not allow_same_episode and left["episode_path"] == right["episode_path"]:
        return None
    date = left["date"]
    if not date or date[2] not in ("day", "datetime") or date != right["date"]:
        return None
    identity = _identity(left)
    if identity is None or identity != _identity(right):
        return None
    a, b = left["transaction"], right["transaction"]
    instrument = _instruments(a)
    if not instrument or instrument != _instruments(b):
        return None
    kind_a, kind_b = _norm(a.get("transaction_type")), _norm(b.get("transaction_type"))
    if kind_a in _UNKNOWN or _TYPE_ALIASES.get(kind_a, kind_a) != _TYPE_ALIASES.get(kind_b, kind_b):
        return None
    for key in ("transaction_id", "trade_id", "execution_id"):
        if (_known(a.get(key)) and _known(b.get(key)) and _text(a[key]) != _text(b[key])):
            return None
    if _aggregate(a) or _aggregate(b):
        return None
    amounts_a, amounts_b = _amounts(a), _amounts(b)
    if _quantity_conflict(amounts_a, amounts_b):
        return None
    return _shared_anchor(a, b)


def _union(values, incoming):
    for item in incoming:
        if item not in values:
            values.append(copy.deepcopy(item))


def _merge_fields(target, source):
    """Preserve differing detail values; combine provenance for equal values."""
    for key, incoming in source.items():
        if key not in target:
            target[key] = copy.deepcopy(incoming)
        elif isinstance(target[key], dict) and isinstance(incoming, dict):
            # Main values remain those of the canonical record. Alternate values
            # and their full provenance are retained in the report snapshots.
            if _norm(target[key]) == _norm(incoming):
                for evidence_key in ("evidence_source_contents", "reasons"):
                    if isinstance(incoming.get(evidence_key), list):
                        if evidence_key not in target[key]:
                            target[key][evidence_key] = copy.deepcopy(incoming[evidence_key])
                        elif isinstance(target[key].get(evidence_key), list):
                            _union(target[key][evidence_key], incoming[evidence_key])
        elif key in ("details", "instruments") and isinstance(target[key], list) and isinstance(incoming, list):
            for field in incoming:
                matching = next((f for f in target[key] if isinstance(f, dict) and isinstance(field, dict) and _norm(f) == _norm(field)), None)
                if matching is None:
                    if field not in target[key]:
                        target[key].append(copy.deepcopy(field))
                else:
                    _merge_fields({"field": matching}, {"field": field})


def _canonical_key(record):
    date, bounds = record["date"], record["bounds"]
    contained = bool(date and bounds and bounds[0] <= date[0] and date[1] <= bounds[1])
    duration = (bounds[1] - bounds[0]).total_seconds() if bounds else float("inf")
    return not contained, duration, record["path"]


def _duplicate_groups(records):
    """Only complete, unambiguous components can be collapsed in one pass.

    Abstaining on an entire non-clique prevents merged evidence from creating
    new matches on a second pass. Multiple records from one Episode may denote
    repeated identical executions and therefore block the entire component.
    """
    edges = [set() for _ in records]
    for i, left in enumerate(records):
        for j in range(i + 1, len(records)):
            if _match(left, records[j], allow_same_episode=True):
                edges[i].add(j)
                edges[j].add(i)
    remaining, groups, issues = set(range(len(records))), [], []
    while remaining:
        first = min(remaining)
        component, pending = set(), [first]
        while pending:
            index = pending.pop()
            if index in component:
                continue
            component.add(index)
            pending.extend(edges[index] - component)
        remaining.difference_update(component)
        if len(component) < 2:
            continue
        group = [records[index] for index in sorted(component)]
        unique_episodes = len({r["episode_path"] for r in group}) == len(group)
        complete = all(component - {index} <= edges[index] for index in component)
        if unique_episodes and complete:
            groups.append(group)
        else:
            _issue(issues, "ambiguous_duplicate_group", group[0]["path"],
                   "Partial evidence matches or repeated same-Episode executions; all records retained.",
                   member_paths=[r["path"] for r in group])
    return groups, issues


def _possible_overlaps(records):
    issues = []
    for i, left in enumerate(records):
        for right in records[i + 1:]:
            if left["episode_path"] == right["episode_path"] or _identity(left) is None or _identity(left) != _identity(right):
                continue
            if not (_aggregate(left["transaction"]) or _aggregate(right["transaction"])):
                continue
            # Numeric evidence overlap can reveal a summary spanning several
            # dates even when labels/instrument wording differ. It only warns.
            evidence_a = {_evidence_norm(s) for d in _details(left["transaction"]) for s in _snippets(d) if _numbers(s)}
            evidence_b = {_evidence_norm(s) for d in _details(right["transaction"]) for s in _snippets(d) if _numbers(s)}
            if any(len(min(a, b, key=len)) >= 24 and (a in b or b in a) for a in evidence_a for b in evidence_b):
                _issue(issues, "possible_aggregate_overlap", left["path"],
                       "A multi-date summary shares evidence with a separate transaction; both retained.", other_path=right["path"])
    return issues


def validate_event_cascade(cascade, *, deduplicate=True):
    """Return an independent cascade and JSON report; never modify the input."""
    if not isinstance(cascade, dict):
        raise TypeError("Event cascade must be a dictionary")
    result = copy.deepcopy(cascade)
    records, before = _collect(result)
    before.extend(_possible_overlaps(records))
    groups, ambiguity = _duplicate_groups(records)
    before.extend(ambiguity)
    report = {"version": 1, "deduplicate": bool(deduplicate), "issues_before": before,
              "duplicate_candidates": [], "merges": []}
    removed = set()
    canonical_objects = []
    for group in groups:
        if len(group) < 2:
            continue
        canonical = min(group, key=_canonical_key)
        report["duplicate_candidates"].append({
            "canonical_original_path": canonical["path"],
            "member_paths": [record["path"] for record in group],
        })
        if not deduplicate:
            continue
        merge = {"canonical_original_path": canonical["path"],
                 "canonical_original_transaction": copy.deepcopy(canonical["transaction"]),
                 "canonical_episode_id": _value(canonical["episode"].get("episode_id")),
                 "removed": []}
        for record in group:
            if record is canonical:
                continue
            merge["removed"].append({"path": record["path"],
                                     "episode_id": _value(record["episode"].get("episode_id")),
                                     "transaction": copy.deepcopy(record["transaction"]),
                                     "matched_evidence": _match(canonical, record)})
        # Match all group members before merging: added background details
        # must not affect duplicate decisions or their explanation.
        for record in group:
            if record is not canonical:
                _merge_fields(canonical["transaction"], record["transaction"])
                removed.add(record["path"])
        canonical_objects.append(canonical["transaction"])
        report["merges"].append(merge)
    for record in reversed(records):
        if record["path"] in removed:
            index = int(record["path"].rsplit("/", 1)[1])
            del record["episode"]["transactions"][index]
    after_records, after = _collect(result)
    after.extend(_possible_overlaps(after_records))
    after.extend(_duplicate_groups(after_records)[1])
    for merge, canonical in zip(report["merges"], canonical_objects):
        merge["canonical_path"] = next(r["path"] for r in after_records if r["transaction"] is canonical)
    report["issues_after"] = after
    report["summary"] = {
        "transactions_before": len(records), "transactions_after": len(after_records),
        "duplicates_removed": len(removed), "duplicate_groups": len(report["duplicate_candidates"]),
        "issues_before": len(before), "issues_after": len(after),
    }
    return result, report
