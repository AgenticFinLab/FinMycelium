"""Bounded event evidence admission; no network/model calls."""
import copy
import math
import random
import unittest

from finmy.runner.context_budget import allocate_context
import test_context_budget as budget_tests
from test_context_budget import document


def settings(limit=60000, cap=12000, seed=2000):
    return {"all_content_config": {"allocation_strategy": "event", "max_content_length": limit,
            "max_document_chars": cap, "min_document_chars": seed}}


def event_doc(identifier, event, term, phase="initial", **kwargs):
    return document(identifier, f"{term} documented action and its surrounding explanation. " * 200,
                    event_ids=[event], event_labels=[f"Synthetic {event} label"],
                    event_terms=[term], search_phase=phase, **kwargs)


class EventContextBudgetTest(unittest.TestCase):
    def assert_valid(self, result, docs, budget, cap=12000, metadata=True):
        budget_tests.ContextBudgetTest.assert_valid(self, result, docs, budget, cap, metadata)

    def test_one_event_cannot_expand_before_other_event_gets_evidence(self):
        docs = [event_doc("a1", "oxy", "Occidental"), event_doc("a2", "oxy", "Occidental"),
                event_doc("b", "activision", "Activision")]
        result = allocate_context(docs, [], settings(4300))
        admitted = {row["document_id"] for row in result["report"]["documents"] if row["included"]}
        self.assertIn("a1", admitted)
        self.assertIn("b", admitted)
        self.assert_valid(result, docs, 4300)


    def test_tail_event_passage_survives_unrelated_p0_quote(self):
        quote = "Occidental financing was discussed with the trading desk."
        text = "Generic macroeconomic comment. " * 400 + quote + " Further execution context. " * 200
        doc = document("transcript", text, event_ids=["oxy"], event_terms=["Occidental"])
        decisions = [{"document_id": "transcript", "chunks": [{"start_char": 0,
            "end_char": len(text), "relevance": "CORE", "evidence": "Generic macroeconomic comment."}]}]
        result = allocate_context([doc], decisions, settings(1800))
        self.assertIn(quote, result["contents"][0])
        self.assertEqual(result["report"]["documents"][0]["event_terms_included"], ["Occidental"])
        self.assert_valid(result, [doc], 1800)

    def test_shared_document_is_emitted_once_and_routed_to_both_events(self):
        doc = document("shared", "Occidental financing. Activision arbitrage. " * 120,
                       event_ids=["oxy", "activision"], event_terms=["Occidental", "Activision"])
        result = allocate_context([doc], [], settings(3000))
        self.assertEqual(len(result["contents"]), 1)
        self.assertEqual(len(result["report"]["event_coverage"]), 2)
        for coverage in result["report"]["event_coverage"]:
            self.assertEqual(coverage["included_document_ids"], ["shared"])
            self.assertFalse(coverage["semantic_support_checked"])
        self.assertFalse(result["report"]["routing_is_evidence"])
        self.assert_valid(result, [doc], 3000)


    def test_title_or_routing_terms_are_not_reported_as_body_evidence(self):
        doc = document("source", "Title:\nOccidental\n\nContent:\n" + "Unrelated body text. " * 100,
                       event_ids=["oxy"], event_terms=["Occidental", "Invented action"],
                       event_labels=["Synthetic label"])
        result = allocate_context([doc], [], settings(1800))
        self.assertEqual(result["report"]["documents"][0]["event_terms_matched"], [])
        self.assertNotIn("Synthetic label", "".join(result["contents"]))
        self.assertNotIn("Invented action", "".join(result["contents"]))


    def test_inputs_unchanged_and_random_budgets_preserve_caps(self):
        rng = random.Random(20261108)
        for trial in range(40):
            docs = [event_doc(f"d{i}", f"e{i % 3}", f"Term{i}",
                              "event_followup" if i % 2 else "initial") for i in range(rng.randrange(1, 8))]
            original = copy.deepcopy(docs)
            limit, cap = rng.randrange(0, 18000), rng.randrange(400, 5000)
            result = allocate_context(docs, [], settings(limit, cap))
            self.assertEqual(docs, original)
            self.assertEqual(result, allocate_context(docs, [], settings(limit, cap)))
            self.assert_valid(result, docs, limit, cap)


if __name__ == "__main__":
    unittest.main()
