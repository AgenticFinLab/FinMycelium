"""Offline source anchoring and diagnostic boundaries; no provider calls."""

import copy
import hashlib
import json
from pathlib import Path
import unittest
import yaml

from finmy.builder.sparse_build.grounding import (
    SourceIndex, grounded_evidence_report, normalize_whitespace, quality_review_report,
)
from finmy.builder.sparse_build.validation import evidence_report
from finmy.generic import DataSample, UserQueryInput
from test_sparse_role_contracts import cascade, vf
import test_sparse_runtime_entry as runtime_tests
from test_sparse_inference_accounting import response


def sample(text, identifier="s1"):
    return DataSample(sample_id=identifier, raw_data_id="raw-" + identifier, content=text)


def field(value, *quotes):
    return {**vf(value), "evidence_source_contents": list(quotes)}


class GroundingTest(unittest.TestCase):
    def test_unicode_offsets_recover_unchanged_text(self):
        text = "前言\nAlpha\t \nBeta\u00a0paid."
        anchor = SourceIndex([sample(text)]).locate("Alpha Beta paid.")[0]
        self.assertEqual(anchor["method"], "whitespace")
        self.assertEqual(text[anchor["start"]:anchor["end"]], anchor["source_text"])
        self.assertEqual(normalize_whitespace(anchor["source_text"])[0], "Alpha Beta paid.")
        self.assertEqual(anchor["source_sha256"], hashlib.sha256(text.encode()).hexdigest())

    def test_exact_and_multiple_locations_retained(self):
        anchors = SourceIndex([sample("Paid. Paid."), sample("Paid.", "s2")]).locate("Paid.")
        self.assertEqual([(a["sample_id"], a["start"], a["end"]) for a in anchors],
                         [("s1", 0, 5), ("s1", 6, 11), ("s2", 0, 5)])
        self.assertTrue(all(a["method"] == "exact" for a in anchors))

    def test_same_quote_in_exact_and_whitespace_sources(self):
        anchors = SourceIndex([sample("A B"), sample("A\nB", "s2")]).locate("A B")
        self.assertEqual([a["method"] for a in anchors], ["exact", "whitespace"])

    def test_empty_and_paraphrased_quotes_rejected(self):
        index = SourceIndex([sample("Company agreed to pay $3m. It did not pay yet.")])
        for quote in ("", " \n", "Company paid $3m.", "Company...$3m.", "company agreed to pay $3m."):
            with self.subTest(quote=quote):
                self.assertEqual(index.locate(quote), [])

    def test_normalization_does_not_join_words(self):
        self.assertEqual(SourceIndex([sample("A B")]).locate("AB"), [])
        self.assertEqual(SourceIndex([sample("AB")]).locate("A B"), [])

    def test_query_metadata_is_not_evidence(self):
        query = UserQueryInput(query_text="Synthetic event", key_words=["Acme", "default"])
        graph = {"title": field("Synthetic event", "Synthetic event"),
                 "type": field("default", "Acme, default")}
        report = grounded_evidence_report(graph, [sample("Source content.")], query)
        self.assertEqual(report["match_counts"]["query_metadata_not_source"], 2)
        self.assertEqual(report["unmatched_quote_count"], 2)
        self.assertEqual(report["query_metadata"]["query_text"], "Synthetic event")
        self.assertFalse(any(link["anchors"] for link in report["links"]))

    def test_metadata_text_can_also_be_real_source_quote(self):
        report = grounded_evidence_report({"title": field("Acme", "Acme")}, [sample("Acme")],
                                          UserQueryInput(query_text="Acme"))
        self.assertEqual(report["match_counts"]["exact"], 1)
        self.assertEqual(report["match_counts"]["query_metadata_not_source"], 0)

    def test_missing_quotes_are_separate_not_fabricated(self):
        report = grounded_evidence_report({"title": vf("A")}, [sample("A")])
        self.assertEqual(report["fields_without_quotes"], ["event.title"])
        self.assertEqual(report["quote_count"], 0)
        self.assertEqual(report["unmatched_quote_count"], 0)
        self.assertFalse(report["semantic_support_checked"])

    def test_no_mutation_and_legacy_exact_checker_unchanged(self):
        graph = {"title": field("A B", "A B")}
        original = copy.deepcopy(graph)
        sources = [sample("A\nB")]
        self.assertEqual(evidence_report(graph, sources)["unmatched_quote_count"], 1)
        self.assertEqual(grounded_evidence_report(graph, sources)["unmatched_quote_count"], 0)
        self.assertEqual(graph, original)
        self.assertEqual(sources[0].content, "A\nB")

    def review(self, graph, text):
        sources = [sample(text)]
        return quality_review_report(graph, sources, grounded_evidence_report(graph, sources))

    def test_inferred_day_is_flagged_despite_located_quote(self):
        text = "On May 14, 2020, staff discovered the attack."
        report = self.review({"end_time": field("2020-05-13", text)}, text)
        self.assertIn("precise_date_not_located_in_attached_quotes", [x["kind"] for x in report["issues"]])

    def test_same_date_different_format_located(self):
        text = "On May 14, 2020, staff discovered the attack."
        report = self.review({"start_time": field("2020-05-14", text)}, text)
        self.assertFalse(report["issues"])
        self.assertEqual(report["status"], "needs_review")

    def test_document_date_flagged(self):
        text = "Prepared/Updated 2024-08-23."
        report = self.review({"start_time": field("2024-08-23", text)}, text)
        self.assertIn("document_or_projected_date_check", [x["kind"] for x in report["issues"]])

    def test_unknown_and_coarse_dates_not_made_precise(self):
        report = self.review({"start_time": vf("unknown"), "end_time": vf("2020-02")}, "February 2020")
        self.assertFalse(report["issues"])
        report = self.review({"end_time": vf("sometime later")}, "Later")
        self.assertEqual(report["issues"][0]["kind"], "unparsed_date")

    def test_approval_not_certified_as_payment(self):
        graph = cascade()
        quote = "The board approved assistance that will enable an immediate disbursement."
        graph["stages"][0]["episodes"][0]["transactions"] = [{"name": field("Disbursement", quote)}]
        report = self.review(graph, quote)
        self.assertIn("transfer_state_requires_review", [x["kind"] for x in report["issues"]])
        self.assertEqual(len(graph["stages"][0]["episodes"][0]["transactions"]), 1)

    def test_action_paid_vs_agreed_flagged(self):
        graph = cascade()
        quote = "The company agreed to pay a penalty."
        graph["stages"][0]["episodes"][0]["participants"][0]["actions"] = [
            {"name": field("Paid penalty", quote)}]
        report = self.review(graph, quote)
        self.assertIn("action_execution_vs_conditional_evidence", [x["kind"] for x in report["issues"]])

    def test_ungrounded_transfer_flagged(self):
        graph = cascade()
        graph["stages"][0]["episodes"][0]["transactions"] = [{"name": vf("Transfer")}]
        report = self.review(graph, "No evidence here.")
        self.assertIn("transfer_without_located_evidence", [x["kind"] for x in report["issues"]])

    def test_endpoint_applicability_needs_review_not_automatic_rewrite(self):
        graph = cascade()
        ep = graph["stages"][0]["episodes"][0]
        ep["participants"].append({"participant_id": "P_2", "name": vf("Official committee")})
        quote = "Local service defaulted on privately held bonds."
        ep["participant_relations"] = [{"from_participant_id": "P_1", "to_participant_id": "P_2",
                                         "relation_name": field("debtor", quote)}]
        before = copy.deepcopy(graph)
        report = self.review(graph, quote)
        issue = next(i for i in report["issues"] if i["kind"] == "relation_endpoint_name_not_in_attached_quotes")
        self.assertEqual(issue["participant_ids"], ["P_2"])
        self.assertEqual(before, graph)

    def test_source_units_are_not_claimed_as_fact_coverage(self):
        report = self.review({"title": field("Alpha", "Alpha")}, "Alpha happened.\n\nOther information.")
        self.assertEqual(report["uncited_source_units"], 1)
        self.assertEqual(len(report["source_units"]), 2)
        self.assertFalse(report["semantic_support_checked"])
        self.assertTrue(report["limitations"])

    def test_empty_sources_and_determinism(self):
        graph = {"title": field("A", " ")}
        first = grounded_evidence_report(graph, [sample("")])
        second = grounded_evidence_report(graph, [sample("")])
        self.assertEqual(first, second)
        self.assertEqual(first["unmatched_quote_count"], 1)


class GroundingIntegrationTest(unittest.TestCase):
    setUp = runtime_tests.SparseRuntimeEntryTest.setUp
    builder = runtime_tests.SparseRuntimeEntryTest.builder

    def test_v3_candidate_saved_on_strict_failure(self):
        self.builder_config["sparse_builder_config"]["evidence_policy"] = "strict"
        values = runtime_tests.responses()
        values[1]["title"]["evidence_source_contents"] = ["Invented source sentence."]
        self.create.side_effect = [response(content=json.dumps(x)) for x in values]
        builder = self.builder()
        with self.assertRaisesRegex(ValueError, "quotes absent"):
            builder.run(self.inputs)
        root = Path(builder.save_dir)
        self.assertTrue((root / "CandidateEventCascade.json").exists())
        self.assertFalse((root / "FinalEventCascade.json").exists())
        receipt = json.loads((root / "AcceptanceDecision.json").read_text())
        self.assertEqual(receipt["status"], "quote_gate_blocked")
        self.assertFalse(receipt["semantic_approval"])

    def test_v3_whitespace_only_quote_passes_with_offsets(self):
        self.builder_config["sparse_builder_config"]["evidence_policy"] = "strict"
        for source in self.inputs.samples:
            source.content = source.content.replace("Council warned", "Council\n warned")
        builder = self.builder()
        graph = builder.run(self.inputs).event_cascades
        root = Path(builder.save_dir)
        check = json.loads((root / "EvidenceCheck.json").read_text())
        self.assertEqual(check["match_counts"]["whitespace"], 1)
        self.assertEqual(graph, json.loads((root / "CandidateEventCascade.json").read_text()))
        self.assertEqual(graph, builder.integrate_from_files(strict=True))
        self.assertEqual(json.loads((root / "RunManifest.json").read_text())["evidence_contract_version"], 2)

    def test_default_report_policy_records_unmatched_without_approval(self):
        self.assertEqual(self.builder_config["sparse_builder_config"]["evidence_policy"], "report")
        values = runtime_tests.responses()
        values[1]["title"]["evidence_source_contents"] = ["Invented source sentence."]
        self.create.side_effect = [response(content=json.dumps(x)) for x in values]
        builder = self.builder()
        builder.run(self.inputs)
        root = Path(builder.save_dir)
        receipt = json.loads((root / "AcceptanceDecision.json").read_text())
        self.assertTrue((root / "FinalEventCascade.json").exists())
        self.assertTrue((root / "CandidateEventCascade.json").exists())
        self.assertEqual(self.create.call_count, len(values))
        self.assertFalse(receipt["quote_check_passed"])
        self.assertFalse(receipt["semantic_approval"])

    def test_build_only_example_uses_report_policy(self):
        config_path = Path(__file__).resolve().parents[1] / "configs/build_only_sparse.yml"
        config = yaml.safe_load(config_path.read_text())
        self.assertEqual(config["builder_config"]["sparse_builder_config"]["evidence_policy"], "report")


if __name__ == "__main__":
    unittest.main()
