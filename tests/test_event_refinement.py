"""Initial EPG facts survive independently budgeted, additive event enrichment."""
import copy
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.context_budget import allocate_context
from finmy.runner.event_refinement import build_with_draft_event_followup
from finmy.runner.source_documents import make_document
from source_test_support import source_batch

FIXTURE = Path(__file__).parent / "fixtures/buffett_person_epg_preview.json"
DETAIL = "The additional source documents a later management conversation."


def package_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def append_grounded_detail(package, text=DETAIL):
    """A structurally valid additive result for testing the wrapper boundary."""
    result = copy.deepcopy(package)
    member = result["event_activity"][0]
    activity_id = member["activity_id"]
    index = 1 + max((d["detail_index"] for d in result["activity_detail"]
                     if d["activity_id"] == activity_id), default=-1)
    result["source_document"].append({"document_id": "TEST_ADDED_DOCUMENT", "content": text})
    result["evidence_span"].append({"span_id": "TEST_ADDED_SPAN", "document_id": "TEST_ADDED_DOCUMENT",
        "char_start": 0, "char_end": len(text), "quote": text})
    result["evidence_set"].append({"evidence_set_id": "TEST_ADDED_SET"})
    result["evidence_link"].append({"evidence_set_id": "TEST_ADDED_SET", "field_path": "/value",
        "quote_order": 0, "span_id": "TEST_ADDED_SPAN"})
    result["activity_detail"].append({"activity_id": activity_id, "detail_index": index,
        "value": text, "evidence_set_id": "TEST_ADDED_SET"})
    if member["detail_mode"] == "selected":
        result["event_activity_detail"].append({"event_id": member["event_id"],
            "activity_id": activity_id, "detail_index": index})
    assert validate_person_epg(result)["valid"]
    return result


class EventRefinementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "builder_config": {"builder_type": "SparseRagBuilder", "save_folder": str(self.root / "initial"),
                "sparse_builder_config": {"max_calls": 10},
                "reconstruction": {"mode": "person", "subject": {
                    "subject_id": "buffett", "name": "Warren Buffett",
                    "coverage_start": "2022", "coverage_end": "2023"}}},
            "subject_search": {"providers": ["bocha"], "max_parse_calls": 40,
                "max_search_calls": 12, "max_elapsed_seconds": 300, "max_followup_queries": 0},
            "event_followup": {"enabled": True, "max_search_calls": 2, "max_parse_calls": 4,
                "max_content_length": 60000, "max_model_calls": 24},
            "all_content_config": {"max_content_length": 6000, "max_document_chars": 3000},
            "relevance_filter": {"max_model_calls": 12, "cache": False},
        }
        self.original_text = "OXY investment ORIGINAL evidence describes an investment decision. " * 18
        self.new_text = "OXY investment NEW evidence describes execution and management communication. " * 18
        self.documents = [make_document(self.original_text,
            {"title": "Original", "url": "https://example.com/original", "datepublished": "2023-05-06"}, "bocha")]
        self.filtered = source_batch(self.documents, "Buffett 2022–2023", [], self.config,
            self.root / "initial_filter", completion=self.classify)
        self.contents = allocate_context(self.filtered["documents"], self.filtered["decisions"],
            self.config)["contents"]
        self.package = package_fixture()
        self.draft = SimpleNamespace(extras={"usage": {"calls": 7}, "person_epg": self.package},
                                     subject_graph=None, event_cascades={"initial_legacy": True}, logs=[])
        self.order, self.build_calls, self.classified, self.enrich_calls = [], [], [], []
        self.usage = {"started_at": time.monotonic(), "search_calls": 2,
                      "parse_calls": 1, "relevance_model_calls": 1,
                      "attempted_urls": ["https://example.com/original"]}

    @staticmethod
    def classify(system, payload):
        return json.dumps({"decisions": [{"chunk_id": c["chunk_id"], "relevance": "CORE",
            "confidence": .99, "event_time": None, "matched_entities": [],
            "reason": "Source directly concerns the event.", "evidence": c["text"][:90]}
            for c in payload["chunks"]]})

    def collect(self, package, query, keywords, subject, config, save_dir, **kwargs):
        self.order.append("search")
        kwargs["usage"].update(search_calls=2, parse_calls=1, search_model_calls=3)
        doc = make_document(self.new_text, {"url": "https://example.com/new",
            "title": "New execution account", "published_at": "2023-05-07"}, "agent")
        doc["event_ids"] = [package["event"][0]["event_id"]]
        return [doc]

    def build(self, contents, query, keywords, config):
        self.assertFalse(self.build_calls, "The complete builder must never be called a second time")
        self.build_calls.append((copy.deepcopy(contents), copy.deepcopy(config)))
        self.order.append("build")
        return self.draft, str(self.root / "draft")

    def completion(self, system, payload):
        self.classified.extend(c["text"] for c in payload["chunks"])
        return self.classify(system, payload)

    def enrich(self, package, sources, config, save_dir, **kwargs):
        self.order.append("enrich")
        self.enrich_calls.append((copy.deepcopy(package), copy.deepcopy(sources), copy.deepcopy(config)))
        return append_grounded_detail(package), {"model_calls": 2, "status": "enriched", "added_details": 1}

    def run_flow(self, **kwargs):
        collector = kwargs.pop("collector", self.collect)
        with patch("finmy.runner.draft_event_search.collect_draft_event_sources", collector):
            return build_with_draft_event_followup(self.contents, "Buffett 2022–2023", [],
                self.config, self.root, documents=self.documents,
                usage=self.usage, build=kwargs.pop("build", self.build),
                completion=kwargs.pop("completion", self.completion),
                enrich=kwargs.pop("enrich", self.enrich), **kwargs)

    def report(self):
        return json.loads((self.root / "event_refinement_report.json").read_text())

    def assert_original_rows_preserved(self, result):
        final = result.extras["person_epg"]
        for table, original in self.package.items():
            self.assertEqual(final[table][:len(original)] if isinstance(original, list) else final[table], original, table)
        self.assertTrue(validate_person_epg(final)["valid"])

    def test_build_once_then_search_and_add_facts_without_replacing_initial_graph(self):
        before_config, before_draft, before_usage = copy.deepcopy(self.config), copy.deepcopy(self.draft), copy.deepcopy(self.usage)
        result, directory = self.run_flow()
        self.assertEqual(len(self.build_calls), 1)
        self.assertEqual(self.order[0], "build")
        self.assertEqual(self.order[-1], "enrich")
        self.assertEqual(len(self.enrich_calls), 1)
        self.assertEqual(self.enrich_calls[0][0], self.package)
        self.assert_original_rows_preserved(result)
        self.assertEqual(len(result.extras["person_epg"]["activity_detail"]), len(self.package["activity_detail"]) + 1)
        self.assertIsNot(result, self.draft)
        self.assertEqual(self.draft, before_draft)
        self.assertEqual(self.config, before_config)
        self.assertEqual(self.usage, before_usage)
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)
        self.assertEqual(json.loads((self.root / "initial_person_epg.json").read_text()), self.package)
        self.assertEqual(self.report()["status"], "enriched")
        self.assertEqual(Path(directory), self.root / "event_enrichment/final")
        self.assertEqual(self.report()["selected_builder_directory"], directory)
        self.assertTrue((Path(directory) / "FinalPersonEPG.json").exists())
        self.assertTrue((Path(directory) / "FinalPersonEPG.html").exists())
        self.assertFalse(self.classified)
        self.assertFalse(any("ORIGINAL evidence" in text for text in self.classified))
        self.assertEqual(self.report()["supplementary_model_calls"], 2)


    def test_no_new_sources_keeps_draft_and_initial_replay_input(self):
        result, _ = self.run_flow(collector=lambda *args, **kwargs: [])
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_new_sources")
        self.assertFalse(self.enrich_calls)
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)


    def test_failed_enrichment_does_not_fail_successful_initial_build(self):
        def fail(*args, **kwargs):
            raise RuntimeError("Offline incremental extraction failure")
        result, directory = self.run_flow(enrich=fail)
        self.assertIs(result, self.draft)
        self.assertEqual(directory, str(self.root / "draft"))
        self.assertEqual(self.report()["status"], "supplementary_processing_failed")
        self.assertEqual(len(self.build_calls), 1)
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)


    def test_injected_enricher_cannot_delete_or_change_existing_facts(self):
        for mutation in ("delete_event", "change_detail", "change_graph", "drop_stage"):
            with self.subTest(mutation=mutation):
                self.build_calls.clear()
                def corrupt(package, *args, **kwargs):
                    result = append_grounded_detail(package)
                    if mutation == "delete_event": result["event"].pop()
                    if mutation == "change_detail": result["activity_detail"][0]["value"] = "rewritten old fact"
                    if mutation == "change_graph": result["graph"]["title"] = "overwritten title"
                    if mutation == "drop_stage": result["stage"].pop()
                    return result, {"model_calls": 2}
                result, _ = self.run_flow(enrich=corrupt)
                self.assertIs(result, self.draft)
                self.assertEqual(self.report()["status"], "enrichment_rejected")


    def test_omitted_followup_builds_once_without_post_build_work(self):
        self.config.pop("event_followup")
        result, _ = self.run_flow(collector=lambda *a, **k: self.fail("Post-build search must be opt-in"),
                                  enrich=lambda *a, **k: self.fail("Post-build enrichment must be opt-in"))
        self.assertIs(result, self.draft)
        self.assertEqual(len(self.build_calls), 1)
        self.assertEqual(self.report()["status"], "disabled_or_unsupported_builder")


    def test_original_archives_stay_unchanged_after_success(self):
        snapshots = {"retrieved_documents.json": [{"archive": "original retrieval"}],
                     "relevance_decisions.json": {"archive": "original relevance"},
                     "context_budget_report.json": {"archive": "original packing"}}
        for name, value in snapshots.items():
            (self.root / name).write_text(json.dumps(value))
        self.run_flow()
        for name, value in snapshots.items():
            self.assertEqual(json.loads((self.root / name).read_text()), value)


    def test_archived_supplementary_sources_skip_acquisition_and_preserve_sources(self):
        source = make_document(self.new_text, {"title": "Previously fetched",
            "url": "https://example.com/archived", "datepublished": "2023-05-07"}, "bocha")
        source["event_ids"] = [self.package["event"][0]["event_id"]]
        before = copy.deepcopy(source)
        result, _ = self.run_flow(supplementary_sources=[source],
            collector=lambda *args, **kwargs: self.fail("Archived sources must not trigger search"))
        self.assert_original_rows_preserved(result)
        self.assertEqual(source, before)
        self.assertTrue(self.report()["acquisition_reused"])
        self.assertEqual(self.report()["supplemental_usage"]["search_calls"], 0)
        self.assertEqual(self.report()["supplemental_usage"]["parse_calls"], 0)
        self.assertNotIn("relevance", self.report())


if __name__ == "__main__":
    unittest.main()
