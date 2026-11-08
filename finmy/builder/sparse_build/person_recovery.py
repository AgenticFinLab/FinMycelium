"""Validate a failed person run and recover organization in a fresh run directory.

Extraction artifacts are immutable inputs. Historical calls remain separate from
the new ledger, but still consume the original request budget.
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
from .prompts import get_agent_prompts
from .runtime import digest, run_identity, sparse_options, summarize_calls, validate_config, validate_input
from .validation import validate_cascade


@dataclass
class PersonCheckpoint:
    source_root: Path
    manifest: dict[str, Any]
    manifest_bytes: bytes
    artifacts: dict[str, bytes]
    build_input: BuildInput
    cascade: dict[str, Any]
    ledger: list[dict[str, Any]]
    inherited_ledger: list[dict[str, Any]]

    @property
    def historical_calls(self):
        return self.inherited_ledger + self.ledger


def _effective_config(config):
    result = {key: config.get(key) for key in (
        "lm_type", "lm_name", "generation_config", "sparse_builder_config", "event_builder_config")}
    result["reconstruction"] = read_reconstruction(config)
    return result


def _json(artifacts, name):
    if name not in artifacts:
        raise ValueError(f"Recovery requires {name}")
    return json.loads(artifacts[name])


def load_person_checkpoint(source_root) -> PersonCheckpoint:
    """Verify the complete extraction checkpoint before constructing an API client."""
    root = Path(source_root).resolve()
    manifest_path = root / "RunManifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Recovery manifest must be a regular local file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("status") != "failed" or manifest.get("builder_type") != "SparseRagBuilder":
        raise ValueError("Recovery requires a failed SparseRagBuilder run")
    versions = {"construction_contract_version": CONSTRUCTION_CONTRACT_VERSION,
                "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                "person_organization_contract_version": ORGANIZATION_CONTRACT_VERSION}
    for field, supported in versions.items():
        if type(manifest.get(field)) is not int or manifest[field] != supported:
            raise ValueError(f"Unsupported recovery {field}")
    execution_version = manifest.get("organization_execution_version", 1)
    # The public plan contract and completed extraction format are unchanged;
    # recovery must accept failed runs from both previously delivered executors.
    if type(execution_version) is not int or execution_version not in {1, 2, ORGANIZATION_EXECUTION_VERSION}:
        raise ValueError("Unsupported recovery organization execution version")
    effective = manifest.get("effective_config")
    if not isinstance(effective, dict) or digest(effective) != manifest.get("config_sha256"):
        raise ValueError("Recovery effective configuration hash mismatch")
    if read_reconstruction(effective)["mode"] != "person":
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
    cascade = _json(artifacts, "FinalEventCascade.json")
    validate_cascade(cascade)
    if _json(artifacts, "CandidateEventCascade.json") != cascade:
        raise ValueError("Recovery candidate and final extraction differ")
    _json(artifacts, "EpisodeExecutionPlan-Result.json")
    verifier = SparseRagBuilder.__new__(SparseRagBuilder)
    verifier.save_dir, verifier.build_config = str(root), {}
    if verifier.integrate_from_files(strict=False) != cascade:
        raise ValueError("Recovery extraction replay differs from FinalEventCascade")
    checks = construction_report(cascade)
    evidence = grounded_evidence_report(cascade, inputs.samples, inputs.user_query)
    review = quality_review_report(cascade, inputs.samples, evidence)
    for name, calculated in (("ConstructionCheck.json", checks), ("EvidenceCheck.json", evidence),
                             ("QualityReview.json", review)):
        if _json(artifacts, name) != calculated:
            raise ValueError(f"Recovery {name} does not match recomputed extraction")
    source_config = {key: value for key, value in effective.items() if value is not None}
    policy = sparse_options(source_config).get("evidence_policy", "report")
    if policy not in {"report", "strict"}:
        raise ValueError("Unsupported recovery evidence policy")
    blocked = policy == "strict" and evidence["unmatched_quote_count"] > 0
    acceptance = {"evidence_contract_version": EVIDENCE_CONTRACT_VERSION, "policy": policy,
                  "candidate_generated": True, "structure_passed": True,
                  "quote_check_passed": evidence["unmatched_quote_count"] == 0,
                  "unmatched_quotes": evidence["unmatched_quote_count"],
                  "fields_without_quotes": len(evidence["fields_without_quotes"]),
                  "review_candidates": len(review["issues"]), "final_artifact_allowed": not blocked,
                  "semantic_approval": False,
                  "status": "quote_gate_blocked" if blocked else "draft_requires_content_review"}
    if blocked or _json(artifacts, "AcceptanceDecision.json") != acceptance:
        raise ValueError("Recovery extraction acceptance gate failed")
    ledger = _json(artifacts, "CallLedger.json")
    if not isinstance(ledger, list) or summarize_calls(ledger) != manifest.get("usage"):
        raise ValueError("Recovery call ledger and usage do not match")
    roles = set(get_agent_prompts()[0])
    if any(row.get("agent") not in roles | {"PersonOrganization"} for row in ledger):
        raise ValueError("Recovery ledger contains an unsupported role")
    inherited = []
    if "recovery" in manifest:
        provenance = manifest["recovery"]
        inherited = _json(artifacts, "OriginalCallLedger.json")
        parent_manifest_bytes = artifacts.get("RecoverySourceManifest.json", b"")
        parent_manifest = json.loads(parent_manifest_bytes)
        if (not isinstance(inherited, list)
                or provenance.get("prior_call_count") != len(inherited)
                or provenance.get("historical_usage") != summarize_calls(inherited)
                or provenance.get("cumulative_usage") != summarize_calls(inherited + ledger)
                or provenance.get("source_manifest_sha256") != hashlib.sha256(parent_manifest_bytes).hexdigest()
                or provenance.get("source_usage") != parent_manifest.get("usage")
                or provenance.get("source_code") != parent_manifest.get("code")
                or parent_manifest.get("effective_config") != effective):
            raise ValueError("Recovery history and cumulative budget do not match")
        if any(row.get("agent") != "PersonOrganization" for row in ledger):
            raise ValueError("Person recovery ledger must not contain new extraction calls")
    elif "OriginalCallLedger.json" in artifacts:
        raise ValueError("Recovery history is missing its provenance")
    checkpoint = PersonCheckpoint(root, manifest, manifest_bytes, artifacts, inputs, cascade, ledger, inherited)
    if any(row.get("agent") not in roles | {"PersonOrganization"} for row in inherited):
        raise ValueError("Recovery history contains an unsupported role")
    accepted_extraction = Counter(row.get("save_name", "") + "-Result.json"
                                  for row in checkpoint.historical_calls
                                  if row.get("agent") in roles and row.get("status") in {"accepted", "recovered"})
    extraction_results = Counter(name for name in artifacts
                                 if name.endswith("-Result.json") and name.split("-", 1)[0] in roles)
    if accepted_extraction != extraction_results:
        raise ValueError("Recovery extraction results and historical accepted calls do not match")
    max_calls = sparse_options(source_config).get("max_calls", 300)
    if type(max_calls) is not int or len(checkpoint.historical_calls) >= max_calls:
        raise ValueError("Original model call budget is exhausted")
    # Verify again after replay; all later copies use the verified byte snapshot.
    if verifier._artifact_hashes() != recorded or manifest_path.read_bytes() != manifest_bytes:
        raise ValueError("Recovery checkpoint changed during validation")
    return checkpoint


def config_from_checkpoint(checkpoint, defaults, output_root=None):
    """Restore recorded semantics; defaults supply only omitted runtime locations/roles."""
    if "builder_config" in defaults:
        defaults = defaults["builder_config"]
    config = {key: copy.deepcopy(value) for key, value in checkpoint.manifest["effective_config"].items()
              if value is not None}
    config.update(builder_type="SparseRagBuilder", agents=copy.deepcopy(defaults["agents"]),
                  save_folder=str(output_root) if output_root is not None else defaults["save_folder"])
    validate_recovery_config(checkpoint, config)
    return config


def validate_recovery_config(checkpoint, config):
    validate_config(config)
    if config.get("builder_type", "SparseRagBuilder") != "SparseRagBuilder":
        raise ValueError("Recovery requires SparseRagBuilder")
    if _effective_config(config) != checkpoint.manifest["effective_config"]:
        raise ValueError("Recovery must preserve the recorded subject, language, policy and model configuration")
    output_root = Path(config["save_folder"]).resolve()
    if output_root == checkpoint.source_root or output_root.is_relative_to(checkpoint.source_root):
        raise ValueError("Recovery output must be outside the original run directory")


def _copy_extraction(name):
    if name in {"CallLedger.json", "OriginalCallLedger.json", "RecoverySourceManifest.json"}:
        return False
    return not name.startswith(("Person", "CandidatePerson", "FinalPerson", "FinalSubject"))


def recover_person(config, source_root) -> BuildOutput:
    """Run only person organization and its normal validation/rendering lifecycle."""
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
    builder._run_started = True
    builder._call_records = []
    builder._prior_call_count = len(historical)
    conflicts = checkpoint.artifacts.get("EpisodeScopeConflicts.json")
    builder._temporal_conflicts = json.loads(conflicts)["conflicts"] if conflicts else []
    manifest.update(builder_type=builder.builder_type,
                    construction_contract_version=CONSTRUCTION_CONTRACT_VERSION,
                    evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
                    person_organization_contract_version=ORGANIZATION_CONTRACT_VERSION,
                    organization_execution_version=ORGANIZATION_EXECUTION_VERSION)
    manifest["recovery"] = {
        "mode": "person_organization_only", "source_root": str(checkpoint.source_root),
        "source_manifest_sha256": hashlib.sha256(checkpoint.manifest_bytes).hexdigest(),
        "source_code": copy.deepcopy(checkpoint.manifest.get("code")),
        "source_usage": copy.deepcopy(checkpoint.manifest["usage"]),
        "historical_usage": summarize_calls(historical), "prior_call_count": len(historical),
        "original_max_calls": max_calls, "remaining_calls_at_start": max_calls - len(historical),
        "inherited_artifact_sha256": {name: checkpoint.manifest["artifact_sha256"][name]
                                      for name in checkpoint.artifacts if _copy_extraction(name)},
    }
    for name, content in checkpoint.artifacts.items():
        if _copy_extraction(name):
            (destination / name).write_bytes(content)
    (destination / "RecoverySourceManifest.json").write_bytes(checkpoint.manifest_bytes)
    builder.save_traces(historical, "OriginalCallLedger", "json")
    builder._save_call_ledger()
    builder.save_traces(manifest, "RunManifest", "json")
    extraction_roles = [row["agent"] for row in historical
                        if row["agent"] != "PersonOrganization" and row.get("status") in {"accepted", "recovered"}]
    output = BuildOutput(event_cascades=copy.deepcopy(checkpoint.cascade), result={"cost": []},
                         logs=extraction_roles.copy(), extras={
                             "agent_executed": extraction_roles.copy(),
                             "acceptance": _json(checkpoint.artifacts, "AcceptanceDecision.json"),
                             "episode_execution_plan": _json(checkpoint.artifacts, "EpisodeExecutionPlan-Result.json"),
                             "episode_scope_conflicts": copy.deepcopy(builder._temporal_conflicts),
                         })
    started = time.perf_counter()
    try:
        output = builder._complete_person(checkpoint.build_input, output, read_reconstruction(config)["subject"])
        manifest.update(status="completed", event_id=output.event_cascades["event_id"])
        return output
    except BaseException as error:
        manifest.update(status="failed", error_type=type(error).__name__)
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
