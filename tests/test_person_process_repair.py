"""Import integrity for saved pre-canonical PersonFactRepair artifacts."""
import copy
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.person_epg.sparse_adapter import build_person_facts
from finmy.builder.sparse_build.person_fact_repair import apply_operation, replay_facts
from finmy.builder.sparse_build.runtime import digest
from test_sparse_person_adapter import fixture


class LegacyFactRepairReplayTest(unittest.TestCase):
    def package(self, duplicate=False):
        cascade, inputs, subject = fixture()
        if duplicate:
            stage = copy.deepcopy(cascade["stages"][0])
            stage["stage_id"] = "S2"
            cascade["stages"].append(stage)
        return build_person_facts(cascade, inputs, subject)[0]

    def operation(self, **kwargs):
        return {"quotes": ["Acme  bought shares on 2023-05-01."],
                "reason": "The original source documents this company action.", **kwargs}

    def artifact(self, package, operations):
        result = copy.deepcopy(package)
        audit = []
        for op in operations:
            result = apply_operation(result, op, [op["activity_id"]])
            audit.append({"status": "applied", "operation": op})
        return {"version": 1, "input_sha256": digest(package), "package": result, "audit": audit}

    def test_paid_fuzzy_date_and_actor_correction_replay_without_model(self):
        package = self.package()
        aid = package["activity"][0]["activity_id"]
        ops = [self.operation(op="edit", activity_id=aid, field="actor_id", value="entity:P_2"),
               self.operation(op="edit", activity_id=aid, field="timestamp", value="before May 2023")]
        artifact = self.artifact(package, ops)
        changed = replay_facts(package, artifact)
        self.assertEqual(changed["action"][0]["actor_id"], "entity:P_2")
        self.assertEqual(package["action"][0]["actor_id"], "alice")
        tid = changed["action"][0]["timestamp_time_id"]
        self.assertEqual(next(t["value"] for t in changed["time_value"] if t["time_id"] == tid), "before May 2023")

    def test_saved_duplicate_transfer_merge_replays_and_detects_tampering(self):
        package = self.package(duplicate=True)
        ids = [a["activity_id"] for a in package["activity"] if a.get("transaction_id")]
        artifact = self.artifact(package, [self.operation(op="merge", activity_id=ids[1], keep_id=ids[0])])
        result = replay_facts(package, artifact)
        self.assertEqual(len(result["financial_transaction"]), 1)
        self.assertEqual(len(package["financial_transaction"]), 2)
        bad = copy.deepcopy(artifact)
        bad["package"]["financial_transaction"][0]["name"] = "tampered"
        with self.assertRaisesRegex(ValueError, "differs"):
            replay_facts(package, bad)

    def test_rejected_legacy_operations_are_not_reapplied(self):
        package = self.package()
        bad = self.operation(op="edit", activity_id="missing", field="actor_id", value="missing")
        artifact = {"version": 1, "input_sha256": digest(package), "package": copy.deepcopy(package),
                    "audit": [{"status": "rejected", "operation": bad}, {"status": "unreviewed"}]}
        self.assertEqual(replay_facts(package, artifact), package)

    def test_legacy_merge_retains_unique_details(self):
        package = self.package(duplicate=True)
        ids = [a["activity_id"] for a in package["activity"] if a.get("action_id")]
        first, second = ids[0], ids[2]
        detail = next(d for d in package["activity_detail"] if d["activity_id"] == second)
        detail["value"] = "Additional original detail"
        artifact = self.artifact(package, [self.operation(op="merge", activity_id=second, keep_id=first)])
        details = [d for d in replay_facts(package, artifact)["activity_detail"] if d["activity_id"] == first]
        self.assertEqual(len(details), 2)
        self.assertEqual(len({d["detail_index"] for d in details}), 2)

    def test_changed_input_or_unsupported_quote_is_rejected(self):
        package = self.package()
        aid = package["activity"][0]["activity_id"]
        artifact = self.artifact(package, [])
        changed = copy.deepcopy(package)
        changed["action"][0]["action_type"] = "different input"
        with self.assertRaisesRegex(ValueError, "input differs"):
            replay_facts(changed, artifact)
        op = self.operation(op="edit", activity_id=aid, field="timestamp", value="2020")
        op["quotes"] = ["not in sources"]
        with self.assertRaisesRegex(ValueError, "Quote not found"):
            self.artifact(package, [op])

    def test_paid_aggregate_replacement_preserves_components(self):
        package = self.package(duplicate=True)
        ids = [a["activity_id"] for a in package["activity"] if a.get("transaction_id")]
        artifact = self.artifact(package, [self.operation(op="covered_by", activity_id=ids[1], keep_ids=[ids[0]])])
        self.assertEqual(len(replay_facts(package, artifact)["financial_transaction"]), 1)


if __name__ == "__main__":
    unittest.main()
