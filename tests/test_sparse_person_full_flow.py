"""Offline person lifecycle tests using real construction and replay code.

Only model responses are sequenced. These tests do not validate a live provider
or the lmbase transport; missing lmbase receives explicit local container doubles.
"""

import copy
from contextlib import ExitStack
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.base import BuildInput
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput
from finmy.person_epg.validation import validate_person_epg
from test_sparse_rag_builder_full_flow import _skeleton, _vf


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    "On 2025-01-01 Alpha authorized and transferred £23.5 million in bitcoin "
    "to Beta. Beta received the transfer during a laundering investigation."
)
ROLES = ["SkeletonReconstructor", "SkeletonChecker", "ParticipantReconstructor",
         "TransactionReconstructor", "EpisodeReconstructor", "StageDescriptionReconstructor",
         "EventDescriptionReconstructor", "PersonOrganization"]


class EmbeddedPersonData(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.capture = False
        self.payload = ""
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.capture = dict(attrs).get("id") == "epg-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    def handle_data(self, text):
        if self.capture:
            self.payload += text


def cited(value, quote=SOURCE):
    return {"value": value, "evidence_source_contents": [quote],
            "reasons": ["The supplied source describes this documented involvement."]}


def extraction_responses():
    """Reuse the existing one-episode seven-role fixture with explicit actors."""
    skeleton = _skeleton()
    participants = {"participants": [
        {"participant_id": "P_1", "name": _vf("Alpha"), "participant_type": _vf("individual"),
         "attributes": {}, "actions": [{"name": _vf("Authorized transfer"),
             "timestamp": _vf("2025-01-01"), "details": [_vf("Alpha authorized the transfer.")]}]},
        {"participant_id": "P_2", "name": _vf("Beta"), "participant_type": _vf("organization"),
         "attributes": {}, "actions": [{"name": _vf("Received transfer"),
             "timestamp": _vf("2025-01-01"), "details": [_vf("Beta received the transfer.")]}]},
    ]}
    transactions = {"transactions": [{"name": _vf("Bitcoin transfer"),
        "transaction_type": _vf("crypto transfer"), "timestamp": _vf("2025-01-01"),
        "details": [_vf("Alpha transferred £23.5 million in bitcoin to Beta.")],
        "from_participant_id": _vf("P_1"), "to_participant_id": _vf("P_2"), "instruments": []}]}
    episode = {**skeleton["stages"][0]["episodes"][0],
        "participants": "Results of ParticipantReconstructor",
        "transactions": "Results of TransactionReconstructor", "participant_relations": [],
        "descriptions": [_vf("Alpha transferred bitcoin to Beta.")]}
    return [skeleton, copy.deepcopy(skeleton), participants, transactions, episode,
            {"descriptions": [_vf("The stage covers the bitcoin flow.")]},
            {"descriptions": [_vf("The event describes a bitcoin laundering transfer.")]}]


def organization_plan(quote=SOURCE):
    return {
        "domains": [{"domain_id": "D1", "label": "Financial activities"}],
        "events": [{"event_id": "PERSON_E1", "domain_id": "D1", "label": "Transfer involvement",
                    "summary": cited("Alpha authorized the bitcoin transfer.", quote)}],
        "stages": [{"event_id": "PERSON_E1", "stage_id": "PERSON_S1", "label": "Transfer execution",
                    "boundary_reason": cited("The documented transfer and its receipt define this stage.")}],
        "memberships": [{"event_id": "PERSON_E1", "activity_id": activity, "stage_id": "PERSON_S1"}
                        for activity in ("A:ACT_O_S1_E1_P1_1", "A:ACT_O_S1_E1_P2_1", "T:TX_O_S1_E1_1")],
        "occurrence_relevance": [{"occurrence_id": "O_S1_E1",
                                  "subject_relevance": cited("Alpha authorized and made the transfer.")}],
        "background_occurrence_ids": [], "activity_relations": [], "unassigned_reasons": [],
    }


class SequencedInference:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, infer_input=None, **kwargs):
        self.calls.append((infer_input, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected model call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        response = json.dumps(value)
        return SimpleNamespace(response=response,
            cost=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            extras={"finish_reason": "stop", "reasoning_tokens": 2, "cached_tokens": 3},
            to_dict=lambda: {"response": response})


class SparsePersonFullFlowTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.config = yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"]
        self.config["save_folder"] = str(self.root / "runs")
        self.config["reconstruction"]["subject"] = {"subject_id": "person_alpha", "name": "Alpha",
            "coverage_start": "2025-01-01", "coverage_end": "2025-01-02", "scope": "Documented transfer"}
        self.config["sparse_builder_config"].update(output_language="English", max_json_attempts=2)
        self.inputs = BuildInput(UserQueryInput(query_text="Alpha bitcoin transfer", key_words=["Alpha", "bitcoin"]),
            [DataSample(sample_id="s1", raw_data_id="r1", content=SOURCE,
                        category="article", knowledge_field="finance")])

    def builder(self, organization=None, *, extraction=None):
        sequence = SequencedInference((extraction or extraction_responses()) +
                                     ([organization_plan()] if organization is None else organization))
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        return builder, sequence

    def artifact(self, builder, name):
        return json.loads(Path(builder.save_dir, name + ".json").read_text())

    def assert_failed(self, builder, calls):
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["usage"]["calls"], calls)
        self.assertFalse(Path(builder.save_dir, "FinalPersonEPG.json").exists())
        self.assertFalse(Path(builder.save_dir, "FinalSubjectGraph.json").exists())

    def test_person_full_flow_accounts_for_all_eight_calls_and_preserves_attribution(self):
        builder, sequence = self.builder()
        output = builder.run(self.inputs)
        person = output.extras["person_epg"]
        self.assertEqual(validate_person_epg(person), {"valid": True, "errors": []})
        self.assertEqual(output.extras["agent_executed"], ROLES)
        self.assertEqual(output.logs, ROLES)
        self.assertEqual([call["agent"] for call in output.result["cost"]], ROLES)
        self.assertEqual(len(sequence.calls), 8)
        self.assertFalse(sequence.responses)
        self.assertIn(SOURCE, sequence.calls[-1][0].user_msg)
        self.assertIn('"output_language": "English"', sequence.calls[-1][0].user_msg)
        self.assertEqual(len(person["action"]), 2)
        self.assertEqual({row["actor_id"] for row in person["action"]}, {"person_alpha", "entity:P_2"})
        self.assertEqual(len(person["financial_transaction"]), 1)
        self.assertEqual(len(person["event_activity"]), 3)
        self.assertEqual(person["event"][0]["event_id"], "PERSON_E1")
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["person_organization_contract_version"], 1)
        self.assertEqual(manifest["usage"]["calls"], 8)
        self.assertEqual(manifest["usage"]["prompt_tokens"], 80)
        self.assertEqual(manifest["usage"]["completion_tokens"], 40)
        self.assertEqual(manifest["usage"]["by_role"]["PersonOrganization"]["prompt_tokens"], 10)
        self.assertEqual(output.extras["usage"], manifest["usage"])
        self.assertEqual(self.artifact(builder, "FinalPersonEPG"), person)
        self.assertEqual(self.artifact(builder, "FinalSubjectGraph"), output.subject_graph)
        self.assertTrue(output.extras["person_acceptance"]["quote_check_passed"])
        self.assertFalse(output.extras["person_acceptance"]["semantic_approval"])
        self.assertGreater(output.extras["person_acceptance"]["fields_without_quotes"], 0)
        page = Path(builder.save_dir, "FinalPersonEPG.html").read_text(encoding="utf-8")
        self.assertEqual(json.loads(EmbeddedPersonData(page).payload), person)
        self.assertIn("Collapse events", page)
        self.assertEqual(self.artifact(builder, "PersonRenderStatus"), {"status": "completed"})
        self.assertFalse(Path(builder.save_dir, "FinalSubjectGraph.html").exists())

    def test_invalid_organization_retries_in_shared_ledger(self):
        invalid = organization_plan()
        invalid["memberships"][0]["activity_id"] = "INVENTED"
        builder, sequence = self.builder([invalid, organization_plan()])
        output = builder.run(self.inputs)
        self.assertEqual(len(sequence.calls), 9)
        records = self.artifact(builder, "CallLedger")[-2:]
        self.assertEqual([r["status"] for r in records], ["invalid_output", "accepted"])
        self.assertEqual([r["attempt"] for r in records], [1, 2])
        self.assertEqual(output.extras["usage"]["retries"], 1)
        self.assertEqual(output.extras["usage"]["prompt_tokens"], 90)
        self.assertEqual(self.artifact(builder, "PersonOrganization-Result"), organization_plan())
        self.assertTrue(Path(builder.save_dir, "PersonOrganization-Retry1.json").exists())
        self.assertIn("Validation issue:", sequence.calls[-1][0].user_msg)

    def test_invalid_organization_exhaustion_fails_without_final_person(self):
        builder, sequence = self.builder([{}, {}])
        with self.assertRaisesRegex(ValueError, "PersonOrganization returned invalid output after 2"):
            builder.run(self.inputs)
        self.assertEqual(len(sequence.calls), 9)
        self.assert_failed(builder, 9)
        self.assertFalse(Path(builder.save_dir, "PersonOrganization-Result.json").exists())

    def test_organization_timeout_records_failed_call_without_final_person(self):
        builder, sequence = self.builder([TimeoutError("Synthetic organization timeout")])
        with self.assertRaisesRegex(TimeoutError, "organization timeout"):
            builder.run(self.inputs)
        self.assertEqual(len(sequence.calls), 8)
        self.assert_failed(builder, 8)
        record = self.artifact(builder, "CallLedger")[-1]
        self.assertEqual(record["agent"], "PersonOrganization")
        self.assertEqual(record["status"], "transport_error")
        self.assertEqual(record["error_type"], "TimeoutError")
        self.assertIsNone(record["prompt_tokens"])
        self.assertFalse(Path(builder.save_dir, "PersonOrganization-Result.json").exists())

    def test_call_budget_covers_initial_organization_and_retries(self):
        for limit, organization, expected_calls in ((7, [organization_plan()], 7), (8, [{}, organization_plan()], 8)):
            with self.subTest(limit=limit):
                self.config["sparse_builder_config"]["max_calls"] = limit
                builder, sequence = self.builder(organization)
                with self.assertRaisesRegex(RuntimeError, "model call limit"):
                    builder.run(self.inputs)
                self.assertEqual(len(sequence.calls), expected_calls)
                self.assert_failed(builder, expected_calls)

    def test_strict_person_quote_gate_retains_candidate_but_no_final(self):
        self.config["sparse_builder_config"]["evidence_policy"] = "strict"
        builder, _ = self.builder([organization_plan("This quote never occurs in the supplied source.")])
        with self.assertRaisesRegex(ValueError, "Person EPG contains quotes"):
            builder.run(self.inputs)
        self.assert_failed(builder, 8)
        self.assertTrue(Path(builder.save_dir, "CandidatePersonEPG.json").exists())
        self.assertEqual(self.artifact(builder, "PersonEvidenceCheck")["unmatched_quote_count"], 1)
        acceptance = self.artifact(builder, "PersonAcceptance")
        self.assertEqual(acceptance["status"], "quote_gate_blocked")
        self.assertFalse(acceptance["final_artifact_allowed"])

    def test_report_policy_keeps_unmatched_quote_as_reviewable_draft(self):
        builder, _ = self.builder([organization_plan("This quote never occurs in the supplied source.")])
        output = builder.run(self.inputs)
        acceptance = output.extras["person_acceptance"]
        self.assertEqual(acceptance["status"], "draft_requires_content_review")
        self.assertTrue(acceptance["final_artifact_allowed"])
        self.assertFalse(acceptance["quote_check_passed"])
        self.assertFalse(acceptance["semantic_approval"])
        self.assertEqual(acceptance["unmatched_quotes"], 1)
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "completed")

    def test_strict_replay_is_repeatable_and_performs_zero_model_calls(self):
        self.config["sparse_builder_config"]["evidence_policy"] = "strict"
        builder, sequence = self.builder()
        output = builder.run(self.inputs)
        before = builder._artifact_hashes()
        with patch.object(sequence, "run", side_effect=AssertionError("Replay must not call the model")) as run:
            self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])
            self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])
            run.assert_not_called()
        self.assertEqual(builder._artifact_hashes(), before)

    def test_strict_replay_rejects_artifact_tampering(self):
        builder, sequence = self.builder()
        builder.run(self.inputs)
        path = Path(builder.save_dir, "PersonOrganization-Result.json")
        plan = self.artifact(builder, "PersonOrganization-Result")
        plan["events"][0]["label"] = "Tampered label"
        path.write_text(json.dumps(plan))
        with patch.object(sequence, "run", side_effect=AssertionError("Replay must not call the model")):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                builder.integrate_person_from_files(strict=True)

    def test_strict_replay_recomputes_person_reports_even_if_hashes_are_replaced(self):
        builder, _ = self.builder()
        builder.run(self.inputs)
        path = Path(builder.save_dir, "PersonMappingReport.json")
        report = self.artifact(builder, "PersonMappingReport")
        report["tampered"] = True
        path.write_text(json.dumps(report))
        manifest = self.artifact(builder, "RunManifest")
        manifest["artifact_sha256"] = builder._artifact_hashes()
        Path(builder.save_dir, "RunManifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "PersonMappingReport does not match"):
            builder.integrate_person_from_files(strict=True)

    def test_replay_rejects_unknown_organization_version_and_changed_scope(self):
        builder, _ = self.builder()
        builder.run(self.inputs)
        path = Path(builder.save_dir, "RunManifest.json")
        original = self.artifact(builder, "RunManifest")
        for version in (99, True, 1.0):
            with self.subTest(version=version):
                manifest = copy.deepcopy(original)
                manifest["person_organization_contract_version"] = version
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "Unsupported person organization"):
                    builder.integrate_person_from_files(strict=True)
        manifest = copy.deepcopy(original)
        manifest["effective_config"]["reconstruction"]["subject"]["scope"] = "Changed scope"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "configuration hash mismatch"):
            builder.integrate_person_from_files(strict=True)

    def test_explicit_empty_sparse_options_override_invalid_legacy_options(self):
        self.config["sparse_builder_config"] = {}
        self.config["event_builder_config"] = {
            "evidence_policy": "invalid-policy", "max_calls": 1, "max_json_attempts": 0,
        }
        builder, sequence = self.builder([organization_plan("Unmatched organization quote.")])
        output = builder.run(self.inputs)
        self.assertEqual(len(sequence.calls), 8)
        self.assertEqual(output.extras["person_acceptance"]["policy"], "report")
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])

    def test_renderer_failure_is_recorded_without_discarding_completed_data(self):
        builder, _ = self.builder()
        with patch("finmy.person_epg.visualizer.render_person_epg", side_effect=RuntimeError("Synthetic render failure")):
            output = builder.run(self.inputs)
        self.assertEqual(self.artifact(builder, "PersonRenderStatus"),
                         {"status": "failed", "error_type": "RuntimeError"})
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "completed")
        self.assertEqual(self.artifact(builder, "FinalPersonEPG"), output.extras["person_epg"])
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])


if __name__ == "__main__":
    unittest.main()
