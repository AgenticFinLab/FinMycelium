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


    def test_same_quote_in_exact_and_whitespace_sources(self):
        anchors = SourceIndex([sample("A B"), sample("A\nB", "s2")]).locate("A B")
        self.assertEqual([a["method"] for a in anchors], ["exact", "whitespace"])


    def test_query_metadata_is_not_evidence(self):
        query = UserQueryInput(query_text="Synthetic event", key_words=["Acme", "default"])
        graph = {"title": field("Synthetic event", "Synthetic event"),
                 "type": field("default", "Acme, default")}
        report = grounded_evidence_report(graph, [sample("Source content.")], query)
        self.assertEqual(report["match_counts"]["query_metadata_not_source"], 2)
        self.assertEqual(report["unmatched_quote_count"], 2)
        self.assertEqual(report["query_metadata"]["query_text"], "Synthetic event")
        self.assertFalse(any(link["anchors"] for link in report["links"]))


    def review(self, graph, text):
        sources = [sample(text)]
        return quality_review_report(graph, sources, grounded_evidence_report(graph, sources))

    def test_inferred_day_is_flagged_despite_located_quote(self):
        text = "On May 14, 2020, staff discovered the attack."
        report = self.review({"end_time": field("2020-05-13", text)}, text)
        self.assertIn("precise_date_not_located_in_attached_quotes", [x["kind"] for x in report["issues"]])


    def test_approval_not_certified_as_payment(self):
        graph = cascade()
        quote = "The board approved assistance that will enable an immediate disbursement."
        graph["stages"][0]["episodes"][0]["transactions"] = [{"name": field("Disbursement", quote)}]
        report = self.review(graph, quote)
        self.assertIn("transfer_state_requires_review", [x["kind"] for x in report["issues"]])
        self.assertEqual(len(graph["stages"][0]["episodes"][0]["transactions"]), 1)


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


if __name__ == "__main__":
    unittest.main()
