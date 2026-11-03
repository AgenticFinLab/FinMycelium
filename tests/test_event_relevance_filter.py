"""Offline tests: no network, API keys, Streamlit or lmbase installation needed."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.relevance_filter import (
    _chunks, filter_documents, load_saved_documents, make_document, render_document,
)

PROFILE = {"subject": "Warren Buffett", "organizations": ["Berkshire", "Occidental"],
           "period": ["2022", "2023"], "focus": ["share purchases"]}
QUERY = "Reconstruct Buffett and Berkshire's Occidental investments in 2022–2023."


def document(text, title="Article", date="", url="https://example.test/article"):
    return make_document(text, {"title": title, "url": url, "datepublished": date}, "bocha")


class FakeCompletion:
    def __init__(self, choose=None):
        self.calls = []
        self.choose = choose or (lambda c: "CORE")

    def __call__(self, system, payload):
        self.calls.append((system, payload))
        if "chunks" not in payload:
            return json.dumps(PROFILE)
        return json.dumps({"decisions": [
            {"chunk_id": c["chunk_id"], "relevance": self.choose(c),
             "confidence": 0.98, "event_time": None, "matched_entities": [],
             "reason": "Mock decision, not a measured relevance judgment.",
             "evidence": c["text"][:80]}
            for c in payload["chunks"]
        ]})


class RelevanceFilterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def run_filter(self, docs, model=None, options=None):
        return filter_documents(docs, QUERY, ["Buffett", "Occidental"],
                                {"relevance_filter": options or {}}, self.path,
                                completion=model or FakeCompletion())

    def report(self):
        return json.loads((self.path / "relevance_decisions.json").read_text())

    def test_keeps_core_context_removes_only_irrelevant(self):
        docs = [document("CORE purchases in 2023"), document("CONTEXT warrants in 2019"),
                document("IRRELEVANT diet preferences")]
        model = FakeCompletion(lambda c: c["text"].split()[0])
        result = self.run_filter(docs, model)
        self.assertEqual(result["summary"]["kept"], 2)
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual([r["relevance"] for r in self.report()["documents"]],
                         ["CORE", "CONTEXT", "IRRELEVANT"])
        raw = json.loads((self.path / "retrieved_documents.json").read_text())
        self.assertEqual([d["raw_text"] for d in raw], [d["raw_text"] for d in docs])

    def test_late_retrospective_is_not_date_filtered(self):
        result = self.run_filter([document("In 2022 Berkshire acquired Occidental shares.", date="2026-01-01")])
        self.assertEqual(result["summary"]["kept"], 1)
        self.assertIn("2026-01-01", result["contents"][0])
        self.assertIn("NOT event time", result["contents"][0])

    def test_long_document_tail_is_classified_and_preserved(self):
        text = ("unrelated content " * 85) + " CORE: OXY acquisition in 2022."
        fake = FakeCompletion(lambda c: "CORE" if "CORE:" in c["text"] else "IRRELEVANT")
        result = self.run_filter([document(text)], fake,
                                 {"chunk_chars": 512, "overlap_chars": 64, "batch_size": 2})
        chunks = [c for _, p in fake.calls for c in p.get("chunks", [])]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[-1]["end_char"], len(text))
        self.assertEqual(result["summary"]["kept"], 1)
        self.assertTrue(result["contents"][0].endswith(text))

    def test_chunk_coverage_has_no_holes(self):
        text = "abcdef" * 500
        chunks = _chunks([{**document(text), "document_id": "DOC_0001"}], 512, 100)
        coverage = set()
        for c in chunks:
            self.assertEqual(c["text"], text[c["start_char"]:c["end_char"]])
            coverage.update(range(c["start_char"], c["end_char"]))
        self.assertEqual(len(coverage), len(text))

    def test_unknown_time_stays_unknown(self):
        base = FakeCompletion()
        def infer(system, payload):
            value = json.loads(base(system, payload))
            for row in value.get("decisions", []):
                row["event_time"] = "2022-01-01"  # unsupported normalisation
            return json.dumps(value)
        self.run_filter([document("Berkshire accumulated shares in early 2022.")], infer)
        self.assertIsNone(self.report()["documents"][0]["chunks"][0]["event_time"])

    def test_explicit_time_is_recorded_but_not_injected(self):
        base = FakeCompletion()
        def infer(system, payload):
            value = json.loads(base(system, payload))
            for row in value.get("decisions", []):
                row["event_time"] = "2023-10-23"
                row["reason"] = "CLASSIFIER_ONLY_SENTENCE"
            return json.dumps(value)
        result = self.run_filter([document("Purchase on 2023-10-23.")], infer)
        self.assertEqual(self.report()["documents"][0]["chunks"][0]["event_time"], "2023-10-23")
        self.assertNotIn("CLASSIFIER_ONLY_SENTENCE", result["contents"][0])

    def test_profile_failure_keeps_all_and_does_not_leak_exception(self):
        def fail(*args):
            raise RuntimeError("sk-TEST-SECRET-IN-EXCEPTION")
        result = self.run_filter([document("one"), document("two")], fail)
        self.assertEqual(result["summary"]["kept"], 2)
        self.assertEqual(result["summary"]["model_calls"], 1)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 2})
        self.assertNotIn("sk-TEST-SECRET", json.dumps(result) + (self.path / "relevance_decisions.json").read_text())

    def test_batch_failure_keeps_documents(self):
        def fail(system, payload):
            if "chunks" not in payload:
                return json.dumps(PROFILE)
            raise TimeoutError("timed out")
        result = self.run_filter([document("one")], fail)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})
        self.assertTrue(result["warnings"])

    def test_invalid_json_keeps_documents(self):
        def invalid(system, payload):
            return json.dumps(PROFILE) if "chunks" not in payload else "{broken"
        result = self.run_filter([document("one")], invalid)
        self.assertEqual(result["summary"]["kept"], 1)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})

    def test_duplicate_or_missing_id_is_review(self):
        base = FakeCompletion(lambda c: "IRRELEVANT")
        def duplicate(system, payload):
            data = json.loads(base(system, payload))
            if "decisions" in data:
                first = data["decisions"][0]
                data["decisions"] = [first, first, {"chunk_id": "not-requested"}]
            return json.dumps(data)
        result = self.run_filter([document("one"), document("two")], duplicate)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 2})

    def test_fabricated_evidence_prevents_rejection(self):
        base = FakeCompletion(lambda c: "IRRELEVANT")
        def fabricated(system, payload):
            data = json.loads(base(system, payload))
            for row in data.get("decisions", []):
                row["evidence"] = "this text was never in the document"
            return json.dumps(data)
        result = self.run_filter([document("actual article")], fabricated)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})

    def test_low_confidence_rejection_is_retained(self):
        base = FakeCompletion(lambda c: "IRRELEVANT")
        def uncertain(system, payload):
            data = json.loads(base(system, payload))
            for row in data.get("decisions", []):
                row["confidence"] = 0.6
            return json.dumps(data)
        result = self.run_filter([document("unclear article")], uncertain)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})

    def test_nan_confidence_is_retained(self):
        base = FakeCompletion(lambda c: "IRRELEVANT")
        def invalid(system, payload):
            data = json.loads(base(system, payload))
            for row in data.get("decisions", []):
                row["confidence"] = float("nan")
            return json.dumps(data)
        self.assertEqual(self.run_filter([document("article")], invalid)["summary"]["labels"], {"REVIEW": 1})

    def test_failed_tail_prevents_document_rejection(self):
        base = FakeCompletion(lambda c: "IRRELEVANT")
        def tail_missing(system, payload):
            data = json.loads(base(system, payload))
            if "decisions" in data:
                data["decisions"] = data["decisions"][:1]
            return json.dumps(data)
        result = self.run_filter([document("xyz " * 220)], tail_missing,
                                 {"chunk_chars": 512, "overlap_chars": 20})
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})

    def test_disabled_uses_exact_original_text_and_no_api(self):
        def unexpected(*args):
            self.fail("Model must not be called when disabled")
        docs = [document("  original\ntext\n")]
        result = self.run_filter(docs, unexpected, {"enabled": False})
        self.assertEqual(result["contents"], ["  original\ntext\n"])
        self.assertFalse(result["summary"]["enabled"])

    def test_manual_profile_skips_profile_call(self):
        fake = FakeCompletion()
        self.run_filter([document("article")], fake, {"event_profile": PROFILE})
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("chunks", fake.calls[0][1])

    def test_cache_reuses_requests(self):
        fake = FakeCompletion()
        docs = [document("article")]
        self.run_filter(docs, fake)
        self.assertEqual(len(fake.calls), 2)
        result = self.run_filter(docs, fake)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(result["summary"]["cache_hits"], 2)
        self.assertEqual(result["summary"]["model_calls"], 0)

    def test_empty_and_all_irrelevant_outputs_are_honest(self):
        result = self.run_filter([], FakeCompletion())
        self.assertEqual(result["summary"]["model_calls"], 0)
        self.assertEqual(result["contents"], [])
        result = self.run_filter([document("unrelated")], FakeCompletion(lambda c: "IRRELEVANT"))
        self.assertEqual(result["contents"], [])
        self.assertEqual(json.loads((self.path / "filtered_documents.json").read_text()), [])

    def test_source_order_preserved(self):
        result = self.run_filter([document("first"), document("second")])
        self.assertTrue(result["contents"][0].endswith("first"))
        self.assertTrue(result["contents"][1].endswith("second"))

    def test_legacy_saved_documents_replay_with_metadata(self):
        (self.path / "All_Text_Content_1.json").write_text(json.dumps(["Title:\nA\n\nContent:\nBody"]))
        (self.path / "formatted_bocha_search_results_1.json").write_text(json.dumps([
            {"title": "A", "url": "https://example.test/a", "datepublished": "2022-07-14"}
        ]))
        docs = load_saved_documents(self.path)
        self.assertEqual(docs[0]["published_at"], "2022-07-14")
        self.assertEqual(docs[0]["source"], "bocha")
        self.assertEqual(docs[0]["url"], "https://example.test/a")

    def test_ambiguous_metadata_is_not_guessed(self):
        (self.path / "All_Text_Content_1.json").write_text(json.dumps(["Title:\nA\n\nBody"]))
        (self.path / "formatted_bocha_search_results_1.json").write_text(json.dumps([
            {"title": "A", "url": "https://example.test/a"},
            {"title": "A", "url": "https://example.test/b"},
        ]))
        docs = load_saved_documents(self.path)
        self.assertEqual(docs[0]["url"], "")
        self.assertEqual(docs[0]["source"], "unknown")

    def test_invalid_config_fails_before_calls(self):
        for opts in ({"enabled": "false"}, {"chunk_chars": 0}, {"batch_size": 5},
                     {"overlap_chars": 8000}, {"drop_confidence": -1}):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                self.run_filter([document("x")], FakeCompletion(), opts)


if __name__ == "__main__":
    unittest.main()
