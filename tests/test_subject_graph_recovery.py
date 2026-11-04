"""Offline recovery must preserve source boundaries and saved review decisions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.recover import recover_run
import test_subject_event_sources as fixtures
from test_subject_graph_builder import vf


class SubjectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        fixture = fixtures.EventSourceTests()
        fixture.setUp()
        wrong = copy.deepcopy(fixture.events[0]["actions"][0])
        wrong.update(action_id="E1_WRONG", action_type=vf("Reviewed profits", fixtures.PROFIT),
                     details=[vf("Profit exceeded $8 billion", fixtures.PROFIT)])
        fixture.events[0]["actions"].append(wrong)
        self.graph, _, self.report = run_subject_build(
            fixture.inp, fixture.cfg, fixture.complete, fixture.save)
        self.saved = fixture.saved
        for name, value in self.saved.items():
            self.write(name, value)

    def write(self, name, value):
        (self.run / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")

    def test_raw_recovery_keeps_cross_event_records_quarantined(self):
        before = {p.name: p.read_bytes() for p in self.run.iterdir()}
        output = recover_run(self.run)
        graph = json.loads((output / "FinalSubjectGraph.json").read_text())
        self.assertEqual(graph, self.graph)
        report = json.loads((output / "subject_graph_validation.json").read_text())
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])
        review = json.loads((output / "subject_event_evidence_review.json").read_text())
        self.assertEqual(review, self.saved["subject_event_evidence_review"])
        self.assertEqual(json.loads((output / "subject_event_sources.json").read_text()),
                         self.saved["subject_event_sources"])
        self.assertEqual({p.name: p.read_bytes() for p in self.run.iterdir()}, before)
        # Repeated recovery keeps the reviewed graph and the review history.
        again = recover_run(output)
        self.assertEqual(json.loads((again / "FinalSubjectGraph.json").read_text()), graph)
        self.assertEqual(json.loads((again / "subject_event_evidence_review.json").read_text()), review)

    def test_completed_graph_and_its_warnings_take_precedence_over_raw(self):
        reviewed = copy.deepcopy(self.graph)
        reviewed["events"][0]["actions"] = []
        self.write("FinalSubjectGraph", reviewed)
        detail = [{"event_id": "E1", "corrections": {"accepted": [
            {"patches": [{"op": "remove", "path": "/event/actions/E1_A1"}],
             "reason": "Reviewed removal"}]}}]
        self.write("subject_event_detail_review", detail)
        warning = {"path": "/events/0", "message": "Saved review needs follow-up"}
        self.write("subject_graph_validation", {**self.report, "warnings": [warning]})
        output = recover_run(self.run)
        self.assertEqual(json.loads((output / "FinalSubjectGraph.json").read_text()), reviewed)
        self.assertEqual(json.loads((output / "subject_event_detail_review.json").read_text()), detail)
        report = json.loads((output / "subject_graph_validation.json").read_text())
        self.assertIn(warning, report["warnings"])

    def test_raw_recovery_refuses_to_discard_accepted_later_reviews(self):
        for name, review in (
            ("subject_event_detail_review", [{"corrections": {"accepted": [{"reason": "changed"}]}}]),
            ("subject_coverage_review", {"event_merges": {"accepted": [{"reason": "merged"}]}}),
        ):
            with self.subTest(name=name):
                self.write(name, review)
                with self.assertRaisesRegex(ValueError, "accepted reviews"):
                    recover_run(self.run)
                self.assertFalse(self.run.with_name("run_recovered").exists())
                self.write(name, self.saved[name])

    def test_missing_routing_cannot_silently_restore_excluded_records(self):
        (self.run / "subject_event_sources.json").unlink()
        with self.assertRaisesRegex(ValueError, "event source"):
            recover_run(self.run)
        self.assertFalse(self.run.with_name("run_recovered").exists())

    def test_recovery_preserves_documents_sharing_a_source_id(self):
        context = copy.deepcopy(self.saved["subject_build_input"])
        context["Sources"].append({"source_id": "DOC_2022", "content": "A supplementary passage."})
        self.write("subject_build_input", context)
        output = recover_run(self.run)
        self.assertEqual(json.loads((output / "FinalSubjectGraph.json").read_text()), self.graph)

    def test_legacy_raw_recovery_reports_unchecked_event_boundaries(self):
        for path in self.run.iterdir():
            if path.name not in ("RawSubjectGraph.json", "subject_build_input.json"):
                path.unlink()
        self.write("RawSubjectGraph", self.graph)
        output = recover_run(self.run)
        self.assertEqual(json.loads((output / "FinalSubjectGraph.json").read_text()), self.graph)
        report = json.loads((output / "subject_graph_validation.json").read_text())
        self.assertTrue(any("event source" in row["message"] for row in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
