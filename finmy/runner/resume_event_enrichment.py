"""Resume event enrichment from saved first-pass EPG and supplementary sources.

No search, page parse or initial builder call is performed. The archived person
scope remains authoritative; the supplied config supplies model and budget settings.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.event_followup_config import normalize_followup_config, followup_enabled
from finmy.runner.event_refinement import build_with_draft_event_followup


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def resume_event_enrichment(input_dir, config, output_dir, *, completion=None,
                            enrichment_completion=None, enrich=None, progress=None):
    source, target = Path(input_dir).resolve(), Path(output_dir).resolve()
    if source == target or (target.exists() and any(target.iterdir())):
        raise ValueError("Use a new, empty output directory; original run files must remain intact")
    package = _read(source / "initial_person_epg.json")
    validation = validate_person_epg(package)
    if not validation["valid"]:
        raise ValueError("Saved initial Person EPG is invalid")
    supplementary = _read(source / "draft_event_search_sources.json")
    if (not isinstance(supplementary, list) or not supplementary or any(
            not isinstance(row, dict) or not isinstance(row.get("raw_text"), str)
            or not row["raw_text"].strip() for row in supplementary)):
        raise ValueError("Saved supplementary sources must be a nonempty list of text documents")
    reconstruction = _read(source / "reconstruction_profile.json")
    if reconstruction.get("mode") != "person":
        raise ValueError("Saved reconstruction must be person mode")
    profile = _read(source / "event_profile.json")
    query = profile.get("original_request")
    keywords = profile.get("keywords", [])
    if (not isinstance(query, str) or not query.strip() or not isinstance(keywords, list)
            or any(not isinstance(key, str) for key in keywords)):
        raise ValueError("Saved original request/keywords are invalid")
    contents = _read(source / "initial_builder_input_contents.json")
    if not isinstance(contents, list) or not contents or any(not isinstance(s, str) for s in contents):
        raise ValueError("Saved initial contents are invalid")
    documents = _read(source / "retrieved_documents.json")
    if not isinstance(documents, list):
        raise ValueError("Saved retrieved documents must be a list")
    previous_report = _read(source / "event_refinement_report.json")
    effective = copy.deepcopy(config)
    builder = effective.get("builder_config", effective)
    if not isinstance(builder, dict):
        raise ValueError("Builder configuration must be a mapping")
    builder["reconstruction"] = reconstruction
    builder.setdefault("builder_type", "SparseRagBuilder")
    # The initial input is a saved artifact, so its prior limit is descriptive;
    # only the separately configured follow-up limits govern new submissions.
    effective.setdefault("all_content_config", {})["max_content_length"] = previous_report.get("budgets", {}).get("initial_content_limit", 60000)
    effective = normalize_followup_config(effective)
    if not followup_enabled(effective):
        raise ValueError("Resume requires enabled person event follow-up with SparseRagBuilder configuration")
    if enrich is None and enrichment_completion is None:
        model = effective.get("builder_config", effective).get("lm_name")
        if not isinstance(model, str) or "/" not in model:
            raise ValueError("Supply your pipeline config with builder lm_name: provider/model")
    target.mkdir(parents=True, exist_ok=True)
    calls = previous_report.get("initial_builder_calls")
    result = SimpleNamespace(extras={"person_epg": package, "usage": {"calls": calls}},
                             subject_graph=None, event_cascades=None, result=None, logs=[])
    saved_initial = target / "saved_initial"

    def restore_initial(*args):
        # This is restoration of existing bytes, not model reconstruction.
        from finmy.person_epg.visualizer import render_person_epg
        _save(saved_initial / "FinalPersonEPG.json", package)
        render_person_epg(package, saved_initial / "FinalPersonEPG.html")
        return result, str(saved_initial)

    output, directory = build_with_draft_event_followup(
        contents, query, keywords, effective, target, documents=documents,
        usage=previous_report.get("initial_usage", {}), build=restore_initial,
        supplementary_sources=supplementary, completion=completion,
        enrichment_completion=enrichment_completion, enrich=enrich, progress=progress)
    report_path = target / "event_refinement_report.json"
    report = _read(report_path)
    report["resume"] = {"input_directory": str(source), "initial_build_reused": True,
                        "new_initial_builder_calls": 0, "new_search_calls": 0,
                        "new_parse_calls": 0,
                        "previous_acquisition_usage": previous_report.get("supplemental_usage", {})}
    _save(report_path, report)
    _save(target / "resume_provenance.json", report["resume"])
    return output, directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="Extracted pipeline_output directory")
    parser.add_argument("--config", required=True, help="Pipeline YAML containing your model settings")
    parser.add_argument("--output-dir", required=True, help="New, empty result directory")
    args = parser.parse_args(argv)
    import yaml
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        parser.error("Pipeline config must be a mapping")
    _, directory = resume_event_enrichment(args.input_dir, config, args.output_dir, progress=print)
    print(Path(directory) / "FinalPersonEPG.html")
    print(Path(args.output_dir) / "event_refinement_report.json")


if __name__ == "__main__":
    main()
