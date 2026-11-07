"""Route event evidence by the plan's source passages, never publication year."""
import copy

from finmy.subject_graph.evidence import restore_source_quotes
from finmy.subject_graph.time_display import time_label
from finmy.subject_graph.validation import date_interval, outside_coverage


def _quotes(value):
    if isinstance(value, dict):
        quotes = value.get("evidence_source_contents", [])
        if isinstance(quotes, list):
            yield from (q for q in quotes if isinstance(q, str) and q.strip())
        for key, child in value.items():
            if key != "evidence_source_contents":
                yield from _quotes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _quotes(child)


def exclude_outside_coverage(graph):
    """Keep dated background in descriptions, outside the reconstructed event list.

    Original date precision and source evidence are retained. Undated events and
    intervals overlapping coverage stay in the graph; this does not guess dates.
    """
    result = copy.deepcopy(graph)
    kept, excluded = [], []
    for index, event in enumerate(result.get("events", [])):
        if not isinstance(event, dict) or not outside_coverage(
                event, result.get("coverage_start"), result.get("coverage_end")):
            kept.append(event)
            continue
        excluded.append({"event_id": event["event_id"], "path": f"/events/{index}",
                         "message": "Event outside configured coverage retained as dated background",
                         "record": copy.deepcopy(event)})
        fields = [event["title"], event["start_time"], event["end_time"],
                  *event.get("descriptions", [])]
        start, end = (time_label(event[key]) or event[key]["value"] for key in ("start_time", "end_time"))
        dates = start if start == end else f"{start} to {end}"
        context = {
            "value": f"Background ({dates}): {event['title']['value']}"
                     + "".join(f". {item['value']}" for item in event.get("descriptions", [])),
            "evidence_source_contents": list(dict.fromkeys(_quotes(fields))),
            "reasons": list(dict.fromkeys(reason for item in fields
                                          for reason in item.get("reasons", []))),
        }
        if any(item.get("evidence_status") == "needs_review" for item in fields):
            context["evidence_status"] = "needs_review"
        result.setdefault("descriptions", []).append(context)
    result["events"] = kept
    removed_ids = {item["event_id"] for item in excluded}
    relations = []
    for relation in result.get("relations", []):
        links = relation.get("event_ids") if isinstance(relation, dict) else None
        if isinstance(links, list) and removed_ids.intersection(links):
            relation["event_ids"] = [eid for eid in links if eid not in removed_ids]
            if not relation["event_ids"]:
                continue
        relations.append(relation)
    if "relations" in result:
        result["relations"] = relations
    return result, excluded


def select_event_sources(target, sources, source_ids=None):
    """Use identifying plan passages; generic subject/role evidence is not an anchor.

    Several documents (including later retrospective accounts) can support one
    event. A document can also support several events. Prefer the planner's explicit
    allocation; older plans fall back to identifying passages. No publication-year
    filter or fallback to the complete source pool is used.
    """
    if isinstance(source_ids, list):
        return [s for s in sources if s["source_id"] in source_ids]
    normalized, _ = restore_source_quotes(target, [s["content"] for s in sources])
    anchors = list(_quotes([normalized.get("title"), normalized.get("descriptions", [])]))
    selected = [s for s in sources if any(q in s["content"] for q in anchors)]
    if not selected:
        anchors = list(_quotes([normalized.get("start_time"), normalized.get("end_time")]))
        selected = [s for s in sources if any(q in s["content"] for q in anchors)]
    return selected


def restrict_event_evidence(graph, targets, event_sources, sources):
    """Quarantine cross-event evidence/date conflicts, retaining their raw records.

    This is a source-boundary check, not semantic entailment. Unmatched quotations
    still use the existing evidence-repair path. A compound claim is not rewritten
    by guessing which words to keep. Within-document event attribution remains the
    reconstructor's responsibility. An out-of-event action is retained for review,
    never redated or made valid by widening the parent event's interval.
    """
    result = copy.deepcopy(graph)
    review = []
    all_texts = [s["content"] for s in sources]

    def conflicts(value, allowed):
        return [q for q in dict.fromkeys(_quotes(value))
                if any(q in text for text in all_texts)
                and not any(q in s["content"] for s in allowed)]

    def record(path, value, quotes, reason="Evidence belongs to sources outside this event"):
        review.append({"path": path, "message": reason, "record": copy.deepcopy(value),
                       "conflicting_quotes": quotes,
                       "source_ids": [s["source_id"] for s in sources
                                      if any(q in s["content"] for q in quotes)]})

    excluded_events = set()
    kept_events = []
    for ei, event in enumerate(result.get("events", [])):
        if not isinstance(event, dict) or event.get("event_id") not in event_sources:
            kept_events.append(event)
            continue
        eid, path = event["event_id"], f"/events/{ei}"
        allowed = event_sources[eid]
        if not allowed:
            record(path, event, [], "No source matched this event; detail reconstruction was skipped")
            excluded_events.add(eid)
            continue
        # Preserve the already planned occurrence if a detail call borrows a
        # different event's title/date. Subject relevance can be global context.
        for key in ("title", "start_time", "end_time"):
            bad = conflicts(event.get(key), allowed)
            if bad:
                record(path + "/" + key, event[key], bad)
                event[key] = copy.deepcopy(targets[eid][key])
        removed_participants = set()
        event_start = date_interval(event.get("start_time"))
        event_end = date_interval(event.get("end_time"))
        for key in ("descriptions", "participations", "actions", "transactions"):
            rows = event.get(key)
            if not isinstance(rows, list):
                continue  # Shape errors remain the validator's responsibility.
            kept = []
            for index, row in enumerate(rows):
                bad = conflicts(row, allowed)
                dependent = False
                outside = False
                if isinstance(row, dict):
                    if key == "actions":
                        dependent = row.get("actor_id") in removed_participants
                    elif key == "transactions":
                        dependent = any(isinstance(row.get(side), dict) and
                                        row[side].get("value") in removed_participants
                                        for side in ("from_entity_id", "to_entity_id"))
                    start = date_interval(row.get("start_time" if key == "participations" else "timestamp"))
                    end = date_interval(row.get("end_time" if key == "participations" else "timestamp"))
                    outside = bool(start and event_end and start[0] > event_end[1] or
                                   end and event_start and end[1] < event_start[0])
                if bad or dependent or outside:
                    reason = ("Evidence belongs to sources outside this event" if bad else
                              "Participation evidence was excluded for this event" if dependent else
                              "Record date is outside the event interval; event attribution needs review")
                    record(f"{path}/{key}/{index}", row, bad, reason)
                    if key == "participations" and isinstance(row, dict):
                        removed_participants.add(row.get("entity_id"))
                else:
                    kept.append(row)
            event[key] = kept
            if key == "participations":
                removed_participants.difference_update(
                    p.get("entity_id") for p in kept if isinstance(p, dict))
        if removed_participants and not event.get("participations"):
            record(path, event, [], "No supported participation remains for this event")
            excluded_events.add(eid)
        else:
            kept_events.append(event)
    result["events"] = kept_events
    kept_relations = []
    for ri, relation in enumerate(result.get("relations", [])):
        event_ids = relation.get("event_ids") if isinstance(relation, dict) else None
        if isinstance(event_ids, list) and excluded_events.intersection(event_ids):
            # A contextual relationship can span events; keep its surviving links.
            relation["event_ids"] = [eid for eid in event_ids if eid not in excluded_events]
            if not relation["event_ids"]:
                record(f"/relations/{ri}", relation, [], "Referenced events were excluded")
                continue
        kept_relations.append(relation)
    if isinstance(result.get("relations"), list):
        result["relations"] = kept_relations
    return result, review
