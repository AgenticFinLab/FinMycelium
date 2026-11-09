"""Offline CLI integration from shared acquisition through native subject outputs.

Only acquisition and model-produced graph changes are substituted. Relevance
normalization, character allocation, event routing, validation, publishing and
the final person HTML renderer run normally.
"""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.search_pipeline_runner import run_search_pipeline
from test_event_refinement import append_grounded_detail, package_fixture, DETAIL


class EnhancedSubjectPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.query = "Trace the documented decisions and their execution"
        self.keywords = ["OXY", "investment"]
        self.documents = [{"raw_text": "Original investment evidence. " * 80,
            "source": "enhanced", "title": "Original announcement",
            "url": "https://example.test/original", "source_id": "S0001",
            "source_version": "v1", "published_at": "2023-05-06T12:00:00Z"}]
        self.calls = []

    def config(self, mode="person", followup=False):
        return {"search_config": {"mode": "agent", "enhancement": {
                    "providers": ["exa"], "allow_network": False,
                    "lm_name": "ark/explicit-search-model"}},
                "all_content_config": {"max_content_length": 60000,
                                       "max_document_chars": 12000},
                "relevance_filter": {"enabled": False},
                "event_followup": {"enabled": followup, "max_content_length": 60000},
                "builder_config": {"builder_type": "SparseRagBuilder" if mode == "person" else "AgentEventBuilder",
                    "lm_name": "deepseek/explicit-builder-model",
                    "reconstruction": {"mode": mode, "subject": {
                        "subject_id": "research_subject", "name": "Warren Buffett"}}}}

    def acquired(self, *args, **kwargs):
        self.calls.append((copy.deepcopy(args), kwargs))
        kwargs["usage"].update(search_calls=2, parse_calls=1, search_model_calls=4)
        return {"status": "finished", "reports": [{"status": "finished"}],
                "documents": copy.deepcopy(self.documents)}

    def forbid_legacy(self):
        for target in ("finmy.runner.scoped_search.plan_search",
                       "finmy.runner.subject_search.collect_subject_sources",
                       "finmy.runner.decision_followup.collect_decision_followup",
                       "finmy.runner.search_pipeline_runner._create_pipeline"):
            p = patch(target, side_effect=AssertionError("Unexpected legacy route: " + target))
            p.start()
            self.addCleanup(p.stop)

    def test_person_and_company_use_native_build_with_original_scope_and_sources(self):
        self.forbid_legacy()
        for mode in ("person", "company"):
            with self.subTest(mode=mode):
                config = self.config(mode)
                original = copy.deepcopy(config)
                task = {"target_type": mode, "target_name": "Warren Buffett",
                        "query_text": self.query, "key_words": self.keywords,
                        "seed_urls": ["https://example.test/seed"]}
                original_task = copy.deepcopy(task)
                dependencies = {"model": object()}
                output = SimpleNamespace(extras={"native": True})
                destination = self.root / mode
                with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
                     patch("finmy.subject_graph.runner.build_from_contents", return_value=(output, "native-output")) as build, \
                     patch("finmy.runner.event_refinement.build_with_draft_event_followup") as followup:
                    result = run_search_pipeline(config, self.query, self.keywords, destination,
                        search_task=task, search_dependencies=dependencies)
                build.assert_called_once()
                followup.assert_not_called()
                contents, query, keywords, build_config = build.call_args.args
                self.assertEqual([text.split("\n\n", 1)[1] for text in contents], [self.documents[0]["raw_text"]])
                self.assertEqual((query, keywords), (self.query, self.keywords))
                self.assertEqual(build_config["builder_config"]["reconstruction"]["mode"], mode)
                registry = build_config["source_registry"]["saved_0"]
                self.assertEqual(registry["source_url"], self.documents[0]["url"])
                self.assertEqual(registry["title"], "Original announcement")
                self.assertEqual(registry["source_id"], "S0001")
                self.assertEqual(registry["source_version"], "v1")
                self.assertEqual(registry["published_at"], "2023-05-06T12:00:00Z")
                self.assertEqual(config, original)
                self.assertEqual(task, original_task)
                self.assertIs(self.calls[-1][1]["dependencies"], dependencies)
                self.assertIs(self.calls[-1][1]["task"], task)
                self.assertEqual(self.calls[-1][0][0:2], (self.query, self.keywords))
                self.assertIs(result["pipeline_result"], output)
                self.assertEqual(result["builder_save_dir"], "native-output")
                self.assertEqual(json.loads((destination / "builder_input_contents.json").read_text()), contents)

    def test_unfinished_or_empty_acquisition_never_calls_relevance_or_builder(self):
        self.forbid_legacy()
        for status, documents in [("paused", self.documents), ("limit", self.documents),
                                  ("failed", []), ("insufficient", []), ("finished", [])]:
            with self.subTest(status=status), \
                 patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources",
                       return_value={"status": status, "reports": [], "documents": documents}), \
                 patch("finmy.runner.source_documents.prepare_documents") as relevance, \
                 patch("finmy.subject_graph.runner.build_from_contents") as build, \
                 patch("finmy.runner.event_refinement.build_with_draft_event_followup") as followup:
                result = run_search_pipeline(self.config(followup=True), self.query,
                    self.keywords, self.root / status)
                self.assertIsNone(result["pipeline_result"])
                relevance.assert_not_called()
                build.assert_not_called()
                followup.assert_not_called()

    def test_explicit_agent_mode_is_not_disabled_by_legacy_subject_search_switch(self):
        self.forbid_legacy()
        config = self.config(followup=True)
        config["subject_search"] = {"enabled": False}
        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=({}, "native")) as build, \
             patch("finmy.runner.event_refinement.build_with_draft_event_followup") as followup:
            run_search_pipeline(config, self.query, [], self.root)
        build.assert_called_once()
        followup.assert_not_called()
        self.assertEqual(len(self.calls), 1)

    def test_budget_exhaustion_after_real_allocation_never_builds(self):
        self.forbid_legacy()
        config = self.config()
        config["all_content_config"]["max_content_length"] = 1
        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents") as build:
            with self.assertRaisesRegex(ValueError, "No relevant source text fits"):
                run_search_pipeline(config, self.query, [], self.root)
        build.assert_not_called()
        self.assertTrue((self.root / "context_budget_report.json").exists())

    def test_existing_events_reach_supplement_and_native_valid_json_html(self):
        self.forbid_legacy()
        config = self.config(followup=True)
        original_config = copy.deepcopy(config)
        package = package_fixture()
        initial = SimpleNamespace(extras={"person_epg": package, "usage": {"calls": 5}},
                                  subject_graph=None, event_cascades={}, logs=[])
        order = []

        def acquire(*args, **kwargs):
            if kwargs.get("events") is None:
                order.append("initial_search")
                return self.acquired(*args, **kwargs)
            order.append("event_search")
            events = kwargs["events"]
            self.assertEqual([e["event_id"] for e in events], [e["event_id"] for e in package["event"]])
            self.assertEqual(args[0], self.query)
            self.assertEqual(kwargs["usage"]["search_calls"], 0)
            kwargs["usage"].update(search_calls=3, parse_calls=1, search_model_calls=6)
            return {"status": "finished", "reports": [], "documents": [{
                "raw_text": DETAIL, "title": "Later documented conversation",
                "url": "https://example.test/later", "source": "enhanced",
                "event_ids": [events[0]["event_id"]]}]}

        def build(*args):
            order.append("initial_build")
            self.assertEqual(args[3]["source_registry"]["saved_0"]["source_url"], self.documents[0]["url"])
            return initial, str(self.root / "initial")

        def enrich(graph, sources, *args, **kwargs):
            order.append("event_enrichment")
            self.assertEqual(sources[0]["content"].split("\n\n", 1)[1], DETAIL)
            self.assertEqual(sources[0]["event_ids"], [package["event"][0]["event_id"]])
            return append_grounded_detail(graph), {"model_calls": 2, "status": "enriched"}

        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", acquire), \
             patch("finmy.subject_graph.runner.build_from_contents", build), \
             patch("finmy.runner.event_enrichment.enrich_events", enrich):
            result = run_search_pipeline(config, self.query, self.keywords, self.root)
        self.assertEqual(order, ["initial_search", "initial_build", "event_search", "event_enrichment"])
        report = json.loads((self.root / "event_refinement_report.json").read_text())
        self.assertEqual(report["status"], "enriched")
        self.assertEqual(report["budgets"]["initial_content_limit"], 60000)
        self.assertEqual(report["budgets"]["supplementary_content_limit"], 60000)
        self.assertEqual(report["initial_usage"]["search_calls"], 2)
        self.assertEqual(report["supplemental_usage"]["search_calls"], 3)
        final_dir = Path(result["builder_save_dir"])
        final = json.loads((final_dir / "FinalPersonEPG.json").read_text())
        self.assertTrue(validate_person_epg(final)["valid"])
        for table, rows in package.items():
            self.assertEqual(final[table][:len(rows)] if isinstance(rows, list) else final[table], rows)
        self.assertTrue((final_dir / "FinalPersonEPG.html").exists())
        self.assertEqual(json.loads((final_dir / "PersonRenderStatus.json").read_text())["status"], "completed")
        self.assertIn(DETAIL, (final_dir / "FinalPersonEPG.html").read_text())
        self.assertEqual(config, original_config)

    def test_simple_subject_mode_retains_scoped_collector_and_native_builder(self):
        config = self.config()
        config["search_config"] = {"mode": "simple"}
        subject = config["builder_config"]["reconstruction"]["subject"]
        subject.update(coverage_start="2022", coverage_end="2023")
        with patch("finmy.runner.subject_search.collect_subject_sources", return_value=self.documents) as collect, \
             patch("finmy.runner.decision_followup.collect_decision_followup", return_value=[]) as decisions, \
             patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources") as enhanced, \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=({}, "native")) as build:
            result = run_search_pipeline(config, self.query, self.keywords, self.root)
        collect.assert_called_once()
        decisions.assert_called_once()
        enhanced.assert_not_called()
        build.assert_called_once()
        self.assertEqual(result["builder_save_dir"], "native")

    def test_simple_company_search_never_runs_personal_investment_followup(self):
        config = self.config(mode="company")
        config["search_config"] = {"mode": "simple"}
        config["builder_config"]["reconstruction"]["subject"].update(
            coverage_start="2022", coverage_end="2023")
        with patch("finmy.runner.subject_search.collect_subject_sources", return_value=self.documents) as collect, \
             patch("finmy.runner.decision_followup.collect_decision_followup") as decisions, \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=({}, "native")) as build:
            result = run_search_pipeline(config, self.query, self.keywords, self.root)
        collect.assert_called_once()
        decisions.assert_not_called()
        build.assert_called_once()
        self.assertEqual(result["builder_save_dir"], "native")


if __name__ == "__main__":
    unittest.main()
