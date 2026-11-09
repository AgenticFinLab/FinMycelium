from contextlib import nullcontext
"""Offline UI/CLI regression: one initial build, then additive event enrichment."""
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_integration as legacy
from test_source_integration import module, load
from test_event_refinement import package_fixture, append_grounded_detail

ROOT = Path(__file__).resolve().parents[1]
INITIAL = "Initial note: Berkshire held Occidental shares in 2023. "
DETAIL = "Buffett personally contacted management after purchases. "


def configuration(output):
    return {
        "output_dir": str(output),
        "all_content_config": {"max_content_length": 6000, "max_document_chars": 2500},
        "relevance_filter": {"cache": False, "max_model_calls": 4},
        "subject_search": {"providers": ["bocha"], "max_search_calls": 6,
            "max_parse_calls": 8, "max_followup_queries": 0,
            "max_decision_followup_queries": 0},
        "event_followup": {"enabled": True, "max_search_calls": 2, "max_parse_calls": 2,
                           "queries_per_event": 1, "max_content_length": 60000,
                           "max_model_calls": 24},
        "builder_config": {"builder_type": "SparseRagBuilder",
            "save_folder": str(output / "builds"),
            "sparse_builder_config": {"max_calls": 20},
            "reconstruction": {"mode": "person", "subject": {
                "subject_id": "person_buffett", "name": "Warren Buffett",
                "coverage_start": "2022", "coverage_end": "2023"}}},
    }


class DraftFollowupEntryPoints(unittest.TestCase):
    def setUp(self):
        legacy.WebSourceIntegrationTest.setUp(self)
        self.errors = []
        self.service.st.error = self.errors.append
        self.timeline, self.searches, self.parses, self.classifications, self.builds, self.enrichments = [], [], [], [], [], []
        self.package = package_fixture()
        self.fail_enrichment = False
        self.empty_followup = False
        self.initial_result = None
        self.enriched_package = None

    def search(self, provider, query, count, start, end):
        after_draft = bool(self.builds)
        kind = "event_search" if after_draft else "initial_search"
        self.timeline.append(kind)
        self.searches.append((kind, provider, query, count, start, end))
        if after_draft and self.empty_followup:
            return []
        suffix = "initial" if not after_draft else "event" + str(sum(s[0] == "event_search" for s in self.searches))
        return [{"url": "https://example.test/" + suffix,
                 "title": suffix + " original report", "published_at": "2023-04-01"}]

    def parse(self, url):
        self.parses.append(url)
        text = INITIAL * 18 if url.endswith("initial") else ("Occidental investment. " + DETAIL + url) * 14
        return {"text": text, "published_at": "2023-04-01", "links": []}

    def completion(self, system, payload):
        # No model gate should re-identify events before using the existing graph.
        self.assertIn("chunks", payload)
        self.timeline.append("classify_new" if self.builds else "classify_initial")
        self.classifications.append(copy.deepcopy(payload))
        return json.dumps({"decisions": [{"chunk_id": c["chunk_id"], "relevance": "CORE",
            "confidence": .99, "event_time": None, "matched_entities": [],
            "reason": "Offline source evidence", "evidence": c["text"][:80]}
            for c in payload["chunks"]]})

    def build(self, contents, query, keywords, config):
        self.assertFalse(self.builds, "A second full builder run would recreate the regression")
        self.timeline.append("draft_build")
        self.builds.append({"contents": copy.deepcopy(contents), "config": copy.deepcopy(config)})
        folder = Path(config["builder_config"]["save_folder"]) / "draft"
        folder.mkdir(parents=True, exist_ok=True)
        result = types.SimpleNamespace(extras={"person_epg": copy.deepcopy(self.package),
            "usage": {"calls": 20}}, subject_graph=None, event_cascades={"initial_legacy": True}, logs=[])
        (folder / "FinalPersonEPG.json").write_text(json.dumps(self.package))
        self.initial_result = result
        return result, str(folder)

    def enrich(self, package, sources, config, save_dir, **kwargs):
        self.timeline.append("event_enrichment")
        self.enrichments.append((copy.deepcopy(package), copy.deepcopy(sources), copy.deepcopy(config)))
        if self.fail_enrichment:
            raise RuntimeError("Offline enrichment failure")
        self.enriched_package = append_grounded_detail(package)
        return self.enriched_package, {"model_calls": 2, "status": "enriched", "added_details": 1}

    def adapters(self):
        return {"finmy.runner.scoped_search_api": module("draft_scoped_api", search=self.search),
                "finmy.runner.scoped_page": module("draft_scoped_page", parse=self.parse),
                "finmy.subject_graph.runner": module("draft_subject_runner", build_from_contents=self.build),
                "finmy.runner.event_enrichment": module("draft_event_enrichment", enrich_events=self.enrich)}

    def run_ui(self, cfg=None):
        service = self.service.ReconstructionService(cfg or configuration(self.path))
        with patch.dict("sys.modules", self.adapters()):
            result = service.run_reconstruction("Warren Buffett activities 2022–2023", [], None)
        return result, next(self.path.glob("pipeline_output_*"))

    def assert_enriched_flow(self, output):
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(len(self.enrichments), 1)
        self.assertEqual(self.timeline[0:2], ["initial_search", "draft_build"])
        self.assertEqual(self.timeline[-1], "event_enrichment")
        first = self.timeline.index("draft_build")
        self.assertTrue(all(i > first for i, value in enumerate(self.timeline) if value == "event_search"))
        self.assertNotIn("西方石油投资", self.searches[0][2])
        queries = [row[2] for row in self.searches if row[0] == "event_search"]
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(row[4:] == ("2022-01-01", "2023-12-31") for row in self.searches))
        self.assertFalse(any(DETAIL in text for text in self.builds[0]["contents"]))
        self.assertEqual(self.builds[0]["config"]["builder_config"]["sparse_builder_config"]["max_calls"], 20)
        self.assertEqual(self.enrichments[0][0], self.package)
        self.assertEqual(json.loads((output / "builder_input_contents.json").read_text()), self.builds[0]["contents"])
        supplemental = json.loads((output / "event_enrichment/supplementary_input_contents.json").read_text())
        self.assertTrue(any(DETAIL in text for text in supplemental))
        self.assertFalse(any(INITIAL in text for text in supplemental))
        self.assertLessEqual(sum(map(len, supplemental)), 60000)
        self.assertEqual(self.classifications, [])
        plan = json.loads((output / "draft_event_search_plan.json").read_text())
        self.assertEqual(plan["event_discovery_model_calls"], 0)
        self.assertEqual([e["event_id"] for e in plan["events"]], [e["event_id"] for e in self.package["event"]])
        self.assertFalse((output / "event_request_plan_input.json").exists())
        report = json.loads((output / "event_refinement_report.json").read_text())
        self.assertEqual(report["status"], "enriched")
        self.assertEqual(report["supplementary_model_calls"], 2)
        self.assertEqual(report["budgets"]["initial_content_limit"], 6000)
        self.assertEqual(report["budgets"]["supplementary_content_limit"], 60000)
        self.assertTrue(Path(report["initial_builder_directory"], "FinalPersonEPG.json").exists())
        self.assertTrue(Path(report["selected_builder_directory"], "FinalPersonEPG.json").exists())
        self.assertEqual(report["supplemental_usage"]["search_calls"], 2)
        self.assertEqual(report["supplemental_usage"]["parse_calls"], 2)
        self.assertFalse(self.errors)

    def test_ui_builds_first_then_enriches_existing_events_under_independent_caps(self):
        cfg = configuration(self.path)
        original = copy.deepcopy(cfg)
        result, output = self.run_ui(cfg)
        self.assertEqual(result, self.enriched_package)
        self.assert_enriched_flow(output)
        report = json.loads((output / "event_refinement_report.json").read_text())
        self.assertEqual(self.service.st.session_state.save_builder_dir_path, report["selected_builder_directory"])
        self.assertEqual(cfg, original)
        self.assertEqual(self.initial_result.extras["person_epg"], self.package)

    def test_cli_uses_same_single_build_additive_enrichment_sequence(self):
        runner = load("draft_cli_entrypoint_test", ROOT / "finmy/runner/search_pipeline_runner.py")
        cfg = configuration(self.path)
        with patch.dict("sys.modules", self.adapters()), \
             nullcontext(), \
             patch.object(runner, "collect_search_contents", side_effect=AssertionError("Unexpected legacy entry")):
            result = runner.run_search_pipeline(cfg, "Warren Buffett activities 2022–2023", [], self.path)
        self.assertEqual(result["pipeline_result"].extras["person_epg"], self.enriched_package)
        self.assert_enriched_flow(self.path)
        report = json.loads((self.path / "event_refinement_report.json").read_text())
        self.assertEqual(result["builder_save_dir"], report["selected_builder_directory"])

    def test_enrichment_failure_returns_initial_ui_result_and_saved_input(self):
        self.fail_enrichment = True
        result, output = self.run_ui()
        self.assertEqual(result, self.initial_result.extras["person_epg"])
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(json.loads((output / "builder_input_contents.json").read_text()), self.builds[0]["contents"])
        report = json.loads((output / "event_refinement_report.json").read_text())
        self.assertEqual(report["status"], "supplementary_processing_failed")
        self.assertEqual(report["selected_builder_directory"], report["initial_builder_directory"])
        self.assertEqual(self.service.st.session_state.save_builder_dir_path, report["initial_builder_directory"])
        self.assertFalse(self.errors)

    def test_empty_initial_events_keep_successful_draft_without_scope_gate(self):
        self.package["event"] = []
        result, output = self.run_ui()
        self.assertEqual(result, self.initial_result.extras["person_epg"])
        self.assertEqual(len(self.builds), 1)
        self.assertFalse(any(row[0] == "event_search" for row in self.searches))
        self.assertEqual(json.loads((output / "event_refinement_report.json").read_text())["status"], "no_existing_events")
        self.assertFalse(self.errors)

    def test_no_new_source_returns_initial_without_extraction(self):
        self.empty_followup = True
        result, output = self.run_ui()
        self.assertEqual(result, self.initial_result.extras["person_epg"])
        self.assertEqual(len(self.builds), 1)
        self.assertFalse(self.enrichments)
        self.assertTrue(any(row[0] == "event_search" for row in self.searches))
        self.assertEqual(json.loads((output / "event_refinement_report.json").read_text())["status"], "no_new_sources")
        self.assertFalse(self.errors)

    def test_disabled_followup_keeps_original_single_build_ui_path(self):
        cfg = configuration(self.path)
        cfg["event_followup"]["enabled"] = False
        result, output = self.run_ui(cfg)
        self.assertEqual(result, self.initial_result.extras["person_epg"])
        self.assertEqual(len(self.builds), 1)
        self.assertFalse(any(row[0] == "event_search" for row in self.searches))
        self.assertFalse((output / "draft_event_search_plan.json").exists())
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
