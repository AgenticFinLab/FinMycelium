"""Agent-only CLI routing and old configuration migration, without paid calls."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from finmy.runner.enhanced_subject_search import (
    _task, agent_search_config, enhanced_search_enabled, storyline_discovery_enabled,
)
from finmy.runner.search_pipeline_runner import run_search_pipeline


class AgentOnlyRunnerTests(unittest.TestCase):
    def test_old_search_flags_cannot_reenable_a_retired_executor(self):
        for options in ({}, {"mode": "agent"}, {"mode": "simple"},
                        {"mode": "simple", "enabled": False}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmp:
                config = {"search_config": options, "subject_search": {"enabled": False}}
                with patch("finmy.search.pipeline.run_search", return_value={
                        "status": "insufficient", "builder_input_path": None}) as search, \
                     patch("finmy.runner.search_pipeline_runner._create_pipeline") as build:
                    result = run_search_pipeline(config, "Acquisition 2023", [], tmp)
                self.assertEqual(search.call_args.args[0]["target_type"], "event")
                self.assertIsNone(result["pipeline_result"])
                build.assert_not_called()

    def test_configuration_migrates_once_without_overriding_agent_choices(self):
        config = {"lm_name": "deepseek/deepseek-chat", "search_config": {
                    "mode": "simple", "enhancement": {"providers": ["bocha"],
                        "allow_network": False, "max_search_requests": 50,
                        "lm_name": "search/independent"}},
                  "subject_search": {"providers": ["baidu"], "max_search_calls": 8,
                                     "max_parse_calls": 20, "enabled": False},
                  "all_content_config": {"max_content_length": 120000}}
        original = copy.deepcopy(config)
        settings = agent_search_config(config)
        self.assertEqual(settings, {"providers": ["bocha"], "allow_network": False,
            "max_search_requests": 50, "max_read_sources": 20,
            "lm_name": "search/independent", "max_builder_material_chars": 120000})
        self.assertEqual(config, original)
        self.assertTrue(enhanced_search_enabled(config))

    def test_old_pipeline_without_agent_section_uses_its_configured_model(self):
        settings = agent_search_config({"lm_name": "deepseek/deepseek-chat",
            "subject_search": {"max_search_calls": 8, "max_parse_calls": 16}})
        self.assertEqual(settings["lm_name"], "deepseek/deepseek-chat")
        self.assertTrue(settings["allow_network"])
        self.assertEqual(settings["max_search_requests"], 8)
        self.assertEqual(settings["max_read_sources"], 16)

    def test_legacy_publication_dates_expand_without_using_event_coverage(self):
        config = {"subject_search": {"publication_start": "2022", "publication_end": "2023-02"},
                  "search_config": {"enhancement": {"publication_start": "2021-12-01"}}}
        settings = agent_search_config(config)
        self.assertEqual(settings["publication_start"], "2021-12-01")
        self.assertEqual(settings["publication_end"], "2023-02-28")
        config["search_config"]["enhancement"]["publication_end"] = None
        self.assertIsNone(agent_search_config(config)["publication_end"])
        settings = agent_search_config({"subject_search": {
            "publication_start": "2022", "publication_end": "2024-02"}})
        self.assertEqual(settings["publication_start"], "2022-01-01")
        self.assertEqual(settings["publication_end"], "2024-02-29")
        self.assertNotIn("publication_start", agent_search_config({"builder_config": {
            "reconstruction": {"mode": "person", "subject": {"coverage_start": "2022"}}}}))

    def test_event_adapter_does_not_require_a_person_identity(self):
        task = _task("Acquisition 2023", ["closing"], {}, {})
        self.assertEqual(task, {"target_type": "event", "target_name": "Acquisition 2023",
                               "query_text": "Acquisition 2023", "key_words": ["closing"]})
        self.assertFalse(storyline_discovery_enabled({}))

    def test_handoff_keeps_exact_material_and_source_identity_for_event_builder(self):
        config = {"all_content_config": {"max_content_length": 120000}}
        original = copy.deepcopy(config)
        body = "Original evidence with dates, amounts and context."
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "builder_input.json"
            path.write_text(json.dumps({"user_query": {"query_text": "Acquisition 2023",
                "key_words": ["closing"], "extras": {"source_registry": {
                    "S1": {"source_id": "S1", "source_url": "https://example.org/filing"}}}},
                "samples": [{"raw_data_id": "S1", "content": body}]}))
            build = Mock(return_value="completed")
            with patch("finmy.search.pipeline.run_search", return_value={
                    "status": "finished", "builder_input_path": str(path)}), \
                 patch("finmy.runner.search_pipeline_runner._create_pipeline",
                       return_value=SimpleNamespace(lm_build_pipeline_with_contents=build)) as factory:
                result = run_search_pipeline(config, "Acquisition 2023", ["closing"], tmp)
        build.assert_called_once_with(contents=[body], query_text="Acquisition 2023", key_words=["closing"])
        self.assertEqual(factory.call_args.args[0]["source_registry"]["saved_0"]["source_id"], "S1")
        self.assertEqual(result["pipeline_result"], "completed")
        self.assertEqual(config, original)


if __name__ == "__main__":
    unittest.main()
