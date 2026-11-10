"""Offline provenance checks from retained search text through Person EPG."""

import copy

import pytest

from finmy.runner.context_budget import allocate_context
from finmy.subject_graph.runner import subject_builder_config, with_source_registry


def config():
    return {"builder_config": {"reconstruction": {"mode": "person", "subject": {
        "subject_id": "alice", "name": "Alice", "aliases": [],
        "coverage_start": "2023", "coverage_end": "2023",
    }}}, "all_content_config": {"max_content_length": 60000}}




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
