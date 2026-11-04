"""The UI service forwards inferred periods through retrieval and building."""
import copy
import json
import unittest
from unittest.mock import patch

import test_event_relevance_integration as legacy
from test_event_relevance_integration import module
from test_subject_search_integration import BODY, result
from finmy.runner.relevance_filter import filter_documents


class ScopedServiceTests(unittest.TestCase):
    setUp = legacy.WebRelevanceIntegrationTest.setUp
    completion = staticmethod(legacy.WebRelevanceIntegrationTest.completion)

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

        def run_filter(*args, **kwargs):
            return filter_documents(*args, **kwargs, completion=self.completion)

        service._run_pipeline = lambda *args: built.append(copy.deepcopy(service.config)) or {}
        adapters = {
            "finmy.runner.scoped_search_api": module("scoped_api", search=search),
            "finmy.runner.scoped_page": module("scoped_page", parse=parse),
        }
        with patch.dict("sys.modules", adapters), \
             patch.object(self.service, "filter_documents", run_filter), \
             patch.object(self.collector.DataCollectorService, "collect_bocha_search_results") as legacy_bocha, \
             patch.object(self.collector.DataCollectorService, "collect_baidu_search_results") as legacy_baidu:
            service.run_reconstruction("Warren Buffett annual meetings from January 2022 through December 2023", [], None)
        legacy_bocha.assert_not_called()
        legacy_baidu.assert_not_called()
        self.assertEqual([(c[2], c[3]) for c in calls],
                         [("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31")])
        self.assertTrue(all('"Warren Buffett"' in c[1] for c in calls))
        scope = built[0]["builder_config"]["reconstruction"]["subject"]
        self.assertEqual((scope["coverage_start"], scope["coverage_end"]), ("2022-01-01", "2023-12-31"))
        output = next(self.path.glob("pipeline_output_*"))
        profile = json.loads((output / "event_profile.json").read_text())
        self.assertEqual(profile["profile"]["period"], ["2022-01-01", "2023-12-31"])
        self.assertEqual(config, original)

    def test_event_mode_still_uses_existing_search_methods(self):
        with patch.object(self.collector.DataCollectorService, "collect_subject_search_results") as scoped:
            result_data, _ = legacy.WebRelevanceIntegrationTest.run_service(self)
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

        def run_filter(*args, **kwargs):
            return filter_documents(*args, **kwargs, completion=self.completion)

        service._run_pipeline = lambda *args: built.append(copy.deepcopy(service.config)) or {}
        adapters = {
            "finmy.runner.scoped_search_api": module("scoped_api", search=search),
            "finmy.runner.scoped_page": module("scoped_page", parse=lambda url: {"text": BODY + url, "links": []}),
        }
        with patch.dict("sys.modules", adapters), patch.object(self.service, "filter_documents", run_filter):
            service.run_reconstruction("Warren Buffett annual meeting discussions", [], None)
        self.assertEqual(calls, [("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31")])
        scope = built[0]["builder_config"]["reconstruction"]["subject"]
        self.assertIsNone(scope["coverage_start"])
        self.assertIsNone(scope["coverage_end"])
        profile = json.loads((next(self.path.glob("pipeline_output_*")) / "event_profile.json").read_text())
        self.assertEqual(profile["profile"]["period"], [None, None])


if __name__ == "__main__":
    unittest.main()
