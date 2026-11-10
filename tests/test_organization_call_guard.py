"""Transaction-detail failures receive precise diagnostics without changing facts."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.organization_batches import _memberships
from finmy.builder.sparse_build.organization_call_guard import (
    REFERENCE_SEPARATOR, guard_organization_call,
)
from finmy.builder.sparse_build.organization_errors import OrganizationValidationError


class Replies:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, infer_input=None, **kwargs):
        self.calls.append(infer_input)
        value = self.responses.pop(0)
        text = json.dumps(value, ensure_ascii=False)
        return SimpleNamespace(response=text,
            cost=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
            extras={"finish_reason": "stop"}, to_dict=lambda: {"response": text})


class OrganizationCallGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = json.loads((Path(__file__).parent / "fixtures" /
            "organization_transaction_detail_replay.json").read_text(encoding="utf-8"))
        self.base = json.dumps(self.case["request"], ensure_ascii=False) + "\n\nBATCH TASK:\n" + json.dumps(self.case["task"])
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {"sparse_builder_config": {"max_json_attempts": 3, "max_calls": 10}}
        self.builder.save_dir = self.temp.name

    def infer(self, responses, validator):
        self.builder.agents_lm = Replies(responses)
        return self.builder._infer_and_parse_json(
            "PersonOrganization", "Return the assignment JSON.", self.base, {},
            "PersonOrganization-Assignments-001", validator=validator)

    def validate(self, value):
        _memberships(value["memberships"], set(self.case["task"]["assigned_ids"]),
                              self.case["task"]["layout"], self.case["request"]["facts"])

    def corrected_response(self):
        # Simulate an explicit second MODEL answer; no production code rewrites
        # a failed candidate. Every other projection and membership is retained.
        value = copy.deepcopy(self.case["response"])
        for member in (7, 9, 14):
            value["memberships"][member]["detail_indices"] = []
        return value

    def test_captured_legacy_request_gets_exact_catalog_and_repairs_all_seven_indices(self):
        self.assertNotIn("available_detail_indices", self.base)
        before = copy.deepcopy(self.case)
        corrected = self.corrected_response()
        self.assertEqual(self.infer([self.case["response"], corrected], self.validate), corrected)
        self.assertEqual(len(self.builder.agents_lm.calls), 2)
        first = self.builder.agents_lm.calls[0]
        self.assertTrue(first.user_msg.startswith(self.base))
        reference = json.loads(first.user_msg.split(REFERENCE_SEPARATOR)[1])
        self.assertEqual(set(reference["available_detail_indices"]), set(self.case["task"]["assigned_ids"]))
        for member in (7, 9, 14):
            aid = self.case["response"]["memberships"][member]["activity_id"]
            self.assertEqual(reference["available_detail_indices"][aid], [])
        self.assertIn("financial_transaction.details", first.system_msg)
        error = json.loads((self.root / "PersonOrganizationValidationErrors.json").read_text())["errors"][0]
        violations = error["issue"]["violations"]
        self.assertEqual([row["path"] for row in violations], [
            "memberships[7].detail_indices[0]", "memberships[7].detail_indices[1]",
            "memberships[7].detail_indices[2]", "memberships[9].detail_indices[0]",
            "memberships[9].detail_indices[1]", "memberships[14].detail_indices[0]",
            "memberships[14].detail_indices[1]",
        ])
        self.assertTrue(all(row["allowed_detail_indices"] == [] for row in violations))
        self.assertEqual(error["rejected_candidate"], self.case["response"])
        retry = self.builder.agents_lm.calls[1].user_msg
        self.assertIn('"allowed_detail_indices":[]', retry)
        self.assertIn("T:TX_O_S2_E5_1", retry)
        self.assertNotIn("invalid or truncated JSON", retry)
        self.assertEqual(len(corrected["memberships"]), 20)
        self.assertEqual(self.case, before)
        # The complete factual input remains in the prompt verbatim, including
        # every transaction detail. [] changed only the model's display choice.
        request, _ = json.JSONDecoder().raw_decode(retry)
        self.assertEqual(request["facts"], before["request"]["facts"])


    def test_repeated_invalid_answer_is_archived_not_silently_salvaged(self):
        with self.assertRaisesRegex(ValueError, "after 3 attempt"):
            self.infer([self.case["response"]] * 3, self.validate)
        errors = json.loads((self.root / "PersonOrganizationValidationErrors.json").read_text())["errors"]
        self.assertEqual(len(errors), 3)
        self.assertTrue(all(len(row["issue"]["violations"]) == 7 for row in errors))
        self.assertTrue(all(row["rejected_candidate"] == self.case["response"] for row in errors))
        self.assertFalse((self.root / "PersonOrganization-Assignments-001-Result.json").exists())


if __name__ == "__main__":
    unittest.main()
