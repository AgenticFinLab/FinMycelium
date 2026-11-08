"""Render additions in time without rewriting or reordering the original graph."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from finmy.person_epg.visualizer import render_person_epg
from test_person_epg_visualizer import PageData
from test_event_refinement import package_fixture

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is used for the actual renderer")
class EnrichmentDisplayOrderTests(unittest.TestCase):
    def setUp(self):
        self.package = package_fixture()
        event = copy.deepcopy(self.package["event"][0])
        self.event_id = event["event_id"]
        self.package["event"] = [event]
        self.package["domain"] = [d for d in self.package["domain"] if d["domain_id"] == event["domain_id"]]
        self.package["stage"] = []
        self.package["event_activity"] = []
        self.package["event_activity_detail"] = []

    def stage(self, name, added=False):
        stage_id = ("EF_STAGE_" if added else "OLD_STAGE_") + name
        self.package["stage"].append({"event_id": self.event_id, "stage_id": stage_id,
            "label": name, "sort_order": len(self.package["stage"])})
        return stage_id

    def activity(self, name, date=None, *, added=False, stage=None):
        activity_id = ("EF_ACTIVITY_" if added else "OLD_ACTIVITY_") + name
        oid, aid, tid = "TEST_OCC_" + name, "TEST_ACTION_" + name, "TEST_TIME_" + name
        if date is not None:
            self.package["time_value"].append({"time_id": tid, "value": date})
        self.package["occurrence"].append({"occurrence_id": oid, "title": name,
            "subject_relevance": "documented_activity", "sort_order": len(self.package["occurrence"])})
        self.package["occurrence_participant"].append({"occurrence_id": oid,
            "entity_id": self.package["graph"]["subject_entity_id"]})
        self.package["action"].append({"action_id": aid, "occurrence_id": oid,
            "actor_id": self.package["graph"]["subject_entity_id"], "action_type": name,
            "timestamp_time_id": tid if date is not None else None, "sort_order": len(self.package["action"])})
        self.package["activity"].append({"activity_id": activity_id, "action_id": aid})
        self.package["event_activity"].append({"event_id": self.event_id, "activity_id": activity_id,
            "stage_id": stage, "detail_mode": "all", "sort_order": len(self.package["event_activity"])})
        return activity_id

    def render_order(self):
        before = copy.deepcopy(self.package)
        exported = json.loads(PageData(render_person_epg(self.package)).payload)
        self.assertEqual(exported, before, "HTML must retain the canonical graph unchanged")
        run = subprocess.run(["node", str(ROOT / "tests/person_epg_render_check.cjs")],
            input=json.dumps({"data": exported, "script": str(ROOT / "finmy/person_epg/assets/timeline.js")}),
            text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.package, before)
        traces = [t for t in json.loads(run.stdout)["data"] if t.get("meta", {}).get("kind") == "activity"]
        return [t["meta"]["activity_id"] for t in traces]

    def test_earlier_ungrouped_addition_is_inserted_and_old_relative_order_stays(self):
        old_later = self.activity("old_later", "2022-09-01")
        old_earlier = self.activity("old_earlier", "2022-04-01")
        new_early = self.activity("new_early", "2022-02-01", added=True)
        new_middle = self.activity("new_middle", "2022-06-01", added=True)
        shown = self.render_order()
        self.assertEqual(shown, [new_early, new_middle, old_later, old_earlier])
        self.assertEqual([a for a in shown if a.startswith("OLD_")], [old_later, old_earlier])

    def test_undated_additions_append_and_equal_times_keep_stable_order(self):
        old = self.activity("old", "2022-06-01")
        later = self.activity("later", "2022-12-01")
        undated = self.activity("undated", added=True)
        same1 = self.activity("same1", "2022-06-01", added=True)
        same2 = self.activity("same2", "2022-06-01", added=True)
        self.assertEqual(self.render_order(), [old, same1, same2, later, undated])

    def test_uncertain_year_does_not_claim_precedence_over_overlapping_day(self):
        old = self.activity("day", "2022-06-01")
        broad = self.activity("whole_year", "2022", added=True)
        self.assertEqual(self.render_order(), [old, broad])

    def test_existing_stage_members_and_new_stage_blocks_insert_without_reassignment(self):
        old_stage = self.stage("old_later_stage")
        another_old_stage = self.stage("old_earlier_stage")
        old_later = self.activity("old_later", "2022-09-01", stage=old_stage)
        old_earlier = self.activity("old_earlier", "2022-04-01", stage=another_old_stage)
        new_inside_old = self.activity("new_inside_old", "2022-06-01", added=True, stage=old_stage)
        new_stage = self.stage("new_early_stage", added=True)
        new_early = self.activity("new_early", "2022-02-01", added=True, stage=new_stage)
        undated_stage = self.stage("new_undated_stage", added=True)
        undated = self.activity("undated", added=True, stage=undated_stage)
        self.assertEqual(self.render_order(), [new_early, new_inside_old, old_later, old_earlier, undated])
        self.assertEqual(self.package["event_activity"][0]["stage_id"], old_stage)
        self.assertEqual(self.package["event_activity"][1]["stage_id"], another_old_stage)

    def test_unenriched_stored_order_is_unchanged_even_if_nonchronological(self):
        late = self.activity("late", "2022-09-01")
        unknown = self.activity("unknown")
        early = self.activity("early", "2022-01-01")
        self.assertEqual(self.render_order(), [late, unknown, early])


if __name__ == "__main__":
    unittest.main()
