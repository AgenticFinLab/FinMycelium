"""Offline regressions for scope diagnostics and fact-preserving retry feedback."""

import copy
import json
import unittest

from finmy.builder.sparse_build.contracts import (
    TemporalScopeError, check_temporal_scope, episode_scope,
)
from finmy.builder.sparse_build.temporal_recovery import build_temporal_retry_user_msg


def vf(value):
    return {"value": value, "evidence_source_contents": ["Original source quotation"],
            "reasons": ["Original reasoning"], "confidence": 0.8}


def target(start="2018", end="2018"):
    return {"episode_id": "E_company", "index_in_stage": 0,
            "name": vf("Company operations"), "start_time": vf(start), "end_time": vf(end)}


def action(name, stamp):
    return {"name": vf(name), "timestamp": vf(stamp), "details": [vf("Unchanged detail")]}


class SparseTemporalScopeTest(unittest.TestCase):
    def capture(self, scope, **kwargs):
        with self.assertRaises(TemporalScopeError) as caught:
            check_temporal_scope(scope, **kwargs)
        return caught.exception

    def test_all_conflicts_retain_original_items_and_actor_ids(self):
        scope = target()
        participants = [
            {"participant_id": "P_person", "actions": [
                action("Later shareholder statement", "2019-03-04"),
                action("Earlier proposal", "2017-12-31")]},
            {"participant_id": "P_company", "actions": [action("Company operation", "2018")]},
        ]
        transactions = [action("Later completed transfer", "2019-03"),
                        action("In-scope transfer", "2018-06")]
        before = copy.deepcopy((scope, participants, transactions))
        error = self.capture(scope, participants=participants, transactions=transactions)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), "Episode scope: participants[0].actions[0].timestamp '2019-03-04' is outside target bounds")
        self.assertEqual(error.report["scope"], episode_scope(scope))
        self.assertEqual(error.report["bounds"], {"start": "2018-01-01T00:00:00",
                                                 "end": "2018-12-31T23:59:59.999999"})
        conflicts = error.report["violations"]
        self.assertEqual([row["path"] for row in conflicts],
                         ["participants[0].actions[0]", "participants[0].actions[1]", "transactions[0]"])
        self.assertEqual(conflicts[0]["participant_id"], "P_person")
        self.assertNotIn("participant_id", conflicts[2])
        self.assertEqual([row["item"] for row in conflicts],
                         participants[0]["actions"] + transactions[:1])
        self.assertEqual((scope, participants, transactions), before)
        participants[0]["actions"][0]["details"][0]["value"] = "Changed after validation"
        self.assertEqual(conflicts[0]["item"]["details"][0]["value"], "Unchanged detail")

    def test_known_overlap_keeps_original_acceptance_shape_and_precision(self):
        scope = target("2018-03", "2018-07")
        values = ["2018", "2018-03", "2018-07-31", "May 2018"]
        people = [{"participant_id": "P_company", "actions": [action("Operation", v) for v in values]}]
        before = copy.deepcopy(people)
        report = check_temporal_scope(scope, participants=people)
        self.assertEqual(set(report), {"scope", "start_checked", "end_checked", "items"})
        self.assertTrue(report["start_checked"])
        self.assertTrue(report["end_checked"])
        self.assertEqual([row["timestamp"] for row in report["items"]], values)
        self.assertEqual({row["status"] for row in report["items"]}, {"overlaps_known_bounds"})
        self.assertEqual(people, before)

    def test_unknown_or_unparsed_dates_remain_unchecked(self):
        values = ["unknown", "around that period", None, "2018-02-30"]
        report = check_temporal_scope(target(), transactions=[action("Transfer", v) for v in values])
        self.assertEqual([row["timestamp"] for row in report["items"]], values)
        self.assertEqual({row["status"] for row in report["items"]}, {"unchecked"})
        unbounded = check_temporal_scope(target(None, None), transactions=[action("Transfer", "1900")])
        self.assertFalse(unbounded["start_checked"])
        self.assertFalse(unbounded["end_checked"])
        self.assertEqual(unbounded["items"][0]["status"], "unchecked")

    def test_one_sided_bounds_still_reject_disjoint_dates(self):
        for scope, stamp, missing in ((target(None, "2018"), "2019", "start"),
                                      (target("2018", None), "2017", "end")):
            with self.subTest(missing=missing):
                error = self.capture(scope, transactions=[action("Transfer", stamp)])
                self.assertIsNone(error.report["bounds"][missing])
                self.assertEqual(error.report["violations"][0]["timestamp"], stamp)

    def test_reversed_episode_bounds_keep_original_error(self):
        with self.assertRaisesRegex(ValueError, "start_time is later than end_time") as caught:
            check_temporal_scope(target("2019", "2018"))
        self.assertNotIsInstance(caught.exception, TemporalScopeError)

    def test_temporal_feedback_is_semantic_and_carries_complete_prior_candidate(self):
        payload = {"participants": [{"participant_id": "P_company", "actions": [
            action("Operation", "2018"), action("Later disclosure", "2019-03-04")]}]}
        error = self.capture(target(), participants=payload["participants"])
        before = copy.deepcopy((payload, error.report))
        source_prompt = 'Original source and StageSkeleton {"value":"{literal}"}'
        message = build_temporal_retry_user_msg(source_prompt, "ParticipantReconstructor", error, payload)
        self.assertTrue(message.startswith(source_prompt))
        self.assertIn("semantic issue, not JSON syntax", message)
        self.assertNotIn("invalid or truncated JSON", message)
        for instruction in ("actual actor", "change a timestamp to unknown", "reduce its precision",
                            "widen TargetEpisode", "keep the company as actor", "matching date alone",
                            "rewrite completed Episodes", "retained separately for review"):
            self.assertIn(instruction, message)
        data = json.loads(message.split("instructions from source material:\n", 1)[1])
        self.assertEqual(data["previous_candidate"], payload)
        self.assertEqual(data["temporal_scope_report"], error.report)
        self.assertEqual(data["agent"], "ParticipantReconstructor")
        self.assertEqual((payload, error.report), before)

    def test_transaction_feedback_retains_transfer_and_does_not_hardcode_people_or_years(self):
        payload = {"transactions": [action("Settlement", "2041-09-08")]}
        error = self.capture(target("2040", "2040"), transactions=payload["transactions"])
        message = build_temporal_retry_user_msg("Source", "TransactionReconstructor", error, payload)
        data = json.loads(message.split("instructions from source material:\n", 1)[1])
        self.assertEqual(data["agent"], "TransactionReconstructor")
        self.assertEqual(data["previous_candidate"], payload)
        self.assertIn("actions or transfers belonging to this Episode", message)
        self.assertNotIn("Buffett", message)
        self.assertNotIn("2022", message)
        self.assertNotIn("2023", message)

    def test_other_validation_errors_cannot_masquerade_as_temporal_feedback(self):
        with self.assertRaisesRegex(TypeError, "TemporalScopeError"):
            build_temporal_retry_user_msg("Source", "ParticipantReconstructor", ValueError("syntax"), {})


if __name__ == "__main__":
    unittest.main()
