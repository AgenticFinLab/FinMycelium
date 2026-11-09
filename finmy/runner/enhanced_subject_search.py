"""Bridge shared search into subject reconstruction without rebuilding its graph.

The search agent owns acquisition and source selection. This adapter exports the
selected original bodies, leaving the person pipeline's single evidence budget
and EPG schema/organization/rendering stages in charge of downstream processing.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, replace
import json
import math
import logging
from pathlib import Path
import time

from finmy.search.state import SearchConfig, SearchState, digest, write_json
from finmy.runner.search_failures import TERMINAL, phase_status, read_task_usage, record_failure


def enhanced_search_enabled(config):
    """Compatibility probe: search always uses the agent, including old YAML."""
    options = config.get("search_config", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("search_config must be a mapping")
    mode = options.get("mode", "agent")
    if mode not in {"simple", "agent"}:
        raise ValueError("search_config.mode must be agent (simple is a deprecated alias)")
    if mode == "simple":
        logging.getLogger(__name__).warning(
            "search_config.mode=simple is retired; using the shared search agent")
    return True


def agent_search_config(config):
    """Migrate old acquisition settings once; explicit agent settings take priority."""
    enhanced_search_enabled(config)
    options = config.get("search_config") or {}
    settings = options.get("enhancement") or {}
    if not isinstance(settings, dict):
        raise ValueError("search_config.enhancement must be a mapping")
    result = copy.deepcopy(settings)
    legacy = config.get("subject_search") or {}
    if not isinstance(legacy, dict):
        raise ValueError("subject_search must be a mapping")
    for old, new in (("providers", "providers"), ("max_search_calls", "max_search_requests"),
                     ("max_parse_calls", "max_read_sources")):
        if old in legacy:
            result.setdefault(new, copy.deepcopy(legacy[old]))
    # Publication filters are independent of the person's event coverage.
    # Old YAML allowed year/month precision; the provider contract uses days.
    from finmy.reconstruction_scope import date_bounds
    for key, bound in (("publication_start", 0), ("publication_end", 1)):
        if key not in result and legacy.get(key) is not None:
            result[key] = date_bounds(legacy[key])[bound].isoformat()
    # Only old YAML lacking the agent section inherits the online pipeline
    # model. Existing agent configurations retain independent search defaults.
    if "enhancement" not in options:
        result.setdefault("allow_network", True)
        builder = config.get("builder_config", config)
        model = config.get("lm_name") or builder.get("lm_name")
        if model:
            result.setdefault("lm_name", model)
    content_limit = (config.get("all_content_config") or {}).get("max_content_length")
    if content_limit is not None:
        result.setdefault("max_builder_material_chars", content_limit)
    return result


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + " must be a finite nonnegative integer")
    return value


def _task(query, keywords, subject, config, event=None, supplied=None):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search requires the original nonempty request")
    if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
        raise ValueError("Search keywords must be a list of strings")
    builder = config.get("builder_config", config)
    mode = (builder.get("reconstruction") or {}).get("mode", "event")
    if mode not in {"event", "person", "company"}:
        raise ValueError("Search requires event or subject reconstruction")
    if mode == "event":
        result = {"target_type": "event", "target_name": query,
                  "query_text": query, "key_words": list(keywords)}
    else:
        if not isinstance(subject, dict) or not isinstance(subject.get("name"), str) or not subject["name"].strip():
            raise ValueError("Subject search requires a nonempty subject name")
        result = {"target_type": mode, "target_name": subject["name"],
                  "query_text": query, "key_words": list(keywords),
                  "subject_scope": copy.deepcopy(subject)}
    if event is not None:
        eid, label = event.get("event_id"), event.get("event_label") or event.get("label")
        if not isinstance(eid, str) or not eid.strip() or not isinstance(label, str) or not label.strip():
            raise ValueError("Event search needs an event ID and label")
        result.update(target_type="event", target_name=label, original_query=query,
                      event_id=eid,
                      query_text=query + "\nResearch this " + ("candidate storyline" if event.get("discovery_candidate") else "existing event") + " involving "
                      + subject["name"] + ": " + label,
                      existing_event={key: copy.deepcopy(event[key]) for key in
                          ("event_id", "event_label", "label", "summary", "event_terms",
                           "entity_clues", "activity_clues", "year_clues", "domain_id",
                           "scope", "person_connection", "questions") if key in event},
                      event_clues_are_evidence=False)
    if supplied is not None:
        if event is not None or not isinstance(supplied, dict):
            raise ValueError("A task override is only supported for initial subject search")
        allowed = {"target_type", "target_name", "query_text", "key_words", "seed_urls", "local_files", "subject_scope"}
        if set(supplied) - allowed:
            raise ValueError("Unsupported subject search task fields")
        for key in ("target_type", "target_name", "query_text", "key_words", "subject_scope"):
            if key in supplied and supplied[key] != result.get(key):
                raise ValueError("Search task cannot override configured subject scope: " + key)
        for key in ("seed_urls", "local_files"):
            if key in supplied:
                if not isinstance(supplied[key], list) or any(not isinstance(v, str) or not v.strip() for v in supplied[key]):
                    raise ValueError(key + " must be a list of nonempty strings")
                result[key] = list(supplied[key])
    return result


def _documents(root, task_id, result, event):
    """Validate the handoff, then export full inspected bodies with provenance."""
    def exclude_source(sid, version, error):
        failure = {"stage": "source_integrity", "source_id": sid, "version": version,
                   "error_type": type(error).__name__}
        if failure not in result.setdefault("errors", []):
            result["errors"].append(failure)
        gap = "Some selected originals failed integrity validation and were excluded."
        if gap not in result.setdefault("gaps", []):
            result["gaps"].append(gap)
        if result.get("status") == "finished":
            result["status"] = "insufficient"

    if result.get("status") not in {"finished", "insufficient", "paused", "failed", "limit"}:
        return []
    run_dir = Path(root) / task_id / "runs" / "initial"
    if result.get("status") != "finished" and not (run_dir / "builder_input.json").exists():
        return []
    state = SearchState(root, task_id)
    handoff = state.run_dir / "builder_input.json"
    if not handoff.exists():
        if result.get("status") != "finished":
            return []
        raise ValueError("Finished search has no saved Builder handoff")
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("samples") == [] and result.get("status") != "finished":
        return []
    if (not isinstance(payload, dict) or not isinstance(payload.get("samples"), list)
            or not payload["samples"] or any(not isinstance(s, dict)
                or not isinstance(s.get("content"), str) or not s["content"].strip()
                or not isinstance(s.get("raw_data_id"), str) for s in payload["samples"])):
        raise ValueError("Finished search has no usable Builder samples")
    expected_query = {"query_text": state.data["task"]["query_text"],
                      "key_words": state.data["task"].get("key_words", [])}
    user_query = payload.get("user_query")
    if (not isinstance(user_query, dict) or
            {k: v for k, v in user_query.items() if k != "extras"} != expected_query):
        raise ValueError("Search handoff differs from its original task scope")
    extras = user_query.get("extras", {})
    if (not isinstance(extras, dict) or set(extras) - {"source_registry"}
            or not isinstance(extras.get("source_registry", {}), dict)):
        raise ValueError("Invalid search handoff metadata")
    registry = extras.get("source_registry", {})
    path = state.run_dir / "complete_material.json"
    if not path.exists():
        # Older search runs selected exact read passages. Export those saved
        # selections, never upgrade them into supposedly complete documents.
        selection = json.loads((state.run_dir / "selection.json").read_text(encoding="utf-8"))
        if not selection.get("selected"):
            raise ValueError("Search handoff has no recorded source selections")
        from finmy.search.sources import SourceStore
        store = SourceStore(state)
        chosen = {}
        for row in selection["selected"]:
            sid, version = row["source_id"], row["version"]
            doc = store.document(sid, version)
            if doc.get("status") not in {"success", "partial"}:
                continue
            block, start, end = row["block"], row["start"], row["end"]
            if any(type(v) is not int for v in (block, start, end)) or not 0 <= block < len(doc["blocks"]):
                raise ValueError("Invalid legacy search selection")
            body = doc["blocks"][block]["text"]
            if not 0 <= start < end <= len(body):
                raise ValueError("Invalid legacy search offsets")
            covered = start
            for lo, hi in sorted((r["start"], r["end"]) for r in state.data["sources"][sid].get("read_ranges", [])
                                 if r["version"] == version and r["block"] == block):
                if lo <= covered:
                    covered = max(covered, hi)
            if covered < end:
                raise ValueError("Legacy handoff passage was not inspected")
            chosen.setdefault((sid, version), []).append(body[start:end])
        records = [(sid, version, "\n\n".join(parts), "partial") for (sid, version), parts in chosen.items()]
    else:
        from finmy.search.handoff import materialize_complete, source_selection_status
        from finmy.search.sources import SourceStore, SourceIntegrityError
        complete = json.loads(path.read_text(encoding="utf-8"))
        source_errors = []
        full = materialize_complete(state, complete, source_errors=source_errors)
        for error in source_errors:
            exclude_source(error["source_id"], error["version"],
                           SourceIntegrityError(error["source_id"], "Unverifiable saved source"))
        if payload.get("user_query") != full["user_query"]:
            raise ValueError("Search handoff scope differs from retained material")
        store = SourceStore(state)
        selected_ids = {s["source_id"] for s in complete["selected"]}
        if any(s["raw_data_id"] not in selected_ids for s in payload["samples"]):
            raise ValueError("Search handoff references unselected sources")
        records = []
        usable_ids = {sample["raw_data_id"] for sample in full["samples"]}
        for entry in complete["selected"]:
            sid, version = entry["source_id"], entry["version"]
            if sid not in usable_ids:
                continue
            try:
                problem = source_selection_status(state, sid, version)
                if problem is not None:
                    raise SourceIntegrityError(sid, "Selected source is not eligible: " + problem)
                doc = store.document(sid, version)
            except (SourceIntegrityError, KeyError, TypeError, AttributeError) as error:
                exclude_source(sid, version, error)
                continue
            body = "\n\n".join(doc["blocks"][i]["text"] for i in entry["blocks"])
            records.append((sid, version, body, entry["source_status"]))
    output = []
    for sid, version, body, status in records:
        from finmy.search.language_policy import assess
        if not assess(store.document(sid, version), state.config.source_languages)['allowed']:
            exclude_source(sid, version, ValueError('Source language excluded'))
            continue
        if not body.strip():
            continue
        source = state.data["sources"][sid]
        discoveries = source.get("discoveries", [])
        metadata = registry.get(sid, {})
        if (not isinstance(metadata, dict) or metadata.get("source_id", sid) != sid or
                ("version" in metadata and metadata["version"] != version) or
                ("versions" in metadata and version not in metadata["versions"])):
            exclude_source(sid, version, ValueError("Search source metadata differs from selected version"))
            continue
        published = (metadata.get("published_at") if metadata else
                     next((d.get("published_at") for d in discoveries if d.get("published_at")), None))
        row = {"raw_text": body, "title": metadata.get("title", source.get("title", "")),
               "url": metadata.get("url", source["url"]),
               "published_at": published, "source": "enhanced", "source_id": sid,
               "source_version": version, "source_status": status,
               "event_search_status": result["status"],
               "search_run_directory": str(state.run_dir),
               "discoveries": copy.deepcopy(discoveries)}
        for key in ("published_at_raw", "publication_candidates", "reused_from"):
            if key in metadata:
                row[key] = copy.deepcopy(metadata[key])
        if event is not None:
            label = event.get("event_label") or event["label"]
            terms = event.get("event_terms", [label])
            row.update(event_ids=[event["event_id"]], event_labels=[label], event_terms=list(terms),
                       event_routes=[{"event_id": event["event_id"], "event_label": label,
                                      "event_terms": list(terms), "search_task_id": task_id,
                                      "search_status": result["status"]}])
        output.append(row)
    return output


def _collect_enhanced_sources(query, keywords, subject, config, save_dir, *,
                             progress=None, usage=None, events=None, dependencies=None,
                             task=None, initial_events=False):
    """Acquire original sources under one persisted phase budget.

    Supplementary tasks share search/read/model ceilings; creating one task per
    event cannot multiply those ceilings. Full selected bodies are archived;
    the caller applies its one initial/supplementary content budget afterwards.
    """
    from finmy.search.pipeline import run_search
    from finmy.search.agent import LmbaseModel
    from finmy.search.sources import fetch_public
    from finmy.search.tools import http_transport

    shared = SearchConfig(**agent_search_config(config))
    dependencies = dict(dependencies or {})
    if set(dependencies) - {"model", "transport", "fetcher", "max_steps", "run_search"}:
        raise ValueError("Unsupported shared search dependencies")
    runner = dependencies.pop("run_search", run_search)
    supplied_model = dependencies.pop("model", None)
    supplied_transport = dependencies.pop("transport", None)
    supplied_fetcher = dependencies.pop("fetcher", None)
    usage = usage if usage is not None else {}
    event_tasks = events is not None
    supplemental = event_tasks and not initial_events
    if event_tasks and (not isinstance(events, list) or any(not isinstance(e, dict) for e in events)):
        raise ValueError("Existing events must be a list of event descriptors")
    entries = events if event_tasks else [None]
    if initial_events and task is not None:
        supplied = _task(query, keywords, subject, config, supplied=task)
        tasks = [_task(query, keywords, subject, config, e) for e in entries]
        for child in tasks:
            for key in ("seed_urls", "local_files"):
                if key in supplied:
                    child[key] = supplied[key]
    else:
        tasks = [_task(query, keywords, subject, config, e, task) for e in entries]
    if len({t.get("event_id") for t in tasks}) != len(tasks):
        raise ValueError("Existing event IDs must be unique")
    options = config.get("event_followup", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("event_followup must be a mapping")
    caps = {"search_calls": shared.max_search_requests, "parse_calls": shared.max_read_sources,
            "search_model_calls": shared.max_model_calls}
    content_limit = (config.get("all_content_config") or {}).get("max_content_length", 120000)
    seconds = None
    if supplemental:
        caps = {"search_calls": options.get("max_search_calls", 12),
                "parse_calls": options.get("max_parse_calls", 40),
                "search_model_calls": options.get("max_search_model_calls", 30)}
        content_limit = options.get("max_content_length", 120000)
        seconds = options.get("max_elapsed_seconds", 300)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("event_followup.max_elapsed_seconds must be positive and finite")
    for key, value in caps.items():
        _integer(value, key)
    _integer(content_limit, "max_content_length", 1)
    shared = replace(shared, max_builder_material_chars=min(shared.max_builder_material_chars, content_limit))
    if initial_events:
        from finmy.runner.initial_event_search import collect_initial_events
        return collect_initial_events(tasks=tasks, events=entries, shared=shared,
            config=config, save_dir=save_dir, usage=usage, content_limit=content_limit,
            runner=runner, dependencies={**dependencies, "model": supplied_model,
                "transport": supplied_transport, "fetcher": supplied_fetcher},
            documents_for=_documents, progress=progress)
    root = Path(save_dir) / ("enhanced_event_search" if supplemental else "initial_event_search" if initial_events else "enhanced_subject_search")
    report_path = root / "phase_report.json"
    identity_fields = {"tasks": tasks, "config": asdict(shared), "caps": caps,
                       "seconds": seconds, "content_limit": content_limit}
    if initial_events:
        identity_fields["initial_events"] = True
    fingerprint = digest(identity_fields)
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("identity") != fingerprint:
            raise ValueError("Search scope/config changed; use a new output directory")
    else:
        report = {"version": "enhanced-subject-search-v1", "identity": fingerprint,
                  "base_usage": {k: _integer(usage.get(k, 0), k) for k in caps},
                  "limits": caps, "content_limit": content_limit,
                  "elapsed_seconds": 0.0, "tasks": {}}
        write_json(report_path, report)
    started = time.monotonic()
    previous_elapsed = report["elapsed_seconds"]

    def elapsed():
        return previous_elapsed + time.monotonic() - started

    def guard():
        if seconds is not None and elapsed() >= seconds:
            raise TimeoutError("Shared supplementary search time limit reached")

    def counters():
        result = dict(report["base_usage"])
        for record in report["tasks"].values():
            path = root / record["task_id"] / "runs" / "initial" / "run.json"
            read_task_usage(record, path)
            for key in caps:
                result[key] += record.get("usage", {}).get(key, 0)
        return result

    def persist():
        report["usage"] = counters()
        report["elapsed_seconds"] = elapsed()
        usage.update({k: max(usage.get(k, 0), v) for k, v in report["usage"].items()})
        write_json(report_path, report)

    documents = []
    try:
        for index, (event, search_task) in enumerate(zip(entries, tasks)):
            task_id = "subject" if event is None else "event_" + digest(event["event_id"])[:16]
            record = report["tasks"].get(task_id)
            if record is None:
                spent = counters()
                reserved = {key: 0 for key in caps}
                # Paused/failed tasks keep their assigned allowance on resume.
                # Reallocating that unspent allowance would multiply the phase
                # budget when the earlier task subsequently resumes.
                names = {"search_calls": "max_search_requests", "parse_calls": "max_read_sources",
                         "search_model_calls": "max_model_calls"}
                for prior in report["tasks"].values():
                    if "config" in prior and prior["status"] not in TERMINAL:
                        for key, option in names.items():
                            reserved[key] += max(0, prior["config"][option] - prior.get("usage", {}).get(key, 0))
                remaining = len(tasks) - index
                quotas = {key: max(0, caps[key] - spent[key] - reserved[key]) // remaining for key in caps}
                record = {"task_id": task_id, "event_id": search_task.get("event_id"),
                          "status": "pending", "usage": {key: 0 for key in caps}}
                report["tasks"][task_id] = record
                minimums = (("search_calls", len(shared.providers)), ("parse_calls", 1),
                            ("search_model_calls", 3)) if event_tasks else ((k, 1) for k in caps)
                if any(quotas[k] < minimum for k, minimum in minimums):
                    record["status"] = "budget_exhausted"
                    persist()
                    continue
                record["config"] = asdict(replace(shared, max_search_requests=quotas["search_calls"],
                    max_read_sources=quotas["parse_calls"], max_model_calls=quotas["search_model_calls"]))
                persist()  # Persist assigned ceilings before the first attempted call.
            if "config" not in record:
                continue
            child_config = SearchConfig(**record["config"])
            if record["status"] not in TERMINAL:
                if seconds is not None and elapsed() >= seconds:
                    record["status"] = "time_budget_exhausted"
                    persist()
                    continue
                if progress:
                    progress("Shared search: " + search_task["target_name"])
                if child_config.allow_network:
                    from dotenv import load_dotenv
                    load_dotenv(Path.cwd() / ".env", override=False)
                model = supplied_model or LmbaseModel(child_config)

                def bounded_model(context):
                    guard()
                    if supplied_model is None and seconds is not None:
                        model.config = replace(child_config,
                            timeout=max(1, min(child_config.timeout, math.ceil(seconds - elapsed()))))
                        if model.adapter is not None:
                            model.adapter.client = model.adapter.client.with_options(timeout=model.config.timeout)
                    try:
                        return model(context)
                    finally:
                        # Keep the shared search trace's provider usage when
                        # wrapping the real model with a phase deadline.
                        bounded_model.last_usage = getattr(model, "last_usage", None)

                def bounded_transport(provider, payload, settings):
                    guard()
                    bounded = settings if seconds is None else replace(settings,
                        timeout=max(1, min(settings.timeout, math.ceil(seconds - elapsed()))))
                    return (supplied_transport or http_transport)(provider, payload, bounded)

                def bounded_fetcher(url):
                    guard()
                    bounded = child_config if seconds is None else replace(child_config,
                        timeout=max(1, min(child_config.timeout, math.ceil(seconds - elapsed()))))
                    return supplied_fetcher(url) if supplied_fetcher else fetch_public(url, bounded)

                try:
                    result = runner(search_task, root=root, task_id=task_id, config=child_config,
                                    model=bounded_model, transport=bounded_transport,
                                    fetcher=bounded_fetcher, **dependencies)
                    record.update(status=result["status"], run_directory=result.get("run_dir"))
                    for key in ("stop_reason", "resume"):
                        if key in result:
                            record[key] = copy.deepcopy(result[key])
                except Exception as exc:
                    record.update(status="failed", error_type=type(exc).__name__)
                    record_failure(record, "event_search", exc)
                finally:
                    persist()
            if record["status"] != "invalid_state":
                try:
                    found = _documents(root, task_id, record, event)
                    if not found and record["status"] == "finished":
                        record["status"] = "insufficient"
                    documents.extend(found)
                    record["document_count"] = len(found)
                except Exception as exc:
                    record.update(status="invalid_handoff", error_type=type(exc).__name__)
                    record_failure(record, "document_export", exc)
                persist()
        # One identical original can support several events without duplicate text.
        unique = {}
        for row in documents:
            key = (row["url"], row["source_version"], digest(row["raw_text"]))
            if key not in unique:
                unique[key] = row
            else:
                prior = unique[key]
                for name in ("event_ids", "event_labels", "event_terms", "event_routes"):
                    for value in row.get(name, []):
                        if value not in prior.setdefault(name, []):
                            prior[name].append(value)
        documents = list(unique.values())
        outcomes = list(report["tasks"].values())
        status = (outcomes[0]["status"] if not event_tasks and
                  outcomes[0]["status"] not in {"paused", "failed"}
                  else phase_status(outcomes, documents))
        report.update(status=status, complete=bool(outcomes) and all(r["status"] == "finished" for r in outcomes),
                      document_count=len(documents),
                      archived_content_chars=sum(len(d["raw_text"]) for d in documents))
        write_json(root / "sources.json", documents)
        return {"documents": documents, "status": status, "reports": outcomes,
                "usage": counters(), "report_path": str(report_path)}
    finally:
        persist()


def storyline_discovery_enabled(config):
    """Optional planning before person agent search; false searches the subject directly."""
    settings = (config.get("search_config") or {}).get("storyline_discovery", {})
    if settings is None:
        settings = {}
    if not isinstance(settings, dict) or type(settings.get("enabled", True)) is not bool:
        raise ValueError("search_config.storyline_discovery.enabled must be a boolean")
    builder = config.get("builder_config", config)
    return (enhanced_search_enabled(config) and settings.get("enabled", True)
            and (builder.get("reconstruction") or {}).get("mode") == "person")


def storyline_search_identity(query, keywords, subject, config, task=None):
    """Version the accounting contract; old combined-budget runs need migration."""
    return digest({"version": "person-storyline-search-v2", "query": query,
                   "keywords": keywords, "subject": subject,
                   "search_config": config.get("search_config"), "task": task,
                   "content_config": config.get("all_content_config")})


def collect_enhanced_sources(query, keywords, subject, config, save_dir, *,
                             progress=None, usage=None, events=None, dependencies=None, task=None):
    """Discover candidates independently, then research them under one phase budget.

    Existing-EPG supplementary calls retain their separate explicitly enabled budget.
    Discovery output is planning metadata only, never appended as source evidence.
    """
    dependencies = dict(dependencies or {})
    discovery_completion = dependencies.pop("discovery_completion", None)
    if events is not None or not storyline_discovery_enabled(config):
        return _collect_enhanced_sources(query, keywords, subject, config, save_dir,
            progress=progress, usage=usage, events=events, dependencies=dependencies, task=task)
    from finmy.search.control import task_lock
    # Protect discovery as well as reservations: two same-output invocations
    # must not duplicate a model call before the event scheduler starts.
    with task_lock(Path(save_dir), "storyline_search"):
        return _collect_storyline_sources(query, keywords, subject, config, save_dir,
            progress=progress, usage=usage, dependencies=dependencies, task=task,
            discovery_completion=discovery_completion)


def _collect_storyline_sources(query, keywords, subject, config, save_dir, *,
                              progress, usage, dependencies, task, discovery_completion):
    from finmy.runner.storyline_discovery import discover_storylines, StorylineDiscoveryError
    from finmy.runner.initial_event_search import event_search_options
    shared = SearchConfig(**agent_search_config(config))
    event_options = event_search_options(config)
    # Reject invalid scheduler settings before discovery costs anything.
    if event_options["max_search_requests"] < len(shared.providers):
        raise ValueError("Event search allowance must fund one query across all selected providers")
    settings = (config.get("search_config") or {}).get("storyline_discovery") or {}
    discovery_limit = _integer(settings.get("max_model_calls", 2), "storyline_discovery.max_model_calls")
    _integer(settings.get("max_events", 8), "storyline_discovery.max_events", 1)
    usage = usage if usage is not None else {}
    state_path = Path(save_dir) / "storyline_search_state.json"
    identity = storyline_search_identity(query, keywords, subject, config, task)
    if state_path.exists():
        discovery_state = json.loads(state_path.read_text(encoding="utf-8"))
        if discovery_state.get("version") != "person-storyline-search-v2" or discovery_state.get("identity") != identity:
            raise ValueError("Storyline search scope/config changed; use a new output directory or explicitly migrate the saved run")
    else:
        discovery_state = {"version": "person-storyline-search-v2", "identity": identity,
            "base_discovery_model_calls": _integer(usage.get("discovery_model_calls", 0), "discovery_model_calls"),
            "base_usage": {
            key: _integer(usage.get(key, 0), key) for key in
            ("search_calls", "parse_calls", "search_model_calls")}}
        write_json(state_path, discovery_state)
    base_usage = discovery_state["base_usage"]
    for key, ceiling in (("search_calls", shared.max_search_requests),
                         ("parse_calls", shared.max_read_sources),
                         ("search_model_calls", shared.max_model_calls)):
        if _integer(base_usage[key], key) > ceiling:
            raise ValueError("Saved base usage exceeds the configured search budget")
    base_discovery_calls = _integer(discovery_state["base_discovery_model_calls"], "discovery_model_calls")
    if base_discovery_calls > discovery_limit:
        raise ValueError("Saved base usage exceeds the configured discovery budget")
    discovery_config = copy.deepcopy(config)
    discovery_settings = dict(settings)
    discovery_settings["max_model_calls"] = discovery_limit - base_discovery_calls
    discovery_search = discovery_config.setdefault("search_config", {})
    discovery_search["storyline_discovery"] = discovery_settings
    # Legacy pipeline YAML has no independent agent section. Discovery must
    # receive the same migrated model/network settings as acquisition. Existing
    # agent sections stay byte-for-byte equivalent for saved discovery identity.
    if "enhancement" not in discovery_search:
        discovery_search["enhancement"] = agent_search_config(config)
    report_path = Path(save_dir) / "storyline_search_report.json"

    def accounted(search_usage, discovery_calls):
        result = dict(search_usage)
        result["discovery_model_calls"] = base_discovery_calls + discovery_calls
        result["total_model_calls"] = result["search_model_calls"] + result["discovery_model_calls"]
        usage.update({key: max(usage.get(key, 0), value) for key, value in result.items()})
        return result

    if progress:
        progress("Discovering domains and storylines before event research.")
    try:
        plan = discover_storylines(query, keywords, subject, discovery_config, save_dir,
                                  completion=discovery_completion, progress=progress)
    except StorylineDiscoveryError as exc:
        report = {"version": "person-storyline-search-v2", "status": "discovery_failed",
                  "documents": [], "reports": [], "complete": False,
                  "usage": accounted(base_usage, exc.usage.get("model_calls", 0)),
                  "usage_accounting": "separate_discovery_and_search",
                  "error_type": type(exc).__name__}
        write_json(report_path, report)
        return report
    # Candidate count depends only on discovery settings, never on today's search
    # allowance. Unfunded candidates remain explicitly queued in the phase report.
    phase_usage = dict(base_usage)
    candidates = [{**event, "discovery_candidate": True} for event in plan["events"]]
    result = _collect_enhanced_sources(query, keywords, subject, config, save_dir,
        progress=progress, usage=phase_usage, events=candidates, dependencies=dependencies,
        task=task, initial_events=True)
    result["usage"] = accounted(result["usage"], plan["usage"]["model_calls"])
    result["storyline_plan"] = plan
    report = {"version": "person-storyline-search-v2", "status": result["status"],
              "complete": result["complete"], "usage_accounting": "separate_discovery_and_search",
              "discovery_model_calls": result["usage"]["discovery_model_calls"], "usage": result["usage"],
              "discovery_model_call_limit": discovery_limit,
              "limits": {"search_calls": shared.max_search_requests,
                         "parse_calls": shared.max_read_sources, "search_model_calls": shared.max_model_calls},
              "event_search": event_search_options(config),
              "event_count": len(candidates), "events": result["reports"],
              "unresolved_events": [r["event_id"] for r in result["reports"] if r["status"] != "finished"],
              "document_count": len(result["documents"]),
              "content_limit": (config.get("all_content_config") or {}).get("max_content_length", 120000)}
    write_json(report_path, report)
    return result
