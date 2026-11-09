"""Explicitly revise a saved storyline search in a new output directory.

This is an offline preparation step. It preserves the discovered plan, native
source/cache state and attempted-call ledgers, then uses the shared search's
configuration revision API. Merely rerunning a pipeline never raises its budget.
"""
from __future__ import annotations

import copy
from contextlib import ExitStack
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import shutil
import tempfile

from finmy.search.control import SearchController, task_lock
from finmy.search.sources import SourceStore, SourceIntegrityError
from finmy.search.state import SearchConfig, SearchState, digest, now, write_json


COUNTERS = {"search_calls": "max_search_requests", "parse_calls": "max_read_sources",
            "search_model_calls": "max_model_calls"}


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read saved search object: " + path.name) from exc
    if not isinstance(value, dict):
        raise ValueError("Saved search object must be a mapping: " + path.name)
    return value


def _counts(value):
    result = {key: value.get(key, 0) for key in COUNTERS}
    if any(type(count) is not int or count < 0 for count in result.values()):
        raise ValueError("Saved search contains an invalid call ledger")
    return result


def _no_links(path):
    if path.is_symlink() or any(child.is_symlink() for child in path.rglob("*")):
        raise ValueError("Saved search must not contain symbolic links")


def _snapshot(source):
    roots = [source / "storyline_discovery", source / "initial_event_search"]
    files = [source / "storyline_search_state.json"]
    for root in roots:
        files.extend(path for path in root.rglob("*") if path.is_file())
    return {str(path.relative_to(source)): digest(path.read_bytes()) for path in files}


def _native_state(root, task_id, expected_task, record):
    path = root / task_id / "runs" / "initial" / "run.json"
    if not path.exists():
        if any(_counts(record.get("usage", {})).values()):
            raise ValueError("Saved task usage has no native run ledger")
        return None, {key: 0 for key in COUNTERS}
    data = _read(path)
    if data.get("task") != expected_task or data.get("input_sha256") != digest(expected_task):
        raise ValueError("Saved event search differs from the requested person, period or storyline")
    old_config = SearchConfig(**data["config"])
    if SearchConfig(**record.get("config", {})) != old_config:
        raise ValueError("Saved task configuration differs from its phase reservation")
    read_ids = data.get("read_sources", [])
    if not isinstance(read_ids, list) or len(set(read_ids)) != len(read_ids):
        raise ValueError("Invalid distinct-source read ledger")
    counts = _counts({"search_calls": data["usage"]["search"],
                      "parse_calls": len(read_ids), "search_model_calls": data["usage"]["model"]})
    if any(counts[key] > getattr(old_config, option) for key, option in COUNTERS.items()):
        raise ValueError("Saved task usage exceeds its original allowance")
    state = SearchState(root, task_id)
    store = SourceStore(state)
    if any(sid not in data["sources"] for sid in read_ids):
        raise ValueError("Read ledger references an unknown source")
    for sid, entry in data["sources"].items():
        if not re.fullmatch(r"[0-9a-f]{24}", sid):
            raise ValueError("Invalid source identifier")
        for version in entry.get("versions", []):
            if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
                raise ValueError("Invalid source version")
            try:
                store.document(sid, version)  # Never promote unverifiable originals.
            except SourceIntegrityError as error:
                data.setdefault("_resume_source_errors", []).append({
                    "stage": "source_integrity", "source_id": sid, "version": version,
                    "error_type": type(error).__name__})
    return data, counts


def prepare_storyline_resume(source, target, query, keywords, subject, config, task=None):
    """Clone a valid search checkpoint and explicitly revise its finite ceilings.

    ``target`` must be new or empty. Existing unfinished tasks must all fit their
    full revised reservations; otherwise preflight raises before copying or API
    calls. Unstarted candidates remain in the plan for the ordinary scheduler.
    """
    source = Path(source)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Resume source must be an existing directory, not a symbolic link")
    for relative in ("storyline_search", "storyline_discovery", "initial_event_search"):
        _no_links(source / relative)
    # Use the same lifecycle locks as the adapter and native search controller.
    # Empty lock metadata may be created, but source plans, bodies and usage are
    # read-only. A running source fails immediately rather than being interrupted.
    with ExitStack() as locks:
        locks.enter_context(task_lock(source, "storyline_search"))
        locks.enter_context(task_lock(source, "initial_event_search"))
        phase = _read(source / "initial_event_search" / "phase_report.json")
        for task_id in phase.get("tasks", {}):
            if not isinstance(task_id, str) or not re.fullmatch(r"event_[0-9a-f]{16}", task_id):
                raise ValueError("Invalid saved event task identifier")
            if (source / "initial_event_search" / task_id / "runs" / "initial" / "run.json").exists():
                locks.enter_context(task_lock(source / "initial_event_search", task_id))
        return _prepare_locked(source, target, query, keywords, subject, config, task)


def _prepare_locked(source, target, query, keywords, subject, config, task):
    from finmy.runner.enhanced_subject_search import _documents, _task, storyline_search_identity
    from finmy.runner.initial_event_search import VERSION, event_search_options, phase_identity
    from finmy.runner.storyline_discovery import DISCOVERY_PROMPT, _options, normalize_plan

    source, target = Path(source), Path(target)
    if source.is_symlink() or target.is_symlink():
        raise ValueError("Resume source and output must not be symbolic links")
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Use a separate new output directory for an explicit search revision")
    if not source.is_dir():
        raise ValueError("Resume source directory does not exist")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("Resume output directory must be new or empty")
    discovery_dir = source / "storyline_discovery"
    source_root = source / "initial_event_search"
    _no_links(discovery_dir)
    _no_links(source_root)
    before = _snapshot(source)
    checkpoint = _read(discovery_dir / "checkpoint.json")
    phase = _read(source_root / "phase_report.json")
    parent = _read(source / "storyline_search_state.json")
    if phase.get("version") not in {"enhanced-subject-search-v1", "initial-event-search-v2", VERSION}:
        raise ValueError("Unsupported saved storyline-search version")
    if checkpoint.get("status") != "completed":
        raise ValueError("Resume requires a completed saved storyline discovery")
    old_request = checkpoint["request"]
    if (old_request.get("original_request") != query or old_request.get("keywords") != keywords
            or old_request.get("subject_scope") != subject or old_request.get("seed_sources")):
        raise ValueError("Resume request, keywords and person scope must match the saved discovery")
    discovery_options, enhancement = _options(config)
    plan = checkpoint["plan"]
    normalized = normalize_plan(plan, subject, discovery_options["max_events"])
    if {key: value for key, value in plan.items() if key != "usage"} != normalized:
        raise ValueError("Saved candidate plan or stable identifiers are invalid")
    if _read(discovery_dir / "plan.json") != plan:
        raise ValueError("Discovery plan differs from its checkpoint")
    discovery_calls = checkpoint.get("usage", {}).get("model_calls")
    if type(discovery_calls) is not int or not 0 <= discovery_calls <= discovery_options["max_model_calls"]:
        raise ValueError("Discovery ceiling is below the saved attempted-call count")
    options = event_search_options(config)
    content_limit = (config.get("all_content_config") or {}).get("max_content_length", 120000)
    if type(content_limit) is not int or content_limit < 1:
        raise ValueError("max_content_length must be a positive integer")
    shared = SearchConfig(**copy.deepcopy(enhancement))
    shared = replace(shared, max_builder_material_chars=min(shared.max_builder_material_chars, content_limit))
    child = replace(shared, **{key: options[key] for key in COUNTERS.values()})
    if child.max_search_requests < len(child.providers):
        raise ValueError("Event allowance must fund all selected providers")
    caps = {key: getattr(shared, option) for key, option in COUNTERS.items()}
    base = _counts(phase.get("base_usage", {}))
    if phase["version"] == "enhanced-subject-search-v1":
        if base["search_model_calls"] < discovery_calls:
            raise ValueError("Legacy phase ledger does not include its discovery calls")
        base["search_model_calls"] -= discovery_calls
    if base != _counts(parent.get("base_usage", {})):
        raise ValueError("Saved phase and parent usage baselines differ")
    base_discovery = parent.get("base_discovery_model_calls", 0)
    if type(base_discovery) is not int or base_discovery < 0:
        raise ValueError("Invalid discovery baseline")
    if base_discovery + discovery_calls > discovery_options["max_model_calls"]:
        raise ValueError("Discovery ceiling is below the saved cumulative call count")
    effective_discovery_options = {**discovery_options,
        "max_model_calls": discovery_options["max_model_calls"] - base_discovery}
    events = [{**event, "discovery_candidate": True} for event in plan["events"]]
    tasks = [_task(query, keywords, subject, config, event) for event in events]
    if task is not None:
        supplied = _task(query, keywords, subject, config, supplied=task)
        for child_task in tasks:
            for key in ("seed_urls", "local_files"):
                if key in supplied:
                    child_task[key] = supplied[key]
    task_ids = ["event_" + digest(event["event_id"])[:16] for event in events]
    if set(phase.get("tasks", {})) - set(task_ids):
        raise ValueError("Saved search has events outside its discovery plan")
    records, native, required, usage = {}, {}, dict(base), dict(base)
    for task_id, event, expected in zip(task_ids, events, tasks):
        old = phase.get("tasks", {}).get(task_id, {})
        data, spent = _native_state(source_root, task_id, expected, old)
        if old and (old.get("task_id") != task_id or old.get("event_id") != event["event_id"]):
            raise ValueError("Saved phase event identifier differs from its plan")
        native[task_id] = data
        record = {"task_id": task_id, "event_id": event["event_id"],
                  "status": "pending", "usage": spent}
        records[task_id] = record
        for key in COUNTERS:
            usage[key] += spent[key]
        if data is None:
            continue  # Unstarted events are admitted by the ordinary scheduler.
        source_errors = data.get("_resume_source_errors", [])
        if source_errors:
            record["errors"] = source_errors
        finished = data.get("status") == "finished" and not source_errors
        if finished:
            try:
                found = _documents(source_root, task_id, {"status": "finished"}, event)
                if not found:
                    raise ValueError("Finished saved event has no usable handoff")
                record.update(status="finished", config=data["config"], document_count=len(found))
            except (ValueError, OSError, KeyError, TypeError) as error:
                from finmy.runner.search_failures import record_failure
                record_failure(record, "saved_handoff", error)
                finished = False
        if not finished:
            if any(spent[key] > getattr(child, option) for key, option in COUNTERS.items()):
                raise ValueError("Per-event ceiling is below saved usage for " + task_id)
            record["config"] = asdict(child)
        record["run_directory"] = str(target / "initial_event_search" / task_id / "runs" / "initial")
        for key, option in COUNTERS.items():
            required[key] += spent[key] if finished else getattr(child, option)
    if any(required[key] > caps[key] for key in COUNTERS):
        raise ValueError("Global search ceilings cannot reserve saved unfinished events; required "
                         + json.dumps(required, sort_keys=True) + "; configured " + json.dumps(caps, sort_keys=True))
    migration = {"version": "storyline-search-resume-v1", "created_at": now(),
                 "source_directory": str(source), "output_directory": str(target),
                 "source_phase_identity": phase.get("identity"),
                 "source_discovery_identity": checkpoint.get("identity"),
                 "source_discovery_request": old_request,
                 "source_state_sha256": digest((source / "storyline_search_state.json").read_bytes()),
                 "required_reservations": required, "limits": caps, "usage": usage,
                 "discovery_model_calls": base_discovery + discovery_calls,
                 "reused_event_ids": [event["event_id"] for event in events],
                 "reopened_task_ids": [key for key, record in records.items()
                                       if native[key] and record["status"] != "finished"],
                 "isolated_source_errors": {key: row["errors"] for key, row in records.items()
                                            if row.get("errors")}}
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".storyline-resume-", dir=target.parent))
    try:
        shutil.copytree(discovery_dir, staging / "storyline_discovery")
        for task_id, data in native.items():
            if data is None:
                continue
            shutil.copytree(source_root / task_id, staging / "initial_event_search" / task_id,
                            ignore=shutil.ignore_patterns(".writer.lock", "pause_requested"))
            record = records[task_id]
            from finmy.search.sources import repair_saved_sources
            with task_lock(staging / "initial_event_search", task_id):
                repaired_state = SearchState(staging / "initial_event_search", task_id)
                repaired = repair_saved_sources(repaired_state)
            if repaired:
                # A decoded body has different character locations. Preserve the
                # old handoff in its repair archive and have the model inspect
                # the corrected local original before selecting it again.
                if any(record["usage"][key] > getattr(child, option) for key, option in COUNTERS.items()):
                    raise ValueError("Per-event ceiling is below saved usage for repaired task " + task_id)
                record.update(status="pending", config=asdict(child))
                record.pop("document_count", None)
                migration.setdefault("reparsed_sources", {})[task_id] = repaired
                if task_id not in migration["reopened_task_ids"]:
                    migration["reopened_task_ids"].append(task_id)
            if record["status"] != "finished":
                controller = SearchController(staging / "initial_event_search")
                controller.configure(task_id, record["config"])
                with task_lock(staging / "initial_event_search", task_id):
                    state = SearchState(staging / "initial_event_search", task_id)
                    state.data.setdefault("resume_history", []).append({"time": now(),
                        "previous_status": state.data["status"],
                        "previous_stop_reason": state.data.get("stop_reason"),
                        "reason": "explicit_storyline_search_revision"})
                    state.data.update(status="ready", stop_reason="explicit_storyline_search_revision")
                    state.save()
        # Repaired finished tasks need a fresh review of their corrected bodies.
        # Account for their reservations before publishing the new run directory.
        required = dict(base)
        for record in records.values():
            if "config" not in record:
                continue
            for key, option in COUNTERS.items():
                required[key] += (record["usage"][key] if record["status"] == "finished"
                                  else record["config"][option])
        if any(required[key] > caps[key] for key in COUNTERS):
            raise ValueError("Global search ceilings cannot reserve corrected-source review; required "
                             + json.dumps(required, sort_keys=True) + "; configured " + json.dumps(caps, sort_keys=True))
        migration["required_reservations"] = required
        revised = copy.deepcopy(checkpoint)
        request = {**old_request, "max_events": discovery_options["max_events"]}
        revised.update(request=request, identity=digest({"request": request,
            "options": effective_discovery_options, "model": enhancement, "prompt": DISCOVERY_PROMPT}))
        write_json(staging / "storyline_discovery" / "checkpoint.json", revised)
        write_json(staging / "storyline_search_state.json", {
            "version": "person-storyline-search-v2",
            "identity": storyline_search_identity(query, keywords, subject, config, task),
            "base_usage": base, "base_discovery_model_calls": base_discovery})
        write_json(staging / "initial_event_search" / "phase_report.json", {
            "version": VERSION, "identity": phase_identity(tasks, shared, caps, content_limit, options),
            "base_usage": base, "limits": caps, "content_limit": content_limit,
            "event_search": options, "elapsed_seconds": phase.get("elapsed_seconds", 0.0),
            "tasks": records, "usage": usage, "status": "prepared",
            "complete": False})
        write_json(staging / "storyline_resume.json", migration)
        if _snapshot(source) != before:
            raise ValueError("Saved source changed during preparation; stop its running search before resuming")
        if target.exists():
            target.rmdir()  # Fails rather than overwriting an output created concurrently.
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return migration
