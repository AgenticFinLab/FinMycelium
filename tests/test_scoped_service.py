from contextlib import nullcontext
"""The UI service forwards inferred periods through retrieval and building."""
import copy
import json
import unittest
from unittest.mock import patch

import test_source_integration as legacy
from test_source_integration import module
from test_subject_search_integration import BODY, result
from source_test_support import source_batch


class ScopedServiceTests(unittest.TestCase):
    def setUp(self):
        legacy.WebSourceIntegrationTest.setUp(self)
        # All service tests remain offline even with model dependencies installed.
        reviewer = patch("finmy.runner.decision_followup._live_completion",
                         return_value=lambda *args: {"gaps": []})
        reviewer.start()
        self.addCleanup(reviewer.stop)
    completion = staticmethod(legacy.WebSourceIntegrationTest.completion)

    def test_request_years_reach_native_search_filter_and_builder(self):
        config = {
            "output_dir": str(self.path),
            "all_content_config": {"max_content_length": 60000},
            "subject_search": {"providers": ["bocha"], "topics": ["meeting"], "max_followup_queries": 0},
            "builder_config": {"reconstruction": {"mode": "person", "subject": {
                "subject_id": "person_warren_buffett", "name": "Warren Buffett",
                "coverage_start": None, "coverage_end": None}}},
        }
        original = copy.deepcopy(config)
        service = self.service.ReconstructionService(config)
        calls, built = [], []

        def search(provider, query, count, start, end):
            calls.append((provider, query, start, end))
            return [result(f"https://www.example.com/meeting/{start[:4]}", start)]

        def parse(url):
            return {"text": BODY + url, "links": []}


        service._run_pipeline = lambda *args: built.append(copy.deepcopy(service.config)) or {}
        adapters = {
            "finmy.runner.scoped_search_api": module("scoped_api", search=search),
            "finmy.runner.scoped_page": module("scoped_page", parse=parse),
        }
        with patch.dict("sys.modules", adapters), \
             nullcontext(), \
             patch.object(self.collector.DataCollectorService, "collect_bocha_search_results") as legacy_bocha, \
             patch.object(self.collector.DataCollectorService, "collect_baidu_search_results") as legacy_baidu:
            service.run_reconstruction("Warren Buffett annual meetings from January 2022 through December 2023", [], None)
        legacy_bocha.assert_not_called()
        legacy_baidu.assert_not_called()
        self.assertEqual([(c[2], c[3]) for c in calls],
                         [("2022-01-01", "2023-12-31")])
        self.assertTrue(all('"Warren Buffett"' in c[1] for c in calls))
        scope = built[0]["builder_config"]["reconstruction"]["subject"]
        self.assertEqual((scope["coverage_start"], scope["coverage_end"]), ("2022-01-01", "2023-12-31"))
        output = next(self.path.glob("pipeline_output_*"))
        profile = json.loads((output / "event_profile.json").read_text())
        self.assertEqual(profile["profile"]["period"], ["2022-01-01", "2023-12-31"])
        self.assertEqual(config, original)

    def test_decision_sources_are_filtered_and_reach_saved_builder_input(self):
        from test_decision_followup import QUOTE, gap
        config = {
            "output_dir": str(self.path),
            "all_content_config": {"max_content_length": 60000},
            "subject_search": {"max_followup_queries": 0},
            "builder_config": {"reconstruction": {"mode": "person", "subject": {
                "subject_id": "person_warren_buffett",
                "name": "Warren Buffett", "coverage_start": "2022", "coverage_end": "2023"}}},
        }
        calls = []
        reason = "Buffett said the valuation compensated for the investment risk. "
        def search(provider, query, count, start, end):
            calls.append((provider, query, count, start, end))
            suffix = "original" if len(calls) <= 2 else "explanation"
            return [result("https://example.com/" + suffix, title="Example Energy investment")]
        def parse(url):
            return {"text": (QUOTE if url.endswith("original") else reason) * 20, "links": []}
        service = self.service.ReconstructionService(config)
        service._run_pipeline = lambda contents, *args: contents
        adapters = {
            "finmy.runner.scoped_search_api": module("scoped_api", search=search),
            "finmy.runner.scoped_page": module("scoped_page", parse=parse),
        }
        with patch.dict("sys.modules", adapters), \
             nullcontext(), \
             patch("finmy.runner.decision_followup._live_completion",
                   return_value=lambda *args: {"gaps": [gap()]}):
            contents = service.run_reconstruction("Buffett investments 2022–2023", [], None)
        self.assertEqual([c[2] for c in calls], [10, 20, 2, 5])
        self.assertTrue(all(c[3:] == ("2022-01-01", "2023-12-31") for c in calls))
        self.assertTrue(any(QUOTE in text for text in contents))
        self.assertTrue(any(reason in text for text in contents))
        output = next(self.path.glob("pipeline_output_*"))
        self.assertEqual(json.loads((output / "builder_input_contents.json").read_text()), contents)
        docs = json.loads((output / "retrieved_documents.json").read_text())
        self.assertEqual(len(docs), 2)
        self.assertEqual(len({d["document_id"] for d in docs}), 2)
        self.assertTrue((output / "decision_followup/subject_search_sources.json").exists())

    def test_search_progress_uses_existing_ui_timestamp_format(self):
        messages = []
        collector = self.collector.DataCollectorService({}, str(self.path))
        def collect(*args, progress):
            progress("Start: Bocha Search")
            progress("Bocha Search: Get 10 search results.")
            progress("Bocha Search: Parsing https://example.com/article")
            return []
        with patch("finmy.runner.subject_search.collect_subject_sources", side_effect=collect), \
             patch.object(self.collector.st, "write", side_effect=messages.append):
            collector.collect_subject_search_results("Buffett 2022–2023", [], {"name": "Buffett"})
        self.assertEqual(messages, ["**now** - Start: Bocha Search",
                                    "**now** - Bocha Search: Get 10 search results.",
                                    "**now** - Bocha Search: Parsing https://example.com/article"])

    def test_event_mode_still_uses_existing_search_methods(self):
        with patch.object(self.collector.DataCollectorService, "collect_subject_search_results") as scoped:
            result_data, _ = legacy.WebSourceIntegrationTest.run_service(self)
        scoped.assert_not_called()
        self.assertIn("https://example.test/oxy", result_data["builder_contents"][0])

    def test_publication_only_window_does_not_invent_event_coverage(self):
        config = {
            "output_dir": str(self.path),
            "all_content_config": {"max_content_length": 60000},
            "subject_search": {"providers": ["bocha"], "topics": ["meeting"],
                               "publication_start": "2022", "publication_end": "2023",
                               "max_followup_queries": 0},
            "builder_config": {"reconstruction": {"mode": "person", "subject": {
                "subject_id": "person_warren_buffett", "name": "Warren Buffett",
                "coverage_start": None, "coverage_end": None}}},
        }
        service = self.service.ReconstructionService(config)
        calls, built = [], []

        def search(provider, query, count, start, end):
            calls.append((start, end))
            return [result(f"https://www.example.com/meeting/{start[:4]}", start)]


        service._run_pipeline = lambda *args: built.append(copy.deepcopy(service.config)) or {}
        adapters = {
            "finmy.runner.scoped_search_api": module("scoped_api", search=search),
            "finmy.runner.scoped_page": module("scoped_page", parse=lambda url: {"text": BODY + url, "links": []}),
        }
        with patch.dict("sys.modules", adapters), nullcontext():
            service.run_reconstruction("Warren Buffett annual meeting discussions", [], None)
        self.assertEqual(calls, [("2022-01-01", "2023-12-31")])
        scope = built[0]["builder_config"]["reconstruction"]["subject"]
        self.assertIsNone(scope["coverage_start"])
        self.assertIsNone(scope["coverage_end"])
        profile = json.loads((next(self.path.glob("pipeline_output_*")) / "event_profile.json").read_text())
        self.assertEqual(profile["profile"]["period"], [None, None])


if __name__ == "__main__":
    unittest.main()
