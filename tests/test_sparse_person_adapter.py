"""Offline checks for identities, provenance and deterministic Sparse assembly."""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from finmy.person_epg.sparse_adapter import (
    add_evidence, build_person_facts, ground_person_evidence,
)
from finmy.person_epg.validation import validate_person_epg


def field(value, quote=None):
    return {"value": value, "evidence_source_contents": [quote] if quote else [],
            "reasons": ["Fixture assertion"], "confidence": 0.8}


def fixture():
    text = "Alice directed Acme to buy shares.\nAcme  bought shares on 2023-05-01."
    participant = {"participant_id": "P_1", "name": field("Alice", "Alice"),
                   "participant_type": field("individual"), "base_role": field("director"),
                   "attributes": {}, "actions": [{
                       "name": field("directed purchase", "Alice directed Acme to buy shares."),
                       "timestamp": None, "details": [field("Company implementation", "Acme  bought shares")]}]}
    company = {"participant_id": "P_2", "name": field("Acme"),
               "participant_type": field("organization"), "base_role": field("buyer"),
               "attributes": {}, "actions": [{
                   "name": field("bought shares", "Acme bought shares on 2023-05-01."),
                   "timestamp": field("2023-05-01", "2023-05-01"), "details": []}]}
    episode = {"episode_id": "E1", "name": field("Purchase"),
               "start_time": None, "end_time": None, "descriptions": [],
               "participants": [participant, company],
               "participant_relations": [{"from_participant_id": "P_1", "to_participant_id": "P_2",
                                          "relation_name": field("director"), "start_time": None, "end_time": None}],
               "transactions": [{"name": field("share purchase"), "transaction_type": field("purchase"),
                                 "from_participant_id": field("P_2"), "to_participant_id": None,
                                 "timestamp": field("2023-05-01"), "details": [field("Company trade")],
                                 "instruments": [field("shares")]}]}
    cascade = {"event_id": "EV", "title": field("Alice and Acme"), "event_type": field("investment"),
               "descriptions": [], "stages": [{"stage_id": "S1", "name": field("Investment"),
                                                 "episodes": [episode]}]}
    inputs = SimpleNamespace(user_query=SimpleNamespace(extras={"source_registry": {
        "raw-1": {"url": "https://example.test/source", "title": "Source"}}}),
        samples=[SimpleNamespace(sample_id="s1", raw_data_id="raw-1", content=text)])
    subject = {"subject_id": "alice", "name": "Alice", "aliases": [],
               "coverage_start": "2023", "coverage_end": "2023", "scope": "Acme investment"}
    return cascade, inputs, subject


class SparsePersonAdapterTest(unittest.TestCase):
    def build(self):
        return build_person_facts(*fixture())

    def test_attribution_and_unknown_transaction_party_are_preserved(self):
        package, report = self.build()
        self.assertEqual(validate_person_epg(package), {"valid": True, "errors": []})
        self.assertEqual(package["graph"]["subject_entity_id"], "alice")
        self.assertEqual([row["actor_id"] for row in package["action"]], ["alice", "entity:P_2"])
        transaction = package["financial_transaction"][0]
        self.assertEqual(transaction["from_entity_id"], "entity:P_2")
        self.assertIsNone(transaction["to_entity_id"])
        self.assertEqual(len(package["activity"]), 3)
        self.assertEqual(package["event"], [])
        self.assertIn("Pending", package["occurrence"][0]["subject_relevance"])
        self.assertTrue(any(r["source_path"].endswith("transaction_type") for r in report["retained_in_sparse_result"]))


    def test_whitespace_quote_uses_original_slice_and_duplicate_spans_merge(self):
        package, _ = self.build()
        sid = add_evidence(package, {"/summary": field("Summary", "Acme bought shares on 2023-05-01.")})
        report = ground_person_evidence(package)
        self.assertEqual(report["unmatched_quote_count"], 0)
        self.assertGreater(report["match_counts"]["whitespace"], 0)
        link = next(r for r in package["evidence_link"] if r["evidence_set_id"] == sid)
        span = next(r for r in package["evidence_span"] if r["span_id"] == link["span_id"])
        self.assertEqual(span["quote"], "Acme  bought shares on 2023-05-01.")
        doc = package["source_document"][0]["content"]
        self.assertEqual(span["quote"], doc[span["char_start"]:span["char_end"]])
        self.assertEqual(len([s for s in package["evidence_span"] if s["quote"] == span["quote"]]), 1)
        self.assertEqual(validate_person_epg(package), {"valid": True, "errors": []})
        before = copy.deepcopy(package)
        ground_person_evidence(package)
        self.assertEqual(package, before)

    def test_ambiguous_quote_does_not_pick_first_document(self):
        package, _ = self.build()
        package["source_document"].append({"document_id": "DOC_SECOND", "content": "Alice"})
        report = ground_person_evidence(package)
        self.assertEqual(report["match_counts"]["ambiguous"], 1)
        span = next(s for s in package["evidence_span"] if s["quote"] == "Alice")
        self.assertIsNone(span["document_id"])
        self.assertGreater(report["unmatched_quote_count"], 0)


    def test_source_snapshots_keep_sample_coordinates_even_for_same_raw_document(self):
        cascade, inputs, subject = fixture()
        inputs.samples.append(SimpleNamespace(sample_id="s2", raw_data_id="raw-1", content="Other paragraph"))
        package, report = build_person_facts(cascade, inputs, subject)
        self.assertEqual(len(package["source_document"]), 2)
        self.assertEqual(package["source_document"][0]["source_url"], "https://example.test/source")
        self.assertEqual(report["source_map"][1]["offset_origin"], "sample.content")
        self.assertNotEqual(report["source_map"][0]["document_id"], report["source_map"][1]["document_id"])


    def test_buffett_fixed_fixture_keeps_25_anchors_and_unresolved_quotes(self):
        path = Path(__file__).parent / "fixtures" / "buffett_person_epg_preview.json"
        original_bytes = path.read_bytes()
        self.assertEqual(hashlib.sha256(original_bytes).hexdigest(),
                         "ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c")
        package = json.loads(original_bytes)
        anchors = {r["span_id"]: copy.deepcopy(r) for r in package["evidence_span"] if r.get("document_id")}
        facts = {key: copy.deepcopy(package[key]) for key in ("action", "financial_transaction", "event", "stage", "activity_relation")}
        report = ground_person_evidence(package)
        self.assertEqual(report["match_counts"], {"exact": 25, "whitespace": 0, "ambiguous": 0, "unresolved": 251})
        self.assertEqual(anchors, {r["span_id"]: r for r in package["evidence_span"] if r.get("document_id")})
        for key, rows in facts.items():
            self.assertEqual(package[key], rows)
        self.assertEqual(validate_person_epg(package), {"valid": True, "errors": []})
        self.assertEqual(path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
