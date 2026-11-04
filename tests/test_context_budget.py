"""Offline allocator regressions: no API keys, Streamlit, or model packages."""
import copy
import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from finmy.runner.context_budget import allocate_context
from finmy.runner.relevance_filter import render_document


def document(identifier, text, label="CORE", **kwargs):
    return {"document_id": identifier, "title": identifier, "url": "https://example.test/" + identifier,
            "source": "fixture", "published_at": "2024-01-01", "raw_text": text,
            "relevance": label, **kwargs}


def config(limit=60000, cap=12000, seed=2000):
    return {"all_content_config": {"max_content_length": limit,
            "max_document_chars": cap, "min_document_chars": seed}}


class ContextBudgetTest(unittest.TestCase):
    def test_packing_merges_only_adjacent_source_slices(self):
        from finmy.runner.context_budget import _fit
        text = "abcdefghij" * 100
        value, ranges = _fit(document("D1", text), [(0, 130, True), (130, 260, True)], 500, False)
        self.assertEqual(ranges, [(0, 260)])
        self.assertEqual(value.count("[Source chars"), 1)
        self.assertIn(text[:260], value)
        self.assertLessEqual(len(value), 500)
        value, ranges = _fit(document("D1", text), [(0, 130, True), (140, 270, True)], 500, False)
        self.assertEqual(ranges, [(0, 130), (140, 270)])
        self.assertEqual(value.count("[Source chars"), 2)

    def assert_valid(self, result, docs, maximum, cap=12000, metadata=True):
        report = result["report"]
        self.assertLessEqual(sum(map(len, result["contents"])), maximum)
        self.assertEqual(report["summary"]["used_chars"], sum(map(len, result["contents"])))
        self.assertEqual(report["summary"]["unused_chars"], maximum - sum(map(len, result["contents"])))
        by_id = {doc["document_id"]: doc for doc in docs}
        output = iter(result["contents"])
        for record in report["documents"]:
            doc = by_id[record["document_id"]]
            previous_end = 0
            source_chars = 0
            for item in record["source_ranges"]:
                a, b = item["start_char"], item["end_char"]
                self.assertTrue(0 <= a < b <= len(doc["raw_text"]))
                self.assertGreaterEqual(a, previous_end)
                previous_end = b
                source_chars += b - a
            self.assertEqual(source_chars, record["included_source_chars"])
            self.assertLessEqual(record["builder_chars"], cap)
            if record["included"]:
                rendered = next(output)
                self.assertEqual(len(rendered), record["builder_chars"])
                whole = render_document(doc) if metadata else doc["raw_text"]
                if rendered != whole:
                    self.assertIn("gaps are omitted", rendered)
                    for item in record["source_ranges"]:
                        self.assertIn(doc["raw_text"][item["start_char"]:item["end_char"]], rendered)

    def test_long_first_source_does_not_block_later_source(self):
        docs = [document("D1", "long. " * 6000), document("D2", "important purchase. " * 30)]
        result = allocate_context(docs, [], config(4500))
        self.assertEqual(result["report"]["summary"]["included_documents"], 2)
        self.assert_valid(result, docs, 4500)

    def test_core_precedes_review_regardless_of_input_order(self):
        docs = [document("noise", "uncertain. " * 3000, "REVIEW"),
                document("trade", "dated trade evidence. " * 300)]
        result = allocate_context(docs, [], config(2500))
        self.assertEqual(result["report"]["documents"][0]["document_id"], "trade")
        self.assertTrue(result["report"]["documents"][0]["included"])
        self.assertFalse(result["report"]["documents"][1]["included"])
        self.assert_valid(result, docs, 2500)

    def test_context_gets_seed_before_core_expansion(self):
        docs = [document("core", "stock purchases. " * 4000),
                document("letter", "financing background. " * 4000, "CONTEXT")]
        result = allocate_context(docs, [], config(5000))
        self.assertEqual(result["report"]["summary"]["included_by_label"], {"CORE": 1, "CONTEXT": 1})
        self.assert_valid(result, docs, 5000)

    def test_review_only_uses_budget_after_core_context(self):
        docs = [document("review", "other. " * 5000, "REVIEW"),
                document("background", "direct background. " * 300, "CONTEXT"),
                document("core", "trade. " * 300)]
        result = allocate_context(docs, [], config(7000))
        rows = result["report"]["documents"]
        self.assertEqual([r["relevance"] for r in rows], ["CORE", "CONTEXT", "REVIEW"])
        self.assertTrue(all(r["included"] for r in rows[:2]))
        self.assert_valid(result, docs, 7000)

    def test_tail_evidence_from_long_annual_letter_survives(self):
        quote = "Occidental warrants explain this investment."
        text = "UNRELATED PREFACE. " * 1400 + quote + " Relevant background. " * 200
        start = text.index(quote)
        docs = [document("letter", text, "CONTEXT")]
        decisions = [{"document_id": "letter", "chunks": [
            {"start_char": 0, "end_char": start, "relevance": "IRRELEVANT", "evidence": "UNRELATED PREFACE."},
            {"start_char": start, "end_char": len(text), "relevance": "CONTEXT", "evidence": quote}]}]
        result = allocate_context(docs, decisions, config(2200))
        self.assertIn(quote, result["contents"][0])
        self.assertNotIn("UNRELATED PREFACE", result["contents"][0])
        self.assert_valid(result, docs, 2200)

    def test_whitespace_normalised_quote_maps_back_to_raw_text(self):
        quote = "Purchase\n  completed\t2023-10-23."
        text = "x" * 10000 + quote + " End of filing. " * 80
        doc = document("filing", text)
        decisions = [{"document_id": "filing", "chunks": [{"start_char": 10000,
                      "end_char": len(text), "relevance": "CORE",
                      "evidence": "Purchase completed 2023-10-23."}]}]
        result = allocate_context([doc], decisions, config(1500))
        self.assertIn(quote, result["contents"][0])
        self.assert_valid(result, [doc], 1500)

    def test_overlapping_chunks_do_not_duplicate_text(self):
        text = "Evidence about purchases and dates. " * 1000
        doc = document("D1", text)
        decisions = [{"document_id": "D1", "chunks": [
            {"start_char": 0, "end_char": 8000, "relevance": "CORE", "evidence": "Evidence about purchases"},
            {"start_char": 7800, "end_char": 15800, "relevance": "CORE", "evidence": "purchases and dates"}]}]
        result = allocate_context([doc], decisions, config(6000))
        self.assert_valid(result, [doc], 6000)

    def test_short_documents_are_preserved_whole(self):
        docs = [document("D1", "Original source. " * 20), document("D2", "原文包含数字与日期。" * 20)]
        result = allocate_context(docs, [], config())
        self.assertEqual(result["contents"], [render_document(d) for d in docs])
        self.assert_valid(result, docs, 60000)

    def test_budget_and_cap_include_metadata_and_markers(self):
        docs = [document("D1", "正文内容。" * 6000)]
        result = allocate_context(docs, [], config(1800, cap=1500))
        self.assert_valid(result, docs, 1800, cap=1500)

    def test_tiny_budget_has_no_header_only_source(self):
        result = allocate_context([document("D1", "evidence" * 100)], [], config(1))
        self.assertEqual(result["contents"], [])
        self.assertTrue(result["report"]["warnings"])

    def test_oversized_metadata_does_not_block_next_document(self):
        docs = [document("huge_header", "evidence", title="title" * 1000),
                document("short", "short useful source. " * 30)]
        result = allocate_context(docs, [], config(1800))
        self.assertFalse(result["report"]["documents"][0]["included"])
        self.assertTrue(result["report"]["documents"][1]["included"])
        self.assert_valid(result, docs, 1800)

    def test_missing_chunk_decisions_falls_back_without_new_calls(self):
        docs = [document("D1", "retain uncertain evidence. " * 2000, "REVIEW")]
        result = allocate_context(docs, [], config(2500))
        self.assertEqual(len(result["contents"]), 1)
        self.assert_valid(result, docs, 2500)

    def test_invalid_offsets_do_not_inject_classifier_text(self):
        docs = [document("D1", "Original source text. " * 200)]
        decisions = [{"document_id": "D1", "chunks": [
            {"start_char": -1, "end_char": 999999, "relevance": "CORE", "evidence": "INVENTED CLAIM"}]}]
        result = allocate_context(docs, decisions, config(1800))
        self.assertNotIn("INVENTED CLAIM", result["contents"][0])
        self.assert_valid(result, docs, 1800)

    def test_disabled_filter_raw_text_compatibility(self):
        docs = [document("D1", "raw input one"), document("D2", "raw input two")]
        for d in docs:
            del d["relevance"]
        result = allocate_context(docs, [], config(), include_metadata=False)
        self.assertEqual(result["contents"], [d["raw_text"] for d in docs])

    def test_empty_and_irrelevant_documents(self):
        docs = [document("empty", ""), document("bad", "off-topic " * 200, "IRRELEVANT")]
        result = allocate_context(docs, [], config())
        self.assertEqual(result["contents"], [])
        self.assertEqual(result["report"]["documents"][0]["omission_reason"], "empty_source")
        self.assertEqual(result["report"]["documents"][1]["omission_reason"], "filtered_irrelevant")
        self.assertEqual(allocate_context([], [], config())["contents"], [])

    def test_deterministic_and_inputs_not_mutated(self):
        docs = [document("D1", "evidence. " * 3000), document("D2", "more. " * 300, "CONTEXT")]
        before = copy.deepcopy(docs)
        first = allocate_context(docs, [], config(4000))
        self.assertEqual(first, allocate_context(docs, [], config(4000)))
        self.assertEqual(docs, before)

    def test_invalid_limits_are_rejected(self):
        for value in (-1, True, "60000", 3.5, float("nan"), -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                allocate_context([], [], config(value))
        for cap in (0, -1, True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                allocate_context([], [], config(cap=cap))
        self.assertEqual(allocate_context([], [], config(0))["contents"], [])

    def test_missing_and_infinite_global_limit(self):
        docs = [document("D1", "short source")]
        self.assertEqual(allocate_context(docs, [], {})["contents"], [render_document(docs[0])])
        self.assertEqual(allocate_context(docs, [], config(math.inf))["contents"], [render_document(docs[0])])

    def test_duplicate_document_id_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            allocate_context([document("D1", "one"), document("D1", "two")], [], config())

    def test_random_budgets_preserve_hard_invariants(self):
        rng = random.Random(20261103)
        for trial in range(100):
            docs = [document(f"D{i}", ("原文 " if i % 2 else "source text. ") * rng.randrange(0, 1800),
                             rng.choice(["CORE", "CONTEXT", "REVIEW"])) for i in range(rng.randrange(1, 9))]
            budget, cap = rng.randrange(0, 14000), rng.randrange(400, 5000)
            with self.subTest(trial=trial):
                result = allocate_context(docs, [], config(budget, cap))
                self.assert_valid(result, docs, budget, cap)

    def test_offline_cli_preserves_original_run(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            docs = [document("D1", "source. " * 400)]
            (path / "filtered_documents.json").write_text(json.dumps(docs), encoding="utf-8")
            original = path / "builder_input_contents.json"
            original.write_text('["previous run"]', encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "finmy.runner.context_budget",
                "--input-dir", str(path), "--max-chars", "2500"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original.read_text(), '["previous run"]')
            output = json.loads((path / "budget_review/context_budget_report.json").read_text())
            self.assertLessEqual(output["summary"]["used_chars"], 2500)


if __name__ == "__main__":
    unittest.main()
