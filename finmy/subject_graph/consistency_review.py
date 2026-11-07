"""Bounded source-grounded corrections and explicit same-occurrence merges."""
import copy
import re

from finmy.subject_graph.evidence import restore_source_quotes
from finmy.subject_graph.event_sources import _quotes, exclude_outside_coverage
from finmy.subject_graph.coverage_review import validate_review
from finmy.subject_graph.repair import _tokens, apply_graph_patch
from finmy.subject_graph.validation import date_interval


def _report():
    return {"accepted": [], "rejected": []}


def _strict_field(field, sources):
    if not isinstance(field, dict) or "value" not in field:
        raise ValueError("Replace a complete evidenced field, not its value or evidence alone")
    if "evidence_status" in field:
        raise ValueError("Corrections cannot assign evidence_status")
    quotes = field.get("evidence_source_contents")
    if not isinstance(quotes, list) or any(not isinstance(q, str) or not q.strip()
        or not any(q in source["content"] for source in sources) for q in quotes):
        raise ValueError("Correction quote is absent from assigned sources")
    if str(field["value"]).strip().lower() not in ("", "unknown", "unspecified", "none", "null", "n/a", "na") and not quotes:
        raise ValueError("Known correction requires evidence")


_REPLACE_FIELD = re.compile(
    r"(?:title|subject_relevance|start_time|end_time|descriptions/\d+|"
    r"participations/\d+/(?:role|start_time|end_time)|"
    r"actions/\d+/(?:action_type|timestamp|details/\d+)|"
    r"transactions/\d+/(?:name|timestamp|from_entity_id|to_entity_id|details/\d+))")
_RECORD_IDS = {"actions": "action_id", "transactions": "transaction_id",
               "participations": "participation_id"}
_LIST_ITEM = r"(?:descriptions|participations|actions|transactions)/{item}|(?:actions|transactions)/\d+/details/{item}"


def _event_pointer(event, path, append=False):
    """Resolve indices or stable row IDs against the unchanged review input."""
    parts = _tokens(path)
    if parts[0] != "event" or len(parts) < 2:
        raise ValueError("Correction path must start with /event/")
    value, resolved = event, []
    for position, token in enumerate(parts[1:]):
        if isinstance(value, list):
            if append and token == "-" and position == len(parts) - 2:
                return "/".join([*resolved, "-"]), value
            if token.isdecimal():
                key = int(token)
            else:
                id_key = _RECORD_IDS.get(resolved[-1])
                matches = [i for i, row in enumerate(value)
                           if isinstance(row, dict) and id_key and row.get(id_key) == token]
                if len(matches) != 1:
                    raise ValueError("Correction row ID does not identify one original record")
                key = matches[0]
            if key >= len(value):
                raise ValueError("Correction target does not exist in the reviewed event")
        elif isinstance(value, dict) and token in value:
            key = token
        else:
            raise ValueError("Correction target does not exist in the reviewed event")
        resolved.append(str(key))
        value = value[key]
    return "/".join(resolved), value


def _strict_value(value, sources):
    """Apply the same evidence rule to a field or every field of an added row."""
    if isinstance(value, dict):
        if "value" in value:
            _strict_field(value, sources)
        else:
            for child in value.values():
                _strict_value(child, sources)
    elif isinstance(value, list):
        for child in value:
            _strict_value(child, sources)


def _correction_operations(event, group, sources):
    if (not isinstance(group, dict) or set(group) != {"reason", "patches"}
            or not isinstance(group["reason"], str) or not group["reason"].strip()
            or not isinstance(group["patches"], list) or not group["patches"]):
        raise ValueError("Each correction requires reason and nonempty patches")
    operations = []
    for patch in group["patches"]:
        if not isinstance(patch, dict):
            raise ValueError("Correction patch must be an object")
        op = patch.get("op")
        required = {"op", "path"} if op == "remove" else {"op", "path", "value"}
        if op not in ("replace", "remove", "add") or set(patch) != required:
            raise ValueError("Correction requires replace, remove or append with its matching fields")
        suffix, _ = _event_pointer(event, patch["path"], append=op == "add")
        operations.append({**copy.deepcopy(patch), "path": suffix})
    for operation in operations:
        op, path = operation["op"], operation["path"]
        actor = re.fullmatch(r"actions/(\d+)/actor_id", path)
        if op == "remove":
            if not re.fullmatch(_LIST_ITEM.format(item=r"\d+"), path):
                raise ValueError("Only individual event records or details may be removed")
            continue
        if op == "replace" and actor:
            if operation["value"] not in {p["entity_id"] for p in event["participations"]}:
                raise ValueError("Corrected actor must already participate")
            prefix = f"actions/{actor[1]}/"
            if not any(p["op"] in ("replace", "add") and
                       (p["path"] == prefix + "action_type" or p["path"].startswith(prefix + "details/"))
                       for p in operations):
                raise ValueError("Actor correction requires an evidenced action correction in the same group")
            continue
        if op == "add":
            if not re.fullmatch(_LIST_ITEM.format(item="-"), path):
                raise ValueError("Correction add must append one event record or detail using /-")
        elif not _REPLACE_FIELD.fullmatch(path):
            raise ValueError("Correction cannot replace records, collections or IDs")
        value, _ = restore_source_quotes(operation["value"], [s["content"] for s in sources])
        if op == "replace":
            _strict_field(value, sources)
        else:
            _strict_value(value, sources)
        operation["value"] = value
    return operations


def _apply_corrections(graph, event_index, operations):
    """Replay accepted groups on the original snapshot, preserving array indices."""
    if len(operations) > 128:
        raise ValueError("Corrections may contain at most 128 operations")
    paths = []
    for operation in operations:
        parts = operation["path"].split("/")
        if any((parts[:len(other)] == other or other[:len(parts)] == parts)
               and not (parts == other and operation["op"] == "add" and parts[-1] == "-")
               for other in paths):
            raise ValueError("Correction paths overlap an accepted correction")
        paths.append(parts)
    candidate = copy.deepcopy(graph)
    event = candidate["events"][event_index]
    for operation in operations:
        if operation["op"] == "add":
            _, target = _event_pointer(event, "/event/" + operation["path"], append=True)
            target.append(copy.deepcopy(operation["value"]))
    edits = [{**operation, "path": f"/events/{event_index}/" + operation["path"]}
             for operation in operations if operation["op"] != "add"]
    return apply_graph_patch(candidate, {"patches": edits}, [{"path": f"/events/{event_index}"}])


def apply_event_corrections(graph, event_id, corrections, event_sources, sources):
    """Apply independent atomic groups; all paths refer to the original event.

    Invalid groups are reported without discarding other accepted corrections.
    Appends, full evidenced field replacements and record removals share the
    same source and graph checks. Missing removal targets are never guessed.
    """
    report = {**_report(), "unchanged": []}
    if isinstance(corrections, dict):
        corrections = [corrections]
    if not isinstance(corrections, list) or len(corrections) > 16:
        report["rejected"].append({"corrections": copy.deepcopy(corrections),
                                   "reason": "corrections must contain at most 16 groups"})
        return graph, report
    index = next((i for i, e in enumerate(graph["events"]) if e["event_id"] == event_id), None)
    if index is None:
        report["rejected"].append({"reason": "Correction event does not exist", "event_id": event_id})
        return graph, report
    event, result, accepted = graph["events"][index], graph, []
    for group in corrections:
        try:
            operations = _correction_operations(event, group, event_sources.get(event_id, []))
            candidate = _apply_corrections(graph, index, [*accepted, *operations])
            candidate, scope_exclusions = exclude_outside_coverage(candidate)
            validate_review(candidate, event_sources, sources)
            if candidate == result:
                report["unchanged"].append(copy.deepcopy(group))
                continue
            result, accepted = candidate, [*accepted, *operations]
            report["accepted"].append(copy.deepcopy(group))
            report["scope_exclusions"] = scope_exclusions
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            report["rejected"].append({"correction": copy.deepcopy(group), "reason": str(exc)})
    if report["accepted"]:
        report["original_event"] = copy.deepcopy(event)
    return result, report


def _family(event):
    title = str(event.get("title", {}).get("value", "")).casefold()
    if re.search(r"\bletter\b|股东信|致股东", title):
        return "letter"
    if re.search(r"\bmeeting\b|股东大会|股东会", title):
        return "meeting"
    return None


def correction_exclusions(event_id, report):
    """Carry superseded claims forward so later additions cannot restore them."""
    original = report.get("original_event")
    records = []
    for group in report.get("accepted", []):
        for patch in group["patches"]:
            if patch["op"] == "add":
                continue
            suffix, _ = _event_pointer(original, patch["path"])
            parts = suffix.split("/")
            if parts[0] in ("actions", "transactions"):
                paths = [parts[:2]]
                if len(parts) == 4 and parts[2] == "details":
                    paths.append(parts)
            elif parts[0] == "descriptions":
                paths = [parts]
            else:
                continue
            for path in paths:
                value = original
                for key in path:
                    value = value[int(key)] if isinstance(value, list) else value[key]
                row = {"event_id": event_id, "path": "/event/" + "/".join(path),
                       "message": group["reason"], "record": copy.deepcopy(value)}
                if row not in records:
                    records.append(row)
    return records


def _same_day(event):
    start, end = date_interval(event.get("start_time")), date_interval(event.get("end_time"))
    if start and end and start[2] == end[2] == "day" and start == end:
        return start[0]
    return None


def _anchors(event):
    fields = [event.get("title"), *event.get("descriptions", [])]
    return list(_quotes(fields))


def apply_event_merges(graph, merges, event_sources, sources):
    """Merge explicit, evidenced same-day letters/meetings; retain distinct records.

    A common date, person or source document alone never authorizes a merge.
    Original removed records are retained in the returned report.
    """
    report, result, allocation = _report(), copy.deepcopy(graph), dict(event_sources)
    if not isinstance(merges, list) or len(merges) > 12:
        report["rejected"].append({"proposal": copy.deepcopy(merges), "reason": "merges must be a list of at most 12 proposals"})
        return graph, allocation, report
    for proposal in merges:
        try:
            if (not isinstance(proposal, dict) or set(proposal) != {"keep_event_id", "remove_event_id", "reason", "evidence_source_contents"}
                    or not isinstance(proposal["reason"], str) or not proposal["reason"].strip()):
                raise ValueError("Merge requires keep/remove IDs, reason and identifying evidence")
            keep_id, remove_id = proposal["keep_event_id"], proposal["remove_event_id"]
            if keep_id == remove_id:
                raise ValueError("Merge requires distinct IDs")
            keep = next(e for e in result["events"] if e["event_id"] == keep_id)
            remove = next(e for e in result["events"] if e["event_id"] == remove_id)
            family = _family(keep)
            if not family or family != _family(remove) or not _same_day(keep) or _same_day(keep) != _same_day(remove):
                raise ValueError("Merge requires compatible occurrence type and the same exact occurrence day")
            quotes = proposal["evidence_source_contents"]
            if not isinstance(quotes, list) or not quotes:
                raise ValueError("Merge requires identifying quotations")
            pattern = r"\bletter\b|股东信|致股东" if family == "letter" else r"\bmeeting\b|股东大会|股东会"
            for quote in quotes:
                if (not isinstance(quote, str) or len(re.sub(r"\s+", "", quote)) < 18
                        or not re.search(pattern, quote, re.I)
                        or not all(any(quote in anchor for anchor in _anchors(event)) for event in (keep, remove))
                        or not all(any(quote in s["content"] for s in allocation.get(eid, [])) for eid in (keep_id, remove_id))):
                    raise ValueError("Merge evidence must identify the occurrence in both events and their assigned sources")
            candidate = copy.deepcopy(result)
            target = next(e for e in candidate["events"] if e["event_id"] == keep_id)
            for key in ("descriptions", "participations", "actions", "transactions"):
                for row in remove[key]:
                    if row not in target[key]:
                        target[key].append(copy.deepcopy(row))
            if remove["subject_relevance"] != target["subject_relevance"] and remove["subject_relevance"] not in target["descriptions"]:
                target["descriptions"].append(copy.deepcopy(remove["subject_relevance"]))
            candidate["events"] = [e for e in candidate["events"] if e["event_id"] != remove_id]
            for relation in candidate["relations"]:
                relation["event_ids"] = list(dict.fromkeys(keep_id if eid == remove_id else eid for eid in relation["event_ids"]))
            selected = dict(allocation)
            selected[keep_id] = list({s["source_id"]: s for s in [*allocation.get(keep_id, []), *allocation.get(remove_id, [])]}.values())
            selected.pop(remove_id, None)
            validate_review(candidate, selected, sources)
            result, allocation = candidate, selected
            report["accepted"].append({**copy.deepcopy(proposal), "original_event": copy.deepcopy(remove)})
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            report["rejected"].append({"proposal": copy.deepcopy(proposal), "reason": str(exc)})
    return result, allocation, report
