"""Protect the fixed v3 fixture and its read-only legacy display projection."""

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finmy.person_epg.compat_projection import project_person_epg
from finmy.person_epg.validation import validate_person_epg
from finmy.subject_graph.validation import validate_subject_graph


FIXTURE = Path(__file__).parent / "fixtures" / "buffett_person_epg_preview.json"
FIXTURE_SHA256 = "ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SparsePersonProjectionTest(unittest.TestCase):
    def test_fixed_fixture_projects_all_facts_without_mutating_source(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)
        package = fixture()
        before = copy.deepcopy(package)
        output = project_person_epg(package)
        self.assertTrue(validate_person_epg(package)["valid"])
        self.assertTrue(validate_subject_graph(output)["valid"])
        self.assertEqual(package, before)
        self.assertEqual(len(output["entities"]), 10)
        self.assertEqual(len(output["events"]), 23)
        self.assertEqual(len(output["relations"]), 8)
        self.assertEqual(sum(len(e["actions"]) for e in output["events"]), 35)
        self.assertEqual(sum(len(e["transactions"]) for e in output["events"]), 3)
        self.assertEqual(len(package["domain"]), 3)
        self.assertEqual(len(package["event"]), 10)
        self.assertEqual(len(package["stage"]), 6)
        self.assertEqual(len(package["activity"]), 45)
        self.assertEqual(len(package["activity_relation"]), 9)
        self.assertEqual(sum(s.get("document_id") is not None for s in package["evidence_span"]), 25)
        self.assertEqual(project_person_epg(package), output)


    def test_fixed_fixture_renders_through_unchanged_html_renderer(self):
        from finmy.subject_graph.visualizer import render_subject_graph

        package = fixture()
        output = project_person_epg(package)
        before = copy.deepcopy(output)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "buffett.html"
            page = render_subject_graph(output, target)
            self.assertEqual(target.read_text(encoding="utf-8"), page)
        self.assertIn("Plotly.newPlot", page)
        self.assertIn("Warren Buffett", page)
        self.assertEqual(output, before)


    def test_unrepresentable_time_keeps_original_in_canonical_data_and_notice(self):
        package = fixture()
        tid = package["action"][0]["timestamp_time_id"]
        row = next(t for t in package["time_value"] if t["time_id"] == tid)
        row["value"] = "sometime that spring"
        output = project_person_epg(package)
        action = next(a for e in output["events"] for a in e["actions"]
                      if a["action_id"] == package["action"][0]["action_id"])
        self.assertEqual(action["timestamp"]["value"], "unknown")
        self.assertIn("sometime that spring", action["timestamp"]["reasons"][-1])
        self.assertEqual(row["value"], "sometime that spring")

    def test_missing_scene_participant_is_not_replaced_by_focal_person(self):
        package = fixture()
        oid = "PDF_OC_oxy_background"
        package["occurrence_participant"] = [p for p in package["occurrence_participant"]
                                             if p["occurrence_id"] != oid]
        self.assertTrue(validate_person_epg(package)["valid"])
        with self.assertRaisesRegex(ValueError, "no recorded participant"):
            project_person_epg(package)


if __name__ == "__main__":
    unittest.main()
