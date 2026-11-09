"""Task-local failure accounting shared by the search phase coordinators."""
from __future__ import annotations

import copy
import json

COUNTERS = {"search_calls": "max_search_requests", "parse_calls": "max_read_sources",
            "search_model_calls": "max_model_calls"}
TERMINAL = {"finished", "insufficient", "limit", "invalid_handoff", "invalid_state"}


def record_failure(record, stage, error):
    """Keep diagnostics without persisting request bodies or provider secrets."""
    failure = {"stage": stage, "error_type": type(error).__name__}
    if failure not in record.setdefault("errors", []):
        record["errors"].append(failure)
    record["error_type"] = failure["error_type"]


def read_task_usage(record, path):
    """Recover a child's counters, quarantining only an unreadable child ledger.

    Unknown usage is charged at its already reserved ceiling; siblings may use
    the rest of the phase budget, but corrupt state never creates free calls.
    Configuration/usage violations remain hard phase errors.
    """
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        config = state["config"]
        counts = {"search_calls": state["usage"]["search"],
                  "parse_calls": len(state["read_sources"]),
                  "search_model_calls": state["usage"]["model"]}
        if not isinstance(state["read_sources"], list) or any(
                type(value) is not int or value < 0 for value in counts.values()):
            raise TypeError("Invalid child call ledger")
        status = state["status"]
        if (not isinstance(status, str) or status not in
                {"ready", "running", "paused", "finished", "insufficient", "failed", "limit"}
                or (state.get("resume") is not None and not isinstance(state["resume"], dict))
                or any(not isinstance(sid, str) for sid in state["read_sources"])
                or len(set(state["read_sources"])) != len(state["read_sources"])):
            raise TypeError("Invalid child lifecycle or source-read ledger")
    except (OSError, ValueError, KeyError, TypeError) as error:
        if "config" not in record:
            raise ValueError("Unreadable child ledger has no phase reservation") from error
        record_failure(record, "task_state", error)
        record.update(status="invalid_state", run_directory=str(path.parent),
                      usage={key: record["config"][option] for key, option in COUNTERS.items()},
                      usage_accounting="reserved_ceiling_unreadable_child",
                      stop_reason="unreadable_task_state")
        return
    if config != record.get("config"):
        raise ValueError("Saved task configuration differs from its phase reservation")
    if any(counts[key] > config[option] for key, option in COUNTERS.items()):
        raise ValueError("Saved task usage exceeds its reserved allowance")
    record.update(usage=counts, run_directory=str(path.parent))
    if state.get("stop_reason"):
        record["stop_reason"] = state["stop_reason"]
    if state.get("resume"):
        record["resume"] = copy.deepcopy(state["resume"])
    else:
        record.pop("resume", None)
    if record["status"] not in TERMINAL and status in TERMINAL:
        record["status"] = status


def phase_status(outcomes, documents):
    if outcomes and all(row["status"] == "finished" for row in outcomes):
        return "finished"
    if documents:
        return "partial"
    paused = [row for row in outcomes if row["status"] == "paused"]
    if any(row.get("resume", {}).get("retryable") or row.get("stop_reason") == "provider_cooldown"
           for row in paused):
        return "waiting"
    if any(row.get("stop_reason") in {"provider_blocked", "provider_retry_exhausted"}
           for row in paused):
        return "blocked"
    if paused:
        return "paused"
    if any(row["status"] in {"failed", "invalid_state", "invalid_handoff"} for row in outcomes):
        return "failed"
    if outcomes and all(row["status"] in {"budget_exhausted", "limit", "time_budget_exhausted"}
                        for row in outcomes):
        return "budget_exhausted"
    return "insufficient"
