"""Completion status is checked before parsing, including during recovery."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError
from finmy.builder.sparse_build.main_build import SparseRagBuilder


class CompletionStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {
            "generation_config": {"max_new_tokens": 8192},
            "sparse_builder_config": {"max_calls": 3, "max_json_attempts": 3},
        }
        self.builder.save_dir = self.temp.name
        self.model = Mock()
        self.builder.agents_lm = self.model
        self.validator = Mock()

    def reply(self, **extras):
        output = SimpleNamespace(response='{"complete_json":true}',
            cost=SimpleNamespace(prompt_tokens=124203, completion_tokens=8192),
            extras=extras,
            to_dict=lambda: {"response": '{"complete_json":true}', "extras": extras})
        self.model.run.return_value = output

    def infer(self):
        return self.builder._infer_and_parse_json(
            "PersonOrganization", "system", "user", {}, "PersonOrganization",
            validator=self.validator)

    def test_length_is_explicit_and_never_salvaged_even_when_json_is_complete(self):
        self.reply(finish_reason="length", refusal=None, tool_calls=False)
        with self.assertRaises(IncompleteCompletionError) as caught:
            self.infer()
        error = caught.exception
        self.assertEqual(error.finish_reason, "length")
        self.assertEqual(error.completion_tokens, 8192)
        self.assertEqual(error.output_limit, 8192)
        self.assertFalse(error.refusal)
        self.assertFalse(error.tool_calls)
        self.assertIn("truncated", str(error))
        self.assertIn("8192", str(error))
        self.assertEqual(self.model.run.call_count, 1)
        self.validator.assert_not_called()
        ledger = json.loads(Path(self.temp.name, "CallLedger.json").read_text())
        self.assertEqual(ledger[0]["status"], "incomplete_response")
        self.assertEqual(ledger[0]["finish_reason"], "length")
        self.assertTrue(Path(self.temp.name, "PersonOrganization.json").exists())
        self.assertFalse(Path(self.temp.name, "PersonOrganization-Result.json").exists())

    def test_refusal_and_tools_are_distinguishable_and_never_accepted(self):
        for extras in ({"finish_reason": "length", "refusal": "Refused"},
                       {"finish_reason": "tool_calls", "tool_calls": True}):
            with self.subTest(extras=extras):
                self.reply(**extras)
                with self.assertRaises(IncompleteCompletionError) as caught:
                    self.infer()
                self.assertTrue(caught.exception.refusal or caught.exception.tool_calls)
                self.assertNotIn("output was truncated", str(caught.exception))
        self.validator.assert_not_called()

    def test_prior_calls_consume_budget_but_new_ledger_only_records_new_requests(self):
        self.builder._prior_call_count = 2
        self.reply(finish_reason="stop")
        self.assertEqual(self.infer(), {"complete_json": True})
        with self.assertRaisesRegex(RuntimeError, "model call limit"):
            self.infer()
        self.assertEqual(self.model.run.call_count, 1)
        self.assertEqual(len(self.builder._call_records), 1)
        self.assertEqual(self.builder._call_records[0]["status"], "accepted")

    def test_exhausted_prior_budget_prevents_any_submission(self):
        self.builder._prior_call_count = 3
        self.reply(finish_reason="stop")
        with self.assertRaisesRegex(RuntimeError, "model call limit"):
            self.infer()
        self.model.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
