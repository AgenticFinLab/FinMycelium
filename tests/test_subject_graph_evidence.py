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
    def test_adjacent_excerpt_offsets_restore_an_exact_input_span(self):
        from finmy.runner.context_budget import EXCERPT_NOTE
        left, right = "这是连续的原文，", "其中描述了一次交易。"
        source = EXCERPT_NOTE + f"[Source chars 100:{100+len(left)}]\n{left}\n\n" + \
            f"[Source chars {100+len(left)}:{100+len(left)+len(right)}]\n{right}\n"
        original = {"evidence_source_contents": [left + right]}
        restored, changes = restore_source_quotes(original, [source])
        self.assertEqual(len(changes), 1)
        self.assertIn(restored["evidence_source_contents"][0], source)
        self.assertIn("[Source chars", restored["evidence_source_contents"][0])
        self.assertEqual(original["evidence_source_contents"], [left + right])

    def test_real_gaps_reversed_ranges_and_bad_lengths_are_never_joined(self):
        from finmy.runner.context_budget import EXCERPT_NOTE
        for first_end, second_start in ((4, 10), (4, 0), (5, 5)):
            source = EXCERPT_NOTE + f"[Source chars 0:{first_end}]\n甲乙丙丁\n\n" + \
                f"[Source chars {second_start}:{second_start+4}]\n戊己庚辛\n"
            original = {"evidence_source_contents": ["甲乙丙丁戊己庚辛"]}
            self.assertEqual(restore_source_quotes(original, [source]), (original, []))

    def test_long_pdf_passage_restores_missing_word_spaces_only(self):
        quote = "We did, though, make reasonable progress in increasing the intrinsic value of your shares."
        source = quote.replace("the intrinsic", "theintrinsic")
        restored, changes = restore_source_quotes({"evidence_source_contents": [quote]}, [source])
        self.assertEqual(restored["evidence_source_contents"], [source])
        self.assertEqual(len(changes), 1)
        for changed in (source.replace("progress", "no progress"),
                        source.replace("shares", "bonds")):
            original = {"evidence_source_contents": [quote]}
            self.assertEqual(restore_source_quotes(original, [changed]), (original, []))

    def test_compact_matching_does_not_change_numbers_or_pick_ambiguous_text(self):
        quote = "The company reported that it had purchased 1 650 shares in this transaction during the year."
        original = {"evidence_source_contents": [quote]}
        self.assertEqual(restore_source_quotes(original, [quote.replace("1 650", "1650")]), (original, []))
        quote = "We did, though, make reasonable progress in increasing the intrinsic value of your shares."
        original = {"evidence_source_contents": [quote]}
        sources = [quote.replace("the intrinsic", "theintrinsic"), quote.replace("your shares", "yourshares")]
        self.assertEqual(restore_source_quotes(original, sources), (original, []))

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
                return {"patches": [
                    {"op": "replace", "path": "/events/0/actions/0/actor_id", "value": "buffett"},
                    {"op": "replace", "path": "/coverage_start", "value": "1900"}]}
            return self.complete(name, system, payload)
        from finmy.subject_graph.build import run_subject_build
        with self.assertRaisesRegex(ValueError, "failed validation"):
            run_subject_build(input_(), config(repair_attempts=1), complete, self.save)
        graph = self.saved["SubjectGraphAfterRepair"]
        self.assertEqual((graph["coverage_start"], graph["coverage_end"]), ("2023", "2023"))
        self.assertIn("identity/coverage", self.saved["subject_repair_error"]["error"])
