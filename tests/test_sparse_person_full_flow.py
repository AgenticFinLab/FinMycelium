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
    """Lifecycle/provenance regressions for the canonical Person entry.

    Historical response factories above remain available to checkpoint import
    tests. Single-event temporal tests explicitly request ``extraction=...``.
    """
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
        from test_person_canonical_full_flow import SOURCE as canonical_source
        self.inputs = BuildInput(UserQueryInput(query_text="Alpha bitcoin transfer", key_words=["Alpha", "bitcoin"]),
            [DataSample(sample_id="s1", raw_data_id="r1", content=SOURCE + "\n" + canonical_source,
                        category="article", knowledge_field="finance")])

    def builder(self, organization=None, *, extraction=None):
        from test_person_canonical_full_flow import CanonicalFixtureInference
        config = copy.deepcopy(self.config)
        if extraction is None:
            if organization is not None:
                raise ValueError("Use phase-aware canonical responses, not the removed monolithic organization response")
            sequence = CanonicalFixtureInference()
        else:
            # This exercises the retained Event builder, not a legacy Person switch.
            config["reconstruction"] = {"mode": "event"}
            sequence = SequencedInference(extraction)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            builder = SparseRagBuilder(build_config=config)
        return builder, sequence

    def artifact(self, builder, name):
        return json.loads(Path(builder.save_dir, name + ".json").read_text())

    def assert_failed(self, builder, calls):
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["usage"]["calls"], calls)
        self.assertFalse(Path(builder.save_dir, "FinalPersonEPG.json").exists())
        self.assertFalse(Path(builder.save_dir, "FinalSubjectGraph.json").exists())

    def test_person_ledger_accounts_for_canonical_phases_and_attribution(self):
        builder, sequence = self.builder()
        output = builder.run(self.inputs)
        person = output.extras["person_epg"]
        ledger = self.artifact(builder, "CallLedger")
        self.assertEqual({row["agent"] for row in ledger}, {"PersonFacts", "PersonOrganization", "PersonOverview"})
        self.assertEqual(len(ledger), len(sequence.calls))
        self.assertEqual(output.result["cost"], ledger)
        self.assertEqual(person["action"][0]["actor_id"], "person_alpha")
        self.assertEqual(person["financial_transaction"][0]["to_entity_id"], "beta")
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["usage"]["calls"], len(sequence.calls))
        self.assertEqual(manifest["person_pipeline_version"], "canonical-person-v1")
        self.assertEqual(output.extras["usage"], manifest["usage"])
        self.assertTrue(output.extras["person_acceptance"]["quote_check_passed"])
        self.assertFalse(output.extras["person_acceptance"]["semantic_approval"])
        self.assertEqual(json.loads(EmbeddedPersonData(Path(builder.save_dir, "FinalPersonEPG.html").read_text()).payload), person)

    def test_storyline_hints_remain_metadata_and_reach_new_fact_and_organization_phases(self):
        discovery = {"version": "person-storylines-v1", "candidate_only": True,
            "domains": [{"domain_id": "D1", "label": "Financial activities"}],
            "events": [{"event_id": "EVENT_TRANSFER", "domain_id": "D1",
                        "label": "Transfer involvement", "summary": "CANDIDATE_ONLY_SCOPE"}]}
        self.inputs.user_query.extras = {"storyline_plan": discovery}
        builder, sequence = self.builder()
        output = builder.run(self.inputs)
        first = sequence.calls[0][1]
        self.assertEqual(first["event_plan"], discovery)
        self.assertNotIn("CANDIDATE_ONLY_SCOPE", json.dumps(output.extras["person_epg"]))
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])

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
        builder, _ = self.builder()
        builder.run(self.inputs)
        path = Path(builder.save_dir, "PersonOrganization-Result.json")
        plan = self.artifact(builder, "PersonOrganization-Result")
        plan["events"][0]["label"] = "Tampered label"
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, "changed|hash mismatch"):
            builder.integrate_person_from_files(strict=True)

    def test_strict_replay_recomputes_organization_report_after_rehashed_tampering(self):
        builder, _ = self.builder()
        builder.run(self.inputs)
        path = Path(builder.save_dir, "PersonOrganizationReport.json")
        report = self.artifact(builder, "PersonOrganizationReport")
        report["tampered"] = True
        path.write_text(json.dumps(report))
        manifest = self.artifact(builder, "RunManifest")
        manifest["artifact_sha256"] = builder._artifact_hashes()
        Path(builder.save_dir, "RunManifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "PersonOrganizationReport does not match"):
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

    def test_person_accepts_empty_roles_but_keeps_explicit_option_precedence(self):
        self.config["agents"] = {}
        self.config["sparse_builder_config"] = {}
        self.config["event_builder_config"] = {"evidence_policy": "invalid-policy", "max_calls": 1}
        builder, _ = self.builder()
        output = builder.run(self.inputs)
        self.assertEqual(output.extras["person_acceptance"]["policy"], "report")
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])

    def test_renderer_failure_is_recorded_without_discarding_completed_data(self):
        builder, _ = self.builder()
        with patch("finmy.person_epg.visualizer.render_person_epg", side_effect=RuntimeError("Synthetic render failure")):
            output = builder.run(self.inputs)
        self.assertEqual(self.artifact(builder, "PersonRenderStatus"), {"status": "failed", "error_type": "RuntimeError"})
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "completed")
        self.assertEqual(self.artifact(builder, "FinalPersonEPG"), output.extras["person_epg"])
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])


if __name__ == "__main__":
    unittest.main()
