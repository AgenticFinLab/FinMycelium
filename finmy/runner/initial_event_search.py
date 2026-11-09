"""Bounded event scheduling around the shared search agent.

Every started event receives an explicit allowance. Reservations protect
the phase budget while events run concurrently or await a later resume. Only
the coordinator writes this report; each search keeps its native task ledger.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
from threading import Lock
import time

from finmy.search.control import task_lock
from finmy.search.state import SearchConfig, digest, write_json


VERSION = "initial-event-search-v3"
COUNTERS = {"search_calls": "max_search_requests", "parse_calls": "max_read_sources",
            "search_model_calls": "max_model_calls"}
TERMINAL = {"finished", "insufficient", "limit", "invalid_handoff"}


def event_search_options(config):
    value = (config.get("search_config") or {}).get("event_search", {})
    if not isinstance(value, dict):
        raise ValueError("search_config.event_search must be a mapping")
    defaults = {"max_search_requests": 12, "max_read_sources": 12,
                "max_model_calls": 24, "max_concurrent_events": 2,
                "reuse_sources": True}
    if set(value) - set(defaults):
        raise ValueError("Unsupported search_config.event_search setting")
    options = {**defaults, **value}
    for key, count in options.items():
        if key == "reuse_sources":
            if type(count) is not bool:
                raise ValueError("search_config.event_search.reuse_sources must be a boolean")
            continue
        if type(count) is not int or count < 1:
            raise ValueError("search_config.event_search." + key + " must be a positive integer")
    if options["max_model_calls"] < 3:
        raise ValueError("Event search needs at least three model calls for search/read/finish")
    return options


def phase_identity(tasks, shared, caps, content_limit, options):
    return digest({"version": VERSION, "tasks": tasks, "config": asdict(shared),
                   "caps": caps, "content_limit": content_limit, "event_search": options})


def _nonnegative(value, key):
    if type(value) is not int or value < 0:
        raise ValueError(key + " must be a nonnegative integer")
    return value


def collect_initial_events(*, tasks, events, shared, config, save_dir, usage,
                           content_limit, runner, dependencies, documents_for,
                           progress=None):
    """Schedule native search runs without changing their decisions or evidence.

    Paused/failed tasks retain unused reservations and resume once per invocation.
    Exhausted and insufficient tasks are terminal under this saved configuration;
    increasing their allowance requires an explicit revision, never a budget reset.
    """
    options = event_search_options(config)
    caps = {key: getattr(shared, option) for key, option in COUNTERS.items()}
    child = replace(shared, **{key: options[key] for key in COUNTERS.values()})
    if child.max_search_requests < len(child.providers):
        raise ValueError("Event search allowance must fund one query across all selected providers")
    root = Path(save_dir) / "initial_event_search"
    report_path = root / "phase_report.json"
    fingerprint = phase_identity(tasks, shared, caps, content_limit, options)
    # This also excludes a concurrent CLI invocation from allocating the same
    # global allowance. Native run_search separately locks each child task.
    with task_lock(Path(save_dir), "initial_event_search"):
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("version") != VERSION or report.get("identity") != fingerprint:
                raise ValueError("Search scope/config changed; use a new output directory or explicitly migrate the saved run")
        else:
            report = {"version": VERSION, "identity": fingerprint,
                      "base_usage": {key: _nonnegative(usage.get(key, 0), key) for key in caps},
                      "limits": caps, "content_limit": content_limit,
                      "event_search": options, "elapsed_seconds": 0.0, "tasks": {}}
        order = ["event_" + digest(event["event_id"])[:16] for event in events]
        if set(report["tasks"]) - set(order):
            raise ValueError("Saved search contains tasks outside the discovered event plan")
        for task_id, task in zip(order, tasks):
            record = report["tasks"].setdefault(task_id, {
                "task_id": task_id, "event_id": task["event_id"], "status": "pending",
                "usage": {key: 0 for key in caps}})
            if record.get("event_id") != task["event_id"]:
                raise ValueError("Saved event task differs from the discovered event plan")
        source_pool = None
        if options["reuse_sources"] and tasks:
            from finmy.search.shared_sources import SharedSourcePool
            scope = tasks[0].get("subject_scope")
            if any(task.get("subject_scope") != scope for task in tasks):
                raise ValueError("Event sources cannot be shared across different subject scopes")
            source_pool = SharedSourcePool(root, scope)
            source_pool.hydrate(order)
        started = time.monotonic()
        previous_elapsed = report.get("elapsed_seconds", 0.0)

        def counters():
            result = dict(report["base_usage"])
            for task_id in order:
                record = report["tasks"][task_id]
                path = root / task_id / "runs" / "initial" / "run.json"
                if path.exists():
                    state = json.loads(path.read_text(encoding="utf-8"))
                    if state["config"] != record.get("config"):
                        raise ValueError("Saved task configuration differs from its phase reservation")
                    record["usage"] = {"search_calls": state["usage"]["search"],
                                       "parse_calls": len(state["read_sources"]),
                                       "search_model_calls": state["usage"]["model"]}
                    record["run_directory"] = str(path.parent)
                    if state.get("stop_reason"):
                        record["stop_reason"] = state["stop_reason"]
                    # Recover a result saved immediately before interruption of
                    # the coordinator, without repeating the completed task.
                    if record["status"] not in TERMINAL and state["status"] in TERMINAL:
                        record["status"] = state["status"]
                for key, option in COUNTERS.items():
                    spent = _nonnegative(record.get("usage", {}).get(key, 0), key)
                    if "config" in record and spent > record["config"][option]:
                        raise ValueError("Saved task usage exceeds its reserved allowance")
                    result[key] += spent
            if any(result[key] > caps[key] for key in caps):
                raise ValueError("Saved phase usage exceeds the configured search budget")
            return result

        def persist():
            report["usage"] = counters()
            report["elapsed_seconds"] = previous_elapsed + time.monotonic() - started
            usage.update({key: max(usage.get(key, 0), value)
                          for key, value in report["usage"].items()})
            write_json(report_path, report)

        def allocate(record):
            spent = counters()
            reserved = {key: 0 for key in caps}
            for prior in report["tasks"].values():
                if "config" in prior and prior["status"] not in TERMINAL:
                    for key, option in COUNTERS.items():
                        reserved[key] += max(0, prior["config"][option] - prior["usage"].get(key, 0))
            available = {key: max(0, caps[key] - spent[key] - reserved[key]) for key in caps}
            quotas = {key: min(available[key], getattr(child, option))
                      for key, option in COUNTERS.items()}
            cached = source_pool is not None and source_pool.has_sources()
            # Use remaining headroom rather than requiring an entire maximum
            # reservation. With shared originals, read -> finish can be useful
            # even when all provider-request capacity is already spent.
            enough_search = quotas["search_calls"] >= len(shared.providers)
            minimum_models = 2 if cached else 3
            if (not (cached or enough_search) or quotas["parse_calls"] < 1
                    or quotas["search_model_calls"] < minimum_models):
                record["status"] = "budget_exhausted"
                return False
            if not enough_search:
                quotas["search_calls"] = 0
            settings = replace(child, **{COUNTERS[key]: value for key, value in quotas.items()})
            record.update(config=asdict(settings), status="pending")
            record["allocation"] = {"reduced_to_remaining_budget": settings != child,
                                    "shared_originals_available": cached}
            persist()  # Reserve all three ceilings before submitting the worker.
            return True

        supplied_model = dependencies.get("model")
        model_lock = Lock()

        def run_one(task, task_id, settings):
            from finmy.search.agent import LmbaseModel
            from finmy.search.sources import fetch_public
            from finmy.search.tools import http_transport
            try:
                # Calling collect again is an explicit resume. Match the native
                # controller's handling of an already acknowledged user pause,
                # without clearing a new pause requested after this launch.
                state_path = root / task_id / "runs" / "initial" / "run.json"
                if state_path.exists():
                    with task_lock(root, task_id):
                        saved = json.loads(state_path.read_text(encoding="utf-8"))
                        if saved.get("status") == "paused" and saved.get("stop_reason") == "user_pause":
                            (root / task_id / "pause_requested").unlink(missing_ok=True)
                if supplied_model is not None and hasattr(supplied_model, "last_usage"):
                    # Injected stateful model instances may publish token usage
                    # on the object. Snapshot it per worker under the same lock
                    # as the call, so concurrent traces cannot exchange usage.
                    def model(context):
                        with model_lock:
                            try:
                                return supplied_model(context)
                            finally:
                                model.last_usage = copy.deepcopy(supplied_model.last_usage)
                    model.last_usage = None
                else:
                    model = supplied_model if supplied_model is not None else LmbaseModel(settings)
                return runner(task, root=root, task_id=task_id, config=settings,
                              model=model, transport=dependencies.get("transport") or http_transport,
                              fetcher=dependencies.get("fetcher") or (lambda url: fetch_public(url, settings)),
                              **({"source_pool": source_pool} if source_pool is not None else {}),
                              **({"max_steps": dependencies["max_steps"]}
                                 if "max_steps" in dependencies else {}))
            except Exception as exc:
                return {"status": "failed", "error_type": type(exc).__name__}

        if shared.allow_network:
            from dotenv import load_dotenv
            load_dotenv(Path.cwd() / ".env", override=False)
        attempted, active = set(), {}
        try:
            persist()
            with ThreadPoolExecutor(max_workers=options["max_concurrent_events"]) as executor:
                while True:
                    # Deterministic plan order for admission and final export.
                    # Completed tasks release unused allowances for queued tasks.
                    for task_id, task in zip(order, tasks):
                        if len(active) >= options["max_concurrent_events"]:
                            break
                        record = report["tasks"][task_id]
                        if task_id in attempted or record["status"] in TERMINAL:
                            continue
                        if "config" not in record and not allocate(record):
                            continue
                        attempted.add(task_id)
                        record["status"] = "running"
                        persist()
                        if progress:
                            progress("Shared search: " + task["target_name"])
                        future = executor.submit(run_one, task, task_id, SearchConfig(**record["config"]))
                        active[future] = task_id
                    persist()
                    if not active:
                        break
                    done, _ = wait(active, return_when=FIRST_COMPLETED)
                    for future in done:
                        task_id = active.pop(future)
                        record = report["tasks"][task_id]
                        result = future.result()
                        record.update(status=result["status"], run_directory=result.get("run_dir"))
                        if result.get("error_type"):
                            record["error_type"] = result["error_type"]
                        else:
                            record.pop("error_type", None)
                    persist()
            documents = []
            for task_id, event in zip(order, events):
                record = report["tasks"][task_id]
                selection_path = root / task_id / "runs" / "initial" / "selection.json"
                if selection_path.exists():
                    selection = json.loads(selection_path.read_text(encoding="utf-8"))
                    record["gaps"] = selection.get("gaps", [])
                    record["selection_reason"] = selection.get("reason")
                if record["status"] not in {"finished", "insufficient"}:
                    continue
                try:
                    with task_lock(root, task_id):
                        found = documents_for(root, task_id, {"status": record["status"]}, event)
                    record["document_count"] = len(found)
                    if not found:
                        record["status"] = "insufficient"
                    documents.extend(found)
                except Exception as exc:
                    record.update(status="invalid_handoff", error_type=type(exc).__name__)
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
            outcomes = [report["tasks"][task_id] for task_id in order]
            complete = bool(outcomes) and all(row["status"] == "finished" for row in outcomes)
            status = ("finished" if complete else "partial" if documents else "budget_exhausted"
                      if outcomes and all("config" not in row for row in outcomes)
                      else "insufficient" if not outcomes or all(row["status"] == "insufficient" for row in outcomes)
                      else "partial")
            unresolved = [row["event_id"] for row in outcomes if row["status"] != "finished"]
            report.update(status=status, complete=complete, unresolved_events=unresolved,
                          document_count=len(documents),
                          build_ready=bool(documents),
                          archived_content_chars=sum(len(row["raw_text"]) for row in documents))
            write_json(root / "sources.json", documents)
            return {"documents": documents, "status": status, "complete": complete,
                    "build_ready": bool(documents),
                    "reports": outcomes, "unresolved_events": unresolved,
                    "usage": counters(), "report_path": str(report_path)}
        finally:
            persist()
