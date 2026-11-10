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


    def test_compact_matching_does_not_change_numbers_or_pick_ambiguous_text(self):
        quote = "The company reported that it had purchased 1 650 shares in this transaction during the year."
        original = {"evidence_source_contents": [quote]}
        self.assertEqual(restore_source_quotes(original, [quote.replace("1 650", "1650")]), (original, []))
        quote = "We did, though, make reasonable progress in increasing the intrinsic value of your shares."
        original = {"evidence_source_contents": [quote]}
        sources = [quote.replace("the intrinsic", "theintrinsic"), quote.replace("your shares", "yourshares")]
        self.assertEqual(restore_source_quotes(original, sources), (original, []))


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
