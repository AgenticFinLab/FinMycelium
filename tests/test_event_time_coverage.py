"""Observed ranges change with accepted members, without rewriting old facts."""
import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from finmy.runner.event_time_coverage import event_time_coverage, compare_event_time_coverage
from finmy.person_epg.visualizer import render_person_epg
from test_event_refinement import package_fixture
from test_person_epg_visualizer import PageData


ROOT = Path(__file__).resolve().parents[1]


class EventTimeCoverageTests(unittest.TestCase):
    def setUp(self):
        self.package = {"event": [{"event_id": "E1"}, {"event_id": "E2"}],
                        "stage": [{"event_id": "E1", "stage_id": "S1"},
                                  {"event_id": "E2", "stage_id": "S1"}],
                        "activity": [], "action": [], "financial_transaction": [],
                        "occurrence": [], "time_value": [], "event_activity": []}

    def add(self, identifier, value=None, *, event="E1", context=False, **time_fields):
        tid = "T" + identifier
        if value is not None:
            self.package["time_value"].append({"time_id": tid, "value": value, **time_fields})
        self.package["activity"].append({"activity_id": identifier,
            "context_occurrence_id" if context else "action_id": identifier})
        self.package["occurrence" if context else "action"].append(
            {"occurrence_id" if context else "action_id": identifier,
             **({"start_time_id": tid, "end_time_id": tid} if context else {"timestamp_time_id": tid})})
        self.package["event_activity"].append({"event_id": event, "activity_id": identifier, "stage_id": "S1"})

    def test_new_member_expands_observed_range_without_mutating_initial_rows(self):
        self.add("old", "2022-06")
        before = copy.deepcopy(self.package)
        self.add("new", "2019")
        snapshot = copy.deepcopy(self.package)
        comparison = compare_event_time_coverage(before, self.package, "E1")
        self.assertTrue(comparison["range_changed"])
        self.assertEqual(comparison["before"]["primary"]["start"]["value"], "2022-06")
        start = comparison["after"]["primary"]["start"]
        self.assertEqual((start["value"], start["precision"]), ("2019", "year"))
        self.assertEqual(comparison["after"]["primary"]["end"]["value"], "2022-06")
        self.assertEqual(self.package, snapshot)
        self.assertEqual(comparison["after"]["stages"][0]["primary"]["start"], start)

    def test_fuzzy_window_preserves_original_precision_and_semantics(self):
        self.add("fuzzy", "unknown", window_start="2022-07-21", window_end="2022-07-31",
                 original_text="2022年7月下旬", is_approximate=True, window_semantics="uncertainty")
        result = event_time_coverage(self.package, "E1")["observed"]
        self.assertEqual(result["start"]["value"], "2022-07-21")
        self.assertEqual(result["end"]["value"], "2022-07-31")
        self.assertEqual(result["start"]["original_value"], "unknown")
        self.assertEqual(result["start"]["original_text"], "2022年7月下旬")
        self.assertTrue(result["start"]["is_approximate"])
        self.assertEqual(result["start"]["window_semantics"], "uncertainty")

    def test_exact_day_window_remains_exact_but_uncertain_range_does_not(self):
        self.add("exact", "2022-07-21", window_start="2022-07-21", window_end="2022-07-21",
                 is_approximate=False, window_semantics="uncertainty")
        exact = event_time_coverage(self.package, "E1")["observed"]
        self.assertFalse(exact["start"]["is_approximate"])
        self.assertFalse(exact["end"]["is_approximate"])
        self.add("uncertain", "unknown", window_start="2022-07-20", window_end="2022-07-22",
                 is_approximate=False, window_semantics="uncertainty")
        uncertain = event_time_coverage(self.package, "E1")["observed"]
        self.assertTrue(uncertain["start"]["is_approximate"])
        self.assertTrue(uncertain["end"]["is_approximate"])

    def test_context_publication_and_quoted_historical_dates_are_distinguished(self):
        self.add("statement", "2023-05-06")
        self.package["action"][0]["action_type"] = "Explained the 2019 purchase"
        self.add("background", "2019", context=True)
        self.package["source_document"] = [{"published_at": "2025-01-01T00:00:00Z"}]
        result = event_time_coverage(self.package, "E1")
        self.assertEqual(result["primary"]["start"]["value"], "2023-05-06")
        self.assertEqual(result["context"]["start"]["value"], "2019")
        self.assertEqual(result["observed"]["start"]["value"], "2019")
        self.assertEqual(result["observed"]["end"]["value"], "2023-05-06")

    def test_unknown_and_other_event_members_do_not_invent_bounds(self):
        self.add("unknown")
        self.add("other", "1900", event="E2")
        result = event_time_coverage(self.package, "E1")
        self.assertIsNone(result["observed"]["start"])
        self.assertIsNone(result["observed"]["end"])
        self.assertEqual(result["observed"]["undated_activity_ids"], ["unknown"])
        self.assertEqual(result["stages"][0]["observed"]["undated_activity_ids"], ["unknown"])
        with self.assertRaisesRegex(ValueError, "Unknown event"):
            event_time_coverage(self.package, "missing")

    def test_partial_and_invalid_windows_do_not_fill_missing_dates(self):
        self.add("partial", "2022", context=True)
        self.package["occurrence"][0]["end_time_id"] = None
        self.add("invalid", "unknown", window_start="2023-12-01", window_end="2023-01-01")
        result = event_time_coverage(self.package, "E1")["observed"]
        self.assertEqual(result["partial_activity_ids"], ["partial"])
        self.assertEqual(result["undated_activity_ids"], ["invalid"])
        self.assertEqual(result["start"]["value"], "2022")
        self.assertIsNone(result["end"])


@unittest.skipUnless(shutil.which("node"), "Node.js exercises the shipped renderer")
class EventCoverageRenderingTests(unittest.TestCase):
    def test_accepted_earlier_fuzzy_activity_expands_event_bar_without_schema_changes(self):
        package = package_fixture()
        event_id = package["event"][0]["event_id"]
        actions = {row["action_id"]: row for row in package["action"]}
        activities = {row["activity_id"]: row for row in package["activity"]}
        member = next(row for row in package["event_activity"]
                      if row["event_id"] == event_id and activities[row["activity_id"]].get("action_id"))
        old_action = actions[activities[member["activity_id"]]["action_id"]]
        old_action["timestamp_time_id"] = "COVERAGE_OLD_TIME"
        package["time_value"].append({"time_id": "COVERAGE_OLD_TIME", "value": "2022-06-15"})
        package["event_activity"] = [copy.deepcopy(member)]
        package["event_activity_detail"] = []
        package["event_activity"][0]["detail_mode"] = "all"
        before = copy.deepcopy(package)
        package["time_value"].append({"time_id": "COVERAGE_NEW_TIME", "value": "unknown",
            "window_start": "2022-01-21", "window_end": "2022-01-31", "original_text": "2022年1月下旬",
            "is_approximate": True, "window_semantics": "uncertainty"})
        package["evidence_set"].append({"evidence_set_id": "COVERAGE_NEW_EVIDENCE"})
        package["action"].append({**copy.deepcopy(old_action), "action_id": "EF_ACTION_coverage",
            "action_type": "Earlier documented action", "timestamp_time_id": "COVERAGE_NEW_TIME",
            "evidence_set_id": "COVERAGE_NEW_EVIDENCE"})
        package["activity"].append({"activity_id": "EF_ACTIVITY_coverage", "action_id": "EF_ACTION_coverage"})
        package["event_activity"].append({"event_id": event_id, "activity_id": "EF_ACTIVITY_coverage",
            "stage_id": member.get("stage_id"), "detail_mode": "all", "sort_order": 999})

        def output(data):
            page = PageData(render_person_epg(data))
            exported = json.loads(page.payload)
            self.assertEqual(exported, data)
            result = subprocess.run(["node", str(ROOT / "tests/person_epg_render_check.cjs")],
                input=json.dumps({"data": exported, "script": str(ROOT / "finmy/person_epg/assets/timeline.js")}),
                capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

        old_display, new_display = output(before), output(package)
        label = "<b>" + package["event"][0]["label"] + "</b><br>"

        def event_bar(rendered):
            return next(row for row in rendered["data"] if row.get("type") == "bar"
                        and row.get("hovertext", [""])[0].startswith(label))

        old_bar, new_bar = event_bar(old_display), event_bar(new_display)
        self.assertLess(datetime.fromisoformat(new_bar["base"][0].replace("Z", "+00:00")),
                        datetime.fromisoformat(old_bar["base"][0].replace("Z", "+00:00")))
        self.assertGreater(new_bar["x"][0], old_bar["x"][0])
        self.assertEqual(package["event"], before["event"])
        self.assertEqual(package["graph"], before["graph"])
        audit = compare_event_time_coverage(before, package, event_id)
        self.assertTrue(audit["range_changed"])
        self.assertEqual(audit["after"]["observed"]["start"]["value"], "2022-01-21")
        new_activity = next(row for row in new_display["data"]
                            if row.get("meta", {}).get("activity_id") == "EF_ACTIVITY_coverage")
        self.assertIn("2022年1月下旬", new_activity["hovertext"][0])


if __name__ == "__main__":
    unittest.main()
