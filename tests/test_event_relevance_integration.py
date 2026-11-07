"""Exercise the Web UI services with fake search, parser and LLM adapters."""
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.relevance_filter import filter_documents

ROOT = Path(__file__).resolve().parents[1]


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class WebRelevanceIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.warnings = []
        class Parser:
            def __init__(self, *args, **kwargs):
                pass
            def run(self, ipt):
                return types.SimpleNamespace(results=[{"content": "Body: " + ipt.urls[0]}])
        self.modules = {
            "streamlit": module("streamlit", write=lambda *a, **k: None,
                                warning=self.warnings.append,
                                session_state=types.SimpleNamespace()),
            "finmy.pipeline": module("finmy.pipeline", FinmyPipeline=object),
            "finmy.builder.utils": module("finmy.builder.utils", estimate_complete_time=lambda **k: 0),
            "finmy.web_ui.utils.formatters": module("formatters", format_timestamp=lambda: "now"),
            "finmy.url_collector.base": module("base", URLCollectorInput=lambda **k: types.SimpleNamespace(**k)),
            "finmy.url_collector.url_parser": module("parser", URLParser=Parser),
            "finmy.url_collector.url_parser_clean": module("clean", extract_content_from_parsed_content=lambda x: x),
            "finmy.pdf_collector.pdf_collector": module("pdf", PDFCollector=object),
            "finmy.pdf_collector.base": module("pdfbase", PDFCollectorInput=object),
            "finmy.url_collector.SearchCollector.bocha_search": module("bocha", bochasearch_api=lambda *a, **k: {
                "data": {"webPages": {"value": [{"name": "OXY purchases", "url": "https://example.test/oxy",
                "snippet": "OXY 2023", "summary": "OXY investment", "siteName": "Site",
                "datePublished": "2023-10-26"}]}}}),
            "finmy.url_collector.SearchCollector.baidu_search": module("baidu", baidusearch_api=lambda *a, **k: {
                "references": [{"title": "Buffett diet", "url": "https://example.test/diet",
                "snippet": "Food", "content": "Favorite foods", "website": "Site", "date": "2026-01-01"}]}),
        }
        self.patcher = patch.dict("sys.modules", self.modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.collector = load("test_collector", ROOT / "finmy/web_ui/services/data_collector_service.py")
        self.modules["finmy.web_ui.services.data_collector_service"] = self.collector
        self.extra = patch.dict("sys.modules", {"finmy.web_ui.services.data_collector_service": self.collector})
        self.extra.start()
        self.addCleanup(self.extra.stop)
        self.service = load("test_reconstruction", ROOT / "finmy/web_ui/services/reconstruction_service.py")

    @staticmethod
    def completion(system, payload):
        if "chunks" not in payload:
            return json.dumps({"subject": "Buffett", "organizations": ["OXY"],
                               "period": ["2022", "2023"], "focus": ["investment"]})
        return json.dumps({"decisions": [
            {"chunk_id": c["chunk_id"], "relevance": "IRRELEVANT" if "diet" in c["title"] else "CORE",
             "confidence": .99, "event_time": None, "matched_entities": [],
             "reason": "Test fixture only", "evidence": c["text"][:60]} for c in payload["chunks"]]})

    def run_service(self, options=None, complete=None, budget=60000):
        service = self.service.ReconstructionService({
            "output_dir": str(self.path), "relevance_filter": options or {},
            "all_content_config": {"max_content_length": budget},
        })
        service._run_pipeline = lambda contents, *args: {"builder_contents": contents}
        def run_filter(*args, **kwargs):
            return filter_documents(*args, **kwargs, completion=complete or self.completion)
        with patch.object(self.service, "filter_documents", run_filter):
            result = service.run_reconstruction("OXY investments in 2022–2023", ["OXY"], None)
        output = next(self.path.glob("pipeline_output_*"))
        return result, output

    def test_filter_precedes_builder_and_keeps_archives(self):
        result, output = self.run_service()
        self.assertEqual(len(result["builder_contents"]), 1)
        self.assertIn("https://example.test/oxy", result["builder_contents"][0])
        self.assertIn("2023-10-26", result["builder_contents"][0])
        raw = json.loads(next(output.glob("All_Text_Content_*.json")).read_text())
        self.assertEqual(len(raw), 2)
        self.assertIn("diet", raw[1])
        saved = json.loads((output / "builder_input_contents.json").read_text())
        self.assertEqual(saved, result["builder_contents"])

    def test_disabled_pipeline_is_legacy_content(self):
        def fail(*args):
            raise AssertionError("No LLM calls expected")
        result, output = self.run_service({"enabled": False}, complete=fail)
        raw = json.loads(next(output.glob("All_Text_Content_*.json")).read_text())
        self.assertEqual(result["builder_contents"], raw)

    def test_all_rejected_does_not_build(self):
        def irrelevant(system, payload):
            value = json.loads(self.completion(system, payload))
            for decision in value.get("decisions", []):
                decision["relevance"] = "IRRELEVANT"
            return json.dumps(value)
        with self.assertRaisesRegex(ValueError, "No relevant sources"):
            self.run_service(complete=irrelevant)
        output = next(self.path.glob("pipeline_output_*"))
        self.assertTrue((output / "relevance_decisions.json").exists())
        self.assertFalse((output / "builder_input_contents.json").exists())

    def test_model_failure_warns_and_retains(self):
        def failed(*args):
            raise TimeoutError("offline failure")
        result, _ = self.run_service(complete=failed)
        self.assertEqual(len(result["builder_contents"]), 2)
        self.assertTrue(self.warnings)

    def test_exhausted_legacy_budget_does_not_build_empty_input(self):
        with self.assertRaisesRegex(ValueError, "Context budget admitted no documents"):
            self.run_service(budget=1)

    def test_person_scope_reaches_search_filter_and_builder_configuration(self):
        subject = {"subject_id": "person_warren_buffett", "name": "Warren Buffett",
                   "aliases": ["巴菲特"], "coverage_start": "2022", "coverage_end": "2023",
                   "scope": "Occidental investment activities only"}
        config = {"output_dir": str(self.path), "all_content_config": {"max_content_length": 60000},
                  "subject_search": {"enabled": False},
                  "builder_config": {"reconstruction": {"mode": "person", "subject": subject}}}
        service = self.service.ReconstructionService(config)
        built = []
        service._run_pipeline = lambda *args: built.append((args, service.config)) or {}
        searches, classifications = [], []
        original_bocha = self.collector.DataCollectorService.collect_bocha_search_results
        original_baidu = self.collector.DataCollectorService.collect_baidu_search_results

        def search(original):
            def call(collector, query, keywords):
                searches.append(query)
                return original(collector, query, keywords)
            return call

        def complete(system, payload):
            classifications.append(payload)
            return self.completion(system, payload)

        def run_filter(*args, **kwargs):
            return filter_documents(*args, **kwargs, completion=complete)

        with patch.object(self.collector.DataCollectorService, "collect_bocha_search_results", search(original_bocha)), \
             patch.object(self.collector.DataCollectorService, "collect_baidu_search_results", search(original_baidu)), \
             patch.object(self.service, "filter_documents", run_filter):
            service.run_reconstruction("OXY statements", ["OXY"], None)
        self.assertEqual(len(searches), 2)
        for query in searches:
            self.assertIn("Warren Buffett", query)
            self.assertIn(subject["scope"], query)
            self.assertIn("2022", query)
        self.assertTrue(classifications)
        self.assertEqual(classifications[0]["reconstruction"]["subject"], subject)
        args, received_config = built[0]
        self.assertEqual(args[1], "OXY statements")
        self.assertEqual(received_config["builder_config"]["reconstruction"]["subject"], subject)

    def test_invalid_person_scope_fails_before_search(self):
        with patch.object(self.collector.DataCollectorService, "collect_bocha_search_results") as search:
            with self.assertRaises(ValueError):
                self.service.ReconstructionService({"builder_config": {
                    "reconstruction": {"mode": "person", "subject": {}}}})
            search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
