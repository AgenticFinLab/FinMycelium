"""Bounded second-pass repairs retain only additions that pass a fresh review."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.event_additions import empty_additions
from finmy.runner.event_enrichment import enrich_events


FIXTURE = Path(__file__).parent / "fixtures/buffett_person_epg_preview.json"
APPROVE = {"approved": True, "issues": []}


class EventEnrichmentRepairTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.event_ids = [row["event_id"] for row in self.package["event"][:2]]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {
            "builder_config": {"builder_type": "SparseRagBuilder",
                "sparse_builder_config": {"output_language": "English"},
                "reconstruction": {"mode": "person", "subject": {
                    "subject_id": "buffett", "name": "Warren Buffett",
                    "coverage_start": "2022", "coverage_end": "2023"}}},
            "event_followup": {"max_model_calls": 24},
        }
        self.sources = [{"document_id": "REPAIR_SOURCE", "event_ids": self.event_ids[:1],
            "content": "Buffett reviewed memorandum ZX-17. Buffett discussed project QY-23. "
                       "Fiction Company issued memorandum AB-34. The memorandum explained the purchase."}]
        self.requests = []

    def citation(self):
        return [{"document_id": "REPAIR_SOURCE", "quote": self.sources[0]["content"]}]

    def proposal(self, *, two=False):
        proposal = empty_additions()
        proposal["activities"] = [{"key": "review", "kind": "action",
            "title": "Reviewed memorandum ZX-17", "actor_id": self.package["graph"]["subject_entity_id"],
            "from_entity_id": None, "to_entity_id": None, "time": None,
            "stage_id": None, "details": [], "citations": self.citation()}]
        if two:
            proposal["activities"].append({**copy.deepcopy(proposal["activities"][0]),
                "key": "discussion", "title": "Discussed project QY-23"})
        return proposal

    def run_script(self, *responses):
        initial = copy.deepcopy(self.package)
        config = copy.deepcopy(self.config)
        pending = list(responses)

        def complete(system, payload):
            self.requests.append((system, copy.deepcopy(payload)))
            self.assertTrue(pending, "Unexpected extra model call")
            response = pending.pop(0)
            if isinstance(response, Exception):
                raise response
            return response if isinstance(response, str) else json.dumps(response)

        result, report = enrich_events(self.package, self.sources, self.config, self.root,
                                      completion=complete)
        self.assertFalse(pending, "Expected scripted model calls did not run")
        self.assertEqual(self.package, initial)
        self.assertEqual(self.config, config)
        for table, value in initial.items():
            self.assertEqual(result[table][:len(value)] if isinstance(value, list) else result[table], value, table)
        self.assertTrue(validate_person_epg(result)["valid"])
        ledger = json.loads((self.root / "CallLedger.json").read_text())
        self.assertEqual(report["model_calls"], len(self.requests))
        self.assertEqual(len(ledger), len(self.requests))
        self.assertLessEqual(len(ledger), self.config["event_followup"]["max_model_calls"])
        return result, report, ledger

    def test_rejected_item_is_removed_and_good_subset_gets_a_new_review(self):
        proposal = self.proposal(two=True)
        original_proposal = copy.deepcopy(proposal)
        result, report, ledger = self.run_script(proposal,
            {"approved": False, "issues": ["Project QY-23 belongs to another event."],
             "rejected_paths": ["/activities/1"]}, APPROVE)
        self.assertEqual(proposal, original_proposal)
        self.assertEqual(len(result["activity"]), len(self.package["activity"]) + 1)
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertEqual(len(self.requests[1][1]["proposal"]["activities"]), 2)
        self.assertEqual([row["key"] for row in self.requests[2][1]["proposal"]["activities"]], ["review"])
        self.assertEqual([row["role"] for row in ledger], ["propose", "review", "review"])
        files = list(self.root.glob("event_*_request.json"))
        self.assertEqual(len(files), 3, "Retry artifacts must not overwrite the first review")


    def test_invalid_citation_can_be_repaired_using_the_same_visible_evidence(self):
        bad = self.proposal()
        bad["activities"][0]["citations"][0]["quote"] = "Invented quotation requiring repair"
        result, report, ledger = self.run_script(bad, self.proposal(), APPROVE)
        self.assertEqual([row["role"] for row in ledger], ["propose", "repair", "review"])
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertEqual(len(result["activity"]), len(self.package["activity"]) + 1)
        repair_request = self.requests[1][1]
        self.assertEqual(repair_request["supplemental_sources"], self.requests[0][1]["supplemental_sources"])
        self.assertIn("Invented quotation requiring repair", json.dumps(repair_request))


    def test_malformed_review_retries_review_without_regenerating_proposal(self):
        for malformed in ('{"approved":', {"approved": True}, '{"approved": NaN, "issues": []}',
                          {"approved": False, "issues": ["Bad item"], "rejected_paths": ["/activities/999"]}):
            with self.subTest(malformed=malformed):
                self.requests = []
                result, report, ledger = self.run_script(self.proposal(), malformed, APPROVE)
                self.assertEqual([row["role"] for row in ledger], ["propose", "review", "review"])
                self.assertEqual(self.requests[1][1]["proposal"], self.requests[2][1]["proposal"])
                self.assertEqual(report["events"][0]["status"], "enriched")
                self.assertNotEqual(result, self.package)


    def test_all_events_get_initial_attempt_before_any_repair(self):
        self.sources[0]["event_ids"] = self.event_ids
        self.config["event_followup"]["max_model_calls"] = 5
        bad = self.proposal()
        bad["activities"][0]["citations"][0]["quote"] = "Invented quotation"
        second = self.proposal()
        second["activities"][0]["key"] = "second_event_meeting"
        second["activities"][0]["title"] = "Discussed project QY-23"
        result, report, ledger = self.run_script(bad, second, APPROVE, self.proposal(), APPROVE)
        self.assertEqual([row["event_id"] for row in ledger],
                         [self.event_ids[0], self.event_ids[1], self.event_ids[1], self.event_ids[0], self.event_ids[0]])
        self.assertEqual([row["status"] for row in report["events"][:2]], ["enriched", "enriched"])
        self.assertEqual(len(result["activity"]), len(self.package["activity"]) + 2)
        known = self.requests[3][1]["known_activities"]
        self.assertTrue(any(row["fact"].get("action_type") == "Discussed project QY-23" for row in known))


    def test_no_budget_for_subset_review_means_no_unreviewed_commit(self):
        self.config["event_followup"]["max_model_calls"] = 2
        result, report, _ = self.run_script(self.proposal(two=True),
            {"approved": False, "issues": ["One activity is unsupported."],
             "rejected_paths": ["/activities/1"]})
        self.assertEqual(result, self.package)
        self.assertNotEqual(report["events"][0]["status"], "enriched")
        self.assertFalse((self.root / "checkpoint_person_epg.json").exists())


    def test_repair_cannot_expand_its_citation_scope(self):
        bad = self.proposal()
        bad["activities"][0]["citations"][0]["quote"] = "Invented quotation"
        repaired = self.proposal()
        repaired["activities"][0]["citations"][0]["document_id"] = "UNSEEN_DOCUMENT"
        result, report, _ = self.run_script(bad, repaired)
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 2)
        self.assertFalse((self.root / "checkpoint_person_epg.json").exists())


    def test_review_timeout_reuses_candidate_and_requires_successful_review(self):
        result, report, ledger = self.run_script(self.proposal(), TimeoutError("Temporary provider failure"), APPROVE)
        self.assertEqual([row["role"] for row in ledger], ["propose", "review", "review"])
        self.assertEqual(self.requests[1][1]["proposal"], self.requests[2][1]["proposal"])
        self.assertEqual(ledger[1]["status"], "failed")
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertNotEqual(result, self.package)


    def test_nonretryable_review_http_failure_does_not_repeat_the_request(self):
        class ProviderError(Exception):
            def __init__(self, status):
                self.status_code = status
                self.body = {"error": {"message": "Invalid request or unavailable credentials"}}

        for status in (400, 401, 403):
            with self.subTest(status=status):
                self.requests = []
                result, report, _ = self.run_script(self.proposal(), ProviderError(status))
                self.assertEqual(result, self.package)
                self.assertEqual(report["model_calls"], 2)
                self.assertFalse((self.root / "checkpoint_person_epg.json").exists())


if __name__ == "__main__":
    unittest.main()
