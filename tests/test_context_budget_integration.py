"""Exercise the real ReconstructionService with fake collector/model dependencies."""
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.source_documents import make_document
from source_test_support import source_batch
from finmy.runner.context_budget import allocate_context

ROOT = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


class ContextBudgetIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.warnings = []
        class Collector:
            def __init__(self, *args):
                self.timestamp = "fixture"
                self.documents = {name: [] for name in ("url", "file", "bocha", "baidu")}
            def collect_bocha_search_results(self, *args):
                text = "CORE filing: purchase dates and quantities. " * 900
                self.documents["bocha"].append(make_document(text,
                    {"title": "CORE trade", "url": "https://example.test/trade"}, "bocha"))
                return [text]
            def collect_baidu_search_results(self, *args):
                text = "CONTEXT annual letter: investment background. " * 900
                self.documents["baidu"].append(make_document(text,
                    {"title": "CONTEXT letter", "url": "https://example.test/letter"}, "baidu"))
                return [text]
            def collect_structured_data(self, *args):
                return [], []
        fake = {
            "streamlit": module("streamlit", write=lambda *a, **k: None,
                warning=self.warnings.append, session_state=types.SimpleNamespace()),
            "finmy.pipeline": module("pipeline", FinmyPipeline=object),
            "finmy.builder.utils": module("utils", estimate_complete_time=lambda **kwargs: 0),
            "finmy.web_ui.utils.formatters": module("formatters", format_timestamp=lambda: "now"),
            "finmy.web_ui.services.data_collector_service": module("collector", DataCollectorService=Collector),
        }
        self.stub = patch.dict("sys.modules", fake)
        self.stub.start()
        self.addCleanup(self.stub.stop)
        spec = importlib.util.spec_from_file_location("budget_service_test",
            ROOT / "finmy/web_ui/services/reconstruction_service.py")
        self.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.service)

    @staticmethod
    def completion(system, payload):
        if "chunks" not in payload:
            return json.dumps({"subject": "fixture", "organizations": [], "focus": [], "period": [None, None]})
        return json.dumps({"decisions": [{"chunk_id": c["chunk_id"],
            "relevance": "CONTEXT" if "CONTEXT" in c["title"] else "CORE", "confidence": .99,
            "event_time": None, "matched_entities": [], "reason": "synthetic test",
            "evidence": c["text"][:80]} for c in payload["chunks"]]})

    def run_pipeline(self, limit=6000, enabled=True):
        instance = self.service.ReconstructionService({"output_dir": str(self.path),
            "relevance_filter": {"enabled": enabled}, "all_content_config": {"max_content_length": limit}})
        self.builder_calls = []
        def build(contents, *args):
            self.builder_calls.append(contents)
            return {"contents": contents}
        instance._run_pipeline = build
        value = instance.run_reconstruction("fixture", None, None)
        return value, next(self.path.glob("pipeline_output_*"))

    def test_report_matches_exact_builder_input(self):
        value, directory = self.run_pipeline()
        saved = json.loads((directory / "builder_input_contents.json").read_text())
        report = json.loads((directory / "context_budget_report.json").read_text())
        self.assertEqual(saved, value["contents"])
        self.assertEqual(report["summary"]["included_documents"], 2)
        self.assertEqual(report["summary"]["used_chars"], sum(map(len, saved)))
        self.assertLessEqual(sum(map(len, saved)), 6000)
        self.assertIn("https://example.test/letter", saved[1])
        raw = json.loads(next(directory.glob("All_Text_Content_*.json")).read_text())
        self.assertGreater(sum(map(len, raw)), 6000)
        self.assertTrue((directory / "retrieved_documents.json").exists())

    def test_disabled_filter_needs_no_saved_decision_file(self):
        value, directory = self.run_pipeline(enabled=False)
        self.assertEqual(len(value["contents"]), 2)
        self.assertFalse((directory / "relevance_decisions.json").exists())
        self.assertLessEqual(sum(map(len, value["contents"])), 6000)

    def test_insufficient_budget_warns_and_does_not_build(self):
        with self.assertRaisesRegex(ValueError, "Context budget admitted no documents"):
            self.run_pipeline(limit=1)
        self.assertEqual(self.builder_calls, [])
        self.assertTrue(self.warnings)
        directory = next(self.path.glob("pipeline_output_*"))
        self.assertTrue((directory / "context_budget_report.json").exists())

    def test_legacy_helper_skips_one_oversized_document(self):
        instance = self.service.ReconstructionService({"all_content_config": {"max_content_length": 20}})
        self.assertEqual(instance._limit_content_length(["x" * 50, "later", "doc"]), ["later", "doc"])

    def test_filter_preserves_search_phases_before_budgeting(self):
        docs = [{**make_document("Evidence. " * 500, {"title": "CORE " + phase}, "bocha"),
                 "search_phase": phase}
                for phase in ("initial", "followup", "decision_followup")]
        for enabled in (False, True):
            with self.subTest(filter_enabled=enabled):
                config = {"relevance_filter": {"enabled": enabled},
                          "all_content_config": {"max_content_length": 4000}}
                first = source_batch(docs[:1], "fixture", [], config, self.path,
                                         completion=self.completion)
                combined = source_batch(docs, "fixture", [], config, self.path,
                                            completion=self.completion)
                self.assertEqual([d["search_phase"] for d in combined["documents"]],
                                 [d["search_phase"] for d in docs])
                before = allocate_context(first["documents"], first["decisions"], config,
                                          include_metadata=enabled)
                after = allocate_context(combined["documents"], combined["decisions"], config,
                                         include_metadata=enabled)
                self.assertEqual(before["contents"], after["contents"])


if __name__ == "__main__":
    unittest.main()
