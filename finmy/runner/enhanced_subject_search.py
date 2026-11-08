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
from pathlib import Path
import time

from finmy.search.state import SearchConfig, SearchState, digest, write_json


def enhanced_search_enabled(config):
    options = config.get("search_config", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("search_config must be a mapping")
    mode = options.get("mode", "simple")
    if mode not in {"simple", "agent"}:
        raise ValueError("search_config.mode must be simple or agent")
    return mode == "agent"


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + " must be a finite nonnegative integer")
    return value


def _task(query, keywords, subject, config, event=None, supplied=None):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search requires the original nonempty request")
    if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
        raise ValueError("Search keywords must be a list of strings")
    if not isinstance(subject, dict) or not isinstance(subject.get("name"), str) or not subject["name"].strip():
        raise ValueError("Subject search requires a nonempty subject name")
    builder = config.get("builder_config", config)
    mode = (builder.get("reconstruction") or {}).get("mode", "person")
    if mode not in {"person", "company"}:
        raise ValueError("Enhanced subject search requires person/company reconstruction")
    result = {"target_type": mode, "target_name": subject["name"],
              "query_text": query, "key_words": list(keywords),
              "subject_scope": copy.deepcopy(subject)}
    if event is not None:
        eid, label = event.get("event_id"), event.get("event_label") or event.get("label")
        if not isinstance(eid, str) or not eid.strip() or not isinstance(label, str) or not label.strip():
            raise ValueError("Supplementary search needs an existing event ID and label")
        result.update(target_type="event", target_name=label, original_query=query,
                      event_id=eid,
                      query_text=query + "\nResearch only this existing event involving "
                      + subject["name"] + ": " + label,
                      existing_event={key: copy.deepcopy(event[key]) for key in
                          ("event_id", "event_label", "label", "summary", "event_terms",
                           "entity_clues", "activity_clues", "year_clues") if key in event},
                      event_clues_are_evidence=False)
    if supplied is not None:
        if event is not None or not isinstance(supplied, dict):
            raise ValueError("A task override is only supported for initial subject search")
        allowed = {"target_type", "target_name", "query_text", "key_words", "seed_urls", "local_files", "subject_scope"}
        if set(supplied) - allowed:
            raise ValueError("Unsupported subject search task fields")
        for key in ("target_type", "target_name", "query_text", "key_words", "subject_scope"):
            if key in supplied and supplied[key] != result[key]:
                raise ValueError("Search task cannot override configured subject scope: " + key)
        for key in ("seed_urls", "local_files"):
            if key in supplied:
                if not isinstance(supplied[key], list) or any(not isinstance(v, str) or not v.strip() for v in supplied[key]):
                    raise ValueError(key + " must be a list of nonempty strings")
                result[key] = list(supplied[key])
    return result


def _documents(root, task_id, result, event):
    """Validate the handoff, then export full inspected bodies with provenance."""
    if result.get("status") != "finished":
        return []
    state = SearchState(root, task_id)
    handoff = state.run_dir / "builder_input.json"
    if not handoff.exists():
        raise ValueError("Finished search has no saved Builder handoff")
    payload = json.loads(handoff.read_text(encoding="utf-8"))
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
        from finmy.search.handoff import materialize_complete
        from finmy.search.sources import SourceStore
        complete = json.loads(path.read_text(encoding="utf-8"))
        full = materialize_complete(state, complete)  # Verifies manifest/raw/parsed hashes.
        if payload.get("user_query") != full["user_query"]:
            raise ValueError("Search handoff scope differs from retained material")
        store = SourceStore(state)
        selected_ids = {s["source_id"] for s in complete["selected"]}
        if any(s["raw_data_id"] not in selected_ids for s in payload["samples"]):
            raise ValueError("Search handoff references unselected sources")
        records = []
        for entry in complete["selected"]:
            sid, version = entry["source_id"], entry["version"]
            doc = store.document(sid, version)
            if not any(r["version"] == version and r["end"] > r["start"]
                       for r in state.data["sources"][sid].get("read_ranges", [])):
                raise ValueError("Selected source was not inspected")
            body = "\n\n".join(doc["blocks"][i]["text"] for i in entry["blocks"])
            records.append((sid, version, body, entry["source_status"]))
    output = []
    for sid, version, body, status in records:
        if not body.strip():
            continue
        source = state.data["sources"][sid]
        discoveries = source.get("discoveries", [])
        metadata = registry.get(sid, {})
        if (not isinstance(metadata, dict) or metadata.get("source_id", sid) != sid or
                ("version" in metadata and metadata["version"] != version) or
                ("versions" in metadata and version not in metadata["versions"])):
            raise ValueError("Search source metadata differs from selected version")
        published = (metadata.get("published_at") if metadata else
                     next((d.get("published_at") for d in discoveries if d.get("published_at")), None))
        row = {"raw_text": body, "title": metadata.get("title", source.get("title", "")),
               "url": metadata.get("url", source["url"]),
               "published_at": published, "source": "enhanced", "source_id": sid,
               "source_version": version, "source_status": status,
               "search_run_directory": str(state.run_dir),
               "discoveries": copy.deepcopy(discoveries)}
        for key in ("published_at_raw", "publication_candidates"):
            if key in metadata:
                row[key] = copy.deepcopy(metadata[key])
        if event is not None:
            label = event.get("event_label") or event["label"]
            terms = event.get("event_terms", [label])
            row.update(event_ids=[event["event_id"]], event_labels=[label], event_terms=list(terms),
                       event_routes=[{"event_id": event["event_id"], "event_label": label,
                                      "event_terms": list(terms)}])
        output.append(row)
    return output


def collect_enhanced_sources(query, keywords, subject, config, save_dir, *,
                             progress=None, usage=None, events=None, dependencies=None,
                             task=None):
    """Acquire original sources under one persisted phase budget.

    Supplementary tasks share search/read/model ceilings; creating one task per
    event cannot multiply those ceilings. Full selected bodies are archived;
    the caller applies its one initial/supplementary content budget afterwards.
    """
    from finmy.search.pipeline import run_search
    from finmy.search.agent import LmbaseModel
    from finmy.search.sources import fetch_public
    from finmy.search.tools import http_transport

    if not enhanced_search_enabled(config):
        raise ValueError("Shared search requires search_config.mode: agent")
    enhancement = (config.get("search_config") or {}).get("enhancement", {})
    if not isinstance(enhancement, dict):
        raise ValueError("search_config.enhancement must be a mapping")
    shared = SearchConfig(**copy.deepcopy(enhancement))
    dependencies = dict(dependencies or {})
    if set(dependencies) - {"model", "transport", "fetcher", "max_steps", "run_search"}:
        raise ValueError("Unsupported shared search dependencies")
    runner = dependencies.pop("run_search", run_search)
    supplied_model = dependencies.pop("model", None)
    supplied_transport = dependencies.pop("transport", None)
    supplied_fetcher = dependencies.pop("fetcher", None)
    usage = usage if usage is not None else {}
    supplemental = events is not None
    if supplemental and (not isinstance(events, list) or any(not isinstance(e, dict) for e in events)):
        raise ValueError("Existing events must be a list of event descriptors")
    entries = events if supplemental else [None]
    tasks = [_task(query, keywords, subject, config, e, task) for e in entries]
    if len({t.get("event_id") for t in tasks}) != len(tasks):
        raise ValueError("Existing event IDs must be unique")
    options = config.get("event_followup", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("event_followup must be a mapping")
    caps = {"search_calls": shared.max_search_requests, "parse_calls": shared.max_read_sources,
            "search_model_calls": shared.max_model_calls}
    content_limit = (config.get("all_content_config") or {}).get("max_content_length", 60000)
    seconds = None
    if supplemental:
        caps = {"search_calls": options.get("max_search_calls", 12),
                "parse_calls": options.get("max_parse_calls", 40),
                "search_model_calls": options.get("max_search_model_calls", 30)}
        content_limit = options.get("max_content_length", 60000)
        seconds = options.get("max_elapsed_seconds", 300)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("event_followup.max_elapsed_seconds must be positive and finite")
    for key, value in caps.items():
        _integer(value, key)
    _integer(content_limit, "max_content_length", 1)
    shared = replace(shared, max_builder_material_chars=min(shared.max_builder_material_chars, content_limit))
    root = Path(save_dir) / ("enhanced_event_search" if supplemental else "enhanced_subject_search")
    report_path = root / "phase_report.json"
    fingerprint = digest({"tasks": tasks, "config": asdict(shared), "caps": caps,
                          "seconds": seconds, "content_limit": content_limit})
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
            if path.exists():
                state = json.loads(path.read_text(encoding="utf-8"))
                record["usage"] = {"search_calls": state["usage"]["search"],
                                   "parse_calls": len(state["read_sources"]),
                                   "search_model_calls": state["usage"]["model"]}
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
                    if "config" in prior and prior["status"] not in {"finished", "insufficient", "invalid_handoff"}:
                        for key, option in names.items():
                            reserved[key] += max(0, prior["config"][option] - prior.get("usage", {}).get(key, 0))
                remaining = len(tasks) - index
                quotas = {key: max(0, caps[key] - spent[key] - reserved[key]) // remaining for key in caps}
                record = {"task_id": task_id, "event_id": search_task.get("event_id"),
                          "status": "pending", "usage": {key: 0 for key in caps}}
                report["tasks"][task_id] = record
                minimums = (("search_calls", len(shared.providers)), ("parse_calls", 1),
                            ("search_model_calls", 3)) if supplemental else ((k, 1) for k in caps)
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
            if record["status"] not in {"finished", "insufficient"}:
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
                except Exception as exc:
                    record.update(status="failed", error_type=type(exc).__name__)
                finally:
                    persist()
            if record["status"] == "finished":
                try:
                    found = _documents(root, task_id, {"status": "finished"}, event)
                    if not found:
                        record["status"] = "insufficient"
                    documents.extend(found)
                    record["document_count"] = len(found)
                except Exception as exc:
                    record.update(status="invalid_handoff", error_type=type(exc).__name__)
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
        status = (outcomes[0]["status"] if not supplemental else
                  "finished" if outcomes and all(r["status"] == "finished" for r in outcomes) else
                  "partial" if documents else "insufficient")
        report.update(status=status, document_count=len(documents),
                      archived_content_chars=sum(len(d["raw_text"]) for d in documents))
        write_json(root / "sources.json", documents)
        return {"documents": documents, "status": status, "reports": outcomes,
                "usage": counters(), "report_path": str(report_path)}
    finally:
        persist()
