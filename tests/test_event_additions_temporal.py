"""Temporal enrichment reuses native windows without treating dates as quotes."""
import copy
import unittest

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.event_additions import empty_additions, merge_event_additions
from test_event_additions import activity, package


def time_field(value, quote, reason="The source establishes this occurrence date.", **extra):
    return {"value": value, "evidence_source_contents": [quote], "reasons": [reason], **extra}


class EventAdditionsTemporalTests(unittest.TestCase):
    def merge(self, quote, time, *, base=None, kind="action"):
        self.base = package() if base is None else base
        proposal = empty_additions()
        row = activity(quote=quote, kind=kind)
        row.update(time=time, event_reason="This is the earlier financing step of the existing investment.")
        proposal["activities"] = [row]
        self.proposal = proposal
        self.sources = [{"document_id": "EF_DOC_1", "content": quote,
                         "published_at": "2025-01-01T00:00:00Z"}]
        return merge_event_additions(self.base, "event", proposal, self.sources)

    def assert_valid_addition(self, result, report):
        self.assertEqual(report["status"], "merged", report)
        self.assertTrue(validate_person_epg(result)["valid"])
        for key, value in self.base.items():
            self.assertEqual(result[key][:len(value)] if isinstance(value, list) else result[key], value)
        docs = {row["document_id"]: row["content"] for row in result["source_document"]}
        for span in result["evidence_span"]:
            self.assertEqual(docs[span["document_id"]][span["char_start"]:span["char_end"]], span["quote"])

    def test_legacy_iso_date_accepts_equivalent_chinese_and_english_source_dates(self):
        for source in ("2023年4月11日", "April 11, 2023", "11 Apr 2023"):
            with self.subTest(source=source):
                result, report = self.merge(source + ": Investor placed the order.", "2023-04-11")
                self.assert_valid_addition(result, report)
                self.assertEqual(result["time_value"][-1]["value"], "2023-04-11")

    def test_legacy_month_preserves_precision_without_inventing_day(self):
        result, report = self.merge("Investor placed the order in April 2023.", "2023-04")
        self.assert_valid_addition(result, report)
        self.assertEqual(result["time_value"][-1]["value"], "2023-04")

    def test_legacy_date_must_not_match_a_numeric_prefix(self):
        result, report = self.merge("On 2023-04-11 Investor placed the order.", "2023-04-1")
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(result, self.base)

    def test_native_empty_reasons_and_unknown_evidence_remain_compatible(self):
        quote = "On April 11, 2023 Investor placed the order."
        for value, excerpts in [("2023-04-11", [quote]), ("unknown", [])]:
            with self.subTest(value=value):
                result, report = self.merge(quote, {"value": value, "evidence_source_contents": excerpts, "reasons": []})
                self.assert_valid_addition(result, report)

    def test_semantic_reviewer_decides_whether_a_conversion_explanation_is_sufficient(self):
        quote = "The purchase occurred on Christmas Day 2022."
        result, report = self.merge(quote, {"value": "2022-12-25", "evidence_source_contents": [quote], "reasons": []})
        self.assert_valid_addition(result, report)
        self.assertFalse(report["semantic_improvement_verified"])

    def test_structured_calendar_conversion_keeps_reason_and_original_quote(self):
        quote = "The purchase occurred on Christmas Day 2022."
        reason = "Christmas Day in the stated Gregorian calendar is December 25; the source supplies 2022."
        for kind in ("action", "transaction", "context"):
            with self.subTest(kind=kind):
                result, report = self.merge(quote, time_field("2022-12-25", quote, reason), kind=kind)
                self.assert_valid_addition(result, report)
                self.assertEqual(result["time_value"][-1]["value"], "2022-12-25")
                metadata = [row.get("field_metadata", {}) for row in result["evidence_set"]]
                self.assertTrue(any(reason in row.get("/timestamp", {}).get("reasons", []) for row in metadata))
                self.assertTrue(any("/subject_relevance" in row for row in metadata))

    def test_relative_time_uses_visible_anchor_and_explanation(self):
        quote = "Investor signed on April 11, 2019. Two days later the purchase closed."
        result, report = self.merge(quote, time_field("2019-04-13", quote,
            "Two elapsed calendar days after the source's April 11, 2019 signing anchor."))
        self.assert_valid_addition(result, report)
        self.assertEqual(result["time_value"][-1]["value"], "2019-04-13")

    def test_imprecise_windows_and_unknown_scalar_survive_canonical_output(self):
        examples = [
            ("2022年7月下旬", "2022-07", "2022-07-21", "2022-07-31"),
            ("calendar Q3 2022", "unknown", "2022-07-01", "2022-09-30"),
            ("Spring 2022 in the northern meteorological convention", "2022", "2022-03-01", "2022-05-31"),
        ]
        for expression, value, start, end in examples:
            with self.subTest(expression=expression):
                quote = expression + ": Investor purchased shares."
                window = {"start": start, "end": end, "original": expression, "approximate": True}
                result, report = self.merge(quote, time_field(value, quote,
                    "The named period gives occurrence bounds, not continuous execution.", time_window=window))
                self.assert_valid_addition(result, report)
                saved = result["time_value"][-1]
                self.assertEqual(saved["value"], value)
                self.assertEqual((saved["window_start"], saved["window_end"]), (start, end))
                self.assertEqual(saved["original_text"], expression)
                self.assertTrue(saved["is_approximate"])
                self.assertEqual(saved["window_semantics"], "uncertainty")

    def test_known_duration_is_distinct_from_uncertain_occurrence(self):
        quote = "Investor negotiated continuously from April 1 to April 30, 2023."
        window = {"start": "2023-04-01", "end": "2023-04-30", "original": "from April 1 to April 30, 2023", "approximate": False}
        result, report = self.merge(quote, time_field("2023-04", quote, time_window=window, window_semantics="duration"))
        self.assert_valid_addition(result, report)
        self.assertEqual(result["time_value"][-1]["window_semantics"], "duration")

    def test_new_date_outside_initial_activity_dates_does_not_block_membership(self):
        base = package()
        base["time_value"] = [{"time_id": "old_time", "value": "2022"}]
        base["action"][0]["timestamp_time_id"] = "old_time"
        quote = "In 2019 Investor arranged the first financing of this investment."
        result, report = self.merge(quote, time_field("2019", quote), base=base)
        self.assert_valid_addition(result, report)
        self.assertEqual(result["event_activity"][-1]["event_id"], "event")
        self.assertEqual(result["time_value"][-1]["value"], "2019")

    def test_missing_date_stays_unknown_despite_publication_metadata(self):
        quote = "Investor purchased shares; the report does not state when."
        result, report = self.merge(quote, time_field("unknown", quote, "The source supplies no occurrence date."))
        self.assert_valid_addition(result, report)
        self.assertEqual(result["time_value"][-1]["value"], "unknown")
        self.assertNotIn("window_start", result["time_value"][-1])

    def test_invalid_or_unlocated_temporal_fields_are_rejected_atomically(self):
        quote = "During calendar Q3 2022 Investor purchased shares."
        valid = time_field("unknown", quote, time_window={"start": "2022-07-01", "end": "2022-09-30", "original": "calendar Q3 2022", "approximate": True})
        bad = []
        for key, value in [("value", "2022-02-30"), ("reasons", [" "]), ("evidence_source_contents", ["Invented anchor"]), ("value", "2021")]:
            field = copy.deepcopy(valid)
            field[key] = value
            bad.append(field)
        for key, value in [("start", "2022-10-01"), ("end", "2022-09-31"), ("original", "Q2 2022"), ("approximate", False)]:
            field = copy.deepcopy(valid)
            field["time_window"][key] = value
            bad.append(field)
        for field in bad:
            with self.subTest(field=field):
                result, report = self.merge(quote, field)
                self.assertEqual(report["status"], "rejected", report)
                self.assertEqual(result, self.base)

    def test_distinct_windows_are_not_collapsed_and_exact_rerun_is_idempotent(self):
        quote = "Investor purchased shares in calendar Q2 2022 and again in calendar Q3 2022."
        first = time_field("2022", quote, time_window={"start": "2022-04-01", "end": "2022-06-30", "original": "calendar Q2 2022", "approximate": True})
        second = time_field("2022", quote, time_window={"start": "2022-07-01", "end": "2022-09-30", "original": "calendar Q3 2022", "approximate": True})
        once, report = self.merge(quote, first)
        self.assert_valid_addition(once, report)
        twice, report = self.merge(quote, second, base=once)
        self.assert_valid_addition(twice, report)
        self.assertEqual(len(twice["activity"]), 3)
        repeated, report = merge_event_additions(twice, "event", self.proposal, self.sources)
        self.assertEqual(report["status"], "no_changes", report)
        self.assertEqual(repeated, twice)


if __name__ == "__main__":
    unittest.main()
