"""Regression for search exhausting its clock before supplementary P0 starts."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.draft_event_search import draft_event_options
from finmy.runner.relevance_filter import filter_documents, make_document


class RelevancePhaseClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = {"builder_config": {"reconstruction": {"mode": "person", "subject": {
            "subject_id": "person", "name": "Investor", "coverage_start": "2022", "coverage_end": "2023"}}},
            "subject_search": {"max_elapsed_seconds": 300},
            "relevance_filter": {"max_model_calls": 12, "cache": False}}
        # Nine sources and twelve chunks reproduce the uploaded failure shape.
        self.docs = [make_document("Source evidence. " * count,
            {"title": str(i), "url": f"https://example.test/{i}"}, "test")
            for i, count in enumerate([60] * 8 + [1500])]
        self.calls = []

    def complete(self, system, payload):
        self.calls.append(len(payload["chunks"]))
        return json.dumps({"decisions": [{"chunk_id": c["chunk_id"], "relevance": "CORE",
            "confidence": 0.99, "event_time": None, "matched_entities": [],
            "reason": "Offline clock test only.", "evidence": c["text"][:80]}
            for c in payload["chunks"]]})

    def run_filter(self, config=None, usage=None, complete=None):
        return filter_documents(self.docs, "Investor 2022-2023", [], config or self.config,
            self.path, usage=usage, completion=complete or self.complete)

    def test_legacy_shared_clock_is_unchanged_and_reports_budget_reason(self):
        with patch("finmy.runner.relevance_filter.time.monotonic", return_value=301):
            result = self.run_filter(usage={"started_at": 0, "relevance_model_calls": 0})
        self.assertEqual(self.calls, [])
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 9})
        self.assertEqual(result["summary"]["blocked_reasons"], {"time_budget_exhausted": 3})
        self.assertEqual(result["summary"]["failed_batches"], 3)
        self.assertEqual(result["summary"]["processing_failed_batches"], 0)

    def test_new_phase_clock_processes_same_sources_with_same_finite_limit(self):
        self.config["relevance_filter"]["max_elapsed_seconds"] = 300
        with patch("finmy.runner.relevance_filter.time.monotonic", return_value=301):
            result = self.run_filter(usage={"started_at": 301, "relevance_model_calls": 0})
        self.assertEqual(self.calls, [4, 4, 4])
        self.assertEqual(result["summary"]["labels"], {"CORE": 9})
        self.assertEqual(result["summary"]["blocked_reasons"], {})

    def test_explicit_relevance_limit_overrides_acquisition_limit(self):
        self.config["subject_search"]["max_elapsed_seconds"] = 1
        self.config["relevance_filter"]["max_elapsed_seconds"] = 10
        with patch("finmy.runner.relevance_filter.time.monotonic", return_value=5):
            result = self.run_filter(usage={"started_at": 0, "relevance_model_calls": 0})
        self.assertEqual(result["summary"]["model_calls"], 3)
        self.assertEqual(self.config["subject_search"]["max_elapsed_seconds"], 1)

    def test_relevance_clock_is_not_reset_between_batches(self):
        clock = [0]
        self.config["relevance_filter"]["max_elapsed_seconds"] = 5
        def complete(*args):
            result = self.complete(*args)
            clock[0] = 6
            return result
        with patch("finmy.runner.relevance_filter.time.monotonic", side_effect=lambda: clock[0]):
            result = self.run_filter(usage={"started_at": 0, "relevance_model_calls": 0}, complete=complete)
        self.assertEqual(self.calls, [4])
        self.assertEqual(result["summary"]["blocked_reasons"], {"time_budget_exhausted": 2})
        self.assertEqual(result["summary"]["labels"], {"CORE": 4, "REVIEW": 5})

    def test_p0_limits_reject_nonfinite_zero_negative_and_boolean_values(self):
        for value in (0, -1, float("inf"), float("nan"), True, "300"):
            with self.subTest(value=value):
                config = copy.deepcopy(self.config)
                config["relevance_filter"]["max_elapsed_seconds"] = value
                with self.assertRaises(ValueError):
                    self.run_filter(config=config)
                with self.assertRaises(ValueError):
                    draft_event_options({"event_followup": {"max_relevance_elapsed_seconds": value}})
        self.assertEqual(self.calls, [])
        followup, acquisition = draft_event_options({"subject_search": {"max_elapsed_seconds": 17}})
        self.assertEqual(followup["max_relevance_elapsed_seconds"], 300)
        self.assertEqual(acquisition["max_elapsed_seconds"], 300)


if __name__ == "__main__":
    unittest.main()
