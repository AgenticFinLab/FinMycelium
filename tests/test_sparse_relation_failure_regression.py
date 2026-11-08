"""Real rejected responses remain proposals, never a verified relation gold set.

The fixture preserves the supplied run's exact relation payloads and only the
ID/time mappings needed for deterministic validation. No online model is called.
"""

import copy
import hashlib
import json
from pathlib import Path
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.organization_errors import OrganizationValidationError
from finmy.builder.sparse_build.person_organization import _check_temporal_link
from finmy.builder.sparse_build.relation_candidates import (
    RelationCandidatePool, validate_relation_candidates,
)


FIXTURES = Path(__file__).parent / "fixtures"


class RealRelationFailureRegressionTest(unittest.TestCase):
    def setUp(self):
        self.fixture_path = FIXTURES / "relation_batch_overflow.json"
        self.fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.package = self.fixture["temporal_package"]
        self.assigned = self.fixture["assigned_ids"]
        self.allowed = self.fixture["allowed_activity_ids"]

    def validate(self, payload):
        return validate_relation_candidates(payload, self.assigned, self.allowed, self.package)

    def test_fixture_preserves_actual_failure_counts_and_known_distinct_endpoints(self):
        self.assertLess(self.fixture_path.stat().st_size, 100_000)
        self.assertIn("not verified facts", self.fixture["provenance"]["warning"])
        self.assertEqual(len(self.assigned), 20)
        self.assertEqual(len(self.allowed), 39)
        self.assertEqual({row["activity_id"] for row in self.package["activity"]}, set(self.allowed))
        for attempt, total, overflow in zip(self.fixture["attempts"], (34, 36, 23), (16, 18, 11)):
            with self.subTest(attempt=attempt["attempt"]):
                rows = attempt["payload"]["activity_relations"]
                self.assertEqual(attempt["finish_reason"], "stop")
                self.assertEqual(len(rows), total)
                self.assertEqual(sum(row["from_activity_id"] not in self.assigned for row in rows), overflow)
                self.assertTrue(all(row["from_activity_id"] in self.allowed for row in rows))
                self.assertTrue(all(row["to_activity_id"] in self.allowed for row in rows))
                self.assertTrue(all(row["from_activity_id"] != row["to_activity_id"] for row in rows))

    def test_structurally_valid_overflow_is_retained_as_unreviewed_candidates(self):
        payload = self.fixture["attempts"][2]["payload"]
        original = copy.deepcopy((payload, self.package))
        self.validate(payload)
        pool = RelationCandidatePool(self.allowed, batch_size=20)
        pool.add(payload, "PersonOrganization-Relations-001", self.assigned)
        report = pool.snapshot()
        candidates = report["candidates"]
        self.assertEqual(len(candidates), 23)
        normalize = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.assertEqual(sorted(normalize(row["relation"]) for row in candidates),
                         sorted(normalize(row) for row in payload["activity_relations"]))
        self.assertEqual(sum(row["relation"]["from_activity_id"] not in self.assigned
                             for row in candidates), 11)
        self.assertFalse(report["semantic_support_checked"])
        self.assertNotIn("activity_relations", report)
        self.assertEqual((payload, self.package), original)

    def test_original_temporal_issues_are_still_rejected_with_precise_rows(self):
        for attempt, indices in zip(self.fixture["attempts"][:2],
                                    ([28, 30, 31, 32, 33], [30, 32, 33, 34, 35])):
            with self.subTest(attempt=attempt["attempt"]):
                payload = attempt["payload"]
                original = copy.deepcopy((payload, self.package))
                with self.assertRaises(OrganizationValidationError) as caught:
                    self.validate(payload)
                issues = caught.exception.report["violations"]
                self.assertEqual(len(issues), 5)
                self.assertEqual([issue["path"] for issue in issues],
                                 [f"activity_relations[{index}]" for index in indices])
                self.assertEqual({issue["code"] for issue in issues}, {"temporal_unestablished"})
                self.assertTrue(all("not established" in issue["message"] for issue in issues))
                self.assertEqual([issue["item"] for issue in issues],
                                 [payload["activity_relations"][index] for index in indices])
                self.assertEqual((payload, self.package), original)

    def test_coarse_and_unknown_dates_are_not_coerced_to_satisfy_time_validation(self):
        payload = self.fixture["attempts"][0]["payload"]
        rows = payload["activity_relations"]
        lookup = {row["activity_id"]: row for row in self.package["activity"]}
        actions = {row["action_id"]: row for row in self.package["action"]}
        times = {row["time_id"]: row for row in self.package["time_value"]}

        def timestamp(activity_id):
            action = actions[lookup[activity_id]["action_id"]]
            return times[action["timestamp_time_id"]]["value"]

        self.assertEqual(timestamp(rows[28]["from_activity_id"]), "unknown")
        self.assertEqual(timestamp(rows[30]["to_activity_id"]), "2023-04")
        self.assertEqual(timestamp(rows[32]["to_activity_id"]), "2023-06 (mid-June)")
        before = copy.deepcopy(self.package)
        for index in (28, 30, 31, 32, 33):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "not established"):
                    _check_temporal_link(self.package, rows[index])
        self.assertEqual(self.package, before)

    def test_fixed_buffett_regression_json_remains_byte_identical(self):
        raw = (FIXTURES / "buffett_person_epg_preview.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c")


if __name__ == "__main__":
    unittest.main()
