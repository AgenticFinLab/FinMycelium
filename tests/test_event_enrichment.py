"""Additive event enrichment: bounded calls, independent review and rollback."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from finmy.runner.event_additions import empty_additions
from finmy.runner.event_enrichment import enrich_events, _validate_visible_citations
from finmy.person_epg.validation import validate_person_epg


FIXTURE = Path(__file__).parent / "fixtures/buffett_person_epg_preview.json"


class EventEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "builder_config": {"builder_type": "SparseRagBuilder",
                "sparse_builder_config": {"max_calls": 1, "output_language": "Chinese"},
                "reconstruction": {"mode": "person", "subject": {
                    "subject_id": "buffett", "name": "Warren Buffett",
                    "coverage_start": "2022", "coverage_end": "2023"}}},
            "event_followup": {"max_model_calls": 4, "max_repair_rounds_per_event": 0},
        }
        self.event_ids = [row["event_id"] for row in self.package["event"][:2]]
        self.sources = [{"document_id": "EF_DOC_demo", "event_ids": self.event_ids,
                         "source_url": "https://example.test/account",
                         "content": "Buffett convened a meeting about memorandum ZX-17."}]
        self.calls = []

    def proposal(self, title="convened a meeting about memorandum ZX-17"):
        proposal = empty_additions()
        proposal["activities"] = [{
            "key": "new_meeting", "kind": "action", "title": title,
            "actor_id": self.package["graph"]["subject_entity_id"],
            "from_entity_id": None, "to_entity_id": None, "time": None,
            "stage_id": None, "details": [],
            "citations": [{"document_id": "EF_DOC_demo", "quote": self.sources[0]["content"]}],
        }]
        return proposal

    def completion(self, system, payload):
        self.calls.append(copy.deepcopy(payload))
        if "proposal" in payload:
            return json.dumps({"approved": True, "issues": []})
        return json.dumps(self.proposal())

    def run_enrichment(self, **kwargs):
        return enrich_events(self.package, self.sources, self.config, self.root,
                             completion=kwargs.pop("completion", self.completion), **kwargs)

    def test_approved_additions_preserve_every_original_row_and_graph(self):
        self.sources[0]["event_ids"] = self.event_ids[:1]
        before = copy.deepcopy(self.package)
        result, report = self.run_enrichment()
        self.assertEqual(self.package, before)
        self.assertEqual(result["graph"], before["graph"])
        for key, value in before.items():
            if isinstance(value, list):
                self.assertEqual(result[key][:len(value)], value, key)
        self.assertEqual(len(result["activity"]), len(before["activity"]) + 1)
        self.assertTrue(validate_person_epg(result)["valid"])
        self.assertEqual(report["model_calls"], 2)
        self.assertEqual(report["status"], "enriched")
        self.assertTrue(report["initial_rows_preserved"])
        self.assertFalse(report["semantic_improvement_verified"])
        self.assertTrue((self.root / "checkpoint_person_epg.json").exists())

    def test_original_model_budget_does_not_cut_supplemental_budget(self):
        self.sources[0]["event_ids"] = self.event_ids[:1]
        _, report = self.run_enrichment()
        self.assertEqual(self.config["builder_config"]["sparse_builder_config"]["max_calls"], 1)
        self.assertEqual(report["model_calls"], 2)
        self.assertEqual(report["model_call_limit"], 4)


    def test_zero_budget_and_unrouted_sources_cannot_call_model(self):
        self.config["event_followup"]["max_model_calls"] = 0
        result, report = self.run_enrichment(completion=lambda *args: self.fail("budget exhausted"))
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 0)
        self.config["event_followup"]["max_model_calls"] = 4
        self.sources[0]["event_ids"] = []
        result, report = self.run_enrichment(completion=lambda *args: self.fail("unrouted evidence"))
        self.assertEqual(report["model_calls"], 0)
        self.assertTrue(all(row["status"] == "no_supplemental_sources" for row in report["events"]))

    def test_review_rejection_keeps_original_and_does_not_repair(self):
        self.sources[0]["event_ids"] = self.event_ids[:1]
        def complete(system, payload):
            if "proposal" in payload:
                return json.dumps({"approved": False, "issues": ["Same transaction, inconsistent scale"]})
            return json.dumps(self.proposal())
        result, report = self.run_enrichment(completion=complete)
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 2)
        self.assertEqual(report["events"][0]["status"], "review_rejected")
        self.assertFalse((self.root / "checkpoint_person_epg.json").exists())


    def test_invalid_quote_is_rejected_before_review(self):
        self.sources[0]["event_ids"] = self.event_ids[:1]
        proposal = self.proposal()
        proposal["activities"][0]["citations"][0]["quote"] = "Invented supporting quotation"
        result, report = self.run_enrichment(completion=lambda *args: json.dumps(proposal))
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 1)
        self.assertEqual(report["events"][0]["status"], "invalid_additions")


    def test_incomplete_completion_cannot_be_accepted_even_if_json_is_valid(self):
        self.sources[0]["event_ids"] = self.event_ids[:1]
        output = SimpleNamespace(response=json.dumps(self.proposal()),
                                 extras={"finish_reason": "length"}, cost=None)
        result, report = self.run_enrichment(completion=lambda *args: output)
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 1)
        ledger = json.loads((self.root / "CallLedger.json").read_text())
        self.assertEqual(ledger[0]["finish_reason"], "length")
        self.assertEqual(ledger[0]["status"], "failed")

    def test_transport_failure_is_counted_and_next_event_can_proceed(self):
        def complete(system, payload):
            if payload["event"]["event_id"] == self.event_ids[0]:
                raise TimeoutError("test transport timeout")
            return self.completion(system, payload)
        result, report = self.run_enrichment(completion=complete)
        self.assertEqual(report["model_calls"], 3)
        self.assertEqual(report["events"][0]["status"], "failed")
        self.assertEqual(report["events"][1]["status"], "enriched")
        self.assertEqual(len(result["activity"]), len(self.package["activity"]) + 1)


    def test_citation_in_same_original_document_but_outside_visible_excerpt_is_rejected(self):
        proposal = self.proposal()
        proposal["activities"][0]["citations"] = [{"document_id": "OLD_DOC", "quote": "hidden fact"}]
        payload = {"supplemental_sources": [], "original_source_excerpts": [
            {"document_id": "OLD_DOC", "content": "visible supporting passage"}]}
        with self.assertRaisesRegex(ValueError, "not visible"):
            _validate_visible_citations(proposal, payload)

    def test_review_malformed_or_failed_does_not_erase_previous_success(self):
        # Different evidence avoids deterministic duplicate filtering on event 2.
        self.sources = [{**self.sources[0], "event_ids": self.event_ids[:1]},
                        {"document_id": "EF_DOC_second", "event_ids": self.event_ids[1:],
                         "content": "Buffett interviewed the technical director about project QY-23."}]
        def complete(system, payload):
            if payload["event"]["event_id"] == self.event_ids[0]:
                return self.completion(system, payload)
            if "proposal" in payload:
                return '{"approved": true}'
            proposal = self.proposal("interviewed the technical director about project QY-23")
            proposal["activities"][0]["citations"] = [{"document_id": "EF_DOC_second",
                                                       "quote": self.sources[1]["content"]}]
            return json.dumps(proposal)
        result, report = self.run_enrichment(completion=complete)
        self.assertEqual(report["model_calls"], 4)
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertEqual(report["events"][1]["status"], "failed")
        self.assertEqual(len(result["activity"]), len(self.package["activity"]) + 1)


if __name__ == "__main__":
    unittest.main()
