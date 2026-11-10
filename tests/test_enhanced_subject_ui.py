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
        for name in ("collect_subject_search_results", "collect_bocha_search_results", "collect_baidu_search_results"):
            self.assertFalse(hasattr(self.collector.DataCollectorService, name))

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
        documents = json.loads((Path(directory) / "retrieved_documents.json").read_text())
        self.assertEqual([d.get("source") for d in documents], ["url", "file", "exa", "bocha", "exa"])
        self.assertEqual([d["raw_text"] for d in documents[2:]], [d["raw_text"] for d in self.search_result["documents"]])
        self.assertFalse(hasattr(service, "_draft_evidence"))
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

    def test_storyline_plan_reaches_builder_separately_from_evidence_and_does_not_leak(self):
        discovery = {"version": "person-storylines-v1", "candidate_only": True,
            "domains": [{"domain_id": "D", "label": "Investments"}],
            "events": [{"event_id": "E", "domain_id": "D", "label": "A specific investment",
                        "summary": "UNVERIFIED CANDIDATE ONLY"}]}
        self.search_result["storyline_plan"] = discovery
        for doc in self.search_result["documents"]:
            doc["event_ids"] = ["E"]
        config = self.config()
        service = self.service.ReconstructionService(config)
        captured = []

        def build(contents, *args):
            captured.append((copy.deepcopy(service.config), contents))
            return {"person_epg": "native downstream"}

        service._run_pipeline = build
        with patch.object(self.service, "allocate_context", wraps=self.service.allocate_context) as allocate:
            service.run_reconstruction("Research subject 2022-2023", [], None)
        self.assertEqual(allocate.call_args.args[2]["all_content_config"]["allocation_strategy"], "event")
        build_config, contents = captured[0]
        self.assertEqual(build_config["storyline_plan"], discovery)
        self.assertIn("source_registry", build_config)
        self.assertNotIn("UNVERIFIED CANDIDATE", "".join(contents))
        self.assertNotIn("storyline_plan", service.config)
        self.assertNotIn("storyline_plan", config)
        self.search_result.pop("storyline_plan")
        service.run_reconstruction("Another request", [], None)
        self.assertNotIn("storyline_plan", captured[1][0])


    def test_partial_search_warns_and_builds_native_result_without_schema_changes(self):
        self.forbid_legacy()
        self.search_result.update(
            status="partial", complete=False,
            reports=[{"event_id": "E1", "status": "finished"},
                     {"event_id": "E2", "status": "limit", "gaps": ["closing date"]}],
            report_path=str(self.path / "initial_event_search" / "phase_report.json"))
        config = self.config()
        config["event_followup"] = "obsolete malformed setting"
        with self.assertLogs("finmy.reconstruction_scope", level="WARNING") as warnings:
            service = self.service.ReconstructionService(config)
        self.assertEqual(len(warnings.output), 1)
        self.assertNotIn("event_followup", service.config)
        native = {"schema_version": "person-epg-3.0", "event": [{"event_id": "E1"}]}
        builder_dir = self.path / "native"
        builder_dir.mkdir()
        with patch("finmy.subject_graph.runner.build_from_contents",
                   return_value=(types.SimpleNamespace(extras={"person_epg": native}), str(builder_dir))) as build:
            result = service.run_reconstruction("Trace documented experiences", [], None)
        build.assert_called_once()
        self.assertIs(result, native)
        coverage = self.service.st.session_state.search_coverage
        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["builder_status"], "completed")
        self.assertFalse(coverage["search_complete"])
        self.assertEqual(coverage["unresolved_events"], ["E2"])
        self.assertEqual(coverage["retained_document_count"], 3)
        self.assertEqual(coverage["search_report_path"], self.search_result["report_path"])
        self.assertEqual(json.loads((builder_dir / "search_coverage_report.json").read_text()), coverage)
        self.assertTrue(any(coverage["search_coverage_report_path"] in warning for warning in self.warnings))
        self.assertNotIn("search_status", result)
        self.assertFalse(self.errors)

        # A subsequent complete run must replace the partial coverage metadata.
        self.search_result.update(status="finished", complete=True, reports=[])
        with patch("finmy.subject_graph.runner.build_from_contents",
                   return_value=(types.SimpleNamespace(extras={"person_epg": native}), str(builder_dir))):
            service.run_reconstruction("Another subject", [], None)
        self.assertTrue(self.service.st.session_state.search_coverage["search_complete"])
        service.config["builder_config"]["reconstruction"] = {"mode": "event"}
        self.search_result.update(status="insufficient", documents=[])
        with patch.object(self.collector.DataCollectorService, "collect_structured_data", return_value=([], [])):
            self.assertIsNone(service.run_reconstruction("An event", [], None))
        self.assertEqual(self.service.st.session_state.search_coverage["builder_status"], "not_started")


    def test_agent_search_serves_person_and_single_event(self):
        self.forbid_legacy()
        for mode in ("person", "event"):
            with self.subTest(mode=mode):
                config = self.config()
                config["subject_search"] = {"enabled": False}
                config["builder_config"]["reconstruction"]["mode"] = mode
                if mode == "event":
                    config["builder_config"]["reconstruction"].pop("subject")
                service = self.service.ReconstructionService(config)
                service._run_pipeline = lambda contents, *args: contents
                contents = service.run_reconstruction("Trace documented experiences", [], None)
                self.assertEqual([text.split("\n\n", 1)[1] for text in contents], [doc["raw_text"] for doc in self.search_result["documents"]])
        self.assertEqual(len(self.search_calls), 2)


    def test_empty_agent_search_keeps_explicit_source_inputs_buildable(self):
        self.search_result.update(status="paused", documents=[])
        service = self.service.ReconstructionService(self.config())
        service._run_pipeline = lambda contents, *args: contents
        def local(collector, *args):
            collector.documents["url"].append({"raw_text": "User supplied acquisition filing.", "source": "url"})
            return ["User supplied acquisition filing."], []
        with patch.object(self.collector.DataCollectorService, "collect_structured_data", local):
            contents = service.run_reconstruction("Research subject", [], object())
        self.assertEqual(len(contents), 1)
        self.assertIn("User supplied acquisition filing.", contents[0])
        self.assertEqual(service.search_coverage["search_status"], "paused")

    def test_explicit_urls_use_parser_config_and_do_not_depend_on_search_budget(self):
        config = self.config()
        config["url_collector_config"] = {"delay": 0.2, "use_selenium_fallback": False}
        config["subject_search"] = {"max_parse_calls": 0, "max_elapsed_seconds": 0}
        with patch.object(self.collector, "URLParser") as parser:
            collector = self.collector.DataCollectorService(config, str(self.path))
        self.assertEqual(parser.call_args.kwargs["delay"], 0.2)
        collector.parser = parser.return_value
        collector.parser.run.return_value = types.SimpleNamespace(results=[{"content": "Original filing body."}])
        class Row(dict):
            def to_dict(self):
                return dict(self)
        rows = types.SimpleNamespace(
            iterrows=lambda: iter(enumerate([Row(url="www.example.org/filing", title="Filing"),
                                            Row(url="https://www.example.org/filing#section", title="Duplicate") ])),
        )
        # The UI accepts a DataFrame interface; this fixture has no pandas dependency.
        class Frame:
            def __len__(self):
                return 2
            iterrows = staticmethod(rows.iterrows)
        contents, files = collector.collect_structured_data(Frame(), [])
        self.assertEqual(len(contents), 1)
        self.assertEqual(files, [])
        collector.parser.run.assert_called_once()
        self.assertEqual(collector.documents["url"][0]["url"], "https://www.example.org/filing")
        collector.parser.run.return_value = types.SimpleNamespace(results=[])
        self.assertEqual(collector.collect_structured_data(Frame(), []), ([], []))


if __name__ == "__main__":
    unittest.main()
