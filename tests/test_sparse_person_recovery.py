"""Offline recovery tests with real extraction checkpoints and sequenced responses."""

import copy
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.base import BuildInput
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput
from test_sparse_person_full_flow import SOURCE, SequencedInference, extraction_responses, organization_plan


ROOT = Path(__file__).resolve().parents[1]


class TruncatedOrganizationInference(SequencedInference):
    """Seven real extraction responses followed by an explicitly incomplete reply."""

    def run(self, infer_input=None, **kwargs):
        output = super().run(infer_input, **kwargs)
        if len(self.calls) == 8:
            output.response = '{"domains": ['
            output.extras["finish_reason"] = "length"
            output.to_dict = lambda: {
                "response": output.response,
                "extras": output.extras,
            }
        return output


class SparsePersonRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.defaults = yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"]
        self.config = copy.deepcopy(self.defaults)
        self.config["save_folder"] = str(self.root / "original")
        self.config["reconstruction"]["subject"] = {
            "subject_id": "person_alpha", "name": "Alpha", "coverage_start": "2025-01-01",
            "coverage_end": "2025-01-02", "scope": "Documented transfer",
        }
        self.config["sparse_builder_config"].update(output_language="English", max_json_attempts=2)
        self.source = SOURCE + " Original source retained. " * 350 + "FINAL_SOURCE_MARKER"
        self.inputs = BuildInput(
            UserQueryInput(query_text="Alpha bitcoin transfer", key_words=["Alpha", "bitcoin"]),
            [DataSample(sample_id="s1", raw_data_id="r1", content=self.source,
                        category="article", knowledge_field="finance")],
        )

    def failed_checkpoint(self, *, max_calls=None):
        if max_calls is not None:
            self.config["sparse_builder_config"]["max_calls"] = max_calls
        sequence = TruncatedOrganizationInference(extraction_responses() + [organization_plan()])
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        def previous_single_call(package, cascade, subject, output_language, infer, save):
            # Reproduce a pre-batching checkpoint: extraction, validation,
            # logging and inference are real, but the old organizer had no
            # fallback after its one incomplete completion. Recovery below
            # uses the new organizer without this patch.
            from finmy.builder.sparse_build.person_organization import (
                ORGANIZATION_SYSTEM_PROMPT, organization_request, validate_organization,
            )
            request = organization_request(package, cascade, subject)
            request["output_language"] = output_language
            return infer(ORGANIZATION_SYSTEM_PROMPT, json.dumps(request, ensure_ascii=False),
                         "PersonOrganization", lambda value: validate_organization(value, package))

        with patch("finmy.builder.sparse_build.organization_batches.organize_person_plan",
                   side_effect=previous_single_call), self.assertRaises(ValueError):
            builder.run(self.inputs)
        source = Path(builder.save_dir)
        self.assertTrue((source / "FinalEventCascade.json").exists())
        self.assertEqual(len(sequence.calls), 8)
        return source

    def read(self, root, name):
        return json.loads((root / f"{name}.json").read_text())

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_recovery_accepts_prior_execution_versions_without_weakening_type_checks(self):
        from finmy.builder.sparse_build.person_recovery import load_person_checkpoint
        from finmy.builder.sparse_build.organization_batches import ORGANIZATION_EXECUTION_VERSION

        source = self.failed_checkpoint()
        manifest = self.read(source, "RunManifest")
        for version in (None, 1, 2, ORGANIZATION_EXECUTION_VERSION):
            with self.subTest(supported=version):
                candidate = copy.deepcopy(manifest)
                if version is None:
                    candidate.pop("organization_execution_version", None)
                else:
                    candidate["organization_execution_version"] = version
                (source / "RunManifest.json").write_text(json.dumps(candidate))
                self.assertEqual(load_person_checkpoint(source).cascade,
                                 self.read(source, "FinalEventCascade"))
        for version in (True, 2.0, 999):
            with self.subTest(unsupported=version):
                candidate = {**manifest, "organization_execution_version": version}
                (source / "RunManifest.json").write_text(json.dumps(candidate))
                with self.assertRaisesRegex(ValueError, "organization execution version"):
                    load_person_checkpoint(source)

    def refresh_hashes(self, root):
        manifest = self.read(root, "RunManifest")
        manifest["artifact_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.json"))
            if p.name not in {"RunManifest.json", "GanttStatus.json"}
        }
        (root / "RunManifest.json").write_text(json.dumps(manifest))

    def recovery_config(self, source, *, output_root=None):
        from finmy.builder.sparse_build.person_recovery import config_from_checkpoint, load_person_checkpoint
        return config_from_checkpoint(load_person_checkpoint(source), self.defaults,
                                      output_root=str(output_root or self.root / "recovered"))

    def test_recovery_only_organizes_and_preserves_source_and_original_run(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        before = self.snapshot(source)
        config = self.recovery_config(source)
        sequence = SequencedInference([organization_plan()])
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence), \
                patch.object(SparseRagBuilder, "_run_validated", side_effect=AssertionError("Do not repeat extraction")):
            output = recover_person(config, source)
        target = Path(output.extras["run_directory"])
        self.assertNotEqual(target, source)
        self.assertEqual(self.snapshot(source), before)
        self.assertEqual(len(sequence.calls), 1)
        self.assertIn(self.source, sequence.calls[0][0].user_msg)
        self.assertEqual(self.read(target, "BuildInput"), self.read(source, "BuildInput"))
        self.assertEqual(self.read(target, "FinalEventCascade"), self.read(source, "FinalEventCascade"))
        self.assertEqual(self.read(target, "OriginalCallLedger"), self.read(source, "CallLedger"))
        ledger = self.read(target, "CallLedger")
        self.assertEqual(len(ledger), 1)
        self.assertTrue(ledger[0]["agent"].startswith("PersonOrganization"))
        manifest = self.read(target, "RunManifest")
        original_manifest = self.read(source, "RunManifest")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["usage"]["calls"], 1)
        self.assertEqual(manifest["recovery"]["prior_call_count"], 8)
        self.assertEqual(manifest["recovery"]["historical_usage"]["calls"], 8)
        self.assertEqual(manifest["recovery"]["cumulative_usage"]["calls"], 9)
        self.assertEqual(manifest["recovery"]["source_usage"], original_manifest["usage"])
        self.assertEqual(manifest["recovery"]["source_manifest_sha256"],
                         hashlib.sha256(before["RunManifest.json"]).hexdigest())
        self.assertEqual(manifest["effective_config"]["reconstruction"],
                         original_manifest["effective_config"]["reconstruction"])
        self.assertEqual(manifest["effective_config"]["sparse_builder_config"]["output_language"], "English")
        replay = SparseRagBuilder.__new__(SparseRagBuilder)
        replay.save_dir = str(target)
        replay.build_config = {}
        with patch.object(sequence, "run", side_effect=AssertionError("Replay must be offline")):
            self.assertEqual(replay.integrate_person_from_files(strict=True), output.extras["person_epg"])

    def test_hash_tampering_is_rejected_before_api_construction(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        config = self.recovery_config(source)
        (source / "FinalEventCascade.json").write_text('{"tampered":true}')
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            with self.assertRaises(ValueError):
                recover_person(config, source)
            api.assert_not_called()

    def test_missing_extraction_result_is_rejected_even_with_updated_hashes(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        config = self.recovery_config(source)
        next(source.glob("EpisodeReconstructor-*-Result.json")).unlink()
        self.refresh_hashes(source)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            with self.assertRaises((ValueError, FileNotFoundError)):
                recover_person(config, source)
            api.assert_not_called()

    def test_recomputed_evidence_report_rejects_rehashed_forgery(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        config = self.recovery_config(source)
        report = self.read(source, "EvidenceCheck")
        report["unmatched_quote_count"] += 1
        (source / "EvidenceCheck.json").write_text(json.dumps(report))
        self.refresh_hashes(source)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            with self.assertRaises(ValueError):
                recover_person(config, source)
            api.assert_not_called()

    def test_semantic_configuration_changes_are_rejected_before_api(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        original = self.recovery_config(source)
        changes = (
            ("subject", lambda c: c["reconstruction"]["subject"].update(name="Another person")),
            ("language", lambda c: c["sparse_builder_config"].update(output_language="Chinese")),
            ("policy", lambda c: c["sparse_builder_config"].update(evidence_policy="strict")),
            ("budget", lambda c: c["sparse_builder_config"].update(max_calls=301)),
            ("model", lambda c: c.update(lm_name="deepseek/another-model")),
            ("generation", lambda c: c["generation_config"].update(temperature=0.8)),
        )
        for label, change in changes:
            with self.subTest(field=label):
                config = copy.deepcopy(original)
                change(config)
                with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
                    with self.assertRaises(ValueError):
                        recover_person(config, source)
                    api.assert_not_called()

    def test_input_and_config_digests_are_checked_independently_of_artifact_hashes(self):
        from finmy.builder.sparse_build.person_recovery import load_person_checkpoint
        source = self.failed_checkpoint()
        manifest_path = source / "RunManifest.json"
        original = manifest_path.read_bytes()
        for field in ("input_sha256", "config_sha256"):
            with self.subTest(field=field):
                manifest = json.loads(original)
                manifest[field] = "0" * 64
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    load_person_checkpoint(source)
        manifest_path.write_bytes(original)

    def test_failed_recovery_retains_new_trace_without_final_person(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        before = self.snapshot(source)
        config = self.recovery_config(source)
        sequence = SequencedInference([TimeoutError("Synthetic recovery timeout")])
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            with self.assertRaises(TimeoutError):
                recover_person(config, source)
        targets = list((self.root / "recovered").glob("build_output_*"))
        self.assertEqual(len(targets), 1)
        target = targets[0]
        self.assertEqual(self.snapshot(source), before)
        self.assertEqual(self.read(target, "RunManifest")["status"], "failed")
        self.assertEqual(len(self.read(target, "CallLedger")), 1)
        self.assertFalse((target / "FinalPersonEPG.json").exists())
        self.assertFalse((target / "FinalSubjectGraph.json").exists())

    def test_recovery_preserves_strict_quote_gate(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        self.config["sparse_builder_config"]["evidence_policy"] = "strict"
        source = self.failed_checkpoint()
        config = self.recovery_config(source)
        sequence = SequencedInference([organization_plan("This quotation is absent from the source.")])
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            with self.assertRaisesRegex(ValueError, "Person EPG contains quotes"):
                recover_person(config, source)
        target = next((self.root / "recovered").glob("build_output_*"))
        acceptance = self.read(target, "PersonAcceptance")
        self.assertEqual(acceptance["policy"], "strict")
        self.assertFalse(acceptance["final_artifact_allowed"])
        self.assertTrue((target / "CandidatePersonEPG.json").exists())
        self.assertFalse((target / "FinalPersonEPG.json").exists())
        self.assertEqual(self.read(target, "RunManifest")["status"], "failed")

    def test_source_acceptance_cannot_be_forged_by_refreshing_hashes(self):
        from finmy.builder.sparse_build.person_recovery import load_person_checkpoint
        source = self.failed_checkpoint()
        acceptance = self.read(source, "AcceptanceDecision")
        acceptance["semantic_approval"] = True
        (source / "AcceptanceDecision.json").write_text(json.dumps(acceptance))
        self.refresh_hashes(source)
        with self.assertRaisesRegex(ValueError, "acceptance"):
            load_person_checkpoint(source)

    def test_historical_calls_exhaust_original_budget_before_api(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint(max_calls=8)
        # Derive the unchanged config directly: preflight may itself reject an
        # exhausted checkpoint, but execution must never initialize a transport.
        config = copy.deepcopy(self.config)
        config["save_folder"] = str(self.root / "recovered")
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            with self.assertRaises((ValueError, RuntimeError)):
                recover_person(config, source)
            api.assert_not_called()

    def test_retry_cannot_spend_more_than_remaining_original_budget(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint(max_calls=9)
        config = self.recovery_config(source)
        sequence = SequencedInference([{}, organization_plan()])
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            with self.assertRaisesRegex(RuntimeError, "call limit"):
                recover_person(config, source)
        self.assertEqual(len(sequence.calls), 1)
        target = next((self.root / "recovered").glob("build_output_*"))
        manifest = self.read(target, "RunManifest")
        self.assertEqual(manifest["recovery"]["remaining_calls_at_start"], 1)
        self.assertEqual(manifest["recovery"]["cumulative_usage"]["calls"], 9)
        self.assertEqual(manifest["status"], "failed")
        self.assertFalse((target / "FinalPersonEPG.json").exists())

    def test_chained_recovery_keeps_all_historical_calls(self):
        from finmy.builder.sparse_build.person_recovery import recover_person
        source = self.failed_checkpoint()
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference",
                   return_value=SequencedInference([TimeoutError("First recovery timeout")])):
            with self.assertRaises(TimeoutError):
                recover_person(self.recovery_config(source), source)
        first = next((self.root / "recovered").glob("build_output_*"))
        before = self.snapshot(first)
        sequence = SequencedInference([organization_plan()])
        config = self.recovery_config(first, output_root=self.root / "recovered_twice")
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            output = recover_person(config, first)
        target = Path(output.extras["run_directory"])
        self.assertEqual(self.snapshot(first), before)
        self.assertEqual(len(self.read(target, "OriginalCallLedger")), 9)
        self.assertEqual(len(self.read(target, "CallLedger")), 1)
        self.assertEqual(self.read(target, "RunManifest")["recovery"]["cumulative_usage"]["calls"], 10)

    def test_cli_without_execute_only_preflights_and_preserves_person_configuration(self):
        from finmy.runner.sparse_person_recovery import main
        source = self.failed_checkpoint()
        before = self.snapshot(source)
        output = io.StringIO()
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api, redirect_stdout(output):
            self.assertEqual(main(["--source-run", str(source), "--output-root", str(self.root / "cli"),
                                   "--config", str(ROOT / "configs/person_sparse.yml")]), 0)
            api.assert_not_called()
        self.assertEqual(self.snapshot(source), before)
        self.assertFalse((self.root / "cli").exists())
        report = json.loads(output.getvalue())
        self.assertIn("preflight", report["status"])


if __name__ == "__main__":
    unittest.main()
