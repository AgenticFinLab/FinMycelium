"""Search handoff, replay and budget regressions without the removed classifier."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from finmy.runner.source_documents import prepare_documents
from finmy.runner.context_budget import allocate_context
from finmy.subject_graph.runner import with_source_registry


class SourceDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.config = {"relevance_filter": {"enabled": True, "max_model_calls": 0},
            "all_content_config": {"max_content_length": 60000},
            "builder_config": {"reconstruction": {"mode": "person", "subject": {
                "subject_id": "p1", "name": "Investor", "coverage_start": "2022",
                "coverage_end": "2023"}}}}

    def test_archive_provenance_routes_ids_and_native_registry_without_classifying(self):
        raw = "Purchased a stake in 2023.\n原文保留。"
        source = {"raw_text": raw, "url": "https://example.test/report", "title": "Report",
            "source": "exa", "published_at": "2024-02-01", "source_id": "S123",
            "source_version": "v123", "source_status": "partial", "relevance": "IRRELEVANT",
            "event_ids": ["E1"], "event_routes": [{"event_id": "E1", "event_terms": ["stake"]}],
            "discoveries": [{"query": "Investor stake purchase", "provider": "exa"}]}
        original = copy.deepcopy(source)
        docs = prepare_documents([source], "Investor 2022-2023", ["stake"], self.config, self.path)
        self.assertEqual(source, original)
        self.assertEqual(docs[0]["document_id"], "DOC_0001")
        for key in ("raw_text", "url", "source_id", "source_version", "event_routes", "published_at"):
            self.assertEqual(docs[0][key], source[key])
        self.assertNotIn("relevance", docs[0])
        self.assertEqual(json.loads((self.path / "retrieved_documents.json").read_text()), docs)
        profile = json.loads((self.path / "event_profile.json").read_text())
        self.assertEqual(profile["original_request"], "Investor 2022-2023")
        self.assertEqual(profile["keywords"], ["stake"])
        self.assertEqual(profile["profile"]["period"], ["2022", "2023"])
        self.assertFalse((self.path / "relevance_decisions.json").exists())
        packed = allocate_context(docs, [], self.config)
        native = with_source_registry(self.config, docs, packed)["source_registry"]["saved_0"]
        self.assertEqual(native["source_id"], "S123")
        self.assertEqual(native["source_version"], "v123")
        self.assertEqual(native["source_url"], source["url"])
        supplemental = prepare_documents([source], "Investor", [], self.config,
            self.path / "supplement", document_id_offset=len(docs))
        self.assertEqual(supplemental[0]["document_id"], "DOC_0002")

    def test_legacy_labels_decisions_and_invalid_old_settings_have_no_effect(self):
        self.config["relevance_filter"] = "obsolete configuration"
        sources = [{"raw_text": "A relevant original. " * 50, "relevance": "REVIEW"},
                   {"raw_text": "Another selected original. " * 50, "relevance": "IRRELEVANT"}]
        docs = prepare_documents(sources, "original", [], self.config, self.path)
        old_decisions = [{"document_id": d["document_id"], "relevance": "IRRELEVANT"} for d in docs]
        for strategy in ("phase_order", "event"):
            self.config["all_content_config"]["allocation_strategy"] = strategy
            for d in docs:
                d["relevance"] = "IRRELEVANT"
            before = copy.deepcopy(docs)
            packed = allocate_context(docs, old_decisions, self.config)
            self.assertEqual(len(packed["contents"]), 2)
            self.assertEqual(docs, before)
            self.assertNotIn("included_by_label", packed["report"]["summary"])
            self.assertTrue(all("relevance" not in row for row in packed["report"]["documents"]))

    def test_search_bm25_preserves_tail_evidence_and_raw_offsets_under_cap(self):
        body = "Unrelated preface. " * 2000 + "\n\nOccidental warrants explain the investment.\n\n" + "Other history. " * 1000
        docs = prepare_documents([{"raw_text": body}], "Occidental warrants", [], self.config, self.path)
        self.config["all_content_config"] = {"max_content_length": 2200, "max_document_chars": 2200}
        result = allocate_context(docs, [], self.config)
        self.assertIn("Occidental warrants explain the investment.", result["contents"][0])
        self.assertLessEqual(sum(map(len, result["contents"])), 2200)
        for row in result["report"]["documents"][0]["source_ranges"]:
            self.assertIn(body[row["start_char"]:row["end_char"]], result["contents"][0])

    def test_budget_cli_replays_new_archives_without_old_decisions(self):
        prepare_documents([{"raw_text": "Saved evidence. " * 100}], "evidence", [], self.config, self.path)
        # Prove obsolete artifacts are not read, even when present in an old run.
        (self.path / "relevance_decisions.json").write_text("not JSON")
        (self.path / "filtered_documents.json").write_text("not JSON")
        result = subprocess.run([sys.executable, "-m", "finmy.runner.context_budget",
            "--input-dir", str(self.path), "--max-chars", "1000"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        contents = json.loads((self.path / "budget_review/builder_input_contents.json").read_text())
        self.assertTrue(contents)
        self.assertLessEqual(sum(map(len, contents)), 1000)

    def test_source_validation_remains_before_builder(self):
        for documents in ([{}], [{"raw_text": None}]):
            with self.assertRaises(ValueError):
                prepare_documents(documents, "query", [], self.config, self.path)
        invalid = copy.deepcopy(self.config)
        invalid["builder_config"]["reconstruction"]["subject"] = {}
        with self.assertRaises(ValueError):
            prepare_documents([], "query", [], invalid, self.path)
