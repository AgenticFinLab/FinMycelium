"""Bounded native SubjectGraph reconstruction with injectable model and persistence."""
import copy
import hashlib
import json
import logging

from finmy.reconstruction_scope import read_reconstruction
from finmy.subject_graph.prompts import COVERAGE, EVENT, EVENT_REVIEW, PLANNER, REPAIR, system_prompt
from finmy.subject_graph.coverage_review import apply_coverage_additions, find_statement_duplicates
from finmy.subject_graph.consistency_review import apply_event_corrections, apply_event_merges, correction_exclusions
from finmy.subject_graph.schema import SCHEMA_VERSION
from finmy.subject_graph.repair import apply_graph_patch
from finmy.subject_graph.validation import validate_subject_graph
from finmy.subject_graph.evidence import restore_source_quotes, flag_evidence_issues
from finmy.subject_graph.event_sources import select_event_sources, restrict_event_evidence


def _options(config):
    builder = config.get("builder_config", config)
    opts = builder.get("subject_graph", {})
    if not isinstance(opts, dict):
        raise ValueError("subject_graph must be a mapping")
    max_events = opts.get("max_events", 60)
    repairs = opts.get("repair_attempts", 1)
    if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 200:
        raise ValueError("subject_graph.max_events must be an integer from 1 to 200")
    if isinstance(repairs, bool) or not isinstance(repairs, int) or repairs not in (0, 1):
        raise ValueError("subject_graph.repair_attempts must be 0 or 1")
    return max_events, repairs


def _identity(subject, kind):
    return {"entity_id": subject["subject_id"], "name": {
        "value": subject["name"], "evidence_source_contents": [],
        "reasons": ["configured_identity"], "confidence": None,
    }, "aliases": list(subject["aliases"]), "entity_type": kind, "attributes": {}}


def run_subject_build(build_input, config, complete, save):
    """Return (validated graph, execution state, report); never calls search or a DB.

    complete(agent_name, system_prompt, payload) returns a parsed JSON object.
    save(value, basename) writes a JSON trace. Invalid outputs remain diagnostic
    traces; only the calling builder publishes FinalSubjectGraph after success.
    """
    reconstruction = read_reconstruction(config)
    if reconstruction["mode"] not in ("person", "company"):
        raise ValueError("Native subject reconstruction requires person or company mode")
    max_events, repairs = _options(config)
    subject = reconstruction["subject"]
    kind = "individual" if reconstruction["mode"] == "person" else "organization"
    sources = []
    for i, sample in enumerate(build_input.samples):
        content = sample.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Subject reconstruction requires nonempty source texts")
        sources.append({"source_id": getattr(sample, "sample_id", None) or f"SOURCE_{i+1}",
                        "content": content})
    if not sources:
        raise ValueError("Subject reconstruction requires at least one source")
    source_texts = [source["content"] for source in sources]
    context = {"SubjectScope": reconstruction, "Query": build_input.user_query.query_text,
               "Keywords": build_input.user_query.key_words, "Sources": sources}
    save(context, "subject_build_input")
    save(reconstruction, "reconstruction_scope")
    state = {"agent_results": [], "agent_executed": []}

    def call(name, task, payload):
        result = complete(name, system_prompt(task), copy.deepcopy(payload))
        save(result, f"{name}-{len(state['agent_executed'])+1}-Result")
        state["agent_executed"].append(name)
        state["agent_results"].append({name: result})
        if not isinstance(result, dict):
            raise ValueError(f"{name} must return a JSON object; inspect its saved result")
        return result

    plan = call("SubjectPlanner", PLANNER, context)
    events = plan.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Subject reconstruction produced no supported in-scope events; inspect SubjectPlanner result")
    if len(events) > max_events:
        raise ValueError(f"Subject plan contains {len(events)} events, exceeding max_events={max_events}; no events were truncated")
    entities = copy.deepcopy(plan.get("entities"))
    if not isinstance(entities, list) or any(not isinstance(e, dict) for e in entities):
        raise ValueError("SubjectPlanner must return an entities list")
    identifiers = [e.get("entity_id") for e in entities]
    if any(not isinstance(i, str) or not i.strip() for i in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("SubjectPlanner contains missing or duplicate entity IDs")
    if subject["subject_id"] not in identifiers:
        entities.insert(0, _identity(subject, kind))
    else:
        principal = next(e for e in entities if e["entity_id"] == subject["subject_id"])
        if principal.get("entity_type") != kind:
            name = principal.get("name", {})
            name = name.get("value") if isinstance(name, dict) else None
            normalize = lambda value: " ".join(value.casefold().split()) if isinstance(value, str) else None
            identities = {normalize(value) for value in [subject["name"], *subject["aliases"]]}
            if not normalize(name) or normalize(name) not in identities:
                raise ValueError("SubjectPlanner assigned the configured subject ID to an unrecognized name; "
                                 "inspect SubjectPlanner result before changing its entity type")
            # Mode is user configuration, not a fact for the model to classify.
            save({"entity_id": subject["subject_id"], "name": name,
                  "before": principal.get("entity_type"), "after": kind},
                 "subject_identity_normalization")
            principal["entity_type"] = kind
            logging.info("Subject identity: Applied configured entity type '%s'.", kind)
    ids = [e.get("event_id") if isinstance(e, dict) else None for e in events]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("SubjectPlanner contains missing or duplicate event IDs")
    graph_id = "SG_" + hashlib.sha256(json.dumps(reconstruction, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    graph = {"schema_version": SCHEMA_VERSION, "graph_id": graph_id,
             "subject_id": subject["subject_id"], "subject_type": kind,
             "coverage_start": subject["coverage_start"], "coverage_end": subject["coverage_end"],
             "title": copy.deepcopy(plan.get("title")), "descriptions": copy.deepcopy(plan.get("descriptions", [])),
             "entities": entities, "events": [], "relations": copy.deepcopy(plan.get("relations", []))}
    if not isinstance(graph["relations"], list):
        raise ValueError("SubjectPlanner relations must be a list")
    targets = {event["event_id"]: event for event in events}
    planned_sources = plan.get("event_sources", {})
    if not isinstance(planned_sources, dict):
        planned_sources = {}
    event_sources = {eid: select_event_sources(target, sources, planned_sources.get(eid))
                     for eid, target in targets.items()}
    source_scope = {eid: [source["source_id"] for source in selected]
                    for eid, selected in event_sources.items()}
    save(source_scope, "subject_event_sources")
    for target in events:
        selected = event_sources[target["event_id"]]
        if not selected:
            # Archive the sparse plan; evidence restriction below will exclude it
            # rather than invent participation from unrelated documents.
            graph["events"].append({**copy.deepcopy(target), "participations": [],
                                    "actions": [], "transactions": []})
            continue
        payload = {**context, "Sources": selected, "EntityRegistry": entities, "TargetEvent": target}
        result = call("SubjectEventReconstructor", EVENT, payload)
        event = result.get("event")
        if not isinstance(event, dict) or event.get("event_id") != target["event_id"]:
            raise ValueError("SubjectEventReconstructor must preserve the target event_id")
        relations = result.get("relations", [])
        if not isinstance(relations, list):
            raise ValueError("SubjectEventReconstructor relations must be a list")
        graph["events"].append(event)
        graph["relations"].extend(relations)
    save(graph, "RawSubjectGraph")
    graph, quote_changes = restore_source_quotes(graph, source_texts)
    save(quote_changes, "subject_quote_restoration")
    graph, event_review = restrict_event_evidence(graph, targets, event_sources, sources)
    save(event_review, "subject_event_evidence_review")

    def validate(candidate, allow_unverified_evidence=False):
        report = validate_subject_graph(candidate, source_texts=source_texts,
                                        allow_unverified_evidence=allow_unverified_evidence)
        report["warnings"].extend({"path": item["path"],
                                   "message": item["message"] + "; original record saved in subject_event_evidence_review.json"}
                                  for item in event_review)
        report["warnings"].extend({"path": f"/events/{i}",
                                   "message": "Planner omitted event_sources; allocation used identifying passages only"}
                                  for i, event in enumerate(events)
                                  if not isinstance(planned_sources.get(event["event_id"]), list))
        expected = {"schema_version": SCHEMA_VERSION, "graph_id": graph_id,
                    "subject_id": subject["subject_id"], "subject_type": kind,
                    "coverage_start": subject["coverage_start"], "coverage_end": subject["coverage_end"]}
        if isinstance(candidate, dict):
            for key, value in expected.items():
                if candidate.get(key) != value:
                    report["errors"].append({"path": f"/{key}", "message": "Configured graph identity/coverage must be preserved"})
            repaired_events = candidate.get("events")
            if not isinstance(repaired_events, list) or not 1 <= len(repaired_events) <= max_events:
                report["errors"].append({"path": "/events", "message": "A nonempty event list within max_events is required"})
            registry = candidate.get("entities", [])
            if isinstance(registry, list):
                principal = next((e for e in registry if isinstance(e, dict)
                                  and e.get("entity_id") == subject["subject_id"]), {})
                name = principal.get("name", {})
                name = name.get("value") if isinstance(name, dict) else None
                normalize = lambda text: " ".join(text.casefold().split()) if isinstance(text, str) else None
                identities = {normalize(n) for n in [subject["name"], *subject["aliases"]]}
                if normalize(name) not in identities:
                    report["errors"].append({"path": "/entities", "message": "Subject entity must match its configured name or alias"})
        report["valid"] = not report["errors"]
        return report

    report = validate(graph)
    save(report, "subject_graph_validation")
    if not report["valid"] and repairs:
        try:
            patch = call("SubjectGraphRepair", REPAIR,
                         {**context, "EventSourceIds": source_scope,
                          "ProposedGraph": graph, "ValidationReport": report})
            graph = apply_graph_patch(graph, patch, report["errors"])
        except ValueError as exc:
            # Keep the assembled graph if the repair response is unusable.
            # Evidence-only issues may still use the existing review fallback;
            # structural errors remain blocking after full validation below.
            save({"error": str(exc)}, "subject_repair_error")
        save(graph, "SubjectGraphAfterRepair")
        graph, repair_quote_changes = restore_source_quotes(graph, source_texts)
        save(quote_changes + repair_quote_changes, "subject_quote_restoration")
        graph, additional_review = restrict_event_evidence(graph, targets, event_sources, sources)
        event_review.extend(additional_review)
        save(event_review, "subject_event_evidence_review")
        report = validate(graph)
        save(report, "subject_graph_validation")
    if not report["valid"]:
        graph, pending = flag_evidence_issues(graph, source_texts)
        save(pending, "subject_evidence_review")
        report = validate(graph, allow_unverified_evidence=True)
        save(report, "subject_graph_validation")
    if not report["valid"]:
        details = "; ".join(f"{e['path']}: {e['message']}" for e in report["errors"][:3])
        raise ValueError(f"SubjectGraph failed validation ({len(report['errors'])} errors): {details}. See subject_graph_validation.json")
    # Focus each detail review on one occurrence and its already assigned sources.
    # Failures keep the usable graph; no search or review loop is introduced.
    detail_reviews = []
    corrected_records = []
    for target in list(graph["events"]):
        eid = target["event_id"]
        logging.info("Event detail review: %s; checking chronology, attribution and omissions once. No search.", eid)
        correction_report = {"accepted": [], "rejected": []}
        try:
            additions = call("SubjectEventReviewer", EVENT_REVIEW,
                             {**context, "Sources": event_sources[eid], "TargetEvent": target,
                              "EntityRegistry": entities, "ExcludedRecords": event_review})
            additions = dict(additions)  # Keep the raw response in execution state intact.
            if set(additions) - {"corrections", "event_additions", "missing_events"}:
                raise ValueError("Unexpected detail review fields")
            if (additions.get("missing_events") != []
                    or not isinstance(additions.get("event_additions"), list)
                    or len(additions["event_additions"]) > 1
                    or any(not isinstance(row, dict) or row.get("event_id") != eid
                           for row in additions["event_additions"])):
                raise ValueError("Detail review may supplement only its target event")
            graph, correction_report = apply_event_corrections(
                graph, eid, additions.pop("corrections", []), event_sources, sources)
            corrected_records.extend(correction_exclusions(eid, correction_report))
            logging.info("Event consistency: %s; %s correction group(s) accepted; %s rejected.",
                         eid, len(correction_report["accepted"]), len(correction_report["rejected"]))
            graph, event_sources, detail_report = apply_coverage_additions(
                graph, additions, event_sources, sources, max_events, corrected_records)
        except Exception as exc:
            detail_report = {"status": "failed", "error": str(exc), "accepted": [], "rejected": []}
            logging.warning("Event detail review: %s unavailable; keeping existing content. No further review.", eid)
        detail_reviews.append({"event_id": eid, **detail_report, "corrections": correction_report})
        save(detail_reviews, "subject_event_detail_review")
    # One final check for omitted occurrences, using the enriched graph.
    logging.info("Coverage review: Checking existing sources for material omissions. No search.")
    try:
        additions = call("SubjectCoverageReviewer", COVERAGE,
                         {**context, "ConstructedGraph": graph, "EntityRegistry": entities,
                          "EventSourceIds": source_scope, "ExcludedRecords": event_review + corrected_records})
        additions = dict(additions)
        merges = additions.pop("event_merges", [])
        graph, event_sources, coverage = apply_coverage_additions(
            graph, additions, event_sources, sources, max_events, corrected_records)
        graph, event_sources, merge_report = apply_event_merges(
            graph, merges, event_sources, sources)
        coverage["event_merges"] = merge_report
        logging.info("Event merge review: %s accepted; %s rejected. No search.",
                     len(merge_report["accepted"]), len(merge_report["rejected"]))
        save({eid: [s["source_id"] for s in selected] for eid, selected in event_sources.items()},
             "subject_event_sources")
    except Exception as exc:
        coverage = {"status": "failed", "error": str(exc), "accepted": [], "rejected": []}
        logging.warning("Coverage review: Unavailable; keeping existing graph. No further review.")
    save(coverage, "subject_coverage_review")
    duplicates = find_statement_duplicates(graph)
    save(duplicates, "subject_statement_duplicates")
    report = validate(graph, allow_unverified_evidence=True)
    for item in detail_reviews:
        if item.get("status") == "failed" or item["corrections"].get("rejected"):
            report["warnings"].append({"path": "/events", "message":
                f"Chronology/attribution review incomplete for {item['event_id']}; see subject_event_detail_review.json"})
    if coverage.get("event_merges", {}).get("rejected"):
        report["warnings"].append({"path": "/events", "message":
            "Some duplicate event merges were rejected; see subject_coverage_review.json"})
    report["warnings"].extend({"path": "/events", "message":
        f"Possible repeated statement {item['event_id']}/{item['action_id']}; see subject_statement_duplicates.json"}
        for item in duplicates)
    save(report, "subject_graph_validation")
    return graph, state, report
