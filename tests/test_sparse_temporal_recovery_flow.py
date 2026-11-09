"""Offline retry/lifecycle regressions, including a supplied failed-run candidate.

Replies are test doubles, not newly generated model results. The corrected fixture
below tests control flow; it is not a repaired or complete version of the user's run.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.contracts import TemporalScopeError, check_temporal_scope
from finmy.builder.sparse_build.validation import validate_role
import test_sparse_person_full_flow as flow


class RawResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, infer_input=None, **kwargs):
        self.calls.append(infer_input)
        response = self.responses.pop(0)
        return SimpleNamespace(response=response,
            cost=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            extras={"finish_reason": "stop"},
            to_dict=lambda: {"response": response})


class TemporalRecoveryFlowTest(unittest.TestCase):
    def setUp(self):
        self.lifecycle = flow.SparsePersonFullFlowTest()
        self.lifecycle.setUp()
        self.addCleanup(self.lifecycle.doCleanups)
        self.fixture = json.loads((Path(__file__).parent / "fixtures" /
                                   "episode_scope_buyback_conflict.json").read_text())
        self.target = self.fixture["target_episode"]
        self.bad = self.fixture["rejected_candidate"]
        # An explicitly authored mock reply: no claim of automatic reallocation.
        self.good = copy.deepcopy(self.bad)
        self.good["participants"][0]["actions"] = []
        self.base_prompt = "TargetEpisode=" + json.dumps(self.target) + "\nSource context remains here."

    def direct_builder(self, responses, *, attempts=3, max_calls=300):
        builder, _ = self.lifecycle.builder()
        builder.build_config["sparse_builder_config"].update(
            max_json_attempts=attempts, max_calls=max_calls)
        builder.save_dir = str(self.lifecycle.root / "direct")
        Path(builder.save_dir).mkdir(exist_ok=True)
        sequence = RawResponses(responses)
        builder.agents_lm = sequence
        return builder, sequence

    def validate(self, payload):
        validate_role("ParticipantReconstructor", payload)
        check_temporal_scope(self.target, participants=payload["participants"])

    def infer(self, builder):
        return builder._infer_and_parse_json("ParticipantReconstructor", "system",
            self.base_prompt, {}, "Participants-E10", validator=self.validate)

    def report(self, builder):
        return self.lifecycle.artifact(builder, "EpisodeScopeConflicts")

    def test_real_failed_candidate_still_rejected_without_mutation(self):
        before = copy.deepcopy(self.fixture)
        with self.assertRaises(TemporalScopeError) as caught:
            self.validate(self.bad)
        self.assertEqual(self.fixture, before)
        self.assertEqual(caught.exception.report["bounds"],
                         {"start": "2022-01-01T00:00:00", "end": "2022-12-31T23:59:59.999999"})
        self.assertEqual(caught.exception.report["violations"][0]["timestamp"], "2023-02-25")
        self.assertEqual(caught.exception.report["scope"]["episode_id"], "E10")

    def test_targeted_retry_preserves_company_action_and_records_rejected_statement(self):
        before = copy.deepcopy(self.fixture)
        builder, sequence = self.direct_builder([json.dumps(self.bad), json.dumps(self.good)])
        result = self.infer(builder)
        self.assertEqual(result, self.good)
        self.assertEqual(result["participants"][1], self.bad["participants"][1])
        self.assertEqual(self.fixture, before)
        self.assertEqual(len(sequence.calls), 2)
        retry = sequence.calls[1].user_msg
        self.assertTrue(retry.startswith(self.base_prompt))
        self.assertIn("EPISODE MEMBERSHIP CORRECTION", retry)
        self.assertNotIn("invalid or truncated JSON", retry)
        self.assertIn('"timestamp":"2023-02-25"', retry)
        self.assertIn("previous_candidate", retry)
        report = self.report(builder)
        self.assertFalse(report["semantic_support_checked"])
        self.assertEqual(len(report["conflicts"]), 1)
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["rejected_candidate"], self.bad)
        self.assertEqual(conflict["status"], "needs_scope_review")
        self.assertFalse(conflict["automatic_reassignment"])
        ledger = self.lifecycle.artifact(builder, "CallLedger")
        self.assertEqual([row["status"] for row in ledger], ["invalid_output", "accepted"])
        self.assertEqual(ledger[0]["validation_kind"], "episode_temporal_scope")
        self.assertEqual(self.lifecycle.artifact(builder, "Participants-E10-Result"), self.good)

    def test_three_invalid_replies_still_fail_and_retain_all_candidates(self):
        builder, sequence = self.direct_builder([json.dumps(self.bad)] * 3)
        with self.assertRaisesRegex(ValueError, "after 3 attempt.*2023-02-25.*outside target bounds"):
            self.infer(builder)
        self.assertEqual(len(sequence.calls), 3)
        self.assertEqual([r["attempt"] for r in self.report(builder)["conflicts"]], [1, 2, 3])
        self.assertTrue(all(r["rejected_candidate"] == self.bad for r in self.report(builder)["conflicts"]))
        self.assertFalse(Path(builder.save_dir, "Participants-E10-Result.json").exists())

    def test_budget_stops_before_retry_but_keeps_scope_diagnostic(self):
        builder, sequence = self.direct_builder([json.dumps(self.bad), json.dumps(self.good)], max_calls=1)
        with self.assertRaisesRegex(RuntimeError, "model call limit"):
            self.infer(builder)
        self.assertEqual(len(sequence.calls), 1)
        self.assertEqual(len(self.report(builder)["conflicts"]), 1)
        self.assertFalse(Path(builder.save_dir, "Participants-E10-Result.json").exists())

    def test_syntax_failure_still_uses_existing_json_retry(self):
        builder, sequence = self.direct_builder(['{"participants":', json.dumps(self.good)])
        self.assertEqual(self.infer(builder), self.good)
        self.assertIn("invalid or truncated JSON", sequence.calls[1].user_msg)
        self.assertNotIn("EPISODE MEMBERSHIP CORRECTION", sequence.calls[1].user_msg)
        self.assertFalse(Path(builder.save_dir, "EpisodeScopeConflicts.json").exists())

    def test_balanced_fragment_recovery_does_not_bypass_scope_validation(self):
        # The second object makes the initial greedy JSON parser fail. A valid
        # balanced first object still has to pass the same temporal validator.
        text = json.dumps(self.bad) + '\nextra {"marker":"trailing"}'
        builder, sequence = self.direct_builder([text, json.dumps(self.good)])
        self.assertEqual(self.infer(builder), self.good)
        self.assertEqual(self.report(builder)["conflicts"][0]["rejected_candidate"], self.bad)
        self.assertIn("EPISODE MEMBERSHIP CORRECTION", sequence.calls[1].user_msg)

    def test_event_lifecycle_counts_retry_and_exports_review_diagnostic(self):
        responses = flow.extraction_responses()
        invalid = copy.deepcopy(responses[2])
        invalid["participants"][0]["actions"][0]["timestamp"]["value"] = "2026-01-01"
        responses.insert(2, invalid)
        responses.insert(3, {"decision": "keep_scope", "episode": None,
                             "reason": "The later action belongs to another scene."})
        builder, sequence = self.lifecycle.builder(extraction=responses)
        output = builder.run(self.lifecycle.inputs)
        self.assertEqual(len(sequence.calls), 9)
        self.assertEqual(output.extras["usage"]["calls"], 9)
        self.assertEqual(output.extras["usage"]["retries"], 1)
        self.assertEqual(len(output.extras["episode_scope_conflicts"]), 1)
        self.assertFalse(output.extras["acceptance"]["semantic_approval"])
        self.assertEqual(output.extras["episode_scope_conflicts"], self.report(builder)["conflicts"])
        self.assertEqual(self.lifecycle.artifact(builder, "RunManifest")["status"], "completed")
        self.assertTrue(Path(builder.save_dir, "FinalEventCascade.json").exists())

    def test_recovered_fragment_exhaustion_preserves_temporal_error_cause(self):
        text = json.dumps(self.bad) + '\nextra {"marker":"trailing"}'
        builder, _ = self.direct_builder([text], attempts=1)
        with self.assertRaises(ValueError) as caught:
            self.infer(builder)
        self.assertIsInstance(caught.exception.__cause__, TemporalScopeError)
        self.assertEqual(caught.exception.__cause__.report["scope"]["episode_id"], "E10")

    def test_event_lifecycle_exhaustion_remains_failed_without_final_artifacts(self):
        self.lifecycle.config["sparse_builder_config"]["max_json_attempts"] = 3
        responses = flow.extraction_responses()
        invalid = copy.deepcopy(responses[2])
        invalid["participants"][0]["actions"][0]["timestamp"]["value"] = "2026-01-01"
        review = {"decision": "keep_scope", "episode": None,
                  "reason": "The later action belongs to another scene."}
        builder, sequence = self.lifecycle.builder(organization=[], extraction=responses[:2] + [invalid, review, invalid, invalid])
        with self.assertRaisesRegex(ValueError, "ParticipantReconstructor returned invalid output after 3"):
            builder.run(self.lifecycle.inputs)
        self.assertEqual(len(sequence.calls), 6)
        self.lifecycle.assert_failed(builder, 6)
        self.assertEqual(len(self.report(builder)["conflicts"]), 3)
        self.assertFalse(Path(builder.save_dir, "FinalPersonEPG.html").exists())


if __name__ == "__main__":
    unittest.main()
