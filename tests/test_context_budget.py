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
from finmy.runner.source_documents import render_document


def document(identifier, text, label="CORE", **kwargs):
    return {"document_id": identifier, "title": identifier, "url": "https://example.test/" + identifier,
            "source": "fixture", "published_at": "2024-01-01", "raw_text": text,
            "relevance": label, **kwargs}


def config(limit=60000, cap=12000, seed=2000):
    return {"all_content_config": {"max_content_length": limit,
            "max_document_chars": cap, "min_document_chars": seed}}


class ContextBudgetTest(unittest.TestCase):
    def test_followups_never_shrink_earlier_excerpts(self):
        initial = [document("core", "Original dated evidence. " * 500),
                   document("review", "Original uncertain evidence. " * 500, "REVIEW")]
        body = document("body", "Recovered meeting text. " * 500, search_phase="followup")
        extra = document("extra", "Additional investment details. " * 500,
                         search_phase="decision_followup")
        settings = config(7500, cap=2200)
        first = allocate_context(initial, [], settings)
        second = allocate_context([body] + initial, [], settings)
        final = allocate_context([extra, body] + initial, [], settings)
        self.assertEqual(second["contents"][:2], first["contents"])
        self.assertEqual(final["contents"][:3], second["contents"])
        self.assertEqual(final["report"]["documents"][:3], second["report"]["documents"])
        self.assertEqual(len(final["contents"]), 4)
        self.assert_valid(final, initial + [body, extra], 7500, cap=2200)


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


    def test_old_labels_cannot_reorder_search_results(self):
        docs = [document("review", "other. " * 5000, "REVIEW"),
                document("background", "direct background. " * 300, "CONTEXT"),
                document("core", "trade. " * 300)]
        result = allocate_context(docs, [], config(7000))
        rows = result["report"]["documents"]
        self.assertEqual([r["document_id"] for r in rows], ["review", "background", "core"])
        self.assertTrue(all(r["included"] for r in rows[:2]))
        self.assert_valid(result, docs, 7000)

    def test_tail_evidence_from_long_annual_letter_survives(self):
        quote = "Occidental warrants explain this investment."
        text = "UNRELATED PREFACE. " * 1400 + quote + " Relevant background. " * 200
        start = text.index(quote)
        docs = [document("letter", text, "CONTEXT", retrieval_queries=["Occidental warrants"])]
        decisions = [{"document_id": "letter", "chunks": [
            {"start_char": 0, "end_char": start, "relevance": "IRRELEVANT", "evidence": "UNRELATED PREFACE."},
            {"start_char": start, "end_char": len(text), "relevance": "CONTEXT", "evidence": quote}]}]
        result = allocate_context(docs, decisions, config(2200))
        self.assertIn(quote, result["contents"][0])
        self.assert_valid(result, docs, 2200)


    def test_budget_and_cap_include_metadata_and_markers(self):
        docs = [document("D1", "正文内容。" * 6000)]
        result = allocate_context(docs, [], config(1800, cap=1500))
        self.assert_valid(result, docs, 1800, cap=1500)


    def test_oversized_metadata_does_not_block_next_document(self):
        docs = [document("huge_header", "evidence", title="title" * 1000),
                document("short", "short useful source. " * 30)]
        result = allocate_context(docs, [], config(1800))
        self.assertFalse(result["report"]["documents"][0]["included"])
        self.assertTrue(result["report"]["documents"][1]["included"])
        self.assert_valid(result, docs, 1800)


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
