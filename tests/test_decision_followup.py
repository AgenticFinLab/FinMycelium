"""Decision gap review and bounded search, using only injected offline adapters."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from finmy.runner.decision_followup import collect_decision_followup, _supported_names
from finmy.runner.relevance_filter import make_document


QUOTE = "Berkshire bought shares in Example Energy in 2023."
SUBJECT = {"name": "Warren Buffett", "coverage_start": "2022", "coverage_end": "2023"}


def gap(**changes):
    return {"investment_object": "Example Energy", "action": "purchase",
            "known_details": QUOTE, "missing": ["decision_basis"],
            "source_id": "SOURCE_1", "quote": QUOTE, **changes}


class DecisionFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        doc = make_document(QUOTE, {"url": "https://example.com/original"}, "file")
        self.filtered = {"documents": [doc], "decisions": []}
        self.config = {"all_content_config": {"max_content_length": 60000},
                       "subject_search": {"min_body_chars": 20}}
        self.calls, self.parsed, self.messages = [], [], []

    def search(self, *args):
        self.calls.append(args)
        return [{"url": "https://example.com/detail", "title": "Investment explanation",
                 "published_at": "2023-05-06"}]

    def parse(self, url):
        self.parsed.append(url)
        return {"text": "Buffett explained why Berkshire bought Example Energy shares.", "links": []}

    def run_review(self, result=None, **kwargs):
        return collect_decision_followup(
            self.filtered, "Buffett activities 2022–2023", [], SUBJECT, self.config, self.path,
            self.messages.append, completion=kwargs.pop("completion", lambda *a: result),
            search=kwargs.pop("search", self.search), parse=kwargs.pop("parse", self.parse), **kwargs)

    def test_no_gap_or_disabled_means_no_search(self):
        self.assertEqual(self.run_review({"gaps": []}), [])
        self.assertEqual(self.calls, [])
        self.config["subject_search"]["max_decision_followup_queries"] = 0
        def fail(*args):
            self.fail("Disabled review called model")
        self.assertEqual(self.run_review(completion=fail), [])
        self.assertEqual(self.calls, [])

    def test_duplicates_merge_and_count_scope_sources_are_preserved(self):
        before = copy.deepcopy(self.filtered)
        docs = self.run_review({"gaps": [gap(), gap(missing=["personal_attribution"])]})
        self.assertEqual([(p, count, start, end) for p, q, count, start, end in self.calls],
                         [("bocha", 10, "2022-01-01", "2023-12-31"),
                          ("baidu", 20, "2022-01-01", "2023-12-31")])
        self.assertEqual(self.calls[0][1], self.calls[1][1])
        self.assertIn("rationale", self.calls[0][1])
        self.assertIn("who made", self.calls[0][1])
        self.assertEqual(len(self.parsed), 1)
        self.assertEqual(len(docs), 1)
        self.assertNotIn("known_details", docs[0]["raw_text"])
        self.assertEqual(before, self.filtered)
        report = json.loads((self.path / "decision_followup/decision_gap_review.json").read_text())
        self.assertEqual(len(report["queries"]), 1)
        self.assertEqual(report["status"], "sources_found")

    def test_invalid_quotes_or_objects_do_not_trigger_search(self):
        for bad in (gap(quote="Invented trade."), gap(investment_object="Absent Company"),
                    gap(action="mentioned"), gap(missing=["biography"]), gap(source_id="missing")):
            self.assertEqual(self.run_review({"gaps": [bad]}), [])
        self.assertEqual(self.calls, [])

    def test_empty_results_and_missing_body_do_not_recurse(self):
        def empty(*args):
            self.calls.append(args)
            return []
        self.assertEqual(self.run_review({"gaps": [gap()]}, search=empty), [])
        self.assertEqual(len(self.calls), 2)
        self.calls.clear()
        self.assertEqual(self.run_review({"gaps": [gap()]},
                         parse=lambda url: {"text": "Watch video", "links": []}), [])
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(any("no further search rounds" in m for m in self.messages))

    def test_failure_does_not_retry_or_block_existing_sources(self):
        reviews = []
        def fail(*args):
            reviews.append(args)
            raise TimeoutError()
        self.assertEqual(self.run_review(completion=fail), [])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(self.calls, [])
        self.assertTrue(any("proceeding with existing sources" in m for m in self.messages))

    def test_existing_urls_and_out_of_range_results_are_not_fetched(self):
        self.assertEqual(self.run_review({"gaps": [gap()]},
                         known_urls=["https://example.com/detail"]), [])
        self.assertEqual(self.parsed, [])
        def wrong_date(*args):
            return [{"url": "https://example.com/late", "title": "Explanation", "published_at": "2026-01-01"}]
        self.assertEqual(self.run_review({"gaps": [gap()]}, search=wrong_date), [])
        self.assertEqual(self.parsed, [])

    def test_request_limit_applies_across_all_gaps(self):
        self.config["subject_search"]["max_decision_followup_queries"] = 1
        self.run_review({"gaps": [gap(), gap(action="holding")]})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][2], 10)

    def test_bilingual_names_use_only_variants_anchored_in_quotes(self):
        for label, quote in (("比亚迪 (BYD)", "Berkshire sold BYD shares."),
                             ("动视暴雪（Activision Blizzard）", "投资动视暴雪的股份是他个人的决定。")):
            names, error = _supported_names(gap(investment_object=label, quote=quote), quote)
            self.assertIsNone(error)
            self.assertTrue(names)
        self.assertFalse(_supported_names(gap(investment_object="BYD", quote="Bought BYDesign."),
                                          "Bought BYDesign.")[0])

    def test_pronouns_require_exact_supplied_local_context(self):
        quote = "We bought 14% of that company."
        context = "Speaking of Occidental Petroleum: " + quote
        candidate = gap(investment_object="西方石油 (Occidental Petroleum)", quote=quote)
        self.assertFalse(_supported_names(candidate, context)[0])
        self.assertTrue(_supported_names({**candidate, "object_context": context}, context)[0])
        self.assertFalse(_supported_names({**candidate, "object_context": context}, quote)[0])
        distant = "Occidental Petroleum. " + "x" * 601 + quote
        self.assertFalse(_supported_names({**candidate, "object_context": distant}, distant)[0])

    def test_bilingual_and_source_names_merge_without_changing_search_limits(self):
        self.run_review({"gaps": [gap(investment_object="示例能源 (Example Energy)"),
                                  gap(missing=["personal_attribution"])]})
        report = json.loads((self.path / "decision_followup/decision_gap_review.json").read_text())
        self.assertEqual(len(report["queries"]), 1)
        self.assertEqual(len(self.calls), 2)
        self.assertIn("example energy", self.calls[0][1])
        self.assertNotIn("示例能源", self.calls[0][1])

    def test_rejected_candidates_are_distinguished_from_no_gap(self):
        self.run_review({"gaps": [gap(investment_object="Missing Company")]})
        report = json.loads((self.path / "decision_followup/decision_gap_review.json").read_text())
        self.assertEqual(report["status"], "candidates_rejected")
        self.assertIn("anchored", report["rejected_gaps"][0]["reason"])
        self.assertEqual(self.calls, [])
        self.run_review({"gaps": []})
        report = json.loads((self.path / "decision_followup/decision_gap_review.json").read_text())
        self.assertEqual(report["status"], "no_gap")


if __name__ == "__main__":
    unittest.main()
