"""Offline consistency regressions; fixtures contain no model or search output."""

import copy
import json
import unittest

from finmy.builder.agent_build.validation import validate_event_cascade


def field(value, evidence=None, reason="fixture", confidence=0.9):
    return {"value": value, "evidence_source_contents": evidence or [],
            "reasons": [reason], "confidence": confidence}


TRADE_EVIDENCE = "On July 13 Acme bought 100 Example shares for USD 1,000."


def transaction(date="2022-07-13", detail="100 shares for USD 1,000", *,
                evidence=TRADE_EVIDENCE, transaction_id=None):
    result = {
        "name": field("Example share purchase", [evidence]),
        "transaction_type": field("share purchase", [evidence]),
        "timestamp": field(date, [evidence]),
        "details": [field(detail, [evidence])],
        "from_participant_id": "P_1", "to_participant_id": "P_2",
        "instruments": [field("Example common stock", [evidence])],
    }
    if transaction_id is not None:
        result["transaction_id"] = transaction_id
    return result


def episode(identifier, start="2022-07-01", end="2022-07-31", trades=None):
    return {
        "episode_id": identifier, "name": field(identifier), "index_in_stage": 0,
        "start_time": field(start), "end_time": field(end),
        "participants": [
            {"participant_id": "P_1", "name": field("Acme"),
             "participant_type": field("organization"), "actions": []},
            {"participant_id": "P_2", "name": field("Example"),
             "participant_type": field("organization"), "actions": []},
        ],
        "participant_relations": [], "descriptions": [],
        "transactions": trades if trades is not None else [transaction()],
    }


def cascade(*episodes):
    return {
        "event_id": "fixture", "title": field("Synthetic investment"),
        "start_time": field("2022-01-01"), "end_time": field("2023-12-31"),
        "stages": [{"stage_id": "S1", "name": field("Investment"),
                    "index_in_event": 0, "start_time": field("2022-01-01"),
                    "end_time": field("2023-12-31"), "descriptions": [],
                    "episodes": list(episodes)}],
        "descriptions": [],
    }


def all_transactions(value):
    return [t for s in value["stages"] for e in s["episodes"]
            for t in e["transactions"]]


class EPGValidationTest(unittest.TestCase):
    @staticmethod
    def issue_codes(report, phase="issues_after"):
        return [item["code"] for item in report[phase]]

    def assert_preserved_pair(self, left, right):
        original = cascade(episode("E1", trades=[left]), episode("E2", trades=[right]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(len(all_transactions(corrected)), 2)
        self.assertEqual(original, corrected)
        return report

    def test_duplicate_keeps_narrowest_containing_episode(self):
        original = cascade(episode("E1", "2022-01-01", "2022-12-31"),
                           episode("E2", "2022-07-01", "2022-07-31"))
        corrected, report = validate_event_cascade(original)
        self.assertEqual([len(e["transactions"]) for e in corrected["stages"][0]["episodes"]],
                         [0, 1])
        self.assertEqual(len(all_transactions(original)), 2)
        self.assertIsInstance(report, dict)

    def test_containing_episode_wins_over_narrow_outside_episode(self):
        original = cascade(episode("E1", "2022-08-01", "2022-08-02"),
                           episode("E2", "2022-07-01", "2022-07-31"))
        corrected, _ = validate_event_cascade(original)
        self.assertEqual([len(e["transactions"]) for e in corrected["stages"][0]["episodes"]],
                         [0, 1])

    def test_same_day_distinct_amounts_survive_shared_source_paragraph(self):
        evidence = ("On July 13 Acme bought 100 Example shares for USD 1,000, "
                    "then bought 200 Example shares for USD 2,000.")
        self.assert_preserved_pair(transaction(detail="100 shares for USD 1,000", evidence=evidence),
                                   transaction(detail="200 shares for USD 2,000", evidence=evidence))

    def test_conflicting_transaction_ids_are_not_merged(self):
        self.assert_preserved_pair(transaction(transaction_id="trade-A"),
                                   transaction(transaction_id="trade-B"))

    def test_transaction_ids_are_case_sensitive(self):
        self.assert_preserved_pair(transaction(transaction_id="trade-A"),
                                   transaction(transaction_id="trade-a"))

    def test_different_currencies_do_not_merge_despite_equal_numbers(self):
        evidence = "The records show 100 shares for USD 100 and 100 shares for EUR 100."
        self.assert_preserved_pair(transaction(detail="100 shares for USD 100", evidence=evidence),
                                   transaction(detail="100 shares for EUR 100", evidence=evidence))

    def test_quantity_unit_is_part_of_identity(self):
        evidence = "The statement records 100 shares and a separate USD 100 payment."
        self.assert_preserved_pair(transaction(detail="100 shares", evidence=evidence),
                                   transaction(detail="USD 100", evidence=evidence))

    def test_signed_amounts_are_not_collapsed(self):
        evidence = "The reconciliation contains USD -100 and USD 100 entries for this payment."
        self.assert_preserved_pair(transaction(detail="USD -100", evidence=evidence),
                                   transaction(detail="USD 100", evidence=evidence))

    def test_conflict_in_additional_detail_prevents_merge(self):
        left, right = transaction(), transaction()
        left["details"].append(field("Execution price: USD 10", ["Execution price: USD 10."]))
        right["details"].append(field("Execution price: USD 20", ["Execution price: USD 20."]))
        self.assert_preserved_pair(left, right)

    def test_wrapped_participant_references_resolve(self):
        first, second = episode("E1"), episode("E2")
        for key in ("from_participant_id", "to_participant_id"):
            second["transactions"][0][key] = field(second["transactions"][0][key])
        corrected, report = validate_event_cascade(cascade(first, second))
        self.assertEqual(len(all_transactions(corrected)), 1)
        self.assertNotIn("missing_participant_reference", self.issue_codes(report))

    def test_transitive_evidence_does_not_merge_conflicting_endpoints(self):
        common = field("100 shares", ["Acme purchased 100 Example shares in this reported transaction."])
        first, bridge, third = transaction(), transaction(), transaction()
        first["details"] = [copy.deepcopy(common), field("USD 100", ["The payment was USD 100."])]
        bridge["details"] = [copy.deepcopy(common)]
        third["details"] = [copy.deepcopy(common), field("USD 200", ["The payment was USD 200."])]
        original = cascade(episode("E1", trades=[first]), episode("E2", trades=[bridge]),
                           episode("E3", trades=[third]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(len(all_transactions(corrected)), 3)
        self.assertEqual(corrected, original)
        self.assertIn("ambiguous_duplicate_group", self.issue_codes(report))
        again, _ = validate_event_cascade(corrected)
        self.assertEqual(again, corrected)

    def test_evidence_bridge_retains_entire_component_on_repeated_runs(self):
        quote_a = "Alpha disclosure states a purchase of 100 shares."
        quote_b = "Omega filing identifies acquisition of 100 shares."
        first, bridge, third = transaction(), transaction(), transaction()
        first["details"] = [field("100 shares", [quote_a])]
        bridge["details"] = [field("100 shares", [quote_a, quote_b])]
        third["details"] = [field("100 shares", [quote_b])]
        original = cascade(episode("E1", trades=[first]), episode("E2", trades=[bridge]),
                           episode("E3", trades=[third]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertEqual(len(all_transactions(corrected)), 3)
        self.assertIn("ambiguous_duplicate_group", self.issue_codes(report))
        again, _ = validate_event_cascade(corrected)
        self.assertEqual(again, corrected)

    def test_missing_actor_is_not_matching_evidence(self):
        left, right = transaction(), transaction()
        left["from_participant_id"] = right["from_participant_id"] = "unknown"
        self.assert_preserved_pair(left, right)

    def test_unknown_instrument_is_not_matching_evidence(self):
        left, right = transaction(), transaction()
        left["instruments"] = right["instruments"] = [field("unknown")]
        self.assert_preserved_pair(left, right)

    def test_missing_instrument_is_not_matching_evidence(self):
        left, right = transaction(), transaction()
        left["instruments"] = right["instruments"] = []
        self.assert_preserved_pair(left, right)

    def test_participant_ids_are_scoped_to_episode(self):
        first, second = episode("E1"), episode("E2")
        second["participants"][0]["name"] = field("Different buyer")
        original = cascade(first, second)
        corrected, _ = validate_event_cascade(original)
        self.assertEqual(len(all_transactions(corrected)), 2)

    def test_reverse_direction_is_a_different_transaction(self):
        left, right = transaction(), transaction()
        right["from_participant_id"], right["to_participant_id"] = "P_2", "P_1"
        self.assert_preserved_pair(left, right)

    def test_same_episode_repeats_are_not_silently_removed(self):
        original = cascade(episode("E1", trades=[transaction(), transaction()]))
        corrected, _ = validate_event_cascade(original)
        self.assertEqual(corrected, original)

    def test_same_episode_multiplicity_blocks_cross_episode_merge(self):
        original = cascade(episode("E1", "2022-01-01", "2022-12-31",
                                   [transaction(), transaction()]),
                           episode("E2", "2022-07-01", "2022-07-31", [transaction()]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertEqual(len(all_transactions(corrected)), 3)
        self.assertIn("ambiguous_duplicate_group", self.issue_codes(report))
        again, _ = validate_event_cascade(corrected)
        self.assertEqual(again, corrected)

    def test_deduplicate_false_preserves_all_transactions(self):
        original = cascade(episode("E1"), episode("E2"))
        corrected, report = validate_event_cascade(original, deduplicate=False)
        self.assertEqual(corrected, original)
        self.assertEqual(report["summary"]["duplicates_removed"], 0)
        self.assertEqual(report["summary"]["duplicate_groups"], 1)
        self.assertEqual(len(report["duplicate_candidates"]), 1)
        self.assertEqual(report["merges"], [])

    def test_input_is_deep_copied(self):
        original = cascade(episode("E1"), episode("E2"))
        saved = copy.deepcopy(original)
        corrected, _ = validate_event_cascade(original)
        self.assertEqual(original, saved)
        corrected["title"]["evidence_source_contents"].append("mutation")
        all_transactions(corrected)[0]["details"][0]["reasons"].append("mutation")
        self.assertEqual(original, saved)

    def test_merge_preserves_evidence_and_reasons(self):
        first, second = episode("E1"), episode("E2")
        first["transactions"][0]["details"][0]["evidence_source_contents"].append("First disclosure.")
        second["transactions"][0]["details"][0]["evidence_source_contents"].append("Second disclosure.")
        first["transactions"][0]["details"][0]["reasons"] = ["first explanation"]
        second["transactions"][0]["details"][0]["reasons"] = ["second explanation"]
        corrected, _ = validate_event_cascade(cascade(first, second))
        self.assertEqual(len(all_transactions(corrected)), 1)
        retained = json.dumps(all_transactions(corrected)[0])
        for text in ("First disclosure.", "Second disclosure.",
                     "first explanation", "second explanation"):
            self.assertIn(text, retained)

    def test_deduplication_is_idempotent(self):
        original = cascade(episode("E1"), episode("E2"), episode("E3"))
        corrected, _ = validate_event_cascade(original)
        again, _ = validate_event_cascade(corrected)
        self.assertEqual(again, corrected)

    def test_aggregate_is_not_merged_into_single_trade(self):
        evidence = ("On Oct 23 Acme bought 100 Example shares for USD 1,000; "
                    "on Oct 25 it bought 200 shares for USD 2,000.")
        aggregate = transaction("2023-10-25", "100 shares on Oct 23 for USD 1,000", evidence=evidence)
        aggregate["details"].append(field("200 shares on Oct 25 for USD 2,000", [evidence]))
        single = transaction("2023-10-25", "200 shares for USD 2,000", evidence=evidence)
        original = cascade(episode("E1", "2023-10-01", "2023-10-31", [aggregate]),
                           episode("E2", "2023-10-23", "2023-10-25", [single]))
        corrected, _ = validate_event_cascade(original)
        self.assertEqual(len(all_transactions(corrected)), 2)

    def test_unknown_dates_are_not_invented(self):
        original = cascade(episode("E1", trades=[transaction("unknown")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIsInstance(report, dict)

    def test_whole_month_inside_episode_preserves_month_precision(self):
        original = cascade(episode("E1", "2022-07-01", "2022-07-31",
                                   [transaction("2022-07")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertNotIn("transaction_out_of_bounds", self.issue_codes(report))
        self.assertNotIn("transaction_boundary_uncertain", self.issue_codes(report))

    def test_month_crossing_episode_boundary_is_uncertain_not_outside(self):
        original = cascade(episode("E1", "2022-07-15", "2022-07-31",
                                   [transaction("2022-07")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIn("transaction_boundary_uncertain", self.issue_codes(report))
        self.assertNotIn("transaction_out_of_bounds", self.issue_codes(report))

    def test_partial_episode_bounds_do_not_invent_day_precision(self):
        original = cascade(episode("E1", "2022-07", "2022-07",
                                   [transaction("2022-07-31")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertNotIn("transaction_out_of_bounds", self.issue_codes(report))

    def test_year_precision_preserved(self):
        original = cascade(episode("E1", "2022-01-01", "2022-12-31",
                                   [transaction("2022")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertNotIn("transaction_out_of_bounds", self.issue_codes(report))

    def test_clear_time_violation_is_reported_without_moving_transaction(self):
        original = cascade(episode("E1", trades=[transaction("2023-10-25")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIn("transaction_out_of_bounds", self.issue_codes(report))

    def test_iso_offset_is_compared_in_utc(self):
        original = cascade(episode("E1", "2022-07-13", "2022-07-13",
                                   [transaction("2022-07-14T01:00:00+02:00")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertNotIn("invalid_time", self.issue_codes(report))
        self.assertNotIn("transaction_out_of_bounds", self.issue_codes(report))

    def test_invalid_calendar_date_is_reported(self):
        original = cascade(episode("E1", trades=[transaction("2022-02-30")]))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIn("invalid_time", self.issue_codes(report))

    def test_reversed_episode_bounds_are_reported(self):
        original = cascade(episode("E1", "2022-07-31", "2022-07-01"))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIn("invalid_time_range", self.issue_codes(report))

    def test_month_and_specific_day_are_not_deduplicated(self):
        self.assert_preserved_pair(transaction("2022-07"), transaction("2022-07-13"))

    def test_synthetic_oxy_shape_keeps_aggregate_and_five_duplicates_removed(self):
        july = transaction()
        august = transaction("2022-08-09", "200 shares for USD 2,000",
                             evidence="On August 9 Acme bought 200 Example shares for USD 2,000.")
        september = transaction("2022-09-09", "300 shares for USD 3,000",
                                evidence="On September 9 Acme bought 300 Example shares for USD 3,000.")
        october = [transaction("2023-10-" + day, amount + " shares for USD " + amount,
                               evidence="Acme's October " + day + " purchase of " + amount + " shares.")
                   for day, amount in [("23", "400"), ("24", "500"), ("25", "600")]]
        aggregate = copy.deepcopy(october[-1])
        aggregate["details"] = [copy.deepcopy(item["details"][0]) for item in october]
        original = cascade(
            episode("E1", "2022-01-01", "2022-07-13",
                    [copy.deepcopy(july), copy.deepcopy(august), copy.deepcopy(september), aggregate]),
            episode("E2", "2022-06-01", "2022-06-30", [transaction("2022-06")]),
            episode("E3", "2022-07-01", "2022-07-13", [copy.deepcopy(july)]),
            episode("E4", "2022-08-01", "2022-08-19", [copy.deepcopy(august)]),
            episode("E5", "2022-08-20", "2022-09-09", [august, july, september]),
            episode("E6", "2023-10-23", "2023-10-25", october))
        corrected, report = validate_event_cascade(original)
        self.assertEqual(len(all_transactions(original)), 13)
        self.assertEqual(len(all_transactions(corrected)), 8)
        self.assertEqual([len(e["transactions"]) for e in corrected["stages"][0]["episodes"]],
                         [1, 1, 1, 1, 1, 3])
        self.assertEqual(report["summary"]["duplicates_removed"], 5)
        self.assertEqual(self.issue_codes(report, "issues_before").count("transaction_out_of_bounds"), 5)
        self.assertEqual(self.issue_codes(report).count("transaction_out_of_bounds"), 1)

    def test_empty_event_is_supported(self):
        original = cascade()
        corrected, report = validate_event_cascade(original)
        self.assertEqual(corrected, original)
        self.assertIsInstance(report, dict)


if __name__ == "__main__":
    unittest.main()
