"""Run person storyline discovery and event research from e.g. 'Buffett 2022-2023'."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata

from finmy.reconstruction_scope import read_reconstruction, strip_retired_event_followup
from finmy.runner.person_period import compact_person_request
from finmy.search.state import digest


def person_config(request, config):
    """Resolve a compact name/period request without a separate model call.

    Model-backed identity and storyline interpretation happens during discovery;
    the supplied name remains an explicit scope constraint. Existing full person
    scope can be used for a longer natural-language request.
    """
    compact = compact_person_request(request)
    effective = strip_retired_event_followup(config)
    builder = effective.setdefault("builder_config", {})
    declared = builder.get("reconstruction") or {}
    if compact:
        name, start, end = compact
        normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        previous = declared.get("subject") if declared.get("mode") == "person" else None
        previous = previous if isinstance(previous, dict) else {}
        names = [previous.get("name")]
        if isinstance(previous.get("aliases"), list):
            names.extend(previous["aliases"])
        identifier = previous.get("subject_id")
        if not (isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identifier)
                and any(isinstance(value, str) and normalize(value) == normalize(name) for value in names)):
            identifier = "person_" + digest(name.casefold())[:16]
        builder["reconstruction"] = {"mode": "person", "subject": {
            "subject_id": identifier, "name": name,
            "aliases": [], "coverage_start": start, "coverage_end": end}}
    elif declared.get("mode") == "person" and declared.get("subject", {}).get("name"):
        read_reconstruction(effective)
    else:
        raise ValueError("Use a person and period, e.g. Buffett 2023 or Buffett 2022–2023, or configure a person scope for a longer request")
    builder.setdefault("builder_type", "SparseRagBuilder")
    effective.setdefault("search_config", {})["mode"] = "agent"
    effective["search_config"]["storyline_discovery"] = dict(effective["search_config"].get("storyline_discovery") or {})
    effective["search_config"]["storyline_discovery"]["enabled"] = True
    effective.setdefault("all_content_config", {}).setdefault("max_content_length", 120000)
    read_reconstruction(effective)
    return effective


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Person and period, e.g. Buffett 2023-05 or Buffett 2022–2023")
    parser.add_argument("--config", default="configs/search_pipeline.yml")
    parser.add_argument("--output-dir", help="New run directory; existing matching searches can resume")
    parser.add_argument("--resume-search-from", metavar="SOURCE",
                        help="Copy a matching saved search to a new output directory and continue with the configured budgets")
    args = parser.parse_args(argv)
    import yaml
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        parser.error("Pipeline config must be a mapping")
    config = person_config(args.request, config)
    target = Path(args.output_dir) if args.output_dir else Path(config.get("output_dir", "output")) / (
        "person_storylines_" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
    if args.resume_search_from:
        from finmy.runner.storyline_search_resume import prepare_storyline_resume
        try:
            prepare_storyline_resume(args.resume_search_from, target, args.request, [],
                                     read_reconstruction(config)["subject"], config)
        except ValueError as exc:
            parser.error(str(exc))
    from finmy.runner.search_pipeline_runner import run_search_pipeline
    result = run_search_pipeline(config, args.request, [], target)
    summary = {"status": result.get("status", "finished"),
               "output_directory": str(target),
               "builder_directory": result.get("builder_save_dir")}
    for key in ("complete", "search_report_path", "status_path", "unresolved_events",
                "search_status", "search_complete", "search_coverage_report_path",
                "retained_document_count", "resume_directory", "usage", "resume", "message", "next_action"):
        if key in result:
            summary[key] = result[key]
    print(json.dumps(summary, ensure_ascii=False))
    return (0 if result.get("pipeline_result") is not None else
            2 if result.get("search_status") in {"waiting", "blocked", "paused"} else 1)


if __name__ == "__main__":
    raise SystemExit(main())
