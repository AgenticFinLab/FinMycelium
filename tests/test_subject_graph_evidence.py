import copy
import json
import tempfile
import unittest
from pathlib import Path

from finmy.subject_graph.evidence import restore_source_quotes, flag_evidence_issues, review_fields
from finmy.subject_graph.recover import recover_run
from finmy.subject_graph.validation import validate_subject_graph
from test_subject_graph_schema import graph_fixture, SOURCE
from test_subject_graph_builder import config, input_
import test_subject_graph_builder as builder_tests


class QuoteRestorationTests(unittest.TestCase):
    def test_chinese_comma_and_html_spacing_restore_exact_original(self):
        source = "2022年，伯克希尔与 苹果 公司进行了回购。"
        graph = {"value": "Summary", "evidence_source_contents": ["2022年,伯克希尔与苹果公司进行了回购。"]}
        before = copy.deepcopy(graph)
        restored, changes = restore_source_quotes(graph, [source])
        self.assertEqual(restored["evidence_source_contents"], [source])
        self.assertEqual(graph, before)
        self.assertEqual(len(changes), 1)
        self.assertEqual(source[changes[0]["start"]:changes[0]["end"]], source)
        self.assertEqual(restore_source_quotes(restored, [source]), (restored, []))

    def test_words_numbers_negation_and_punctuation_are_not_fuzzily_repaired(self):
        for quote, source in [("Bought 20 shares", "Bought 10 shares"),
                              ("Did buy shares", "Did not buy shares"),
                              ("nowhere", "now here"), ("1,000", "1000"),
                              ("capital returned", "Capital returned"),
                              ("甲乙", "甲，乙")]:
            graph = {"evidence_source_contents": [quote]}
            with self.subTest(quote=quote):
                self.assertEqual(restore_source_quotes(graph, [source]), (graph, []))

    def test_common_typographic_punctuation_restores_exact_source(self):
        quote = '他说:"优势:长期投资;耐心!"(年会)'
        source = '他说：“优势：长期投资；耐心！”（年会）'
        graph = {"evidence_source_contents": [quote]}
        restored, changes = restore_source_quotes(graph, [source])
        self.assertEqual(restored["evidence_source_contents"], [source])
        self.assertEqual(changes[0]["after"], source)

    def test_flagged_evidence_remains_strictly_invalid_but_can_be_viewed(self):
        from finmy.subject_graph.visualizer import render_subject_graph
        from finmy.subject_graph.compat import to_event_cascade
        graph = graph_fixture()
        fact = graph["events"][0]["descriptions"][0]
        fact["evidence_source_contents"] = ["An unsupported quotation"]
        marked, issues = flag_evidence_issues(graph, [SOURCE])
        self.assertEqual(len(issues), 1)
        self.assertEqual(review_fields(marked), ["/events/0/descriptions/0"])
        self.assertFalse(validate_subject_graph(marked, [SOURCE])["valid"])
        report = validate_subject_graph(marked, [SOURCE], allow_unverified_evidence=True)
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])
        html = render_subject_graph(marked)
        self.assertIn("Plotly.newPlot", html)
        self.assertIn("Company share purchase", html)
        projected = to_event_cascade(marked)
        self.assertNotIn('"evidence_status"', json.dumps(projected))
        self.assertIn("待核实", projected["descriptions"][0]["value"])
        # Re-validating against actual supporting sources removes the stale flag.
        marked["events"][0]["descriptions"][0]["evidence_source_contents"] = [SOURCE]
        cleaned, issues = flag_evidence_issues(marked, [SOURCE])
        self.assertEqual(review_fields(cleaned), [])
        self.assertEqual(issues, [])

    def test_recovery_validates_sources_and_does_not_overwrite(self):
        graph = graph_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            run.mkdir()
            source_path = run / "RawSubjectGraph.json"
            source_path.write_text(json.dumps(graph))
            context = {"SubjectScope": {"mode": "person", "subject": {
                "subject_id": graph["subject_id"], "name": "Warren Buffett", "aliases": [],
                "coverage_start": "2023", "coverage_end": "2023"}},
                "Sources": [{"content": SOURCE}]}
            (run / "subject_build_input.json").write_text(json.dumps(context))
            original = source_path.read_bytes()
            output = recover_run(run)
            self.assertTrue((output / "FinalSubjectGraph.html").exists())
            self.assertEqual(json.loads((output / "FinalSubjectGraph.json").read_text()), graph)
            self.assertEqual(source_path.read_bytes(), original)
            with self.assertRaises(FileExistsError):
                recover_run(run)
            graph["events"][0]["title"]["evidence_source_contents"] = ["fabricated"]
            source_path.write_text(json.dumps(graph))
            review_dest = recover_run(run, Path(tmp) / "review")
            pending_graph = json.loads((review_dest / "FinalSubjectGraph.json").read_text())
            self.assertEqual(pending_graph["events"][0]["title"]["evidence_status"], "needs_review")
            self.assertIn("needs_review", (review_dest / "FinalSubjectGraph.json").read_text())
            graph["events"][0]["actions"][0]["actor_id"] = "missing"
            source_path.write_text(json.dumps(graph))
            bad_dest = Path(tmp) / "bad"
            with self.assertRaisesRegex(ValueError, "Recovery failed"):
                recover_run(run, bad_dest)
            self.assertFalse(bad_dest.exists())


class BuildFormattingTests(unittest.TestCase):
    setUp = builder_tests.NativeBuildTests.setUp
    save = builder_tests.NativeBuildTests.save
    complete = builder_tests.NativeBuildTests.complete
    def test_formatting_only_error_needs_no_model_repair(self):
        src = "巴菲特，回购了 苹果 股票。"
        inp = input_()
        inp.samples[0].content += src
        self.events[0]["descriptions"][0]["evidence_source_contents"] = ["巴菲特,回购了苹果股票。"]
        from finmy.subject_graph.build import run_subject_build
        graph, state, report = run_subject_build(inp, config(repair_attempts=1), self.complete, self.save)
        self.assertTrue(report["valid"])
        self.assertNotIn("SubjectGraphRepair", state["agent_executed"])
        self.assertEqual(graph["events"][0]["descriptions"][0]["evidence_source_contents"], [src])
        self.assertEqual(len(self.saved["subject_quote_restoration"]), 1)

    def test_repair_cannot_override_configured_coverage(self):
        self.events[0]["actions"][0]["actor_id"] = "wrong"
        def complete(name, system, payload):
            if name == "SubjectGraphRepair":
                graph = copy.deepcopy(payload["ProposedGraph"])
                graph["events"][0]["actions"][0]["actor_id"] = "buffett"
                graph["coverage_start"], graph["coverage_end"] = "1900", "2099"
                return graph
            return self.complete(name, system, payload)
        from finmy.subject_graph.build import run_subject_build
        graph, _, report = run_subject_build(input_(), config(repair_attempts=1), complete, self.save)
        self.assertTrue(report["valid"])
        self.assertEqual((graph["coverage_start"], graph["coverage_end"]), ("2023", "2023"))
        self.assertEqual(len(self.saved["subject_repair_metadata_restoration"]), 2)
