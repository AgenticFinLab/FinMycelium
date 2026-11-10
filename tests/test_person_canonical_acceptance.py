"""Real-output regressions for canonical facts, before event organization.

The fixture is intentionally faulty input, extracted from the supplied Buffett
run. Proposals below represent a source-grounded semantic decision; these tests
verify that committing that decision preserves evidence and synchronizes graph
references, rather than claiming a mocked LLM has passed a quality evaluation.
"""
import copy
import json
from pathlib import Path
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.person_epg.validation import validate_person_epg

FIXTURE = Path(__file__).parent / "fixtures" / "person_canonical_cases.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def cited(package, value, quote, document_id=None):
    documents = [d for d in package["source_document"]
                 if quote in d["content"] and (document_id is None or d["document_id"] == document_id)]
    if len(documents) != 1:
        raise AssertionError("Fixture citation must identify exactly one source")
    return {"value": value, "citations": [{"document_id": documents[0]["document_id"], "quote": quote}]}


def fact_citations(package, fact_id):
    fact = next(r for table in ("action", "financial_transaction") for r in package[table]
                if fact_id == r.get("action_id", r.get("transaction_id")))
    sets = {fact["evidence_set_id"]}
    aids = {r["activity_id"] for r in package["activity"]
            if fact_id in (r.get("action_id"), r.get("transaction_id"))}
    sets.update(r["evidence_set_id"] for r in package["activity_detail"] if r["activity_id"] in aids)
    spans = {r["span_id"]: r for r in package["evidence_span"]}
    return {(spans[r["span_id"]].get("document_id"), spans[r["span_id"]]["quote"])
            for r in package["evidence_link"] if r["evidence_set_id"] in sets}


def details(package, fact_id):
    aids = {r["activity_id"] for r in package["activity"]
            if fact_id in (r.get("action_id"), r.get("transaction_id"))}
    result = {r["value"] for r in package["activity_detail"] if r["activity_id"] in aids}
    for row in package["financial_transaction"]:
        if row["transaction_id"] == fact_id:
            result.update(row["details"])
    return result


def unknown():
    return {"value": "unknown", "citations": []}


class CanonicalRealOutputAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.package = self.data["package"]
        self.cases = {r["case_id"]: r for r in self.data["cases"]}

    def apply(self, operations):
        from finmy.builder.sparse_build.person_fact_pipeline import apply_canonical_proposal
        before = copy.deepcopy(self.package)
        result, audit = apply_canonical_proposal(self.package, {"operations": operations})
        self.assertEqual(self.package, before, "Committing a proposal must not mutate the source checkpoint")
        self.assertEqual(validate_person_epg(result), {"valid": True, "errors": []})
        return result, audit

    def test_fixture_retains_exact_source_anchors(self):
        self.assertEqual(validate_person_epg(self.package), {"valid": True, "errors": []})
        docs = {r["document_id"]: r["content"] for r in self.package["source_document"]}
        for row in self.package["evidence_span"]:
            if row.get("document_id"):
                self.assertEqual(docs[row["document_id"]][row["char_start"]:row["char_end"]], row["quote"])

    def test_fixture_contains_only_retained_fact_evidence(self):
        # Keep the full Buffett package in its separate rendering fixture. This
        # one needs only the facts distinguishing the seven failure cases.
        self.assertEqual(len(self.package['activity']), 18)
        self.assertEqual(len(self.package['activity_detail']), 17)
        used_sets = set()
        for table, rows in self.package.items():
            if table.startswith('evidence_'):
                continue
            for row in rows if isinstance(rows, list) else [rows]:
                if isinstance(row, dict) and row.get('evidence_set_id'):
                    used_sets.add(row['evidence_set_id'])
        self.assertEqual({r['evidence_set_id'] for r in self.package['evidence_set']}, used_sets)
        self.assertEqual({r['span_id'] for r in self.package['evidence_span']},
                         {r['span_id'] for r in self.package['evidence_link']})
        self.assertEqual({r['document_id'] for r in self.package['source_document']},
                         {r['document_id'] for r in self.package['evidence_span'] if r.get('document_id')})

    def test_captured_response_relation_uses_vote_as_response_not_proposal(self):
        from finmy.builder.sparse_build.relation_candidates import (
            normalize_response_direction, validate_relation_candidates,
        )
        case = self.cases['responds_to_direction']
        captured = case['incorrect_relation']
        quote = next(r['quote'] for r in self.package['evidence_span']
                     if 'CalPERS' in r['quote'] and '被否决' in r['quote'])
        relation = {key: captured[key] for key in
                    ('from_activity_id', 'to_activity_id', 'relation_type', 'basis')}
        relation['description'] = {'value': captured['description'],
                                   'evidence_source_contents': [quote], 'reasons': []}
        before = copy.deepcopy(relation)
        result = normalize_response_direction(relation, {
            'response_activity_id': case['expected_from'],
            'trigger_activity_id': case['expected_to'],
        })
        ids = [r['activity_id'] for r in self.package['activity']]
        validate_relation_candidates({'activity_relations': [result]}, ids, ids, self.package)
        self.assertEqual(result['from_activity_id'], case['expected_from'])
        self.assertEqual(result['to_activity_id'], case['expected_to'])
        self.assertEqual(relation, before)

    def test_import_retains_existing_context_activity_and_all_fact_evidence(self):
        result, _ = self.apply([])
        self.assertIn("C:O_S4_E1", {r["activity_id"] for r in result["activity"]})
        for table, key in (("action", "action_id"), ("financial_transaction", "transaction_id")):
            self.assertEqual({r[key] for r in self.package[table]}, {r[key] for r in result[table]})
            for row in self.package[table]:
                self.assertTrue(fact_citations(self.package, row[key]) <= fact_citations(result, row[key]))
                self.assertTrue(details(self.package, row[key]) <= details(result, row[key]))

    def test_duplicate_results_keep_unique_details_evidence_and_distinct_speech(self):
        case = self.cases["annual_results_duplicate"]
        keep, duplicate = case["duplicate_fact_ids"]
        expected_details = details(self.package, keep) | details(self.package, duplicate)
        expected_quotes = fact_citations(self.package, keep) | fact_citations(self.package, duplicate)
        result, _ = self.apply([{"op": "merge_facts", "keep_id": keep,
                                "fact_ids": [duplicate], "reason": "Same company results disclosure on February 25."}])
        ids = {r["action_id"] for r in result["action"]}
        self.assertIn(keep, ids)
        self.assertNotIn(duplicate, ids)
        self.assertTrue(set(case["distinct_fact_ids"]) <= ids)
        self.assertTrue(expected_details <= details(result, keep))
        self.assertTrue(expected_quotes <= fact_citations(result, keep))
        self.assertFalse(any(r.get("action_id") == duplicate for r in result["activity"]))
        self.assertFalse(any(r["activity_id"] == "A:" + duplicate for r in result["activity_detail"]))

    def test_same_meeting_deduplicates_without_merging_different_actions(self):
        case = self.cases["annual_meeting_duplicate"]
        keep, duplicate = case["duplicate_fact_ids"]
        result, _ = self.apply([{"op": "merge_facts", "keep_id": keep,
                                "fact_ids": [duplicate], "reason": "Same 59th annual meeting, same company and date."}])
        ids = {r["action_id"] for r in result["action"]}
        self.assertIn(case["historical_fact_id"], ids)
        self.assertIn("ACT_O_S5_E3_P1_1", ids)
        self.assertIn("ACT_O_S5_E2_P5_1", ids)
        self.assertNotIn(duplicate, ids)

    def test_activision_announcement_moves_to_its_own_occurrence(self):
        case = self.cases["activision_occurrence_dates"]
        quote = "几周之后，这家以魔兽世界和使命召唤等游戏闻名全球的游戏制造商宣布以687亿美元的价格将自己出售给了微软"
        result, _ = self.apply([
            {"op": "create_occurrence", "occurrence": {
                "occurrence_id": case["new_occurrence_id"],
                "title": cited(self.package, "Activision acquisition announcement", quote),
                "descriptions": [],
                "start_time": cited(self.package, "2022-01", quote),
                "end_time": cited(self.package, "2022-01", quote),
                "subject_relevance": cited(self.package, "Announcement concerning Berkshire's Activision investment", quote),
            }, "reason": "The announcement follows the Q4 holding snapshot; it is a different occurrence."},
            {"op": "move_fact", "fact_id": case["later_fact_id"],
             "occurrence_id": case["new_occurrence_id"], "reason": "January announcement, not Q4 holding snapshot."},
        ])
        actions = {r["action_id"]: r for r in result["action"]}
        self.assertEqual(actions[case["later_fact_id"]]["occurrence_id"], case["new_occurrence_id"])
        self.assertEqual(actions[case["historical_fact_ids"][0]]["occurrence_id"], "O_S4_E1")
        transaction = next(r for r in result["financial_transaction"] if r["transaction_id"] == case["historical_fact_ids"][1])
        self.assertEqual(transaction["occurrence_id"], "O_S4_E1")
        times = {r["time_id"]: r["value"] for r in result["time_value"]}
        moved = next(r for r in result["occurrence"] if r["occurrence_id"] == case["new_occurrence_id"])
        self.assertIn("2022", times[moved["start_time_id"]])
        self.assertTrue(fact_citations(self.package, case["later_fact_id"]) <= fact_citations(result, case["later_fact_id"]))

    def test_abel_purchase_keeps_fuzzy_historic_time_outside_later_meeting(self):
        case = self.cases["abel_historic_purchase"]
        quote = "Abel made headlines last fall after he bought nearly $70 million worth of stock in Berkshire Hathaway"
        result, _ = self.apply([
            {"op": "create_occurrence", "occurrence": {
                "occurrence_id": case["new_occurrence_id"],
                "title": cited(self.package, "Greg Abel purchases Berkshire shares", quote),
                "descriptions": [], "start_time": cited(self.package, "2022-fall", quote),
                "end_time": cited(self.package, "2022-fall", quote),
                "subject_relevance": cited(self.package, "Historical purchase by Berkshire's designated successor", quote),
            }, "reason": "Historical purchase mentioned by the 2023 report."},
            {"op": "move_fact", "fact_id": case["historical_fact_id"],
             "occurrence_id": case["new_occurrence_id"], "reason": "Actual purchase preceded the 2023 meeting."},
        ])
        action = next(r for r in result["action"] if r["action_id"] == case["historical_fact_id"])
        times = {r["time_id"]: r["value"] for r in result["time_value"]}
        self.assertEqual(action["occurrence_id"], case["new_occurrence_id"])
        self.assertEqual(times[action["timestamp_time_id"]], "2022")
        metadata = next(s["field_metadata"] for s in result["evidence_set"]
                        if s["evidence_set_id"] == action["evidence_set_id"])
        self.assertEqual(metadata["/timestamp"]["time_normalization"]["original"], "2022-fall")
        self.assertEqual(next(r for r in result["action"] if r["action_id"] == "ACT_O_S5_E3_P1_1")["occurrence_id"], "O_S5_E3")

    def november_split(self):
        case = self.cases["november_multiple_recipients"]
        tx = next(r for r in self.package["financial_transaction"] if r["transaction_id"] == case["transaction_id"])
        quotes = {
            "entity:P_26": "1,500,000 were gifted to the Susan Thompson Buffett Foundation",
            "entity:P_27": "300,000 shares were given to the Sherwood Foundation, the Howard G. Buffett Foundation, and NoVo Foundation, respectively.",
        }
        entities = {r["entity_id"]: r["name"] for r in self.package["entity"]}
        legs = []
        for index, (recipient, quantity) in enumerate(case["recipient_shares"].items()):
            quote = quotes.get(recipient, quotes["entity:P_27"])
            legs.append({"transaction_id": f"TX_NOVEMBER_LEG_{index}",
                         "name": cited(self.package, "Class B stock gift to " + entities[recipient], quote),
                         "from_entity_id": tx["from_entity_id"], "to_entity_id": recipient,
                         "timestamp": cited(self.package, "2023-11-21 (filing date)", "submitted to the SEC on Nov. 21"),
                         "details": [cited(self.package, f"{quantity:,} Class B shares gifted to {entities[recipient]}.", quote)],
                         "instruments": []})
        return {"op": "split_transaction", "transaction_id": case["transaction_id"],
                "legs": legs, "reason": "Four recipients and supported share quantities, one aggregate donation."}

    def test_november_donation_has_four_legs_and_preserves_aggregate_observations(self):
        case = self.cases["november_multiple_recipients"]
        original_details = details(self.package, case["transaction_id"])
        result, _ = self.apply([self.november_split()])
        legs = [r for r in result["financial_transaction"] if r["occurrence_id"] == "O_S6_E2"]
        self.assertEqual({r["to_entity_id"] for r in legs}, set(case["recipient_shares"]))
        self.assertEqual(len(legs), 4)
        self.assertNotIn(case["transaction_id"], {r["transaction_id"] for r in legs})
        all_details = {r["value"] for r in result["activity_detail"]}
        self.assertTrue(original_details <= all_details, "Aggregate information needs a retained overview action")
        for leg in legs:
            quantity = case["recipient_shares"][leg["to_entity_id"]]
            self.assertTrue(any(f"{quantity:,}" in d for d in leg["details"]))
            self.assertFalse(any("$866 million" in d for d in leg["details"]))
        self.assertIn("ACT_O_S6_E2_P1_1", {r["action_id"] for r in result["action"]})

    def test_june_aggregate_is_preserved_without_inventing_ambiguous_recipient_amounts(self):
        case = self.cases["june_multiple_recipients"]
        tx = next(r for r in self.package["financial_transaction"] if r["transaction_id"] == case["transaction_id"])
        names = {r["entity_id"]: r["name"] for r in self.package["entity"]}
        common = "104.53 万股捐给了苏珊・汤普森・巴菲特基金会（Susan Thompson Buffett Foundation），73.17 万股捐给了谢伍德基金会（Sherwood Foundation）、霍华德・G・巴菲特基金会（Howard G. Buffett Foundation）和诺沃基金会（NoVo Foundation）。"
        gates = "巴菲特向盖茨基金会捐赠了 35.4 亿美元（76%）"
        legs = []
        for index, recipient in enumerate(case["recipient_entity_ids"]):
            quote = gates if recipient == "entity:P_25" else common
            detail = ("$3.54 billion given to the Gates Foundation." if recipient == "entity:P_25"
                      else "Named recipient: " + names[recipient] + ".")
            legs.append({"transaction_id": f"TX_JUNE_LEG_{index}",
                         "name": cited(self.package, "Charitable stock gift to " + names[recipient], quote),
                         "from_entity_id": tx["from_entity_id"], "to_entity_id": recipient,
                         "timestamp": cited(self.package, "2023-06-21 (Wednesday)", "巴菲特周三进行了年度慈善捐赠"),
                         "details": [cited(self.package, detail, quote)], "instruments": []})
        result, _ = self.apply([{"op": "split_transaction", "transaction_id": case["transaction_id"],
                                 "legs": legs, "reason": "Recipient legs preserve the aggregate without assuming an ambiguous per-recipient share allocation."}])
        actual = [r for r in result["financial_transaction"] if r["occurrence_id"] == "O_S6_E1"]
        self.assertEqual({r["to_entity_id"] for r in actual}, set(case["recipient_entity_ids"]))
        self.assertEqual(len(actual), 5)
        self.assertTrue(details(self.package, case["transaction_id"]) <= {r["value"] for r in result["activity_detail"]})
        for leg in actual:
            self.assertFalse(any("$4.63 billion" in d for d in leg["details"]))
            if leg["to_entity_id"] in {"entity:P_27", "entity:P_28", "entity:P_29"}:
                self.assertFalse(any("731,700" in d or "731700" in d for d in leg["details"]))

    def test_different_recipients_cannot_merge_and_bad_operation_keeps_valid_split(self):
        result, _ = self.apply([
            self.november_split(),
            {"op": "merge_facts", "keep_id": "TX_NOVEMBER_LEG_0", "fact_ids": ["TX_NOVEMBER_LEG_1"],
             "reason": "Invalid proposed merge across different recipients."},
            {"op": "move_fact", "fact_id": "missing_fact", "occurrence_id": "O_S6_E2", "reason": "Invalid neighboring proposal."},
        ])
        legs = [r for r in result["financial_transaction"] if r["occurrence_id"] == "O_S6_E2"]
        self.assertEqual(len(legs), 4)
        self.assertEqual({r["to_entity_id"] for r in legs}, set(self.cases["november_multiple_recipients"]["recipient_shares"]))


if __name__ == "__main__":
    unittest.main()
