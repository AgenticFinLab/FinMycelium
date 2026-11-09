"""Reorganize saved person facts without repeating search or completed extraction.

A checkpoint is a verified input snapshot, not a promise that its previous
organization was correct. Old cascades are imported into the current person
pipeline; completed native drafts can be reorganized by the same entry point.
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from finmy.builder.base import BuildInput, BuildOutput
from finmy.generic import DataSample, UserQueryInput
from finmy.reconstruction_scope import read_reconstruction

from .contracts import CONSTRUCTION_CONTRACT_VERSION, construction_report
from .grounding import EVIDENCE_CONTRACT_VERSION, grounded_evidence_report, quality_review_report
from .main_build import SparseRagBuilder
from .organization_batches import ORGANIZATION_EXECUTION_VERSION
from .person_organization import ORGANIZATION_CONTRACT_VERSION
from .runtime import digest, run_identity, sparse_options, summarize_calls, validate_config, validate_input
from .validation import validate_cascade

PERSON_PIPELINE_VERSION = "canonical-person-v1"


@dataclass
class PersonCheckpoint:
    source_root: Path
    manifest: dict[str, Any]
    manifest_bytes: bytes
    artifacts: dict[str, bytes]
    build_input: BuildInput
    cascade: dict[str, Any] | None
    ledger: list[dict[str, Any]]
    inherited_ledger: list[dict[str, Any]]
    extraction_state: dict[str, Any] | None = None
    fact_seed: dict[str, Any] | None = None
    canonical_checkpoint: dict[str, Any] | None = None

    @property
    def mode(self):
        return "canonical_person_reorganization"

    @property
    def historical_calls(self):
        return self.inherited_ledger + self.ledger


def _effective_config(config):
    result = {key: config.get(key) for key in (
        "lm_type", "lm_name", "generation_config", "sparse_builder_config", "event_builder_config")}
    result["reconstruction"] = read_reconstruction(config)
    return result


def _semantic_config(config):
    """A new invocation owns a new budget; the factual task stays unchanged."""
    result = copy.deepcopy(config)
    for key in ("sparse_builder_config", "event_builder_config"):
        if isinstance(result.get(key), dict):
            result[key].pop("max_calls", None)
    return result


def _json(artifacts, name):
    if name not in artifacts:
        raise ValueError(f"Recovery requires {name}")
    return json.loads(artifacts[name])


def _validate_seed(package, inputs, subject):
    from finmy.person_epg.validation import validate_person_epg
    validation = validate_person_epg(package)
    if not validation["valid"]:
        raise ValueError("Saved person facts are invalid: " + json.dumps(validation["errors"][:3]))
    if package["graph"]["subject_entity_id"] != subject["subject_id"]:
        raise ValueError("Saved person facts refer to a different subject")
    # Citation offsets and IDs refer to these immutable source snapshots. A new
    # source collection cannot be silently substituted during reorganization.
    documents = Counter(row["content"] for row in package["source_document"])
    if documents != Counter(sample.content for sample in inputs.samples):
        raise ValueError("Saved person sources differ from BuildInput")


def _load_legacy_extraction(verifier, manifest, artifacts, inputs):
    """Import an old complete cascade or completed episodes; no overview call."""
    _json(artifacts, "EpisodeExecutionPlan-Result.json")
    if "FinalEventCascade.json" not in artifacts:
        state = verifier._load_saved_state(manifest["construction_contract_version"])
        verifier._validate_replay_completeness(state, include_event_description=False)
        cascade = verifier.integrate_results(state)
        cascade["descriptions"] = []
        validate_cascade(cascade)
        return cascade, state
    cascade = _json(artifacts, "FinalEventCascade.json")
    validate_cascade(cascade)
    if _json(artifacts, "CandidateEventCascade.json") != cascade:
        raise ValueError("Recovery candidate and final extraction differ")
    if verifier.integrate_from_files(strict=False) != cascade:
        raise ValueError("Recovery extraction replay differs from FinalEventCascade")
    evidence = grounded_evidence_report(cascade, inputs.samples, inputs.user_query)
    review = quality_review_report(cascade, inputs.samples, evidence)
    checks = construction_report(cascade)
    for name, calculated in (("ConstructionCheck.json", checks), ("EvidenceCheck.json", evidence),
                             ("QualityReview.json", review)):
        if _json(artifacts, name) != calculated:
            raise ValueError(f"Recovery {name} does not match recomputed extraction")
    policy = sparse_options(manifest["effective_config"]).get("evidence_policy", "report")
    if policy == "strict" and evidence["unmatched_quote_count"]:
        raise ValueError("Recovery extraction quote gate failed")
    acceptance = _json(artifacts, "AcceptanceDecision.json")
    if (acceptance.get("semantic_approval") is not False
            or acceptance.get("final_artifact_allowed") is not True
            or acceptance.get("policy") != policy
            or acceptance.get("unmatched_quotes") != evidence["unmatched_quote_count"]):
        raise ValueError("Recovery extraction acceptance gate failed")
    return cascade, None


def load_person_checkpoint(source_root) -> PersonCheckpoint:
    """Validate saved sources, facts and provenance before opening any transport."""
    root = Path(source_root).resolve()
    manifest_path = root / "RunManifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Recovery manifest must be a regular local file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("status") not in {"failed", "completed"} or manifest.get("builder_type") != "SparseRagBuilder":
        raise ValueError("Recovery requires a failed or completed SparseRagBuilder run")
    for field, supported in {
        "construction_contract_version": CONSTRUCTION_CONTRACT_VERSION,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "person_organization_contract_version": ORGANIZATION_CONTRACT_VERSION,
    }.items():
        if type(manifest.get(field)) is not int or manifest[field] != supported:
            raise ValueError(f"Unsupported recovery {field}")
    execution_version = manifest.get("organization_execution_version", 1)
    if type(execution_version) is not int or not 1 <= execution_version <= ORGANIZATION_EXECUTION_VERSION:
        raise ValueError("Unsupported recovery organization execution version")
    effective = manifest.get("effective_config")
    if not isinstance(effective, dict) or digest(effective) != manifest.get("config_sha256"):
        raise ValueError("Recovery effective configuration hash mismatch")
    subject_scope = read_reconstruction(effective)
    if subject_scope["mode"] != "person":
        raise ValueError("Recovery requires person mode")
    recorded = manifest.get("artifact_sha256")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("Recovery requires complete artifact hashes")
    artifacts = {}
    for path in root.glob("*.json"):
        if path.name in {"RunManifest.json", "GanttStatus.json"}:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("Recovery artifacts must be regular local files")
        artifacts[path.name] = path.read_bytes()
    actual = {name: hashlib.sha256(value).hexdigest() for name, value in artifacts.items()}
    if actual != recorded:
        raise ValueError("Recovery artifacts are incomplete or changed (hash mismatch)")
    payload = _json(artifacts, "BuildInput.json")
    if not isinstance(payload, dict) or set(payload) != {"user_query", "samples"}:
        raise ValueError("Invalid recovery BuildInput")
    inputs = BuildInput(UserQueryInput(**payload["user_query"]),
                        [DataSample(**item) for item in payload["samples"]])
    validate_input(inputs)
    if digest(payload) != manifest.get("input_sha256") or asdict(inputs) != payload:
        raise ValueError("Recovery input hash or serialized input mismatch")
    ledger = _json(artifacts, "CallLedger.json")
    if not isinstance(ledger, list) or summarize_calls(ledger) != manifest.get("usage"):
        raise ValueError("Recovery call ledger and usage do not match")
    inherited = []
    if "recovery" in manifest:
        provenance = manifest["recovery"]
        inherited = _json(artifacts, "OriginalCallLedger.json")
        parent_bytes = artifacts.get("RecoverySourceManifest.json", b"")
        parent = json.loads(parent_bytes)
        if (not isinstance(inherited, list)
                or provenance.get("prior_call_count") != len(inherited)
                or provenance.get("historical_usage") != summarize_calls(inherited)
                or provenance.get("cumulative_usage") != summarize_calls(inherited + ledger)
                or provenance.get("source_manifest_sha256") != hashlib.sha256(parent_bytes).hexdigest()
                or provenance.get("source_usage") != parent.get("usage")
                or provenance.get("source_code") != parent.get("code")
                or _semantic_config(parent.get("effective_config", {})) != _semantic_config(effective)):
            raise ValueError("Recovery history and cumulative usage do not match")
    elif "OriginalCallLedger.json" in artifacts:
        raise ValueError("Recovery history is missing its provenance")

    verifier = SparseRagBuilder.__new__(SparseRagBuilder)
    verifier.save_dir, verifier.build_config = str(root), {}
    cascade, extraction_state, seed, canonical = None, None, None, None
    if "PersonCanonicalFacts.json" in artifacts:
        seed = _json(artifacts, "PersonCanonicalFacts.json")
        _validate_seed(seed, inputs, subject_scope["subject"])
        audit = json.loads(artifacts.get("PersonCanonicalAudit.json", b"{}"))
        if audit.get("package_sha256") is not None and audit["package_sha256"] != digest(seed):
            raise ValueError("Saved canonical facts differ from their audit")
        from .person_fact_pipeline import canonical_input_hash
        storyline = (getattr(inputs.user_query, "extras", None) or {}).get("storyline_plan")
        if (audit.get("version") == PERSON_PIPELINE_VERSION
                and audit.get("input_sha256") == canonical_input_hash(inputs, subject_scope["subject"], storyline)
                and audit.get("package_sha256") == digest(seed)
                and audit.get("status") in {"completed", "partial", "no_usable_facts"}):
            canonical = {"package": copy.deepcopy(seed), "audit": audit}
    elif "FinalPersonEPG.json" in artifacts:
        seed = _json(artifacts, "FinalPersonEPG.json")
        _validate_seed(seed, inputs, subject_scope["subject"])
    elif "PersonImportedFacts.json" in artifacts:
        seed = _json(artifacts, "PersonImportedFacts.json")
        _validate_seed(seed, inputs, subject_scope["subject"])
    else:
        cascade, extraction_state = _load_legacy_extraction(verifier, manifest, artifacts, inputs)
        from finmy.person_epg.sparse_adapter import build_person_facts
        seed, _ = build_person_facts(cascade, inputs, subject_scope["subject"])
        if "PersonFactRepair-Result.json" in artifacts:
            # Import already paid, audited corrections from pre-canonical runs.
            # The retired repair algorithm is never called again.
            from .person_fact_repair import replay_facts
            seed = replay_facts(seed, _json(artifacts, "PersonFactRepair-Result.json"))
        _validate_seed(seed, inputs, subject_scope["subject"])
    if verifier._artifact_hashes() != recorded or manifest_path.read_bytes() != manifest_bytes:
        raise ValueError("Recovery checkpoint changed during validation")
    return PersonCheckpoint(root, manifest, manifest_bytes, artifacts, inputs, cascade, ledger,
                            inherited, extraction_state, seed, canonical)


def config_from_checkpoint(checkpoint, defaults, output_root=None, max_new_calls=None):
    """Restore the factual task, with an explicit per-invocation model budget."""
    if "builder_config" in defaults:
        defaults = defaults["builder_config"]
    config = {key: copy.deepcopy(value) for key, value in checkpoint.manifest["effective_config"].items()
              if value is not None}
    config.update(builder_type="SparseRagBuilder", agents=copy.deepcopy(defaults["agents"]),
                  save_folder=str(output_root) if output_root is not None else defaults["save_folder"])
    if max_new_calls is not None:
        if type(max_new_calls) is not int or max_new_calls < 1:
            raise ValueError("max_new_calls must be a positive integer")
        key = "sparse_builder_config" if "sparse_builder_config" in config else "event_builder_config"
        config.setdefault(key, {})["max_calls"] = max_new_calls
    validate_recovery_config(checkpoint, config)
    return config


def validate_recovery_config(checkpoint, config):
    validate_config(config)
    if config.get("builder_type", "SparseRagBuilder") != "SparseRagBuilder":
        raise ValueError("Recovery requires SparseRagBuilder")
    if _semantic_config(_effective_config(config)) != _semantic_config(checkpoint.manifest["effective_config"]):
        raise ValueError("Recovery must preserve the recorded subject, language, policy and model configuration")
    output_root = Path(config["save_folder"]).resolve()
    if output_root == checkpoint.source_root or output_root.is_relative_to(checkpoint.source_root):
        raise ValueError("Recovery output must be outside the original run directory")


def _copy_extraction(name):
    """The new run consumes imported facts, not a second old extraction tree.

    Historical artifacts remain immutable in source_root and their hashes stay
    in RecoverySourceManifest. Copying old FinalEventCascade into the new run
    would mislabel it as a new export if projection subsequently failed.
    """
    return name == "BuildInput.json"


def recover_person(config, source_root, *, reorganize=False) -> BuildOutput:
    """Reuse verified sources/facts and run the current person pipeline only."""
    checkpoint = load_person_checkpoint(source_root)
    validate_recovery_config(checkpoint, config)
    config = copy.deepcopy(config)
    inputs, manifest = run_identity(checkpoint.build_input, config)
    if digest(inputs) != checkpoint.manifest["input_sha256"]:
        raise ValueError("Recovery serialization changed the original input")
    historical = checkpoint.historical_calls
    max_calls = sparse_options(config).get("max_calls", 300)
    builder = SparseRagBuilder(build_config=config)
    destination = Path(builder.save_dir).resolve()
    if destination == checkpoint.source_root or destination.is_relative_to(checkpoint.source_root) or any(destination.iterdir()):
        raise ValueError("Recovery requires a fresh output directory outside the source run")
    builder._run_started, builder._call_records, builder._prior_call_count = True, [], 0
    builder._temporal_conflicts, builder._organization_validation_errors = [], []
    builder._organization_resume_artifacts = {} if reorganize else checkpoint.artifacts
    builder._organization_resume_history = [] if reorganize else historical
    manifest.update(builder_type=builder.builder_type,
                    construction_contract_version=CONSTRUCTION_CONTRACT_VERSION,
                    evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
                    person_organization_contract_version=ORGANIZATION_CONTRACT_VERSION,
                    organization_execution_version=ORGANIZATION_EXECUTION_VERSION,
                    person_pipeline_version=PERSON_PIPELINE_VERSION)
    manifest["recovery"] = {
        "mode": checkpoint.mode, "source_root": str(checkpoint.source_root),
        "source_manifest_sha256": hashlib.sha256(checkpoint.manifest_bytes).hexdigest(),
        "source_code": copy.deepcopy(checkpoint.manifest.get("code")),
        "source_usage": copy.deepcopy(checkpoint.manifest["usage"]),
        "historical_usage": summarize_calls(historical), "prior_call_count": len(historical),
        "budget_scope": "new_invocation", "max_new_calls": max_calls,
        "remaining_calls_at_start": max_calls, "search_calls": 0,
        "force_reorganization": reorganize,
        "inherited_artifact_sha256": {name: checkpoint.manifest["artifact_sha256"][name]
                                      for name in checkpoint.artifacts if _copy_extraction(name)},
    }
    for name, content in checkpoint.artifacts.items():
        if _copy_extraction(name):
            (destination / name).write_bytes(content)
    (destination / "RecoverySourceManifest.json").write_bytes(checkpoint.manifest_bytes)
    builder.save_traces(historical, "OriginalCallLedger", "json")
    builder.save_traces(inputs, "BuildInput", "json")
    builder.save_traces(checkpoint.fact_seed, "PersonImportedFacts", "json")
    if checkpoint.canonical_checkpoint is not None:
        builder.save_traces(checkpoint.canonical_checkpoint["package"], "PersonCanonicalFacts", "json")
        builder.save_traces(checkpoint.canonical_checkpoint["audit"], "PersonCanonicalAudit", "json")
    builder._save_call_ledger()
    builder.save_traces(manifest, "RunManifest", "json")
    output = BuildOutput(event_cascades=None, result={"cost": []}, logs=[], extras={})
    started = time.perf_counter()
    try:
        output = builder._complete_person(checkpoint.build_input, output, read_reconstruction(config)["subject"],
                                          package=checkpoint.fact_seed,
                                          canonical_checkpoint=checkpoint.canonical_checkpoint)
        graph = output.extras.get("person_epg", {}).get("graph", {})
        manifest.update(status="completed", graph_id=graph.get("graph_id"))
        return output
    except BaseException as error:
        manifest.update(status="failed", error_type=type(error).__name__, error_message=str(error),
                        interruption={"recovery_scope": "canonical_person_reorganization",
                                      "source_run": str(checkpoint.source_root),
                                      "run_directory": str(destination)})
        # Keep the original exception type while making CLI/library callers able
        # to locate new diagnostics without searching output folders.
        try:
            error.run_directory = str(destination)
        except (AttributeError, TypeError):
            pass
        raise
    finally:
        manifest.update(elapsed_seconds=time.perf_counter() - started,
                        usage=summarize_calls(builder._call_records))
        manifest["recovery"]["cumulative_usage"] = summarize_calls(historical + builder._call_records)
        manifest["artifact_sha256"] = builder._artifact_hashes()
        builder.save_traces(manifest, "RunManifest", "json")
        if manifest["status"] == "completed":
            output.extras.update(builder_type=builder.builder_type, run_directory=builder.save_dir,
                                elapsed_seconds=manifest["elapsed_seconds"], usage=copy.deepcopy(manifest["usage"]),
                                recovery=copy.deepcopy(manifest["recovery"]))
