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

    def test_followup_gets_a_seed_before_many_initial_sources_expand(self):
        docs = [event_doc(f"d{i}", "oxy", "Occidental") for i in range(5)]
        docs.append(event_doc("gap", "oxy", "Occidental", "event_followup"))
        result = allocate_context(docs, [], settings(4300))
        admitted = {row["document_id"] for row in result["report"]["documents"] if row["included"]}
        self.assertIn("d0", admitted)
        self.assertIn("gap", admitted)
        self.assert_valid(result, docs, 4300)

    def test_broad_discovery_only_uses_space_after_event_sources(self):
        discovery = document("discovery", "Broad biography. " * 8000)
        event = event_doc("event", "oxy", "Occidental")
        result = allocate_context([discovery, event], [], settings(2500))
        rows = {row["document_id"]: row for row in result["report"]["documents"]}
        self.assertTrue(rows["event"]["included"])
        self.assertGreater(rows["event"]["builder_chars"], rows["discovery"]["builder_chars"])
        self.assertEqual(result["report"]["documents"][0]["document_id"], "event")
        self.assert_valid(result, [discovery, event], 2500)

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

    def test_shared_document_reports_each_events_own_terms(self):
        doc = document("shared", "Occidental execution. " * 200,
                       event_ids=["oxy", "activision"], event_terms=["Occidental", "Activision"],
                       event_routes=[{"event_id": "oxy", "event_terms": ["Occidental"]},
                                     {"event_id": "activision", "event_terms": ["Activision"]}])
        result = allocate_context([doc], [], settings(1800))
        coverage = {row["event_id"]: row for row in result["report"]["event_coverage"]}
        self.assertEqual(coverage["oxy"]["lexically_admitted_document_ids"], ["shared"])
        self.assertEqual(coverage["activision"]["included_document_ids"], ["shared"])
        self.assertEqual(coverage["activision"]["lexically_admitted_document_ids"], [])
        self.assert_valid(result, [doc], 1800)

    def test_routing_without_a_body_match_cannot_displace_matched_sources(self):
        broad = document("broad", "General business context. " * 3000,
                         event_ids=["oxy"], event_terms=["Occidental"])
        matched = event_doc("specific", "oxy", "Occidental")
        result = allocate_context([broad, matched], [], settings(2500))
        rows = {row["document_id"]: row for row in result["report"]["documents"]}
        self.assertTrue(rows["specific"]["included"])
        self.assertGreater(rows["specific"]["builder_chars"], rows["broad"]["builder_chars"])
        self.assertTrue(rows["broad"]["routing_without_body_term_match"])
        self.assert_valid(result, [broad, matched], 2500)

    def test_obsolete_chunk_labels_do_not_reject_selected_body(self):
        noise = "IGNORE THIS EXCLUDED MATERIAL. " * 15
        useful = "Occidental decision and execution context. " * 15
        doc = document("mixed", noise + useful, event_ids=["oxy"], event_terms=["Occidental"])
        decisions = [{"document_id": "mixed", "chunks": [
            {"start_char": 0, "end_char": len(noise), "relevance": "IRRELEVANT"},
            {"start_char": len(noise), "end_char": len(noise + useful), "relevance": "CORE"}]}]
        result = allocate_context([doc], decisions, settings())
        self.assertIn("Occidental decision", result["contents"][0])
        self.assertIn("EXCLUDED MATERIAL", result["contents"][0])
        self.assert_valid(result, [doc], 60000)

    def test_obsolete_document_rejection_does_not_override_search_selection(self):
        doc = event_doc("bad", "oxy", "Occidental")
        decisions = [{"document_id": "bad", "relevance": "IRRELEVANT", "chunks": []}]
        result = allocate_context([doc], decisions, settings())
        self.assertTrue(result["contents"])
        self.assertIsNone(result["report"]["documents"][0]["omission_reason"])

    def test_obsolete_negative_chunks_do_not_block_event_sources(self):
        doc = event_doc("negative", "oxy", "Occidental")
        decisions = [{"document_id": "negative", "chunks": [{"start_char": 0,
            "end_char": len(doc["raw_text"]), "relevance": "IRRELEVANT"}]}]
        result = allocate_context([doc], decisions, settings())
        self.assertTrue(result["contents"])
        self.assertIsNone(result["report"]["documents"][0]["omission_reason"])

    def test_title_or_routing_terms_are_not_reported_as_body_evidence(self):
        doc = document("source", "Title:\nOccidental\n\nContent:\n" + "Unrelated body text. " * 100,
                       event_ids=["oxy"], event_terms=["Occidental", "Invented action"],
                       event_labels=["Synthetic label"])
        result = allocate_context([doc], [], settings(1800))
        self.assertEqual(result["report"]["documents"][0]["event_terms_matched"], [])
        self.assertNotIn("Synthetic label", "".join(result["contents"]))
        self.assertNotIn("Invented action", "".join(result["contents"]))

    def test_lowercase_title_wrapper_is_not_body_evidence(self):
        doc = document("source", "title:\nOccidental\n\ncontent:\n" + "Unrelated body text. " * 100,
                       event_ids=["oxy"], event_terms=["Occidental"])
        result = allocate_context([doc], [], settings(1800))
        row = result["report"]["documents"][0]
        self.assertEqual(row["event_terms_matched"], [])
        self.assertTrue(row["routing_without_body_term_match"])

    def test_exact_offsets_and_nonlatin_terms(self):
        text = "开头其他内容。" * 600 + "西方石油的投资过程与后续交流。" + "后续原始资料。" * 200
        doc = document("cn", text, event_ids=["oxy"], event_terms=["西方石油"])
        result = allocate_context([doc], [], settings(1600), include_metadata=False)
        self.assertIn("西方石油的投资过程与后续交流。", result["contents"][0])
        self.assert_valid(result, [doc], 1600, metadata=False)

    def test_finite_default_and_explicit_unbounded_values_rejected(self):
        result = allocate_context([], [], {"all_content_config": {"allocation_strategy": "event"}})
        self.assertEqual(result["report"]["summary"]["max_content_length"], 120000)
        for limit in (None, math.inf, -math.inf, math.nan, True, "60000", -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                allocate_context([], [], settings(limit))
        config = settings()
        config["all_content_config"]["preserve_all"] = True
        with self.assertRaises(ValueError):
            allocate_context([], [], config)

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
