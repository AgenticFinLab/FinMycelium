"""Organization validation retries carry actionable diagnostics, not JSON advice."""

import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.organization_errors import OrganizationValidationError


class Replies:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, infer_input=None, **kwargs):
        self.calls.append(infer_input)
        response = self.responses.pop(0)
        return SimpleNamespace(response=response,
            cost=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
            extras={"finish_reason": "stop"},
            to_dict=lambda: {"response": response})


class OrganizationRetryFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {"sparse_builder_config": {"max_json_attempts": 3, "max_calls": 10}}
        self.builder.save_dir = self.temp.name
        self.base = 'Full source context includes {Query} and {"unchanged":true}.'
        self.bad = {"activity_relations": [{"from_activity_id": "UNKNOWN", "to_activity_id": "A2"}]}
        self.good = {"activity_relations": []}

    def validator(self, value):
        if value != self.good:
            raise OrganizationValidationError({
                "phase": "Relations", "assigned_ids": ["A1"], "allowed_activity_ids": ["A1", "A2"],
                "violations": [{"path": "activity_relations[0].from_activity_id",
                                "code": "unknown_source", "message": "UNKNOWN is not an existing Activity ID",
                                "item": copy.deepcopy(value["activity_relations"][0])}],
            })

    def infer(self, responses, validator=None):
        self.responses = Replies(responses)
        self.builder.agents_lm = self.responses
        return self.builder._infer_and_parse_json("PersonOrganization", "system", self.base, {},
            "PersonOrganization-Relations-001", validator=validator or self.validator)

    def artifact(self, name):
        return json.loads(Path(self.temp.name, name + ".json").read_text())

    def test_semantic_retry_has_specific_error_and_retains_rejected_response(self):
        before = copy.deepcopy(self.bad)
        result = self.infer([json.dumps(self.bad), json.dumps(self.good)])
        self.assertEqual(result, self.good)
        self.assertEqual(self.bad, before)
        retry = self.responses.calls[1].user_msg
        self.assertTrue(retry.startswith(self.base))
        self.assertIn("unknown_source", retry)
        self.assertIn("activity_relations[0].from_activity_id", retry)
        self.assertIn("UNKNOWN", retry)
        self.assertIn("previous_candidate", retry)
        self.assertNotIn("invalid or truncated JSON", retry)
        errors = self.artifact("PersonOrganizationValidationErrors")
        self.assertFalse(errors["semantic_support_checked"])
        self.assertEqual(errors["errors"][0]["rejected_candidate"], self.bad)
        self.assertEqual(errors["errors"][0]["attempt"], 1)
        ledger = self.artifact("CallLedger")
        self.assertEqual([r["status"] for r in ledger], ["invalid_output", "accepted"])
        self.assertEqual(ledger[0]["validation_kind"], "organization_semantic")


    def test_exhaustion_preserves_diagnostics_and_does_not_save_result(self):
        with self.assertRaisesRegex(ValueError, "after 3 attempt") as caught:
            self.infer([json.dumps(self.bad)] * 3)
        self.assertIsInstance(caught.exception.__cause__, OrganizationValidationError)
        self.assertEqual(len(self.responses.calls), 3)
        self.assertEqual(len(self.artifact("PersonOrganizationValidationErrors")["errors"]), 3)
        self.assertFalse(Path(self.temp.name, "PersonOrganization-Relations-001-Result.json").exists())


    def test_captured_real_responses_use_temporal_feedback_then_keep_global_candidates(self):
        # Replay captured replies only; this does not claim a live model would
        # produce the same replies after seeing the corrected feedback.
        from finmy.builder.sparse_build.relation_candidates import validate_relation_candidates

        case = json.loads((Path(__file__).parent / "fixtures" / "relation_batch_overflow.json").read_text())
        validate = lambda value: validate_relation_candidates(
            value, case["assigned_ids"], case["allowed_activity_ids"], case["temporal_package"])
        result = self.infer([json.dumps(row["payload"]) for row in case["attempts"]], validator=validate)
        self.assertEqual(result, case["attempts"][2]["payload"])
        self.assertEqual(len(result["activity_relations"]), 23)
        self.assertEqual(sum(row["from_activity_id"] not in case["assigned_ids"]
                             for row in result["activity_relations"]), 11)
        reports = self.artifact("PersonOrganizationValidationErrors")["errors"]
        self.assertEqual([len(row["issue"]["violations"]) for row in reports], [5, 5])
        for prompt in self.responses.calls[1:]:
            self.assertIn("temporal_unestablished", prompt.user_msg)
            self.assertIn("2023-04", prompt.user_msg)
            self.assertIn("2023-06 (mid-June)", prompt.user_msg)
            self.assertNotIn("invalid or truncated JSON", prompt.user_msg)
        self.assertEqual([row["status"] for row in self.artifact("CallLedger")],
                         ["invalid_output", "invalid_output", "accepted"])


if __name__ == "__main__":
    unittest.main()
