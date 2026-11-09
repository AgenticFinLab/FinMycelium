from contextlib import nullcontext
"""Shared search reaches the existing subject UI build contract without live APIs."""
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_integration as legacy
from source_test_support import source_batch
from finmy.subject_graph.runner import with_source_registry


class EnhancedSubjectUI(unittest.TestCase):
    def setUp(self):
        legacy.WebSourceIntegrationTest.setUp(self)
        self.errors = []
        self.service.st.error = self.errors.append
        self.search_calls = []
        self.search_result = {
            "status": "finished", "reports": [],
            "documents": [
                {"raw_text": "First original acquisition announcement.",
                 "source": "exa", "url": "https://example.test/first",
                 "title": "First", "source_id": "S1", "source_version": "v1",
                 "published_at": "2024-01-15T10:00:00Z"},
                {"raw_text": "Second original execution report.",
                 "source": "bocha", "url": "https://example.test/second",
                 "title": "Second", "source_id": "S2", "source_version": "v2"},
                {"raw_text": "Third original closing notice.",
                 "source": "exa", "url": "https://example.test/third",
                 "title": "Third", "source_id": "S3", "source_version": "v3"},
            ],
        }
        bridge = legacy.module(
            "enhanced_subject_search_ui_test",
            enhanced_search_enabled=lambda config: (config.get("search_config") or {}).get("mode") == "agent",
            collect_enhanced_sources=self.search,
        )
        patcher = patch.dict("sys.modules", {"finmy.runner.enhanced_subject_search": bridge})
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self):
        # A broad biography need not impose publication bounds. The search task
        # retains its own explicit network and model configuration.
        return {
            "output_dir": str(self.path),
            "search_config": {"mode": "agent", "enhancement": {
                "providers": ["exa", "bocha"], "allow_network": False,
                "lm_name": "ark/search-only-model"}},
            "all_content_config": {"max_content_length": 60000},
            "relevance_filter": {"enabled": False},
            "event_followup": {"enabled": False},
            "builder_config": {"builder_type": "SparseRagBuilder",
                "lm_name": "deepseek/build-only-model",
                "reconstruction": {"mode": "person", "subject": {
                    "subject_id": "person_test", "name": "Research subject"}}},
        }

    def search(self, *args, **kwargs):
        self.search_calls.append((copy.deepcopy(args), kwargs))
        kwargs["usage"].update(search_calls=2, search_model_calls=4)
        return copy.deepcopy(self.search_result)

    def forbid_legacy(self):
        patches = [
            patch("finmy.runner.scoped_search.plan_search", side_effect=AssertionError("legacy scoped plan")),
            patch("finmy.runner.decision_followup.collect_decision_followup", side_effect=AssertionError("legacy decision search")),
            patch.object(self.collector.DataCollectorService, "collect_bocha_search_results", side_effect=AssertionError("legacy Bocha")),
            patch.object(self.collector.DataCollectorService, "collect_baidu_search_results", side_effect=AssertionError("legacy Baidu")),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_shared_search_preserves_provider_order_metadata_and_structured_inputs(self):
        self.forbid_legacy()
        config = self.config()
        original = copy.deepcopy(config)
        service = self.service.ReconstructionService(config)
        captures = []
        registries = []

        def build(contents, query, keywords, output):
            captures.append((contents, query, keywords, output))
            registries.append(copy.deepcopy(service.config["source_registry"]))
            return {"person_epg": "native downstream"}

        service._run_pipeline = build
        structured = object()

        def collect_local(collector, value, keywords):
            self.assertIs(value, structured)
            collector.documents["url"].append({"raw_text": "Local URL original.", "source": "url"})
            collector.documents["file"].append({"raw_text": "Local file original.", "source": "file"})
            return ["Local URL original."], ["Local file original."]

        with patch.object(self.collector.DataCollectorService, "collect_structured_data", collect_local):
            output = service.run_reconstruction("Trace documented experiences", ["subject"], structured)
        self.assertEqual(output, {"person_epg": "native downstream"})
        self.assertEqual(config, original)
        self.assertEqual(len(captures), 1)
        contents, query, keywords, directory = captures[0]
        expected = ["Local URL original.", "Local file original."] + [d["raw_text"] for d in self.search_result["documents"]]
        self.assertEqual([text.split("\n\n", 1)[1] for text in contents], expected)
        self.assertEqual(query, "Trace documented experiences")
        self.assertEqual(keywords, ["subject"])
        documents = service._draft_evidence["documents"]
        self.assertEqual([d.get("source") for d in documents], ["url", "file", "exa", "bocha", "exa"])
        self.assertEqual([d["raw_text"] for d in documents[2:]], [d["raw_text"] for d in self.search_result["documents"]])
        self.assertEqual(service._draft_evidence["usage"]["search_model_calls"], 4)
        self.assertEqual(json.loads((Path(directory) / "builder_input_contents.json").read_text()), contents)
        args = self.search_calls[0][0]
        self.assertEqual(args[3]["search_config"]["enhancement"], original["search_config"]["enhancement"])
        self.assertEqual(args[3]["builder_config"]["lm_name"], "deepseek/build-only-model")
        registry = registries[0]
        self.assertEqual(list(registry), [f"saved_{i}" for i in range(5)])
        self.assertEqual(registry["saved_2"]["source_url"], "https://example.test/first")
        self.assertEqual(registry["saved_2"]["title"], "First")
        self.assertEqual(registry["saved_2"]["source_id"], "S1")
        self.assertEqual(registry["saved_2"]["source_version"], "v1")
        self.assertEqual(registry["saved_2"]["published_at"], "2024-01-15T10:00:00Z")
        self.assertNotIn("raw_text", registry["saved_2"])
        self.assertNotIn("source_registry", service.config)

    def test_unfinished_or_empty_search_never_reaches_filter_or_builder(self):
        self.forbid_legacy()
        for status, documents in [("paused", self.search_result["documents"]),
                                  ("failed", []), ("limit", []),
                                  ("insufficient", []), ("finished", [])]:
            with self.subTest(status=status):
                self.search_result = {"status": status, "documents": documents, "reports": []}
                service = self.service.ReconstructionService(self.config())
                with patch.object(service, "_run_pipeline") as build, \
                     patch.object(self.service, "prepare_documents") as relevance:
                    with self.assertRaisesRegex(ValueError, "Enhanced search did not finish"):
                        service.run_reconstruction("Trace documented experiences", [], None)
                    build.assert_not_called()
                    relevance.assert_not_called()

    def test_explicit_agent_mode_selects_shared_search_for_each_subject_type(self):
        self.forbid_legacy()
        for mode in ("person", "company"):
            with self.subTest(mode=mode):
                config = self.config()
                config["subject_search"] = {"enabled": False}
                config["builder_config"]["reconstruction"]["mode"] = mode
                if mode == "company":
                    config["builder_config"]["builder_type"] = "AgentEventBuilder"
                service = self.service.ReconstructionService(config)
                service._run_pipeline = lambda contents, *args: contents
                contents = service.run_reconstruction("Trace documented experiences", [], None)
                self.assertEqual([text.split("\n\n", 1)[1] for text in contents], [doc["raw_text"] for doc in self.search_result["documents"]])
        self.assertEqual(len(self.search_calls), 2)

    def test_null_legacy_subject_options_keep_agent_mode_runnable(self):
        self.forbid_legacy()
        config = self.config()
        config["subject_search"] = None
        service = self.service.ReconstructionService(config)
        service._run_pipeline = lambda contents, *args: contents
        contents = service.run_reconstruction("Trace documented experiences", [], None)
        self.assertEqual([text.split("\n\n", 1)[1] for text in contents], [doc["raw_text"] for doc in self.search_result["documents"]])
        self.assertEqual(len(self.search_calls), 1)

    def test_agent_selection_is_not_reclassified_and_budget_still_applies(self):
        self.forbid_legacy()
        self.search_result["documents"][0]["raw_text"] = "Original execution detail. " * 200
        self.search_result["documents"][1]["relevance"] = "IRRELEVANT"
        config = self.config()
        config["relevance_filter"] = {"enabled": True, "max_model_calls": 0}
        config["all_content_config"] = {"max_content_length": 2500, "max_document_chars": 1300}
        service = self.service.ReconstructionService(config)
        service._run_pipeline = lambda contents, *args: contents
        contents = service.run_reconstruction("Trace documented experiences", [], None)
        self.assertLessEqual(sum(map(len, contents)), 2500)
        self.assertTrue(any("Second original" in text for text in contents))
        self.assertTrue(any("Original execution" in text for text in contents))
        self.assertFalse(list(self.path.rglob("relevance_decisions.json")))

    def test_shared_search_reaches_native_person_json_return_path(self):
        self.forbid_legacy()
        service = self.service.ReconstructionService(self.config())
        person = {"schema_version": "person-epg-3.0", "event": [{"event_id": "E1"}]}
        builds = []

        def native_build(contents, query, keywords, config):
            builds.append((contents, config))
            return types.SimpleNamespace(extras={"person_epg": person},
                                         subject_graph={"legacy": True}), str(self.path / "native")

        with patch.dict("sys.modules", {"finmy.subject_graph.runner": legacy.module(
                "native_subject_ui_test", build_from_contents=native_build,
                with_source_registry=with_source_registry)}):
            result = service.run_reconstruction("Trace documented experiences", [], None)
        self.assertIs(result, person)
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0][1]["source_registry"]["saved_0"]["title"], "First")
        self.assertEqual(builds[0][1]["source_registry"]["saved_0"]["source_id"], "S1")
        self.assertEqual(builds[0][1]["source_registry"]["saved_0"]["source_version"], "v1")
        self.assertEqual(self.service.st.session_state.save_builder_dir_path, str(self.path / "native"))
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
