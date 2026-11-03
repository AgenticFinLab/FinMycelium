"""Offline provider response, failure and call-budget accounting."""

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from finmy.builder.sparse_build.inference import SparseAPIInference
from finmy.builder.sparse_build.main_build import SparseRagBuilder


def response(*, usage=None, finish_reason="stop", content='{"participants": []}'):
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content, refusal=None, tool_calls=None),
        finish_reason=finish_reason,
    )
    return SimpleNamespace(
        usage=usage, choices=[choice],
        model_dump=lambda **kwargs: {"choices": [{"finish_reason": finish_reason}], "id": "synthetic"},
    )


class SparseInferenceAccountingTest(unittest.TestCase):
    def setUp(self):
        self.api = SparseAPIInference.__new__(SparseAPIInference)
        self.api.model_name = "synthetic-model"
        self.api.max_tokens = 8192
        self.api.generation_config = {"max_new_tokens": 100, "temperature": 0.2}
        self.create = Mock(return_value=response())
        self.api.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {}
        self.builder.agents_lm = self.api

    def run_role(self):
        return self.builder._infer_and_parse_json(
            "ParticipantReconstructor", "system", 'source {"literal": 1}', {}, "participant"
        )

    def test_generation_params_and_missing_usage(self):
        self.run_role()
        params = self.create.call_args.kwargs
        self.assertEqual(params["model"], "synthetic-model")
        self.assertEqual(params["max_tokens"], 100)
        self.assertNotIn("max_new_tokens", params)
        self.assertEqual(self.builder._call_records[0]["status"], "accepted")
        self.assertIsNone(self.builder._call_records[0]["prompt_tokens"])
        self.assertIsNone(self.builder._call_records[0]["completion_tokens"])

    def test_usage_and_details_are_retained(self):
        self.create.return_value = response(usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=50,
            prompt_tokens_details=SimpleNamespace(cached_tokens=10),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=20),
        ))
        self.run_role()
        record = self.builder._call_records[0]
        self.assertEqual([record[k] for k in ("prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens")], [100, 50, 10, 20])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)

    def test_length_response_is_not_salvaged_even_if_json_parses(self):
        self.create.return_value = response(finish_reason="length")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.run_role()
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual(self.builder._call_records[0]["status"], "incomplete_response")

    def test_empty_response_is_not_retried(self):
        self.create.return_value = response(content=None)
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_role()
        self.assertEqual(self.create.call_count, 1)

    def test_timeout_records_unknown_usage_and_does_not_retry(self):
        self.create.side_effect = TimeoutError("synthetic")
        with self.assertRaises(TimeoutError):
            self.run_role()
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual(self.builder._call_records[0]["status"], "transport_error")
        self.assertIsNone(self.builder._call_records[0]["completion_tokens"])

    def test_global_call_limit_prevents_second_submission(self):
        self.builder.build_config = {"sparse_builder_config": {"max_calls": 1}}
        self.run_role()
        with self.assertRaisesRegex(RuntimeError, "call limit"):
            self.run_role()
        self.assertEqual(self.create.call_count, 1)

    def test_invalid_output_attempt_limit_is_bounded(self):
        self.builder.build_config = {"sparse_builder_config": {"max_json_attempts": 2}}
        self.create.return_value = response(content="not JSON")
        with self.assertRaisesRegex(ValueError, "2 attempt"):
            self.run_role()
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual([r["status"] for r in self.builder._call_records], ["invalid_output", "invalid_output"])

    def test_failed_submission_persists_ledger_without_final_graph(self):
        import json
        from pathlib import Path

        self.create.side_effect = TimeoutError("synthetic")
        with tempfile.TemporaryDirectory() as root:
            self.builder.save_dir = root
            with self.assertRaises(TimeoutError):
                self.run_role()
            ledger = json.loads(Path(root, "CallLedger.json").read_text())
            self.assertEqual(ledger[0]["status"], "transport_error")
            self.assertFalse(Path(root, "FinalEventCascade.json").exists())


if __name__ == "__main__":
    unittest.main()
