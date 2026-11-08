"""Offline provenance checks from retained search text through Person EPG."""

import copy
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from finmy.person_epg.sparse_adapter import build_person_facts, ground_person_evidence
from finmy.person_epg.validation import validate_person_epg
from finmy.person_epg.visualizer import render_person_epg
from finmy.runner.context_budget import allocate_context
from finmy.subject_graph.runner import build_from_contents, subject_builder_config, with_source_registry


def config():
    return {"builder_config": {"reconstruction": {"mode": "person", "subject": {
        "subject_id": "alice", "name": "Alice", "aliases": [],
        "coverage_start": "2023", "coverage_end": "2023",
    }}}, "all_content_config": {"max_content_length": 60000}}


def test_allocated_search_sources_reach_schema_json_and_html(monkeypatch):
    documents = [
        {"document_id": "BACKGROUND", "relevance": "CONTEXT", "title": "Background",
         "url": "https://example.test/background", "published_at": "2023-05-01",
         "raw_text": "Acme provided additional background."},
        {"document_id": "REMOVED", "relevance": "IRRELEVANT", "title": "Unrelated",
         "url": "https://example.test/removed", "raw_text": "An unrelated company reported results."},
        {"document_id": "FILING", "relevance": "CORE", "title": "Purchase filing",
         "url": "https://example.test/filing", "published_at": "2023-05-02T10:00:00+08:00",
         "source_id": "search-source-17", "version": "original-version-sha256",
         "raw_text": "Alice directed Acme to purchase shares."},
    ]
    original_config, original_documents = config(), copy.deepcopy(documents)
    packed = allocate_context(documents, [], original_config)
    original_packed = copy.deepcopy(packed)
    routed = with_source_registry(original_config, documents, packed)
    registry = routed["source_registry"]
    assert [row["document_id"] for row in registry.values()] == ["FILING", "BACKGROUND"]
    assert registry["saved_0"]["source_id"] == "search-source-17"
    assert registry["saved_0"]["version"] == "original-version-sha256"
    assert registry["saved_1"]["published_at"] is None
    assert registry["saved_1"]["published_at_raw"] == "2023-05-01"
    assert "raw_text" not in registry["saved_0"]
    captured = {}

    class Builder:
        def __init__(self, build_config):
            assert "source_registry" not in build_config
            self.save_dir = "synthetic-output"

        def run(self, inputs):
            captured["inputs"] = inputs
            cascade = {"event_id": "CASE", "title": {
                "value": "Alice's documented investment", "reasons": [],
                "evidence_source_contents": ["Alice directed Acme to purchase shares."],
            }, "stages": []}
            package, mapping = build_person_facts(
                cascade, inputs, original_config["builder_config"]["reconstruction"]["subject"])
            ground_person_evidence(package)
            return package, mapping

    base = ModuleType("finmy.builder.base")
    base.BuildInput = SimpleNamespace
    sparse = ModuleType("finmy.builder.sparse_build.main_build")
    sparse.SparseRagBuilder = Builder
    monkeypatch.setitem(sys.modules, base.__name__, base)
    monkeypatch.setitem(sys.modules, sparse.__name__, sparse)
    (package, mapping), output_dir = build_from_contents(
        packed["contents"], "Trace Alice's investment", ["Acme"], routed)
    assert output_dir == "synthetic-output"
    inputs = captured["inputs"]
    assert [sample.raw_data_id for sample in inputs.samples] == ["saved_0", "saved_1"]
    assert [sample.sample_id for sample in inputs.samples] == ["saved_0", "saved_1"]
    assert [sample.content for sample in inputs.samples] == packed["contents"]
    assert inputs.user_query.extras["source_registry"] == registry
    assert inputs.user_query.extras["source_registry"] is not registry
    first, second = package["source_document"]
    assert first["title"] == "Purchase filing"
    assert first["source_url"] == "https://example.test/filing"
    assert first["published_at"] == "2023-05-02T02:00:00Z"
    assert second["source_url"] == "https://example.test/background"
    assert second["published_at"] is None
    span = next(row for row in package["evidence_span"] if row["document_id"])
    assert span["document_id"] == first["document_id"] == mapping["source_map"][0]["document_id"]
    assert first["content"][span["char_start"]:span["char_end"]] == span["quote"]
    assert validate_person_epg(package) == {"valid": True, "errors": []}
    saved = json.loads(json.dumps(package))
    html = render_person_epg(saved)
    assert '"source_url": "https://example.test/filing"' in html
    assert '"published_at": "2023-05-02T02:00:00Z"' in html
    assert documents == original_documents and packed == original_packed
    assert original_config == config()


@pytest.mark.parametrize("publication, expected", [
    (None, None), ("", None), ("2023", None), ("2023-05-01", None),
    ("2023-05-01T12:00:00", None), ("not a date", None),
    ("2023-02-30T12:00:00Z", None), ("0999-12-31T12:00:00Z", None),
    ("9999-12-31T23:59:59-12:00", None),
    ("2023-05-01T12:00:00.123456+01:00", "2023-05-01T11:00:00.123456Z"),
    ("2023-05-01T12:00:00Z", "2023-05-01T12:00:00Z"),
])
def test_publication_metadata_never_fills_missing_time_or_timezone(publication, expected):
    documents = [{"raw_text": "Original text", "published_at": publication}]
    packed = allocate_context(documents, [], config())
    routed = with_source_registry(config(), documents, packed)
    metadata = routed["source_registry"]["saved_0"]
    assert metadata["document_id"] == "DOC_0001"
    assert metadata["published_at"] == expected
    if publication is not None:
        assert metadata["published_at_raw"] == publication


def test_registry_rejects_misalignment_and_stays_outside_bare_builder_config():
    documents = [{"document_id": "SOURCE", "raw_text": "Source text"}]
    packed = allocate_context(documents, [], config())
    malformed = copy.deepcopy(packed)
    malformed["contents"].append("An extra sample")
    with pytest.raises(ValueError, match="does not match allocated"):
        with_source_registry(config(), documents, malformed)
    malformed = copy.deepcopy(packed)
    malformed["report"]["documents"][0]["document_id"] = "MISSING"
    with pytest.raises(ValueError, match="missing its document metadata"):
        with_source_registry(config(), documents, malformed)
    with pytest.raises(ValueError, match="unique nonempty"):
        with_source_registry(config(), documents + documents, packed)
    bare = config()["builder_config"]
    routed = with_source_registry(bare, documents, packed)
    assert "source_registry" in routed
    assert "source_registry" not in subject_builder_config(routed)
    routed["reconstruction"]["subject"]["aliases"].append("Copied only")
    assert bare["reconstruction"]["subject"]["aliases"] == []
