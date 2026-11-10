"""Offline CLI integration from shared acquisition through native subject outputs.

Acquisition and model building are substituted. Source normalization, character
allocation, event routing, validation and the person HTML renderer run normally.
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
from finmy.person_epg.visualizer import render_person_epg


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

    def config(self, mode="person"):
        return {"search_config": {"mode": "agent", "enhancement": {
                    "providers": ["exa"], "allow_network": False,
                    "lm_name": "ark/explicit-search-model"}},
                "all_content_config": {"max_content_length": 60000,
                                       "max_document_chars": 12000},
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
        for target in ("finmy.runner.search_pipeline_runner._create_pipeline",):
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
                     patch("finmy.subject_graph.runner.build_from_contents", return_value=(output, "native-output")) as build:
                    result = run_search_pipeline(config, self.query, self.keywords, destination,
                        search_task=task, search_dependencies=dependencies)
                build.assert_called_once()
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


    def test_old_followup_enabled_is_ignored_and_native_result_still_renders(self):
        self.forbid_legacy()
        config = self.config()
        config["event_followup"] = {"enabled": True, "max_content_length": "invalid"}
        original = copy.deepcopy(config)
        package = json.loads((Path(__file__).parent / "fixtures" / "buffett_person_epg_preview.json").read_text())
        output = SimpleNamespace(extras={"person_epg": package})
        with self.assertLogs("finmy.reconstruction_scope", level="WARNING") as warnings, \
             patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=(output, str(self.root))) as build:
            result = run_search_pipeline(config, self.query, self.keywords, self.root)
        self.assertEqual(len(warnings.output), 1)
        self.assertEqual(len(self.calls), 1)
        build.assert_called_once()
        self.assertNotIn("event_followup", build.call_args.args[3])
        self.assertIs(result["pipeline_result"], output)
        self.assertTrue(validate_person_epg(package)["valid"])
        target = self.root / "FinalPersonEPG.html"
        render_person_epg(result["pipeline_result"].extras["person_epg"], target)
        self.assertIn("Warren Buffett", target.read_text())
        self.assertEqual(config, original)

    def test_old_simple_and_disabled_flags_use_agent_and_native_builder(self):
        config = self.config()
        config["search_config"] = {"mode": "simple", "enabled": False}
        config["subject_search"] = {"enabled": False}
        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=({}, "native")) as build:
            result = run_search_pipeline(config, self.query, self.keywords, self.root)
        self.assertEqual(len(self.calls), 1)
        build.assert_called_once()
        self.assertEqual(result["builder_save_dir"], "native")


if __name__ == "__main__":
    unittest.main()
