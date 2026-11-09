"""Keep evidence coverage separate from whether a graph can be constructed."""
import copy
import json
from pathlib import Path

from finmy.search.state import write_json


def has_search_material(acquired):
    """The acquisition adapter validates provenance; require its document contract."""
    documents = acquired.get("documents", [])
    if not isinstance(documents, list) or any(
            not isinstance(doc, dict) or not isinstance(doc.get("raw_text"), str)
            or not doc["raw_text"].strip() for doc in documents):
        raise ValueError("Enhanced search returned an invalid source document")
    return bool(documents)


def record_search_coverage(acquired, save_dir, *, builder_directory=None, build_completed=False):
    """Archive coverage independently of EPG schema and generated graph contents."""
    directory = Path(save_dir).resolve()
    reports = copy.deepcopy(acquired.get("reports", []))
    unresolved = acquired.get("unresolved_events")
    if unresolved is None:
        unresolved = [row["event_id"] for row in reports
                      if row.get("event_id") and row.get("status") != "finished"]
    search_status = acquired.get("status", "failed")
    documents = acquired.get("documents", [])
    complete = search_status == "finished" and bool(acquired.get("complete", True)) and not unresolved
    if not documents:
        complete = False
        if search_status == "finished":
            search_status = "insufficient"
    events = []
    for row in reports:
        event = {key: copy.deepcopy(row[key]) for key in
                 ("event_id", "task_id", "status", "usage", "run_directory", "document_count", "gaps", "stop_reason")
                 if key in row}
        path = Path(row["run_directory"]) / "selection.json" if row.get("run_directory") else None
        if "gaps" not in event and path is not None and path.is_file():
            try:
                selection = json.loads(path.read_text(encoding="utf-8"))
                event["gaps"] = selection.get("gaps", [])
                event["stop_reason"] = selection.get("reason")
            except (OSError, ValueError, AttributeError):
                pass  # Coverage diagnostics cannot replace validated source material.
        event.setdefault("gaps", [])
        events.append(event)
    labels = {row["event_id"]: row.get("label", row["event_id"])
              for row in (acquired.get("storyline_plan") or {}).get("events", [])}
    result = {
        "version": "search-coverage-v1",
        "status": "finished" if complete else "partial" if documents else search_status,
        "search_status": search_status,
        "complete": complete,
        "search_complete": complete,
        "builder_status": "completed" if build_completed else "not_started",
        "builder_directory": str(builder_directory) if builder_directory is not None else None,
        "save_dir": str(directory),
        "resume_directory": str(directory),
        "search_report_path": acquired.get("report_path"),
        "search_coverage_report_path": str(directory / "search_coverage_report.json"),
        "status_path": str(directory / "search_pipeline_status.json"),
        "search_reports": reports,
        "events": events,
        "unresolved_events": list(unresolved),
        "unresolved_event_labels": [labels.get(identifier, identifier) for identifier in unresolved],
        "retained_document_count": len(documents),
        "retained_source_chars": sum(len(row["raw_text"]) for row in documents),
        "usage": copy.deepcopy(acquired.get("usage", {})),
        "scope": "Retained evidence supports only documented activities; unresolved storylines and listed gaps are not reconstructed facts.",
    }
    write_json(directory / "search_coverage_report.json", result)
    write_json(directory / "search_pipeline_status.json", result)
    if builder_directory is not None:
        builder_path = Path(builder_directory)
        if builder_path.is_dir() and builder_path.resolve() != directory:
            write_json(builder_path / "search_coverage_report.json", result)
    return result


def incomplete_search_result(acquired, save_dir):
    """No usable handoff exists; retain diagnostics rather than building empty input."""
    result = record_search_coverage(acquired, save_dir)
    result["pipeline_result"] = None
    write_json(result["status_path"], result)
    return result


class IncompleteSearchError(ValueError):
    """An empty acquisition, with saved coverage diagnostics attached."""

    def __init__(self, result):
        self.result = result
        super().__init__(
            "Enhanced search did not finish with usable source text "
            f"(status={result['search_status']}; retained documents="
            f"{result['retained_document_count']}; unresolved events="
            f"{len(result['unresolved_events'])}). Builder was not started. "
            f"Saved status: {result['status_path']}. "
            f"Search report: {result['search_report_path'] or 'see saved status'}. "
            f"Saved run directory: {result['resume_directory']}."
        )
