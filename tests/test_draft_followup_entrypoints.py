"""Offline UI/CLI regression: one initial build, then additive event enrichment."""
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_integration as ui_support
from test_source_integration import module, load
from test_event_refinement import package_fixture, append_grounded_detail
from finmy.search.state import SearchConfig
from finmy.subject_graph.runner import with_source_registry

ROOT = Path(__file__).resolve().parents[1]
INITIAL = "Initial note: Berkshire held Occidental shares in 2023. "
DETAIL = "Buffett personally contacted management after purchases. "


def configuration(output):
    return {
        "output_dir": str(output),
        "all_content_config": {"max_content_length": 6000, "max_document_chars": 2500},
        "search_config": {"enhancement": {"providers": ["bocha"]}},
        "event_followup": {"enabled": True, "max_search_calls": 2, "max_parse_calls": 2,
                           "max_content_length": 60000,
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
        ui_support.WebSourceIntegrationTest.setUp(self)
        self.errors = []
        self.service.st.error = self.errors.append
        self.timeline, self.searches, self.builds, self.enrichments = [], [], [], []
        self.package = package_fixture()
        self.fail_enrichment = False
        self.empty_followup = False
        self.initial_result = None
        self.enriched_package = None

    def collect(self, query, keywords, subject, config, save_dir, **kwargs):
        events = kwargs.get("events")
        kind = "event_search" if events is not None else "initial_search"
        self.timeline.append(kind)
        self.searches.append((kind, copy.deepcopy(events)))
        supplementary = kind == "event_search"
        if supplementary and self.empty_followup:
            documents = []
        else:
            documents = [{"url": "https://example.test/" + ("event" if supplementary else "initial"),
                "title": "Original report", "published_at": "2023-04-01", "source": "bocha",
                "raw_text": (DETAIL if supplementary else INITIAL) * 18}]
            if supplementary:
                documents[0]["event_ids"] = [e["event_id"] for e in events]
        kwargs["usage"].update(search_calls=1, parse_calls=len(documents), search_model_calls=3)
        reports = [{"event_id": event["event_id"], "status": "finished" if documents else "insufficient",
                    "usage": {"search_calls": 1}} for event in events or []]
        return {"documents": documents, "reports": reports,
                "status": "finished" if documents else "insufficient"}

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
        return {"finmy.runner.enhanced_subject_search": module("agent_search",
                    collect_enhanced_sources=self.collect,
                    agent_search_config=lambda config: SearchConfig(**config["search_config"]["enhancement"])),
                "finmy.subject_graph.runner": module("draft_subject_runner", build_from_contents=self.build,
                                                     with_source_registry=with_source_registry),
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
        self.assertIsNone(self.searches[0][1])
        events = next(row[1] for row in self.searches if row[0] == "event_search")
        self.assertEqual([e["event_id"] for e in events], [e["event_id"] for e in self.package["event"]])
        self.assertFalse(any(DETAIL in text for text in self.builds[0]["contents"]))
        self.assertEqual(self.builds[0]["config"]["builder_config"]["sparse_builder_config"]["max_calls"], 20)
        self.assertEqual(self.enrichments[0][0], self.package)
        self.assertEqual(json.loads((output / "builder_input_contents.json").read_text()), self.builds[0]["contents"])
        supplemental = json.loads((output / "event_enrichment/supplementary_input_contents.json").read_text())
        self.assertTrue(any(DETAIL in text for text in supplemental))
        self.assertFalse(any(INITIAL in text for text in supplemental))
        self.assertLessEqual(sum(map(len, supplemental)), 60000)
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
        self.assertEqual(report["supplemental_usage"]["search_calls"], 1)
        self.assertEqual(report["supplemental_usage"]["parse_calls"], 1)
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


if __name__ == "__main__":
    unittest.main()
