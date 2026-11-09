"""Resume uses archived inputs rather than spending another search/build budget."""
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from finmy.runner.resume_event_enrichment import resume_event_enrichment

ROOT = Path(__file__).parent


def setup_run(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    package = json.loads((ROOT / "fixtures/buffett_person_epg_preview.json").read_text())
    scope = {"mode": "person", "subject": {"subject_id": "buffett", "name": "Warren Buffett",
             "coverage_start": "2022", "coverage_end": "2023"}}
    documents = [{"raw_text": "New source evidence about Buffett's investment. " * 20,
                  "url": "https://example.test/report", "title": "Investment report",
                  "published_at": "2023-05-06", "source": "test",
                  "event_ids": [package["event"][0]["event_id"]]}]
    values = {"initial_person_epg.json": package, "draft_event_search_sources.json": documents,
              "reconstruction_profile.json": scope,
              "event_profile.json": {"original_request": "Buffett activities 2022–2023", "keywords": []},
              "initial_builder_input_contents.json": ["Initial evidence"],
              "retrieved_documents.json": [],
              "event_refinement_report.json": {"initial_builder_calls": 51,
                  "budgets": {"initial_content_limit": 60000},
                  "supplemental_usage": {"started_at": 0, "search_calls": 7, "parse_calls": 25}}}
    for name, value in values.items():
        (source / name).write_text(json.dumps(value))
    config = {"builder_config": {"builder_type": "SparseRagBuilder", "lm_name": "test/model"},
              "event_followup": {"enabled": True, "max_model_calls": 2}, "relevance_filter": {"cache": False}}
    return source, config, package


def no_classification(*args, **kwargs):
    raise AssertionError("Saved evidence must not invoke the removed relevance classifier")


def test_resume_reuses_original_and_found_sources_with_no_search_or_builder(tmp_path):
    source, config, package = setup_run(tmp_path)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    seen = []
    def enrich(current, sources, effective, directory, **kwargs):
        seen.append((copy.deepcopy(current), sources, effective))
        return current, {"model_calls": 1, "status": "no_changes"}
    with patch("finmy.runner.draft_event_search.collect_draft_event_sources", side_effect=AssertionError("No new search")):
        result, directory = resume_event_enrichment(source, config, tmp_path / "resumed",
                                                    completion=no_classification, enrich=enrich)
    assert result.extras["person_epg"] == package
    assert len(seen) == 1
    assert seen[0][1][0]["content"]
    assert (Path(directory) / "FinalPersonEPG.html").exists()
    report = json.loads((tmp_path / "resumed/event_refinement_report.json").read_text())
    assert report["acquisition_reused"] is True
    assert report["resume"]["new_initial_builder_calls"] == 0
    assert report["supplemental_usage"]["search_calls"] == report["supplemental_usage"]["parse_calls"] == 0
    assert "relevance" not in report
    assert report["supplemental_usage"].get("relevance_model_calls", 0) == 0
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert "reconstruction" not in config["builder_config"]


def test_resume_refuses_overwriting_existing_directory(tmp_path):
    source, config, _ = setup_run(tmp_path)
    with pytest.raises(ValueError, match="new, empty"):
        resume_event_enrichment(source, config, source)
    destination = tmp_path / "nonempty"
    destination.mkdir()
    (destination / "keep.txt").write_text("Keep")
    with pytest.raises(ValueError, match="new, empty"):
        resume_event_enrichment(source, config, destination)
    assert (destination / "keep.txt").read_text() == "Keep"


def test_resume_refuses_invalid_saved_graph_before_model_calls(tmp_path):
    source, config, _ = setup_run(tmp_path)
    (source / "initial_person_epg.json").write_text('{}')
    with pytest.raises(ValueError, match="invalid"):
        resume_event_enrichment(source, config, tmp_path / "resumed", completion=lambda *a: pytest.fail("No call"))
    assert not (tmp_path / "resumed").exists()
