"""Saved draft migration and no-search recovery lifecycle regressions."""
import copy
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
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
from finmy.builder.sparse_build.person_recovery import (
    PERSON_PIPELINE_VERSION, config_from_checkpoint, load_person_checkpoint, recover_person,
)
from finmy.builder.sparse_build.runtime import digest, summarize_calls
from finmy.builder.sparse_build.contracts import CONSTRUCTION_CONTRACT_VERSION
from finmy.builder.sparse_build.grounding import EVIDENCE_CONTRACT_VERSION
from finmy.builder.sparse_build.person_organization import ORGANIZATION_CONTRACT_VERSION
from finmy.generic import DataSample, UserQueryInput
from test_sparse_person_organization import facts

ROOT = Path(__file__).resolve().parents[1]


class CanonicalRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Search/network forbidden")))
        self.config = yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"]
        self.config["save_folder"] = str(self.root / "output")
        self.package = facts()
        self.config["reconstruction"]["subject"] = {
            "subject_id": self.package["graph"]["subject_entity_id"], "name": "Example person",
            "coverage_start": "2025", "coverage_end": "2025", "scope": "Documented communication"}
        self.config["sparse_builder_config"]["max_calls"] = 2
        self.inputs = BuildInput(UserQueryInput(query_text="Example person 2025", key_words=["Example person"]),
            [DataSample(sample_id="one", raw_data_id="one", content=self.package["source_document"][0]["content"],
                        category="article", knowledge_field="finance")])

    def write(self, root, name, value):
        (root / name).write_text(json.dumps(value), encoding="utf-8")

    def refresh(self, root, manifest):
        manifest["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in root.glob("*.json") if p.name != "RunManifest.json"}
        self.write(root, "RunManifest.json", manifest)

    def source(self, *, status="completed", historical=3):
        root = self.root / "source"
        root.mkdir()
        payload = asdict(self.inputs)
        effective = {key: copy.deepcopy(self.config.get(key)) for key in (
            "lm_type", "lm_name", "generation_config", "sparse_builder_config", "event_builder_config")}
        from finmy.reconstruction_scope import read_reconstruction
        effective["reconstruction"] = read_reconstruction(self.config)
        ledger = [{"agent": "PersonOrganization", "attempt": 1, "elapsed_seconds": 1,
                   "status": "accepted", "save_name": "Previous"} for _ in range(historical)]
        manifest = {"status": status, "builder_type": "SparseRagBuilder",
            "construction_contract_version": CONSTRUCTION_CONTRACT_VERSION,
            "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
            "person_organization_contract_version": ORGANIZATION_CONTRACT_VERSION,
            "organization_execution_version": 5, "effective_config": effective,
            "config_sha256": digest(effective), "input_sha256": digest(payload),
            "usage": summarize_calls(ledger), "code": {"git_commit": "old-snapshot"}}
        self.write(root, "BuildInput.json", payload)
        self.write(root, "FinalPersonEPG.json", self.package)
        self.write(root, "CallLedger.json", ledger)
        self.refresh(root, manifest)
        return root, manifest

    def test_completed_native_draft_needs_no_legacy_cascade_or_search(self):
        root, _ = self.source()
        with patch.object(SparseRagBuilder, "integrate_from_files", side_effect=AssertionError("Legacy replay")):
            checkpoint = load_person_checkpoint(root)
        self.assertEqual(checkpoint.fact_seed, self.package)
        self.assertIsNone(checkpoint.cascade)
        self.assertEqual(len(checkpoint.historical_calls), 3)

    def test_budget_is_per_invocation_and_other_semantics_stay_fixed(self):
        root, _ = self.source(historical=10)
        checkpoint = load_person_checkpoint(root)
        config = config_from_checkpoint(checkpoint, self.config, max_new_calls=4)
        self.assertEqual(config["sparse_builder_config"]["max_calls"], 4)
        self.assertEqual(checkpoint.manifest["effective_config"]["sparse_builder_config"]["max_calls"], 2)
        from finmy.builder.sparse_build.person_recovery import validate_recovery_config
        config["reconstruction"]["subject"]["name"] = "Different person"
        with self.assertRaisesRegex(ValueError, "preserve"):
            validate_recovery_config(checkpoint, config)

    def test_artifact_and_source_integrity_are_checked(self):
        root, manifest = self.source()
        changed = copy.deepcopy(self.package)
        changed["source_document"][0]["content"] += "changed"
        self.write(root, "FinalPersonEPG.json", changed)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_person_checkpoint(root)
        self.refresh(root, manifest)
        with self.assertRaisesRegex(ValueError, "sources differ"):
            load_person_checkpoint(root)

    def test_matching_canonical_checkpoint_reuses_completed_phase(self):
        root, manifest = self.source()
        from finmy.builder.sparse_build.person_fact_pipeline import canonical_input_hash
        from finmy.reconstruction_scope import read_reconstruction
        subject = read_reconstruction(self.config)["subject"]
        audit = {"version": PERSON_PIPELINE_VERSION, "status": "completed", "phase": "completed",
                 "input_sha256": canonical_input_hash(self.inputs, subject),
                 "package_sha256": digest(self.package)}
        self.write(root, "PersonCanonicalFacts.json", self.package)
        self.write(root, "PersonCanonicalAudit.json", audit)
        self.refresh(root, manifest)
        checkpoint = load_person_checkpoint(root)
        self.assertEqual(checkpoint.canonical_checkpoint, {"package": self.package, "audit": audit})
        audit["version"] = "obsolete"
        self.write(root, "PersonCanonicalAudit.json", audit)
        self.refresh(root, manifest)
        checkpoint = load_person_checkpoint(root)
        self.assertIsNone(checkpoint.canonical_checkpoint)
        self.assertEqual(checkpoint.fact_seed, self.package)

    def test_no_usable_facts_checkpoint_retains_extraction_retry_state(self):
        root, manifest = self.source(status="failed")
        from finmy.builder.sparse_build.person_fact_pipeline import canonical_input_hash
        from finmy.reconstruction_scope import read_reconstruction
        empty = copy.deepcopy(self.package)
        for table in ("occurrence", "occurrence_participant", "participation", "action", "financial_transaction",
                      "transaction_instrument", "entity_relation", "relation_occurrence", "occurrence_label",
                      "activity", "activity_detail", "domain", "event", "stage", "event_activity",
                      "event_activity_detail", "activity_relation"):
            empty[table] = []
        audit = {"version": PERSON_PIPELINE_VERSION, "status": "no_usable_facts", "phase": "completed",
                 "input_sha256": canonical_input_hash(self.inputs, read_reconstruction(self.config)["subject"]),
                 "package_sha256": digest(empty), "seed_sha256": None,
                 "extraction": [{"document_id": "DOC", "char_start": 0, "status": "unavailable"}]}
        self.write(root, "PersonCanonicalFacts.json", empty)
        self.write(root, "PersonCanonicalAudit.json", audit)
        self.refresh(root, manifest)
        checkpoint = load_person_checkpoint(root)
        self.assertEqual(checkpoint.canonical_checkpoint["audit"]["status"], "no_usable_facts")
        self.assertIsNone(checkpoint.canonical_checkpoint["audit"]["seed_sha256"])
        self.assertEqual(checkpoint.canonical_checkpoint["audit"]["extraction"], audit["extraction"])

    def test_recovery_only_calls_current_person_pipeline_and_keeps_history(self):
        root, _ = self.source(historical=10)
        before = {p.name:p.read_bytes() for p in root.iterdir()}
        checkpoint = load_person_checkpoint(root)
        config = config_from_checkpoint(checkpoint, self.config, max_new_calls=4)
        received = {}
        package = self.package
        destination = self.root / "output" / "build_output_test"
        def initialize(builder, build_config):
            builder.save_dir, builder.build_config = str(destination), build_config
            destination.mkdir(parents=True)
        def complete(builder, inputs, output, subject, **kwargs):
            received.update(kwargs)
            self.assertEqual(builder._prior_call_count, 0)
            self.assertEqual(builder._organization_resume_history, [])
            output.extras["person_epg"] = copy.deepcopy(package)
            builder.save_traces(package, "FinalPersonEPG", "json")
            builder._save_call_ledger()
            return output
        with patch.object(SparseRagBuilder, "__init__", initialize), \
                patch.object(SparseRagBuilder, "_run_validated", side_effect=AssertionError("Extraction repeated")), \
                patch.object(SparseRagBuilder, "execute_agent", side_effect=AssertionError("Old summary repeated")), \
                patch.object(SparseRagBuilder, "_complete_person", complete):
            output = recover_person(config, root, reorganize=True)
        self.assertEqual(received["package"], self.package)
        self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()}, before)
        self.assertEqual(output.extras["usage"]["calls"], 0)
        self.assertEqual(output.extras["recovery"]["prior_call_count"], 10)
        self.assertEqual(output.extras["recovery"]["remaining_calls_at_start"], 4)
        self.assertEqual(output.extras["recovery"]["cumulative_usage"]["calls"], 10)
        # A completed new draft remains a valid next recovery checkpoint.
        recovered = load_person_checkpoint(destination)
        self.assertEqual(len(recovered.historical_calls), 10)

    def test_failed_run_records_specific_error_and_new_directory(self):
        root, _ = self.source()
        config = config_from_checkpoint(load_person_checkpoint(root), self.config)
        destination = self.root / "output" / "build_output_failed"
        def initialize(builder, build_config):
            builder.save_dir, builder.build_config = str(destination), build_config
            destination.mkdir(parents=True)
        with patch.object(SparseRagBuilder, "__init__", initialize), \
                patch.object(SparseRagBuilder, "_complete_person", side_effect=ValueError("Specific normalization error")):
            with self.assertRaises(ValueError) as caught:
                recover_person(config, root)
        self.assertEqual(caught.exception.run_directory, str(destination))
        result = json.loads((destination / "RunManifest.json").read_text())
        self.assertEqual(result["error_message"], "Specific normalization error")
        self.assertEqual(result["status"], "failed")
        checkpoint = load_person_checkpoint(destination)
        self.assertEqual(checkpoint.fact_seed, self.package)


if __name__ == "__main__":
    unittest.main()
