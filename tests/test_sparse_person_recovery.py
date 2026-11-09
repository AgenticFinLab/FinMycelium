"""Old extraction checkpoints remain importable by the canonical person path.

These fixtures run the old extraction state machine directly. New person runs
must not recreate that state machine merely to satisfy a legacy replay test.
"""
import copy
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
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
from finmy.builder.sparse_build.contracts import CONSTRUCTION_CONTRACT_VERSION
from finmy.builder.sparse_build.grounding import EVIDENCE_CONTRACT_VERSION
from finmy.builder.sparse_build.person_organization import ORGANIZATION_CONTRACT_VERSION
from finmy.builder.sparse_build.person_recovery import (
    _effective_config, config_from_checkpoint, load_person_checkpoint, recover_person,
)
from finmy.builder.sparse_build.runtime import digest, summarize_calls
from finmy.generic import DataSample, UserQueryInput
from test_sparse_person_full_flow import SOURCE, SequencedInference, extraction_responses

ROOT = Path(__file__).resolve().parents[1]


class SparsePersonRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.defaults = yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"]
        self.config = copy.deepcopy(self.defaults)
        self.config["save_folder"] = str(self.root / "original")
        self.config["reconstruction"]["subject"] = {"subject_id": "person_alpha", "name": "Alpha",
            "coverage_start": "2025-01-01", "coverage_end": "2025-01-02", "scope": "Documented transfer"}
        self.config["sparse_builder_config"].update(output_language="English", max_json_attempts=2,
            person_coverage_repair=False, person_fact_repair=False)
        self.source = SOURCE + " Original source retained. " * 350 + "FINAL_SOURCE_MARKER"
        self.inputs = BuildInput(UserQueryInput(query_text="Alpha bitcoin transfer", key_words=["Alpha", "bitcoin"]),
            [DataSample(sample_id="s1", raw_data_id="r1", content=self.source,
                        category="article", knowledge_field="finance")])

    def read(self, root, name):
        return json.loads((root / f"{name}.json").read_text())

    def refresh_hashes(self, root):
        manifest = self.read(root, "RunManifest")
        manifest["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.glob("*.json") if p.name not in {"RunManifest.json", "GanttStatus.json"}}
        (root / "RunManifest.json").write_text(json.dumps(manifest))

    def failed_checkpoint(self):
        sequence = SequencedInference(extraction_responses())
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=sequence):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        builder._call_records, builder._prior_call_count = [], 0
        builder._temporal_conflicts, builder._organization_validation_errors = [], []
        builder._run_validated(self.inputs)
        effective, payload = _effective_config(self.config), asdict(self.inputs)
        manifest = {"status": "failed", "builder_type": "SparseRagBuilder",
            "construction_contract_version": CONSTRUCTION_CONTRACT_VERSION,
            "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
            "person_organization_contract_version": ORGANIZATION_CONTRACT_VERSION,
            "organization_execution_version": 5, "effective_config": effective,
            "config_sha256": digest(effective), "input_sha256": digest(payload),
            "usage": summarize_calls(builder._call_records), "code": {"git_commit": "old-snapshot"}}
        builder.save_traces(payload, "BuildInput", "json")
        builder.save_traces(manifest, "RunManifest", "json")
        source = Path(builder.save_dir)
        self.refresh_hashes(source)
        self.assertEqual(len(sequence.calls), 7)
        return source

    def test_old_extraction_is_imported_without_opening_api(self):
        source = self.failed_checkpoint()
        before = {p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            checkpoint = load_person_checkpoint(source)
            api.assert_not_called()
        self.assertEqual(checkpoint.cascade, self.read(source, "FinalEventCascade"))
        self.assertEqual(len(checkpoint.fact_seed["activity"]), 3)
        self.assertEqual(checkpoint.fact_seed["source_document"][0]["content"], self.source)
        self.assertEqual({p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}, before)

    def test_missing_overview_uses_completed_episode_facts_without_summary_call(self):
        source = self.failed_checkpoint()
        for name in ("FinalEventCascade", "CandidateEventCascade", "ConstructionCheck", "EvidenceCheck",
                     "QualityReview", "AcceptanceDecision", "EventSummaryStatus",
                     "EventDescriptionReconstructor-1", "EventDescriptionReconstructor-1-Result"):
            (source / f"{name}.json").unlink(missing_ok=True)
        ledger = [r for r in self.read(source, "CallLedger") if r["agent"] != "EventDescriptionReconstructor"]
        (source / "CallLedger.json").write_text(json.dumps(ledger))
        manifest = self.read(source, "RunManifest")
        manifest["usage"] = summarize_calls(ledger)
        (source / "RunManifest.json").write_text(json.dumps(manifest))
        self.refresh_hashes(source)
        with patch.object(SparseRagBuilder, "execute_agent", side_effect=AssertionError("Model call")):
            checkpoint = load_person_checkpoint(source)
        self.assertIsNotNone(checkpoint.extraction_state)
        self.assertEqual(checkpoint.cascade["descriptions"], [])
        self.assertEqual(len(checkpoint.fact_seed["activity"]), 3)

    def test_hash_tampering_and_missing_role_are_rejected_before_api(self):
        source = self.failed_checkpoint()
        original = (source / "FinalEventCascade.json").read_bytes()
        (source / "FinalEventCascade.json").write_text('{"tampered":true}')
        with self.assertRaises(ValueError):
            load_person_checkpoint(source)
        (source / "FinalEventCascade.json").write_bytes(original)
        next(source.glob("EpisodeReconstructor-*-Result.json")).unlink()
        self.refresh_hashes(source)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api:
            with self.assertRaises((ValueError, FileNotFoundError)):
                load_person_checkpoint(source)
            api.assert_not_called()

    def test_rehashed_false_evidence_report_is_rejected(self):
        source = self.failed_checkpoint()
        report = self.read(source, "EvidenceCheck")
        report["unmatched_quote_count"] += 1
        (source / "EvidenceCheck.json").write_text(json.dumps(report))
        self.refresh_hashes(source)
        with self.assertRaisesRegex(ValueError, "EvidenceCheck"):
            load_person_checkpoint(source)

    def test_input_and_config_hashes_are_checked_independently(self):
        source = self.failed_checkpoint()
        original = self.read(source, "RunManifest")
        for field in ("input_sha256", "config_sha256"):
            manifest = copy.deepcopy(original)
            manifest[field] = "0" * 64
            (source / "RunManifest.json").write_text(json.dumps(manifest))
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_person_checkpoint(source)

    def test_prior_versions_are_imported_and_future_or_wrong_types_rejected(self):
        from finmy.builder.sparse_build.organization_batches import ORGANIZATION_EXECUTION_VERSION
        source = self.failed_checkpoint()
        original = self.read(source, "RunManifest")
        for version in (1, 2, 3, 4, 5, ORGANIZATION_EXECUTION_VERSION):
            (source / "RunManifest.json").write_text(json.dumps({**original, "organization_execution_version": version}))
            self.assertEqual(len(load_person_checkpoint(source).fact_seed["activity"]), 3)
        for version in (True, 2.0, 999):
            (source / "RunManifest.json").write_text(json.dumps({**original, "organization_execution_version": version}))
            with self.assertRaisesRegex(ValueError, "organization execution version"):
                load_person_checkpoint(source)

    def test_semantic_config_changes_rejected_but_new_budget_allowed(self):
        source = self.failed_checkpoint()
        checkpoint = load_person_checkpoint(source)
        original = config_from_checkpoint(checkpoint, self.defaults, output_root=self.root / "recovered")
        from finmy.builder.sparse_build.person_recovery import validate_recovery_config
        for key, value in (("output_language", "Chinese"), ("evidence_policy", "strict")):
            config = copy.deepcopy(original)
            config["sparse_builder_config"][key] = value
            with self.assertRaisesRegex(ValueError, "preserve"):
                validate_recovery_config(checkpoint, config)
        changed = config_from_checkpoint(checkpoint, self.defaults, self.root / "recovered", max_new_calls=5)
        self.assertEqual(changed["sparse_builder_config"]["max_calls"], 5)

    def test_cli_preflight_needs_no_credentials_or_model_calls(self):
        from finmy.runner.sparse_person_recovery import main
        source = self.failed_checkpoint()
        output = io.StringIO()
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference") as api, redirect_stdout(output):
            self.assertEqual(main(["--source-run", str(source), "--output-root", str(self.root / "cli"),
                "--config", str(ROOT / "configs/person_sparse.yml"), "--max-new-calls", "8"]), 0)
            api.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["search_calls"], 0)
        self.assertEqual(report["max_new_calls"], 8)
        self.assertEqual(report["prior_calls"], 7)
        self.assertFalse((self.root / "cli").exists())


if __name__ == "__main__":
    unittest.main()
