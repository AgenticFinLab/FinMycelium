"""Keep the first EPG and add separately budgeted evidence to its existing events."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from finmy.reconstruction_scope import read_reconstruction
from finmy.runner.context_budget import allocate_context
from finmy.runner.source_documents import prepare_documents


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _extras(output):
    value = getattr(output, "extras", None)
    return value if isinstance(value, dict) else {}


def _calls(output):
    usage = _extras(output).get("usage")
    value = usage.get("calls") if isinstance(usage, dict) else None
    return value if type(value) is int and value >= 0 else None


def _preserves_initial(initial, candidate):
    """Rows are append-only, including IDs, ordering, stage and detail selections."""
    if not isinstance(candidate, dict) or set(initial) != set(candidate):
        return False
    return all((isinstance(candidate[key], list) and candidate[key][:len(value)] == value)
               if isinstance(value, list) else candidate[key] == value
               for key, value in initial.items())


def _packed_sources(package, retained, packed):
    """Map allocated documents to exact, uniquely named evidence strings."""
    included = [row for row in packed["report"]["documents"] if row["included"]]
    if len(included) != len(packed["contents"]):
        raise ValueError("Allocated document/text mapping is inconsistent")
    docs = {row["document_id"]: row for row in retained}
    used = {row["document_id"] for row in package["source_document"]}
    result = []
    for record, content in zip(included, packed["contents"]):
        origin = docs[record["document_id"]]
        base = "EF_" + record["document_id"]
        identifier, suffix = base, 0
        while identifier in used:
            suffix += 1
            identifier = f"{base}_{suffix}"
        used.add(identifier)
        result.append({"document_id": identifier, "content": content,
            "title": origin.get("title"), "source_url": origin.get("url"),
            # Preserve the unnormalized publication value in retrieval artifacts;
            # it must never silently become the date of an extracted action.
            "published_at": None, "retrieval_document_id": record["document_id"],
            "event_ids": list(record.get("event_ids", origin.get("event_ids", []))),
            "source_ranges": record["source_ranges"]})
    return result


def _publish(initial, package, target, initial_dir, report):
    from finmy.person_epg.visualizer import render_person_epg
    from finmy.person_epg.compat_projection import project_person_epg
    result = copy.deepcopy(initial)
    result.extras = copy.deepcopy(_extras(initial))
    result.extras["person_epg"] = package
    directory = target / "event_enrichment" / "final"
    directory.mkdir(parents=True, exist_ok=True)
    _save(directory / "FinalPersonEPG.json", package)
    try:
        render_person_epg(package, directory / "FinalPersonEPG.html")
    except Exception as exc:
        _save(directory / "PersonRenderStatus.json", {"status": "failed", "error_type": type(exc).__name__})
    else:
        _save(directory / "PersonRenderStatus.json", {"status": "completed"})
    # A nullable v3 context activity need not have a participant. A legacy
    # projection failure must not erase supported canonical additions.
    try:
        projection = project_person_epg(package)
    except ValueError as exc:
        result.subject_graph = None
        result.extras.pop("subject_graph", None)
        _save(directory / "SubjectProjectionStatus.json", {
            "status": "unavailable", "reason": str(exc), "canonical_person_epg_preserved": True})
    else:
        result.subject_graph = projection
        result.extras["subject_graph"] = projection
        _save(directory / "FinalSubjectGraph.json", projection)
    result.extras["initial_usage"] = copy.deepcopy(_extras(initial).get("usage"))
    initial_calls = _calls(initial)
    result.extras["usage"] = {
        "calls": None if initial_calls is None else initial_calls + report["supplementary_model_calls"],
        "initial_builder_calls": initial_calls,
        "supplementary_model_calls": report["supplementary_model_calls"],
        "budgets_are_independent": True,
    }
    # Old sparse traces and cascade refer to the initial extraction, not the
    # augmented canonical graph. Do not falsely label them as replayable extras.
    result.extras["initial_run_directory"] = str(initial_dir)
    result.extras["run_directory"] = str(directory)
    result.extras["event_refinement"] = {
        "mode": "append_only_event_enrichment", "initial_builder_directory": str(initial_dir),
        "report_path": str(target / "event_refinement_report.json"),
        "legacy_cascade_scope": "initial_build_only", "initial_rows_preserved": True,
        "content_requires_review": True,
    }
    result.extras["person_acceptance"] = {
        "structure_passed": True, "initial_rows_preserved": True,
        "new_quotes_grounded": True, "semantic_approval": False,
        "status": "draft_requires_content_review",
    }
    if isinstance(getattr(result, "logs", None), list):
        result.logs.append("EventEnrichment")
    _save(directory / "EventEnrichmentProvenance.json", result.extras["event_refinement"])
    return result, str(directory)


def build_with_draft_event_followup(contents, query, keywords, config, save_dir,
                                    *, documents, filtered=None, usage=None, build=None,
                                    completion=None, search=None, parse=None, progress=None,
                                    enrichment_completion=None, enrich=None,
                                    supplementary_sources=None):
    """Run the original builder once, then append verified event-local additions.

    The obsolete filtered/completion keyword arguments are accepted but unused.
    First-phase inputs and artifacts never compete with supplementary evidence.
    Supplemental retrieval, evidence characters and model calls have their
    own finite limits. A failed event leaves its initial rows untouched.
    """
    if build is None:
        from finmy.subject_graph.runner import build_from_contents
        build = build_from_contents
    from finmy.runner.draft_event_search import draft_event_options, collect_draft_event_sources
    from finmy.runner.event_followup_config import followup_enabled
    enabled = followup_enabled(config)
    options, _ = draft_event_options(config) if enabled else ({}, {})
    if supplementary_sources is not None and (
            not isinstance(supplementary_sources, list)
            or any(not isinstance(row, dict) or not isinstance(row.get("raw_text"), str)
                   for row in supplementary_sources)):
        raise ValueError("supplementary_sources must be a list of archived source documents")
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    initial_usage = copy.deepcopy(usage or {})
    supplemental_usage = {}
    report = {"version": "event-enrichment-v2", "status": "initial_build",
              "mode": "append_only_event_enrichment", "event_source": "initial_person_epg",
              "initial_builder_directory": None, "selected_builder_directory": None,
              "refinement_attempted": False, "max_refinement_builds": 0,
              "supplementary_model_calls": 0, "semantic_improvement_verified": False,
              "budgets": {"initial_content_limit": (config.get("all_content_config") or {}).get("max_content_length", 120000),
                          "supplementary_content_limit": options.get("max_content_length", 120000),
                          "supplementary_search_model_call_limit": options.get("max_search_model_calls", 30),
                          "supplementary_model_call_limit": options.get("max_model_calls", 24)}}
    _save(target / "initial_builder_input_contents.json", contents)
    _save(target / "builder_input_contents.json", contents)

    def log(message):
        if progress:
            progress(message)

    try:
        initial, initial_dir = build(contents, query, keywords, config)
    except Exception as exc:
        report.update(status="initial_build_failed", error_type=type(exc).__name__)
        _save(target / "event_refinement_report.json", report)
        raise
    report.update(initial_builder_directory=str(initial_dir), selected_builder_directory=str(initial_dir),
                  initial_builder_calls=_calls(initial))
    selected = initial, initial_dir
    try:
        if not enabled:
            report["status"] = "disabled_or_unsupported_builder"
            return selected
        package = _extras(initial).get("person_epg")
        if not isinstance(package, dict):
            report["status"] = "no_person_package"
            return selected
        events = package.get("event", [])
        report["initial_event_count"] = len(events) if isinstance(events, list) else 0
        _save(target / "initial_person_epg.json", package)
        if not events:
            report["status"] = "no_existing_events"
            return selected
        if options["max_model_calls"] < 2:
            report["status"] = "supplementary_model_budget_exhausted"
            return selected
        reconstruction = read_reconstruction(config)
        supplemental_usage = {"started_at": time.monotonic(), "search_calls": 0, "parse_calls": 0,
                              "followup_queries": 0}
        if supplementary_sources is None:
            log(f"Event enrichment: Searching around {len(events)} existing events with a separate evidence budget.")
            added_sources = collect_draft_event_sources(package, query, keywords,
                reconstruction["subject"], config, target, progress=progress,
                usage=supplemental_usage, search=search, parse=parse, known_documents=documents)
        else:
            log("Event enrichment: Reusing archived supplementary sources without new acquisition.")
            added_sources = copy.deepcopy(supplementary_sources)
            report["acquisition_reused"] = True
        report["acquisition_elapsed_seconds"] = max(0.0, time.monotonic() - supplemental_usage["started_at"])
        report["new_source_count"] = len(added_sources)
        if not added_sources:
            report["status"] = "no_new_sources"
            return selected
        candidate_dir = target / "event_enrichment"
        candidate_config = copy.deepcopy(config)
        retained = prepare_documents(added_sources, query, keywords, candidate_config,
            candidate_dir / "sources", document_id_offset=len(documents))
        report["new_retained_source_count"] = len(retained)
        candidate_config["all_content_config"] = {
            "max_content_length": options["max_content_length"],
            "max_document_chars": options["max_document_chars"],
            "allocation_strategy": "event",
        }
        packed = allocate_context(retained, [], candidate_config, include_metadata=True)
        sources = _packed_sources(package, retained, packed)
        _save(candidate_dir / "context_budget_report.json", packed["report"])
        _save(candidate_dir / "supplementary_input_contents.json", packed["contents"])
        _save(candidate_dir / "supplementary_sources.json", sources)
        report["supplementary_input_chars"] = sum(len(row["content"]) for row in sources)
        report["new_admitted_document_ids"] = [row["document_id"] for row in sources]
        if not sources:
            report["status"] = "no_new_sources_admitted"
            return selected
        if enrich is None:
            from finmy.runner.event_enrichment import enrich_events
            enrich = enrich_events
        report["refinement_attempted"] = True
        log("Event enrichment: Adding supported activities and details without rebuilding the initial EPG.")
        candidate, enrichment_report = enrich(copy.deepcopy(package), sources, config, candidate_dir,
                                              completion=enrichment_completion, progress=progress)
        _save(candidate_dir / "enrichment_report.json", enrichment_report)
        actual = enrichment_report.get("model_calls")
        if type(actual) is not int or not 0 <= actual <= options["max_model_calls"]:
            report["status"] = "enrichment_usage_invalid"
            return selected
        report["supplementary_model_calls"] = actual
        if not _preserves_initial(package, candidate):
            report["status"] = "enrichment_rejected"
            report["reason"] = "initial_rows_changed_or_removed"
            return selected
        from finmy.person_epg.validation import validate_person_epg
        validation = validate_person_epg(candidate)
        if not validation["valid"]:
            report["status"] = "enrichment_rejected"
            report["reason"] = "invalid_person_epg"
            report["validation_errors"] = validation["errors"][:10]
            return selected
        if not any(len(candidate[table]) > len(package[table])
                   for table in ("activity", "activity_detail", "activity_relation",
                                 "event_activity", "event_activity_detail")):
            report["status"] = "no_changes"
            return selected
        selected = _publish(initial, candidate, target, initial_dir, report)
        report.update(status="enriched", initial_rows_preserved=True,
                      selected_builder_directory=selected[1])
        return selected
    except Exception as exc:
        report.update(status="supplementary_processing_failed", error_type=type(exc).__name__)
        log(f"Event enrichment: Supplementary processing failed ({type(exc).__name__}); retaining the initial EPG.")
        return selected
    finally:
        report["initial_usage"] = initial_usage
        report["supplemental_usage"] = copy.deepcopy(supplemental_usage)
        _save(target / "event_refinement_report.json", report)
        _save(target / "evidence_supply_usage.json", {"initial": initial_usage,
                                                     "supplementary": supplemental_usage,
                                                     "budgets_are_independent": True})
