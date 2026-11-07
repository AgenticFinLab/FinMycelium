"""Independent event calls may reuse IDs without changing the underlying facts."""
import copy
import unittest

import test_subject_graph_builder as fixtures
from finmy.subject_graph.build import _unique_record_ids, run_subject_build


COLLECTIONS = {"participations": "participation_id", "actions": "action_id",
               "transactions": "transaction_id"}


class RecordIdTests(unittest.TestCase):
    def test_all_record_types_reserve_existing_suffixes_and_preserve_content(self):
        graph = {"events": [{"event_id": f"E{i}", **{
            name: [{key: identifier, "content": str(i)}] for name, key in COLLECTIONS.items()
        }} for i, identifier in enumerate(("ID", "ID", "ID_2", "ID"))]}
        original = copy.deepcopy(graph)
        fixed, changes = _unique_record_ids(graph)
        self.assertEqual(len(changes), 6)
        for name, key in COLLECTIONS.items():
            self.assertEqual([e[name][0][key] for e in fixed["events"]],
                             ["ID", "ID_3", "ID_2", "ID_4"])
        restored = copy.deepcopy(fixed)
        for before, after in zip(graph["events"], restored["events"]):
            for name, key in COLLECTIONS.items():
                after[name][0][key] = before[name][0][key]
        self.assertEqual(restored, original)
        self.assertEqual(graph, original)
        self.assertEqual(_unique_record_ids(fixed), (fixed, []))

    def test_thirty_duplicate_ids_build_without_repair_and_reviews_use_new_ids(self):
        build = fixtures.NativeBuildTests()
        build.setUp()
        for event in build.events:
            event["transactions"] = [{
                "transaction_id": "T1", "name": fixtures.vf("Transfer"),
                "from_entity_id": fixtures.vf(event["participations"][0]["entity_id"]),
                "to_entity_id": fixtures.vf("unknown", None),
                "timestamp": copy.deepcopy(event["start_time"]), "instruments": [], "details": [],
            }]
            for name, key in COLLECTIONS.items():
                template = event[name][0]
                event[name] = [{**copy.deepcopy(template), key: f"EV1_{name}_{i}"}
                               for i in range(10)]
        graph, state, report = run_subject_build(
            fixtures.input_(), fixtures.config(), build.complete, build.save)
        self.assertTrue(report["valid"], report)
        self.assertEqual(len(build.saved["subject_record_id_normalization"]), 30)
        self.assertNotIn("SubjectGraphRepair", state["agent_executed"])
        for name, key in COLLECTIONS.items():
            self.assertEqual(len({row[key] for event in graph["events"] for row in event[name]}), 20)
            self.assertEqual([row[key] for row in build.saved["RawSubjectGraph"]["events"][1][name]],
                             [row[key] for row in build.events[1][name]])
        for name, _, payload in build.calls:
            if name == "SubjectEventReviewer":
                target = payload["TargetEvent"]
                self.assertEqual(target, next(e for e in graph["events"] if e["event_id"] == target["event_id"]))
        for before, after in zip(build.events, graph["events"]):
            restored = copy.deepcopy(after)
            for name, key in COLLECTIONS.items():
                for old, row in zip(before[name], restored[name]):
                    row[key] = old[key]
            self.assertEqual(restored, before)


if __name__ == "__main__":
    unittest.main()
