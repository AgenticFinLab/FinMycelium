"""Bounded source-grounded corrections and explicit same-occurrence merges."""
import copy
import re

from finmy.subject_graph.evidence import restore_source_quotes
from finmy.subject_graph.event_sources import _quotes, restrict_event_evidence
from finmy.subject_graph.repair import apply_graph_patch
from finmy.subject_graph.validation import date_interval, validate_subject_graph


def _report():
    return {"accepted": [], "rejected": []}


def _checked(graph, allocation, sources):
    report = validate_subject_graph(graph, [s["content"] for s in sources],
                                    allow_unverified_evidence=True)
    if not report["valid"]:
        raise ValueError("; ".join(e["message"] for e in report["errors"][:3]))
    checked, conflicts = restrict_event_evidence(
        graph, {e["event_id"]: e for e in graph["events"]}, allocation, sources)
    if conflicts or checked != graph:
        raise ValueError("Correction conflicts with event source allocation or dates")


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


def apply_event_corrections(graph, event_id, corrections, event_sources, sources):
    """Apply one event's correction groups atomically, using original array indices.

    Paths are /event/... . Only complete VF replacements, evidenced actor changes,
    and removal of individual records are allowed. Unchanged fields remain intact.
    """
    report = _report()
    if corrections == []:
        return graph, report
    try:
        if not isinstance(corrections, list) or len(corrections) > 16:
            raise ValueError("corrections must contain at most 16 groups")
        if any(not isinstance(group, dict) for group in corrections):
            raise ValueError("Correction groups must be objects")
        index = next(i for i, e in enumerate(graph["events"]) if e["event_id"] == event_id)
        event = graph["events"][index]
        allowed = event_sources.get(event_id, [])
        operations = []
        for group in corrections:
            if (not isinstance(group, dict) or set(group) != {"reason", "patches"}
                    or not isinstance(group["reason"], str) or not group["reason"].strip()
                    or not isinstance(group["patches"], list) or not group["patches"]):
                raise ValueError("Each correction requires reason and nonempty patches")
            for operation in group["patches"]:
                if not isinstance(operation, dict):
                    raise ValueError("Correction patch must be an object")
                op, path = operation.get("op"), operation.get("path", "")
                if not isinstance(path, str) or not path.startswith("/event/"):
                    raise ValueError("Correction path must start with /event/")
                suffix = path[len("/event/"):]
                if op == "replace":
                    is_field = re.fullmatch(r"(?:title|subject_relevance|start_time|end_time|descriptions/\d+|"
                        r"participations/\d+/(?:role|start_time|end_time)|"
                        r"actions/\d+/(?:action_type|timestamp|details/\d+)|"
                        r"transactions/\d+/(?:name|timestamp|from_entity_id|to_entity_id|details/\d+))", suffix)
                    actor = re.fullmatch(r"actions/(\d+)/actor_id", suffix)
                    operation = copy.deepcopy(operation)
                    if is_field:
                        value, _ = restore_source_quotes(operation.get("value"), [s["content"] for s in allowed])
                        _strict_field(value, allowed)
                        operation["value"] = value
                    elif actor:
                        if operation.get("value") not in {p["entity_id"] for p in event["participations"]}:
                            raise ValueError("Corrected actor must already participate")
                        prefix = f"/event/actions/{actor[1]}/"
                        if not any(p.get("op") == "replace" and (p.get("path") == prefix + "action_type"
                            or str(p.get("path", "")).startswith(prefix + "details/"))
                            for g in corrections for p in g.get("patches", []) if isinstance(p, dict)):
                            raise ValueError("Actor correction requires an evidenced action correction")
                    else:
                        raise ValueError("Correction cannot replace records, collections or IDs")
                elif op == "remove":
                    if not re.fullmatch(r"(?:descriptions|participations|actions|transactions)/\d+|(?:actions|transactions)/\d+/details/\d+", suffix):
                        raise ValueError("Only individual event records or details may be removed")
                else:
                    raise ValueError("Corrections support replace and remove only")
                operations.append({**operation, "path": f"/events/{index}/" + suffix})
        candidate = apply_graph_patch(graph, {"patches": operations}, [{"path": f"/events/{index}"}])
        _checked(candidate, event_sources, sources)
        report["accepted"] = copy.deepcopy(corrections)
        report["original_event"] = copy.deepcopy(event)
        return candidate, report
    except (ValueError, KeyError, TypeError, StopIteration, IndexError) as exc:
        report["rejected"].append({"corrections": copy.deepcopy(corrections), "reason": str(exc)})
        return graph, report


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
            parts = patch["path"].split("/")[2:]
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
            _checked(candidate, selected, sources)
            result, allocation = candidate, selected
            report["accepted"].append({**copy.deepcopy(proposal), "original_event": copy.deepcopy(remove)})
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            report["rejected"].append({"proposal": copy.deepcopy(proposal), "reason": str(exc)})
    return result, allocation, report
