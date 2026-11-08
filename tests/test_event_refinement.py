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
from finmy.runner.relevance_filter import filter_documents, make_document

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
            "event_followup": {"max_search_calls": 2, "max_parse_calls": 4,
                "max_content_length": 60000, "max_model_calls": 24},
            "all_content_config": {"max_content_length": 6000, "max_document_chars": 3000},
            "relevance_filter": {"max_model_calls": 12, "cache": False},
        }
        self.original_text = "OXY investment ORIGINAL evidence describes an investment decision. " * 18
        self.new_text = "OXY investment NEW evidence describes execution and management communication. " * 18
        self.documents = [make_document(self.original_text,
            {"title": "Original", "url": "https://example.com/original", "datepublished": "2023-05-06"}, "bocha")]
        self.filtered = filter_documents(self.documents, "Buffett 2022–2023", [], self.config,
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

    def search(self, provider, query, count, start, end):
        self.order.append("search")
        self.assertEqual((start, end), ("2022-01-01", "2023-12-31"))
        return [{"url": "https://example.com/new", "title": "New execution account",
                 "published_at": "2023-05-07"}]

    def parse(self, url):
        return {"text": self.new_text, "links": []}

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
        return build_with_draft_event_followup(self.contents, "Buffett 2022–2023", [],
            self.config, self.root, filtered=self.filtered, documents=self.documents,
            usage=self.usage, build=kwargs.pop("build", self.build),
            completion=kwargs.pop("completion", self.completion),
            enrich=kwargs.pop("enrich", self.enrich),
            search=kwargs.pop("search", self.search), parse=kwargs.pop("parse", self.parse), **kwargs)

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
        self.assertTrue(self.classified)
        self.assertFalse(any("ORIGINAL evidence" in text for text in self.classified))
        self.assertEqual(self.report()["supplementary_model_calls"], 2)

    def test_initial_budget_exhaustion_does_not_spend_or_block_independent_supplement(self):
        self.draft.extras["usage"]["calls"] = 10
        self.usage.update(started_at=0, search_calls=12, parse_calls=40, relevance_model_calls=12)
        before = copy.deepcopy(self.usage)
        result, _ = self.run_flow()
        self.assert_original_rows_preserved(result)
        self.assertEqual(len(self.enrich_calls), 1)
        self.assertEqual(self.usage, before)
        supplemental = self.report()["supplemental_usage"]
        self.assertGreater(supplemental["started_at"], 0)
        self.assertLessEqual(supplemental["search_calls"], 2)
        self.assertLessEqual(supplemental["parse_calls"], 4)
        self.assertGreater(supplemental["relevance_model_calls"], 0)

    def test_supplementary_characters_have_their_own_limit(self):
        self.config["all_content_config"]["max_content_length"] = 1000
        self.config["event_followup"].update(max_content_length=8000, max_document_chars=8000)
        self.new_text *= 8
        result, _ = self.run_flow()
        self.assert_original_rows_preserved(result)
        supplemental = json.loads((self.root / "event_enrichment/supplementary_input_contents.json").read_text())
        self.assertGreater(sum(map(len, supplemental)), 1000)
        self.assertLessEqual(sum(map(len, supplemental)), 8000)
        self.assertTrue(any("NEW evidence" in text for text in supplemental))
        self.assertFalse(any("ORIGINAL evidence" in text for text in supplemental))
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)
        self.assertEqual(self.report()["budgets"]["initial_content_limit"], 1000)
        self.assertEqual(self.report()["budgets"]["supplementary_content_limit"], 8000)

    def test_no_new_sources_keeps_draft_and_initial_replay_input(self):
        result, _ = self.run_flow(search=lambda *args: [])
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_new_sources")
        self.assertFalse(self.enrich_calls)
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)

    def test_irrelevant_added_sources_do_not_enrich(self):
        def reject(system, payload):
            value = json.loads(self.classify(system, payload))
            for row in value["decisions"]:
                row["relevance"] = "IRRELEVANT"
            return json.dumps(value)
        result, _ = self.run_flow(completion=reject)
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_new_relevant_sources")
        self.assertFalse(self.enrich_calls)

    def test_tiny_supplementary_budget_keeps_initial(self):
        self.config["event_followup"]["max_content_length"] = 1
        result, _ = self.run_flow()
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_new_sources_admitted")
        self.assertFalse(self.enrich_calls)

    def test_failed_enrichment_does_not_fail_successful_initial_build(self):
        def fail(*args, **kwargs):
            raise RuntimeError("Offline incremental extraction failure")
        result, directory = self.run_flow(enrich=fail)
        self.assertIs(result, self.draft)
        self.assertEqual(directory, str(self.root / "draft"))
        self.assertEqual(self.report()["status"], "supplementary_processing_failed")
        self.assertEqual(len(self.build_calls), 1)
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), self.contents)

    def test_no_change_returns_original_without_new_final_directory(self):
        result, _ = self.run_flow(enrich=lambda package, *a, **k: (copy.deepcopy(package), {"model_calls": 2}))
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_changes")

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

    def test_empty_initial_events_need_no_new_scope_gate(self):
        self.draft.extras["person_epg"]["event"] = []
        result, _ = self.run_flow(search=lambda *a: self.fail("No events must not trigger discovery"))
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "no_existing_events")
        self.assertEqual(len(self.build_calls), 1)

    def test_disabled_or_other_builder_keeps_original_single_call(self):
        for disabled in (True, False):
            with self.subTest(disabled=disabled):
                self.build_calls.clear()
                self.config["event_followup"]["enabled"] = not disabled
                self.config["builder_config"]["builder_type"] = "SparseRagBuilder" if disabled else "AgentEventBuilder"
                result, _ = self.run_flow(search=lambda *a: self.fail("Should use original builder path"))
                self.assertIs(result, self.draft)
                self.assertEqual(len(self.build_calls), 1)

    def test_initial_build_failure_is_still_reported(self):
        def fail(*args): raise ValueError("original failure")
        with self.assertRaisesRegex(ValueError, "original failure"):
            self.run_flow(build=fail)
        self.assertEqual(self.report()["status"], "initial_build_failed")

    def test_original_archives_stay_unchanged_after_success(self):
        snapshots = {"retrieved_documents.json": [{"archive": "original retrieval"}],
                     "relevance_decisions.json": {"archive": "original relevance"},
                     "context_budget_report.json": {"archive": "original packing"}}
        for name, value in snapshots.items():
            (self.root / name).write_text(json.dumps(value))
        self.run_flow()
        for name, value in snapshots.items():
            self.assertEqual(json.loads((self.root / name).read_text()), value)

    def test_expired_acquisition_clock_does_not_prevent_fresh_bounded_p0(self):
        clock = [100.0]
        source = make_document(self.new_text, {"title": "New execution account",
            "url": "https://example.com/new", "datepublished": "2023-05-07"}, "bocha")
        source["event_ids"] = [self.package["event"][0]["event_id"]]
        def collect(*args, **kwargs):
            kwargs["usage"].update(search_calls=7, parse_calls=25)
            clock[0] += 301
            return [source]
        with patch("finmy.runner.event_refinement.time.monotonic", side_effect=lambda: clock[0]), \
             patch("finmy.runner.draft_event_search.collect_draft_event_sources", side_effect=collect):
            result, _ = self.run_flow()
        self.assert_original_rows_preserved(result)
        self.assertEqual(self.report()["status"], "enriched")
        self.assertEqual(self.report()["acquisition_elapsed_seconds"], 301)
        self.assertEqual(self.report()["relevance"]["usage"]["started_at"], 401)
        self.assertGreater(self.report()["relevance"]["summary"]["model_calls"], 0)
        self.assertEqual(self.report()["relevance"]["max_elapsed_seconds"], 300)
        self.assertEqual(self.config["subject_search"]["max_elapsed_seconds"], 300)

    def test_p0_failure_does_not_claim_sources_were_reviewed_as_irrelevant(self):
        def fail(*args):
            raise RuntimeError("https://private.test/?api_key=SECRET")
        result, _ = self.run_flow(completion=fail)
        self.assertIs(result, self.draft)
        report = self.report()
        self.assertEqual(report["status"], "relevance_processing_failed")
        self.assertGreater(report["relevance"]["summary"]["processing_failed_batches"], 0)
        self.assertGreater(report["relevance"]["summary"]["labels"]["REVIEW"], 0)
        self.assertNotIn("SECRET", json.dumps(report))
        decisions = (self.root / "event_enrichment/relevance/relevance_decisions.json").read_text()
        self.assertNotIn("SECRET", decisions)

    def test_supplementary_p0_own_time_limit_still_blocks_before_submission(self):
        clock = [100.0]
        self.config["event_followup"]["max_relevance_elapsed_seconds"] = 10
        def progress(message):
            if message.startswith("Relevance filtering:"):
                clock[0] += 11
        with patch("finmy.runner.event_refinement.time.monotonic", side_effect=lambda: clock[0]):
            result, _ = self.run_flow(progress=progress)
        self.assertIs(result, self.draft)
        report = self.report()
        self.assertEqual(report["status"], "relevance_time_budget_exhausted")
        self.assertEqual(report["relevance"]["summary"]["model_calls"], 0)
        self.assertGreater(report["relevance"]["summary"]["blocked_reasons"]["time_budget_exhausted"], 0)
        self.assertEqual(report["relevance"]["max_elapsed_seconds"], 10)

    def test_supplementary_p0_call_limit_is_distinct_from_irrelevance(self):
        self.config["event_followup"]["max_relevance_model_calls"] = 0
        result, _ = self.run_flow()
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "relevance_call_budget_exhausted")
        self.assertEqual(self.report()["relevance"]["summary"]["model_calls"], 0)

    def test_unreviewed_model_decisions_are_not_negative_classification(self):
        result, _ = self.run_flow(completion=lambda *args: json.dumps({"decisions": []}))
        self.assertIs(result, self.draft)
        self.assertEqual(self.report()["status"], "unreviewed_sources")

    def test_archived_supplementary_sources_skip_acquisition_and_use_same_p0(self):
        source = make_document(self.new_text, {"title": "Previously fetched",
            "url": "https://example.com/archived", "datepublished": "2023-05-07"}, "bocha")
        source["event_ids"] = [self.package["event"][0]["event_id"]]
        before = copy.deepcopy(source)
        result, _ = self.run_flow(supplementary_sources=[source],
            search=lambda *args: self.fail("Archived sources must not trigger search"),
            parse=lambda *args: self.fail("Archived sources must not trigger parsing"))
        self.assert_original_rows_preserved(result)
        self.assertEqual(source, before)
        self.assertTrue(self.report()["acquisition_reused"])
        self.assertEqual(self.report()["supplemental_usage"]["search_calls"], 0)
        self.assertEqual(self.report()["supplemental_usage"]["parse_calls"], 0)
        self.assertGreater(self.report()["relevance"]["summary"]["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
