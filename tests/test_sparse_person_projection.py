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

    def test_original_actors_transaction_parties_and_details_are_retained(self):
        package = fixture()
        output = project_person_epg(package)
        actions = {a["action_id"]: a for e in output["events"] for a in e["actions"]}
        action_activities = {a["action_id"]: a["activity_id"] for a in package["activity"] if a.get("action_id")}
        for row in package["action"]:
            target = actions[row["action_id"]]
            self.assertEqual(target["actor_id"], row["actor_id"])
            self.assertEqual(target["action_type"]["value"], row["action_type"])
            expected = sorted((d for d in package["activity_detail"]
                               if d["activity_id"] == action_activities[row["action_id"]]),
                              key=lambda d: d["detail_index"])
            self.assertEqual([d["value"] for d in target["details"]], [d["value"] for d in expected])
        transactions = {t["transaction_id"]: t for e in output["events"] for t in e["transactions"]}
        for row in package["financial_transaction"]:
            target = transactions[row["transaction_id"]]
            for side in ("from_entity_id", "to_entity_id"):
                self.assertEqual(target[side]["value"], row.get(side) or "unknown")
            self.assertEqual([d["value"] for d in target["details"]], row.get("details") or [])

    def test_nullable_attributes_and_missing_roles_use_only_known_membership(self):
        package = fixture()
        output = project_person_epg(package)
        entities = {e["entity_id"]: e for e in output["entities"]}
        for row in package["entity"]:
            if row.get("attributes") is None:
                self.assertEqual(entities[row["entity_id"]]["attributes"], {})
        existing = {p["participation_id"] for p in package["participation"]}
        for event in output["events"]:
            expected = {p["entity_id"] for p in package["occurrence_participant"]
                        if p["occurrence_id"] == event["event_id"]}
            self.assertEqual({p["entity_id"] for p in event["participations"]}, expected)
            for part in event["participations"]:
                if part["participation_id"] not in existing:
                    self.assertEqual(part["role"]["value"], "unknown")
                    self.assertEqual(part["start_time"]["value"], "unknown")
                    self.assertEqual(part["end_time"]["value"], "unknown")

    def test_aliases_and_recorded_dates_and_windows_survive(self):
        package = fixture()
        output = project_person_epg(package)
        times = {row["time_id"]: row for row in package["time_value"]}
        tables = [
            ("occurrence", "occurrence_id", output["events"], "event_id", {"start_time": "start_time_id", "end_time": "end_time_id"}),
            ("participation", "participation_id", [p for e in output["events"] for p in e["participations"]], "participation_id", {"start_time": "start_time_id", "end_time": "end_time_id"}),
            ("action", "action_id", [a for e in output["events"] for a in e["actions"]], "action_id", {"timestamp": "timestamp_time_id"}),
            ("financial_transaction", "transaction_id", [t for e in output["events"] for t in e["transactions"]], "transaction_id", {"timestamp": "timestamp_time_id"}),
            ("entity_relation", "relation_id", output["relations"], "relation_id", {"valid_from": "valid_from_time_id", "valid_to": "valid_to_time_id"}),
        ]
        for table, key, targets, target_key, fields in tables:
            by_id = {row[target_key]: row for row in targets}
            for row in package[table]:
                for name, column in fields.items():
                    if not row.get(column):
                        continue
                    source, target = times[row[column]], by_id[row[key]][name]
                    self.assertEqual(target["value"], source["value"])
                    if source.get("window_start") is not None:
                        self.assertEqual(target["time_window"], {
                            "start": source["window_start"], "end": source["window_end"],
                            "original": source["original_text"], "approximate": source["is_approximate"],
                        })
        for entity in output["entities"]:
            self.assertEqual(entity["aliases"], [a["alias"] for a in
                sorted(package["entity_alias"], key=lambda row: row.get("sort_order", 0))
                if a["entity_id"] == entity["entity_id"]])

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

    def test_context_outside_scope_uses_unbounded_display_not_changed_dates(self):
        package = fixture()
        output = project_person_epg(package)
        self.assertIsNone(output["coverage_start"])
        self.assertIsNone(output["coverage_end"])
        self.assertEqual(package["graph"]["coverage_start"], "2022-01-01")
        self.assertEqual(package["graph"]["coverage_end"], "2023-12-31")
        context = next(e for e in output["events"] if e["event_id"] == "PDF_OC_oxy_background")
        self.assertEqual(context["start_time"]["time_window"]["start"], "2019-01-01")
        self.assertEqual(context["end_time"]["time_window"]["end"], "2019-12-31")
        notice = output["descriptions"][-1]
        self.assertIn("2022-01-01 to 2023-12-31", notice["value"])
        self.assertEqual(notice["evidence_source_contents"], [])

    def test_field_quotes_reasons_and_unlocated_state_survive(self):
        package = fixture()
        row = package["action"][0]
        sid = row["evidence_set_id"]
        selected = sorted([r for r in package["evidence_link"]
                           if r["evidence_set_id"] == sid and r["field_path"] == "/action_type"],
                          key=lambda r: r["quote_order"])
        spans = {s["span_id"]: s["quote"] for s in package["evidence_span"]}
        output = project_person_epg(package)
        action = next(a for e in output["events"] for a in e["actions"] if a["action_id"] == row["action_id"])
        self.assertEqual(action["action_type"]["evidence_source_contents"], [spans[r["span_id"]] for r in selected])
        self.assertEqual(action["action_type"]["evidence_status"], "needs_review")
        info = next(s for s in package["evidence_set"] if s["evidence_set_id"] == sid)["field_metadata"]["/action_type"]
        self.assertEqual(action["action_type"]["reasons"], info["reasons"])

    def test_detail_quotes_restore_even_without_optional_field_metadata(self):
        package = fixture()
        detail = package["activity_detail"][0]
        sid = detail["evidence_set_id"]
        evidence = next(s for s in package["evidence_set"] if s["evidence_set_id"] == sid)
        evidence["field_metadata"] = None
        activity = next(a for a in package["activity"] if a["activity_id"] == detail["activity_id"])
        spans = {s["span_id"]: s["quote"] for s in package["evidence_span"]}
        expected = [spans[r["span_id"]] for r in sorted(package["evidence_link"], key=lambda r: r["quote_order"])
                    if r["evidence_set_id"] == sid and r["field_path"] == "/value"]
        self.assertTrue(expected)
        output = project_person_epg(package)
        action = next(a for e in output["events"] for a in e["actions"] if a["action_id"] == activity["action_id"])
        target = action["details"][detail["detail_index"]]
        self.assertEqual(target["value"], detail["value"])
        self.assertEqual(target["evidence_source_contents"], expected)
        self.assertEqual(target["reasons"], [])

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

    def test_invalid_source_references_are_rejected(self):
        package = fixture()
        package["action"][0]["actor_id"] = "not-an-entity"
        with self.assertRaisesRegex(ValueError, "Invalid Person EPG"):
            project_person_epg(package)


if __name__ == "__main__":
    unittest.main()
