"""Bounded native SubjectGraph reconstruction with injectable model and persistence."""
import copy
import hashlib
import json

from finmy.reconstruction_scope import read_reconstruction
from finmy.subject_graph.prompts import EVENT, PLANNER, REPAIR, system_prompt
from finmy.subject_graph.schema import SCHEMA_VERSION
from finmy.subject_graph.validation import validate_subject_graph
from finmy.subject_graph.evidence import restore_source_quotes, flag_evidence_issues


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
    elif next(e for e in entities if e["entity_id"] == subject["subject_id"]).get("entity_type") != kind:
        raise ValueError("SubjectPlanner changed the configured subject type")
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
    for target in events:
        payload = {**context, "EntityRegistry": entities, "TargetEvent": target}
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

    def validate(candidate, allow_unverified_evidence=False):
        report = validate_subject_graph(candidate, source_texts=source_texts,
                                        allow_unverified_evidence=allow_unverified_evidence)
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
        graph = call("SubjectGraphRepair", REPAIR, {**context, "ProposedGraph": graph, "ValidationReport": report})
        # Coverage belongs to the request configuration, not the repair model.
        coverage_changes = []
        if isinstance(graph, dict):
            for key in ("coverage_start", "coverage_end"):
                if graph.get(key) != subject[key]:
                    coverage_changes.append({"field": key, "before": graph.get(key), "after": subject[key]})
                graph[key] = subject[key]
        save(coverage_changes, "subject_repair_metadata_restoration")
        graph, repair_quote_changes = restore_source_quotes(graph, source_texts)
        save(quote_changes + repair_quote_changes, "subject_quote_restoration")
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
    return graph, state, report
