"""Sparse RAG enhanced event reconstruction builder."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from lmbase.inference.base import InferInput

from finmy.builder.base import AgentState, BaseBuilder, BuildInput, BuildOutput
from finmy.builder.utils import run_single_inference
from finmy.reconstruction_scope import read_reconstruction, render_scope

from .context_assets import (
    EvidenceAssetBundle,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
    summarize_context_assets,
)
from .completion_errors import IncompleteCompletionError
from .contracts import (
    CONSTRUCTION_CONTRACT_VERSION, TemporalScopeError, check_temporal_scope, compact_values,
    construction_report, episode_scope, participant_registry, stage_scope, bind_episode_scope,
    validate_episode_reuse, validate_participant_identity,
)
from .execution_budget import (
    build_stage_aware_execution_budget,
    episode_budget_prompt_vars,
)
from .local_context_builder import LocalContextBuilder, LocalContextRequest
from .grounding import EVIDENCE_CONTRACT_VERSION, grounded_evidence_report, quality_review_report
from .prompts import get_agent_prompts, structure_spec
from .renderers import render_context_asset_summary
from .runtime import PERSON_SCOPE_GUIDANCE, digest, run_identity, sparse_options, summarize_calls, validate_config, validate_input
from .temporal_recovery import build_temporal_retry_user_msg
from .organization_errors import OrganizationValidationError, build_organization_retry_user_msg
from .organization_call_guard import guard_organization_call
from .relation_grounding import (
    CounterpartyEvidenceGuard, RelationGroundingError, ReviewUnavailableError,
    build_relation_retry_user_msg,
)
from .validation import (
    validate_cascade, validate_endpoints, validate_episode, validate_role,
)


_REPLAY_STAGE_EPISODE_SUFFIX = re.compile(
    r"-Stage(?P<stage>\d+)-Episode(?P<episode>\d+)-Result\.json$"
)


class SparseAgentState(AgentState):
    context_assets: EvidenceAssetBundle
    episode_execution_plan: dict[str, Any]
    stage_sparse_cache: dict[str, Any]
    construction_contract_version: int


class SparseRagBuilder(BaseBuilder):
    """Independent builder entry point for sparse RAG event reconstruction."""

    builder_type = "SparseRagBuilder"
    build_input_fields = ("user_query", "samples")
    required_build_config_keys = (
        "agents",
        "lm_type",
        "lm_name",
        "generation_config",
        "save_folder",
    )
    event_config_key = "sparse_builder_config"
    legacy_event_config_key = "event_builder_config"
    _JSON_PARSE_RETRY_AGENTS = {
        "PersonFacts",
        "PersonOverview",
        "PersonOrganization",
        "SkeletonReconstructor",
        "SkeletonChecker",
        "ParticipantReconstructor",
        "TransactionReconstructor",
        "EpisodeReconstructor",
        "StageDescriptionReconstructor",
        "EventDescriptionReconstructor",
    }
    _JSON_SYNTACTIC_RECOVERY_AGENTS = {
        "SkeletonChecker",
        "ParticipantReconstructor",
        "EpisodeReconstructor",
        "StageDescriptionReconstructor",
    }

    def define_agent_models(self):
        from .inference import SparseAPIInference

        validate_config(self.build_config)
        if self.build_config["lm_type"].lower() != "api":
            raise ValueError("SparseRagBuilder currently supports API inference only")
        timeout = self._event_config_value("request_timeout_seconds", 900)
        if type(timeout) not in (int, float) or not 0 < timeout <= 3600:
            raise ValueError("request_timeout_seconds must be in (0, 3600]")
        self.agents_lm = SparseAPIInference(
            self.build_config["lm_name"], self.build_config["generation_config"], timeout=timeout
        )

    def _save_call_ledger(self):
        if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
            self.save_traces(self._call_records, "CallLedger", "json")

    def _record_temporal_conflict(self, agent_name, savename, attempt, error, candidate):
        """Retain rejected scene facts for review without rewriting or relocating them."""
        if not hasattr(self, "_temporal_conflicts"):
            self._temporal_conflicts = []
        self._temporal_conflicts.append({
            "agent": agent_name, "save_name": savename, "attempt": attempt,
            "status": "needs_scope_review", "automatic_reassignment": False,
            "issue": copy.deepcopy(error.report),
            "rejected_candidate": copy.deepcopy(candidate),
        })
        if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
            self.save_traces({
                "contract_version": 1, "semantic_support_checked": False,
                "conflicts": self._temporal_conflicts,
            }, "EpisodeScopeConflicts", "json")

    def _record_organization_error(self, agent_name, savename, attempt, error, candidate):
        """Retain rejected organization candidates without silently rewriting them."""
        if not hasattr(self, "_organization_validation_errors"):
            self._organization_validation_errors = []
        self._organization_validation_errors.append({
            "agent": agent_name, "save_name": savename, "attempt": attempt,
            "status": "rejected_candidate", "issue": copy.deepcopy(error.report),
            "rejected_candidate": copy.deepcopy(candidate),
        })
        if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
            self.save_traces({
                "contract_version": 1, "semantic_support_checked": False,
                "errors": self._organization_validation_errors,
            }, "PersonOrganizationValidationErrors", "json")

    def save_traces(self, traces, save_name, file_format, **kwargs):
        if file_format != "json":
            return super().save_traces(traces, save_name, file_format, **kwargs)
        destination = Path(self.save_dir) / f"{save_name}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.save_dir,
                                         prefix=".writing-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                json.dump(traces, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _get_agent_prompts(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return system and user prompt templates for all event agents."""

        return get_agent_prompts()

    def _event_config(self) -> dict[str, Any]:
        build_config = getattr(self, "build_config", None) or {}
        return sparse_options(build_config)

    def _event_config_value(self, key: str, default: Any) -> Any:
        return self._event_config().get(key, default)

    def _build_private_context_assets(
        self,
        build_input: BuildInput,
    ) -> EvidenceAssetBundle:
        """Derive private context assets from the existing BuildInput shape."""

        if not self._event_config_value("enable_context_assets", True):
            return EvidenceAssetBundle.empty()
        policy = EvidenceRetrievalPolicy(
            max_cards=self._event_config_value("context_top_k", 8),
            excerpt_char_limit=self._event_config_value("excerpt_char_limit", 240),
            max_card_tokens=self._event_config_value("max_card_tokens", 48),
        )
        return build_evidence_assets(
            user_query=build_input.user_query,
            samples=build_input.samples,
            retrieval_policy=policy,
        )

    def _content_from_samples(self, build_input: BuildInput) -> str:
        return "\n\n".join(
            f"SOURCE {json.dumps({'sample_id': sample.sample_id, 'raw_data_id': sample.raw_data_id}, ensure_ascii=False)}\n{sample.content or ''}"
            for sample in build_input.samples
        )

    def _build_local_context_package(
        self,
        build_input: BuildInput,
        agent_name: str,
        context_assets: EvidenceAssetBundle | None = None,
        target_stage: str = "",
        target_episode: str = "",
    ):
        bundle = context_assets or self._build_private_context_assets(build_input)
        return LocalContextBuilder().build(
            LocalContextRequest(
                agent_name=agent_name,
                query_text=build_input.user_query.query_text or "",
                key_words=build_input.user_query.key_words or [],
                target_stage=target_stage,
                target_episode=target_episode,
                context_assets=bundle,
                max_context_chars=self._event_config_value("max_context_chars", 6000),
            )
        )

    def _build_prompt_kwargs(
        self,
        build_input: BuildInput,
        agent_name: str,
        context_assets: EvidenceAssetBundle | None = None,
        target_stage: str = "",
        target_episode: str = "",
        episode_budget: dict[str, Any] | None = None,
        **extra_kwargs: Any,
    ) -> dict[str, str]:
        """Build explicit prompt variables for one event agent call."""

        if agent_name == "EventDescriptionReconstructor":
            # The overview cannot add facts: no full sources, occurrence tables,
            # retrieval memory or coverage checklist need to be re-emitted here.
            return {
                "Query": build_input.user_query.query_text or "",
                "OutputLanguage": str(self._event_config_value("output_language", "English")),
                "STRUCTURE_SPEC": structure_spec(agent_name),
                "EventCascade": "{}", "Content": "[]",
                **{key: self._format_prompt_value(value) for key, value in extra_kwargs.items()},
            }
        bundle = context_assets or self._build_private_context_assets(build_input)
        local_context = self._build_local_context_package(
            build_input=build_input,
            agent_name=agent_name,
            context_assets=bundle,
            target_stage=target_stage,
            target_episode=target_episode,
        )
        budget_vars = episode_budget_prompt_vars(episode_budget)
        kwargs: dict[str, str] = {
            "Query": build_input.user_query.query_text or "",
            "Keywords": ", ".join(build_input.user_query.key_words or []),
            "Content": self._content_from_samples(build_input),
            "RetrievedContext": local_context.rendered_context,
            "RetrievedContextSummary": render_context_asset_summary(
                summarize_context_assets(bundle)
            ),
            "RetrievedContextQueryBundle": json.dumps(
                local_context.query_bundle,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "RetrievedContextBudgetSummary": json.dumps(
                local_context.budget_summary,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "RetrievedContextMemory": json.dumps(
                local_context.memory,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "TargetStage": target_stage,
            "TargetEpisode": target_episode,
            "ProposedSkeleton": "",
            "StageSkeleton": "",
            "EventCascade": "",
            "ReconstructedParticipants": "",
            "StageSparseCache": "",
            "ParticipantDetailTier": str((episode_budget or {}).get("participant_tier", "standard")),
            "OutputLanguage": str(self._event_config_value("output_language", "English")),
            "STRUCTURE_SPEC": structure_spec(agent_name),
        }
        kwargs.update(budget_vars)
        kwargs.update(
            {key: self._format_prompt_value(value) for key, value in extra_kwargs.items()}
        )
        return kwargs

    def _format_prompt_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        return str(value)

    def _format_agent_messages(
        self,
        agent_name: str,
        prompt_kwargs: dict[str, str],
    ) -> tuple[str, str]:
        """Format system and user prompt templates for one agent."""

        system_prompts, user_prompts = self._get_agent_prompts()
        if agent_name not in system_prompts or agent_name not in user_prompts:
            raise ValueError(f"Unknown SparseRagBuilder agent: {agent_name}")
        system = system_prompts[agent_name].format(**prompt_kwargs)
        config = getattr(self, "build_config", None)
        if read_reconstruction(config)["mode"] == "person":
            system += "\n\n" + render_scope(config) + "\n" + PERSON_SCOPE_GUIDANCE
        return system, user_prompts[agent_name].format(**prompt_kwargs)

    @staticmethod
    def _load_finite_json(text: str) -> Any:
        value = json.loads(text)
        # Python also accepts NaN/Infinity and overflowing floats. Reject these
        # before validators or strict diagnostic writers see a candidate.
        json.dumps(value, allow_nan=False)
        return value

    def _parse_json_response(self, response_text: str) -> Any:
        clean_text = (response_text or "").strip()
        code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.S)
        if code_block_match:
            clean_text = code_block_match.group(1).strip()
        try:
            return self._load_finite_json(clean_text)
        except json.JSONDecodeError:
            object_match = re.search(r"(\{.*\}|\[.*\])", clean_text, re.S)
            if object_match:
                return self._load_finite_json(object_match.group(1))
            return response_text

    def _build_json_retry_user_msg(self, base_user_msg: str, agent_name: str) -> str:
        return (
            f"{base_user_msg}\n\n"
            "IMPORTANT OUTPUT RECOVERY:\n"
            f"- Your previous {agent_name} response was invalid or truncated JSON.\n"
            "- Return exactly one complete raw JSON object.\n"
            "- Do not include markdown fences, commentary, or partial output.\n"
            "- Ensure all braces, brackets, strings, and commas are properly closed.\n"
        )

    def _extract_balanced_json_fragment(self, text: str, start_idx: int) -> str | None:
        if start_idx < 0 or start_idx >= len(text):
            return None
        opener = text[start_idx]
        if opener not in "{[":
            return None

        closers = {"{": "}", "[": "]"}
        stack = [closers[opener]]
        in_string = False
        escape = False
        for idx in range(start_idx + 1, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(closers[ch])
            elif ch in "}]":
                if not stack or ch != stack[-1]:
                    return None
                stack.pop()
                if not stack:
                    return text[start_idx : idx + 1]
        return None

    def _recover_syntactic_json_response(self, response_text: str) -> Any:
        clean_text = response_text.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.S)
        if fence_match:
            clean_text = fence_match.group(1).strip()

        seen_candidates: set[str] = set()
        for start_idx, ch in enumerate(clean_text):
            if ch not in "{[":
                continue
            candidate = self._extract_balanced_json_fragment(clean_text, start_idx)
            if not candidate or candidate in seen_candidates:
                continue
            seen_candidates.add(candidate)
            try:
                return self._load_finite_json(candidate)
            except json.JSONDecodeError:
                continue
        raise ValueError("Failed to recover a balanced JSON fragment from response")

    def _infer_and_parse_json(
        self,
        agent_name: str,
        sys_msg: str,
        user_msg: str,
        prompt_kwargs: dict[str, str],
        savename: str,
        validator=None,
        temporal_reviewer=None,
    ) -> Any:
        if agent_name == "PersonOrganization":
            sys_msg, user_msg, validator = guard_organization_call(
                sys_msg, user_msg, validator, phase=savename)
        max_attempts = self._event_config_value("max_json_attempts", 3)
        max_calls = self._event_config_value("max_calls", 300)
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError("max_json_attempts must be an integer in [1, 3]")
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        if agent_name not in self._JSON_PARSE_RETRY_AGENTS:
            max_attempts = 1
        current_user_msg = user_msg
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            if not hasattr(self, "_call_records"):
                self._call_records = []
            if len(self._call_records) + getattr(self, "_prior_call_count", 0) >= max_calls:
                raise RuntimeError("Configured model call limit reached")
            record = {
                "agent": agent_name, "attempt": attempt, "save_name": savename,
                "status": "pending", "prompt_tokens": None, "completion_tokens": None,
                "reasoning_tokens": None, "cached_tokens": None, "elapsed_seconds": None,
            }
            self._call_records.append(record)
            self._save_call_ledger()
            started = time.perf_counter()
            # Messages already contain source text and JSON; never interpolate twice.
            try:
                output = run_single_inference(
                    self.agents_lm,
                    InferInput(system_msg=sys_msg, user_msg=current_user_msg),
                )
            except Exception as exc:
                record.update(status="transport_error", error_type=type(exc).__name__)
                raise
            finally:
                record["elapsed_seconds"] = time.perf_counter() - started
                if record["status"] == "transport_error":
                    self._save_failure_ledger()
                else:
                    self._save_call_ledger()
            cost = getattr(output, "cost", None)
            details = getattr(output, "extras", None) or {}
            record.update(
                status="response_received",
                prompt_tokens=getattr(cost, "prompt_tokens", None),
                completion_tokens=getattr(cost, "completion_tokens", None),
                reasoning_tokens=details.get("reasoning_tokens"),
                cached_tokens=details.get("cached_tokens"),
                finish_reason=details.get("finish_reason"),
            )
            self._save_call_ledger()
            response_text = str(getattr(output, "response", output))
            self._save_agent_trace(agent_name, output, savename, attempt)
            if ("finish_reason" in details and details["finish_reason"] != "stop") or details.get("refusal") or details.get("tool_calls"):
                record["status"] = "incomplete_response"
                record["refusal"] = bool(details.get("refusal"))
                record["tool_calls"] = bool(details.get("tool_calls"))
                self._save_call_ledger()
                generation = (getattr(self, "build_config", None) or {}).get("generation_config", {})
                limit = next((generation[key] for key in
                              ("max_new_tokens", "max_tokens", "max_completion_tokens")
                              if key in generation), None)
                raise IncompleteCompletionError(
                    agent_name, finish_reason=details.get("finish_reason"),
                    refusal=details.get("refusal"), tool_calls=details.get("tool_calls"),
                    completion_tokens=record["completion_tokens"], output_limit=limit)
            if not response_text.strip():
                record["status"] = "empty_response"
                self._save_call_ledger()
                raise ValueError(f"{agent_name}: empty completion")
            parsed = None
            try:
                parsed = self._parse_json_response(response_text)
                if isinstance(parsed, str):
                    raise ValueError("Response did not contain JSON")
                if validator is not None:
                    try:
                        validator(parsed)
                    except (TypeError, ValueError) as validation_error:
                        if agent_name != "PersonOrganization" or isinstance(validation_error, OrganizationValidationError):
                            raise
                        raise OrganizationValidationError({
                            "phase": savename, "violations": [{
                                "path": "$", "code": "organization_contract",
                                "message": str(validation_error),
                            }],
                        }) from validation_error
                self._save_agent_result(parsed, savename)
                record["status"] = "accepted"
                self._save_call_ledger()
                return parsed
            except ReviewUnavailableError as exc:
                record.update(status="review_pending", validation_kind="review_unavailable",
                              error_type=exc.review_error_type, review_role=exc.review_role,
                              candidate_checkpoint_saved=exc.audit_saved,
                              pending_candidate_artifact=exc.audit_artifact if exc.audit_saved else None)
                self._save_failure_ledger()
                raise
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if (agent_name in self._JSON_SYNTACTIC_RECOVERY_AGENTS
                        and not isinstance(last_error, (TemporalScopeError, RelationGroundingError))):
                    try:
                        recovered = self._recover_syntactic_json_response(response_text)
                        parsed = recovered
                        if validator is not None:
                            validator(recovered)
                        self._save_agent_result(recovered, savename)
                        record["status"] = "recovered"
                        self._save_call_ledger()
                        return recovered
                    except ValueError as recovery_exc:
                        last_error = recovery_exc
                record.update(status="invalid_output", error_type=type(last_error).__name__)
                if isinstance(last_error, TemporalScopeError):
                    record["validation_kind"] = "episode_temporal_scope"
                    self._record_temporal_conflict(agent_name, savename, attempt, last_error, parsed)
                    if temporal_reviewer is not None:
                        reviewer, temporal_reviewer = temporal_reviewer, None
                        try:
                            revised = reviewer(last_error, parsed)
                        except ReviewUnavailableError as review_error:
                            record.update(status="review_pending", error_type=review_error.review_error_type,
                                          review_role=review_error.review_role,
                                          candidate_checkpoint_saved=review_error.audit_saved,
                                          pending_candidate_artifact=review_error.audit_artifact
                                              if review_error.audit_saved else None)
                            self._save_failure_ledger()
                            raise
                        if revised:
                            validator(parsed)
                            self._save_agent_result(parsed, savename)
                            record.update(status="accepted", scope_revision=True)
                            self._save_call_ledger()
                            return parsed
                elif isinstance(last_error, OrganizationValidationError):
                    record["validation_kind"] = "organization_semantic"
                    self._record_organization_error(agent_name, savename, attempt, last_error, parsed)
                elif isinstance(last_error, RelationGroundingError):
                    record["validation_kind"] = "relation_evidence"
                self._save_call_ledger()
                if attempt >= max_attempts:
                    raise ValueError(
                        f"{agent_name} returned invalid output after {attempt} attempt(s): {last_error}"
                    ) from last_error
                if isinstance(last_error, TemporalScopeError):
                    current_user_msg = build_temporal_retry_user_msg(
                        user_msg, agent_name, last_error, parsed)
                elif isinstance(last_error, OrganizationValidationError):
                    current_user_msg = build_organization_retry_user_msg(
                        user_msg, agent_name, last_error, parsed)
                elif isinstance(last_error, RelationGroundingError):
                    current_user_msg = build_relation_retry_user_msg(user_msg, last_error, parsed)
                else:
                    current_user_msg = self._build_json_retry_user_msg(user_msg, agent_name) + f"\nValidation issue: {last_error}\n"

        raise ValueError(f"{agent_name} returned invalid JSON: {last_error}")

    def _save_failure_ledger(self):
        """A diagnostic write failure must not replace the active request error."""
        try:
            self._save_call_ledger()
        except OSError as exc:
            logging.getLogger(__name__).warning('Could not save failure CallLedger (%s)',
                                               type(exc).__name__)

    def _save_agent_trace(
        self,
        agent_name: str,
        output: Any,
        savename: str,
        attempt: int,
    ) -> None:
        if not hasattr(self, "save_dir") or not getattr(self, "save_dir", None):
            return
        if not os.path.isdir(self.save_dir):
            return
        trace = output.to_dict() if hasattr(output, "to_dict") else {"response": output}
        attempt_savename = savename if attempt == 1 else f"{savename}-Retry{attempt - 1}"
        self.save_traces({agent_name: trace}, attempt_savename, "json")

    def _save_agent_result(self, parsed_result: Any, savename: str) -> None:
        if not hasattr(self, "save_dir") or not getattr(self, "save_dir", None):
            return
        if not os.path.isdir(self.save_dir):
            return
        self.save_traces(parsed_result, f"{savename}-Result", "json")

    def _agent_save_name(self, state: AgentState, agent_name: str) -> str:
        savename = self.get_save_name(
            agent_name,
            state["agent_executed"].count(agent_name) + 1,
        )
        if agent_name in {
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        }:
            event_skeleton = self._get_event_skeleton(state)
            sequence_index = self._current_episode_sequence_index(state)
            stage_index, episode_index, _, _, _ = self._get_episode_by_sequence_index(
                event_skeleton,
                sequence_index,
            )
            return f"{savename}-Stage{stage_index}-Episode{episode_index}"
        if agent_name == "StageDescriptionReconstructor":
            stage_index = state["agent_executed"].count("StageDescriptionReconstructor")
            return f"{savename}-Stage{stage_index}"
        return savename

    def _latest_agent_result(self, state: AgentState, agent_name: str) -> Any:
        for result in reversed(state["agent_results"]):
            if agent_name in result:
                return result[agent_name]
        return None

    def _get_event_skeleton(self, state: AgentState) -> dict[str, Any]:
        skeleton = self._latest_agent_result(state, "SkeletonChecker")
        if skeleton is not None:
            return skeleton
        skeleton = self._latest_agent_result(state, "SkeletonReconstructor")
        if skeleton is not None:
            return skeleton
        raise ValueError("No skeleton result found in SparseRagBuilder state")

    def _scalar_value(self, field: Any) -> str:
        if field is None:
            return ""
        if isinstance(field, str):
            return field
        if isinstance(field, dict):
            for key in ("value", "text", "name", "title"):
                if key in field:
                    return self._scalar_value(field[key])
            return ""
        if isinstance(field, (list, tuple, set)):
            return " ".join(self._scalar_value(item) for item in field).strip()
        return str(field)

    def _is_unknown_value(self, value: str) -> bool:
        return value.strip().lower() in {"", "unknown", "n/a", "none", "null"}

    def _field_value(self, field: Any) -> str:
        return self._scalar_value(field).strip()

    def _validate_event_skeleton(self, skeleton: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(skeleton, dict):
            return False, "Skeleton must be a JSON object."
        if self._is_unknown_value(self._field_value(skeleton.get("title"))):
            return False, "Skeleton title is missing or unknown."
        stages = skeleton.get("stages")
        if not isinstance(stages, list) or not stages:
            return False, "Skeleton must contain at least one stage."

        total_episodes = 0
        for stage_index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                return False, f"Stage {stage_index} must be a JSON object."
            if self._is_unknown_value(self._field_value(stage.get("name"))):
                return False, f"Stage {stage_index} name is missing or unknown."
            episodes = stage.get("episodes")
            if not isinstance(episodes, list) or not episodes:
                return False, f"Stage {stage_index} must contain at least one episode."
            total_episodes += len(episodes)
            for episode_index, episode in enumerate(episodes):
                if not isinstance(episode, dict):
                    return False, f"Episode {stage_index}/{episode_index} must be a JSON object."
                if self._is_unknown_value(self._field_value(episode.get("name"))):
                    return (
                        False,
                        f"Episode {stage_index}/{episode_index} name is missing or unknown.",
                    )
        if total_episodes == 0:
            return False, "Skeleton must contain at least one episode."
        return True, ""

    def _episode_locator(
        self,
        stage_index: int,
        episode_index: int,
        stage_id: str | None = None,
        episode_id: str | None = None,
    ) -> dict[str, object]:
        locator: dict[str, object] = {
            "stage_index": stage_index,
            "episode_index": episode_index,
        }
        if stage_id is not None:
            locator["stage_id"] = stage_id
        if episode_id is not None:
            locator["episode_id"] = episode_id
        return locator

    def _episode_locator_key(self, locator: dict[str, object] | None) -> tuple:
        if not locator:
            return ()
        return (
            locator.get("stage_index"),
            locator.get("episode_index"),
            locator.get("stage_id", ""),
            locator.get("episode_id", ""),
        )

    def _iter_skeleton_episodes(self, event_skeleton: dict[str, Any]):
        for stage_index, stage in enumerate(event_skeleton.get("stages", []) or []):
            stage_id = self._scalar_value(stage.get("stage_id"))
            for episode_index, episode in enumerate(stage.get("episodes", []) or []):
                episode_id = self._scalar_value(episode.get("episode_id"))
                yield stage_index, episode_index, stage, episode, self._episode_locator(
                    stage_index,
                    episode_index,
                    stage_id,
                    episode_id,
                )

    def _current_episode_sequence_index(self, state: AgentState) -> int:
        return state["agent_executed"].count("EpisodeReconstructor")

    def _get_episode_by_sequence_index(
        self,
        event_skeleton: dict[str, Any],
        sequence_index: int,
    ):
        for (
            stage_index,
            episode_index,
            stage,
            episode,
            locator,
        ) in self._iter_skeleton_episodes(event_skeleton):
            if sequence_index == 0:
                return stage_index, episode_index, stage, episode, locator
            sequence_index -= 1
        return None, None, None, None, None

    def _build_episode_execution_plan(
        self,
        build_input: BuildInput,
        event_skeleton: dict[str, Any],
        context_assets: EvidenceAssetBundle | None = None,
    ) -> dict[str, object]:
        budget_skeleton = copy.deepcopy(event_skeleton)
        for si, stage in enumerate(budget_skeleton.get("stages", [])):
            stage["stage_id"] = f"stage-{si}"
            for ei, episode in enumerate(stage.get("episodes", [])):
                episode["episode_id"] = f"episode-{ei}"
        budget = build_stage_aware_execution_budget(
            build_input,
            budget_skeleton,
            context_assets=context_assets,
        )
        plan_entries: list[dict[str, object]] = []
        for stage_index, episode_index, stage, episode, locator in self._iter_skeleton_episodes(
            event_skeleton
        ):
            stage_id = self._scalar_value(stage.get("stage_id"))
            episode_id = self._scalar_value(episode.get("episode_id"))
            budget_entry = dict(budget.get("episodes", {}).get(
                (f"stage-{stage_index}", f"episode-{episode_index}"), {}
            ))
            if not self._event_config_value("enable_sparse_routing", True):
                budget_entry.update(
                    mode="full", participant_tier="standard", transaction_tier="standard",
                    episode_detail_tier="standard", transaction_step_skipped=False,
                    compactness_hint="Retain all supported process details without inventing facts.",
                )
            entry = {
                **budget_entry,
                "locator": locator,
                "stage_id": stage_id,
                "episode_id": episode_id,
                "stage_index": stage_index,
                "episode_index": episode_index,
            }
            plan_entries.append(entry)
        stages = budget.get("stages", [])
        for si, stage in enumerate(stages):
            stage["stage_id"] = self._scalar_value(event_skeleton["stages"][si].get("stage_id"))
        return {"stages": stages, "episodes": plan_entries}

    def _get_episode_execution_plan_entry(
        self,
        episode_execution_plan: dict[str, object] | None,
        stage_index: int,
        episode_index: int,
    ) -> dict[str, Any] | None:
        if not episode_execution_plan:
            return None
        for entry in episode_execution_plan.get("episodes", []) or []:
            if (
                entry.get("stage_index") == stage_index
                and entry.get("episode_index") == episode_index
            ):
                return entry
        return None

    def _transaction_step_skipped(
        self,
        plan_entry: dict[str, object] | None,
        execution_mode: str | None = None,
    ) -> bool:
        if plan_entry and plan_entry.get("transaction_step_skipped") is True:
            return True
        if str((plan_entry or {}).get("transaction_tier") or "").lower() == "skip":
            return True
        mode = execution_mode or (plan_entry or {}).get("mode")
        # Old checkpoints sometimes only stored mode. Explicit tiers take priority.
        return mode == "light" and not (plan_entry or {}).get("transaction_tier")

    def _episode_execution_mode(self, plan_entry: dict[str, object] | None) -> str:
        return str((plan_entry or {}).get("mode") or "light")

    def _result_locator_map(
        self,
        state: AgentState,
        agent_name: str,
    ) -> dict[tuple, Any]:
        result_map: dict[tuple, Any] = {}
        for item in state.get("agent_results", []):
            if agent_name not in item:
                continue
            locator = (item.get("_meta") or {}).get("episode_locator")
            if locator is not None:
                result_map[self._episode_locator_key(locator)] = item[agent_name]
        return result_map

    def _result_locator_meta_map(
        self,
        state: AgentState,
        agent_name: str,
    ) -> dict[tuple, dict[str, Any]]:
        meta_map: dict[tuple, dict[str, Any]] = {}
        for item in state.get("agent_results", []):
            if agent_name not in item:
                continue
            meta = item.get("_meta") or {}
            locator = meta.get("episode_locator")
            if locator is not None:
                meta_map[self._episode_locator_key(locator)] = meta
        return meta_map

    def _append_agent_result(
        self,
        state: AgentState,
        agent_name: str,
        parsed_result: Any,
        meta: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {agent_name: parsed_result}
        if meta:
            entry["_meta"] = meta
        state["agent_results"].append(entry)
        state["agent_executed"].append(agent_name)
        state.setdefault("cost", [])

    def _prompt_context_for_agent(
        self,
        state: AgentState,
        agent_name: str,
    ) -> tuple[str, str, dict[str, Any] | None, dict[str, Any]]:
        build_input = state["build_input"]
        event_skeleton = None
        if agent_name not in {"SkeletonReconstructor"}:
            event_skeleton = self._get_event_skeleton(state)

        if agent_name == "SkeletonChecker":
            proposed = self._latest_agent_result(state, "SkeletonReconstructor")
            return "", "", None, {"ProposedSkeleton": compact_values(proposed)}

        if agent_name == "EventDescriptionReconstructor":
            from .event_summary import overview_context
            overview, quotes = overview_context(self.integrate_results(state), build_input.samples)
            return "", "", None, {"EventCascade": overview, "Content": quotes}

        if agent_name == "StageDescriptionReconstructor":
            stage_index = state["agent_executed"].count("StageDescriptionReconstructor")
            stage = self.integrate_results(state)["stages"][stage_index]
            return self._scalar_value(stage.get("name")), "", None, {"TargetStage": compact_values(stage)}

        if agent_name in {
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        }:
            sequence_index = self._current_episode_sequence_index(state)
            (
                stage_index,
                episode_index,
                stage,
                episode,
                locator,
            ) = self._get_episode_by_sequence_index(event_skeleton, sequence_index)
            if stage is None or episode is None:
                raise ValueError("No target episode available for agent execution")
            plan_entry = self._get_episode_execution_plan_entry(
                state.get("episode_execution_plan"),
                stage_index,
                episode_index,
            )
            target_episode = episode_scope(episode)
            completed_stage_episodes = []
            for item in state["agent_results"]:
                if "EpisodeReconstructor" not in item:
                    continue
                loc = (item.get("_meta") or {}).get("episode_locator")
                if not loc:
                    continue
                if loc["stage_index"] == stage_index:
                    completed_stage_episodes.append(episode_scope(item["EpisodeReconstructor"]))
            extra: dict[str, Any] = {
                "EpisodeLocator": locator,
                "StageSkeleton": stage_scope(stage),
                "StageSparseCache": completed_stage_episodes,
                "ReconstructedParticipants": participant_registry(state["agent_results"]),
                "TargetEpisode": target_episode,
            }
            if agent_name in {"TransactionReconstructor", "EpisodeReconstructor"}:
                participants = self._latest_agent_result(
                    state, "ParticipantReconstructor"
                )
                if isinstance(participants, dict):
                    target_episode["participants"] = compact_values(participants.get("participants", []))
            if agent_name == "EpisodeReconstructor":
                transaction_skipped = self._transaction_step_skipped(plan_entry)
                transactions = (
                    {"transactions": []}
                    if transaction_skipped
                    else self._latest_agent_result(state, "TransactionReconstructor")
                )
                if isinstance(transactions, dict):
                    target_episode["transactions"] = compact_values(transactions.get("transactions", []))
                extra["TargetEpisode"] = target_episode
            return (
                self._scalar_value(stage.get("name")),
                self._scalar_value(episode.get("name")),
                plan_entry,
                extra,
            )

        return "", "", None, {}

    def _validate_agent_output(self, state: AgentState, agent_name: str, payload: Any) -> None:
        if agent_name in {"SkeletonReconstructor", "SkeletonChecker"}:
            valid, reason = self._validate_event_skeleton(payload)
            if not valid:
                raise ValueError(reason)
        validate_role(agent_name, payload)
        version = state.get("construction_contract_version", CONSTRUCTION_CONTRACT_VERSION)
        if version == CONSTRUCTION_CONTRACT_VERSION and agent_name in {"SkeletonReconstructor", "SkeletonChecker"}:
            for stage in payload["stages"]:
                for episode in stage["episodes"]:
                    check_temporal_scope(episode)
        if version == CONSTRUCTION_CONTRACT_VERSION and agent_name in {
            "ParticipantReconstructor", "TransactionReconstructor", "EpisodeReconstructor"
        }:
            _, _, _, target, _ = self._get_episode_by_sequence_index(
                self._get_event_skeleton(state), self._current_episode_sequence_index(state)
            )
            if agent_name == "ParticipantReconstructor":
                validate_participant_identity(payload["participants"], state["agent_results"])
                check_temporal_scope(target, participants=payload["participants"])
            elif agent_name == "TransactionReconstructor":
                check_temporal_scope(target, transactions=payload["transactions"])
            else:
                validate_episode_reuse(payload, target)
        if agent_name not in {"TransactionReconstructor", "EpisodeReconstructor"}:
            return
        participants = self._latest_agent_result(state, "ParticipantReconstructor")["participants"]
        participant_ids = {p["participant_id"] for p in participants}
        if agent_name == "TransactionReconstructor":
            validate_endpoints(payload["transactions"], participant_ids, "transactions")
            return
        skeleton = self._get_event_skeleton(state)
        si, ei, _, target, _ = self._get_episode_by_sequence_index(
            skeleton, self._current_episode_sequence_index(state)
        )
        if payload["episode_id"] != target["episode_id"] or payload["index_in_stage"] != ei:
            raise ValueError("Episode identity must match the target skeleton")
        assembled = copy.deepcopy(payload)
        if isinstance(assembled["participants"], str):
            assembled["participants"] = participants
        plan = self._get_episode_execution_plan_entry(state.get("episode_execution_plan"), si, ei)
        if self._transaction_step_skipped(plan):
            if isinstance(assembled["transactions"], list) and assembled["transactions"]:
                raise ValueError("Skipped transaction role cannot introduce transactions")
            assembled["transactions"] = []
        elif isinstance(assembled["transactions"], str) or not assembled["transactions"]:
            assembled["transactions"] = self._latest_agent_result(state, "TransactionReconstructor")["transactions"]
        validate_episode(assembled)

    def _review_episode_scope(self, state, agent_name, user_msg, savename, error, candidate):
        """Review a draft boundary once, retaining facts and an auditable old skeleton."""
        from .temporal_scope_review import SYSTEM, apply_revision, review_message, validate_proposal

        skeleton = self._get_event_skeleton(state)
        si, ei, _, target, locator = self._get_episode_by_sequence_index(
            skeleton, self._current_episode_sequence_index(state))
        participants = candidate.get("participants", []) if agent_name == "ParticipantReconstructor" else (
            self._latest_agent_result(state, "ParticipantReconstructor") or {}).get("participants", [])
        transactions = candidate.get("transactions", []) if agent_name == "TransactionReconstructor" else (
            (self._latest_agent_result(state, "TransactionReconstructor") or {}).get("transactions", [])
            if agent_name == "EpisodeReconstructor" else [])
        if agent_name == "EpisodeReconstructor":
            entry = self._get_episode_execution_plan_entry(state.get("episode_execution_plan"), si, ei)
            if self._transaction_step_skipped(entry):
                transactions = []
        review_name = "TemporalScopeReview-" + savename
        audit = {"agent": agent_name, "save_name": savename, "episode_locator": locator,
                 "before": copy.deepcopy(skeleton), "candidate": copy.deepcopy(candidate),
                 "conflict": copy.deepcopy(error.report), "status": "not_revised"}
        try:
            proposal = self._infer_and_parse_json("EpisodeScopeReviewer", SYSTEM,
                review_message(user_msg, skeleton, target, candidate, error), {}, review_name,
                validator=lambda value: validate_proposal(value, target,
                    state["build_input"].samples, participants, transactions))
        except Exception as exc:
            audit_name = "TemporalScopeAudit-" + savename
            review_calls = [row for row in getattr(self, "_call_records", [])
                            if row.get("save_name") == review_name]
            review_status = review_calls[-1]["status"] if review_calls else "not_called"
            audit.update(status="review_unavailable", review_error_type=type(exc).__name__,
                         review_status=review_status, semantic_approval=False)
            audit_saved = True
            try:
                self._save_agent_result(audit, audit_name)
            except OSError as save_error:
                audit_saved = False
                logging.getLogger(__name__).warning('Could not save %s (%s)',
                    audit_name, type(save_error).__name__)
            # Invalid review proposals never relax the original check. A local
            # response failure can use the ordinary bounded role correction;
            # transport/budget failures must not be misclassified as bad facts.
            if audit_saved and isinstance(exc, ValueError) and review_status in {
                    "invalid_output", "empty_response", "incomplete_response"}:
                return False
            raise ReviewUnavailableError("EpisodeScopeReviewer", audit_name, exc,
                                         audit_saved=audit_saved) from exc
        audit["review"] = copy.deepcopy(proposal)
        if proposal["decision"] != "revise_scope":
            if agent_name == "EpisodeReconstructor" and proposal["decision"] == "keep_scope":
                # A reviewed rejection of newly proposed boundaries retains the
                # canonical scene; extracted descriptions/actions remain intact.
                for key in ("start_time", "end_time"):
                    candidate[key] = copy.deepcopy(target.get(key))
                audit["status"] = "kept_scope"
                self._validate_agent_output(state, agent_name, candidate)
                self._save_agent_result(audit, "TemporalScopeAudit-" + savename)
                return True
            self._save_agent_result(audit, "TemporalScopeAudit-" + savename)
            return False
        revised = apply_revision(skeleton, si, ei, proposal["episode"])
        original = copy.deepcopy(skeleton)
        skeleton.clear()
        skeleton.update(revised)
        try:
            if agent_name == "EpisodeReconstructor":
                bound = bind_episode_scope(candidate, revised["stages"][si]["episodes"][ei])
                candidate.clear()
                candidate.update(bound)
            self._validate_agent_output(state, agent_name, candidate)
        except (TypeError, ValueError):
            skeleton.clear()
            skeleton.update(original)
            if agent_name == "EpisodeReconstructor":
                candidate.clear()
                candidate.update(copy.deepcopy(audit["candidate"]))
            audit["status"] = "revision_failed_validation"
            self._save_agent_result(audit, "TemporalScopeAudit-" + savename)
            return False
        audit.update(status="revised", after=copy.deepcopy(skeleton))
        self._save_agent_result(audit, "TemporalScopeAudit-" + savename)
        role = "SkeletonChecker" if self._latest_agent_result(state, "SkeletonChecker") is not None else "SkeletonReconstructor"
        count = sum(role in row for row in state["agent_results"])
        self._save_agent_result(skeleton, f"{role}-{count}")
        # Persist the revision in the same source artifact consumed by strict
        # replay; the audit above retains the exact previous checked skeleton.
        if getattr(self, "_temporal_conflicts", None):
            self._temporal_conflicts[-1].update(status="scope_revised", review_artifact=review_name)
            if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
                self.save_traces({"contract_version": 1, "semantic_support_checked": False,
                    "conflicts": self._temporal_conflicts}, "EpisodeScopeConflicts", "json")
        return True

    def _infer_person_phase(self, agent, system, user, name, validator):
        """Expose recorded provider failures to item/phase recovery uniformly."""
        start = len(getattr(self, "_call_records", []))
        try:
            return self._infer_and_parse_json(agent, system, user, {}, name, validator=validator)
        except Exception as error:
            calls = getattr(self, "_call_records", [])[start:]
            if calls and calls[-1].get("status") == "transport_error" and not isinstance(error, AssertionError):
                raise RuntimeError(f"{agent} provider request failed ({type(error).__name__}): {error}") from error
            raise

    def _infer_event_overview(self, state, system, user, kwargs, name, validator):
        from .event_summary import stage_summary_fallback
        start = len(getattr(self, "_call_records", []))
        try:
            result = self._infer_and_parse_json("EventDescriptionReconstructor",
                system, user, kwargs, name, validator=validator)
        except Exception as error:
            calls = getattr(self, "_call_records", [])[start:]
            local_failure = calls and calls[-1].get("status") in {
                "incomplete_response", "invalid_output", "empty_response", "transport_error"}
            budget_exhausted = (type(error) is RuntimeError
                and str(error) == "Configured model call limit reached")
            # Do not conceal programming errors, failed checkpoint writes or interrupts.
            if isinstance(error, AssertionError) or (isinstance(error, OSError) and not (
                    calls and calls[-1].get("status") == "transport_error")):
                raise
            if not local_failure and not budget_exhausted:
                raise
            result, origins = stage_summary_fallback(self.integrate_results(state))
            validator(result)
            self._summary_status = {"status": "degraded", "strategy": "existing_stage_descriptions",
                "error_type": type(error).__name__, "source_fields": origins,
                "result_sha256": digest(result), "partial_response_used": False,
                "detailed_facts_preserved": True, "semantic_approval": False}
            self._save_agent_result(result, name)
        else:
            self._summary_status = {"status": "completed", "strategy": "model_overview",
                "detailed_facts_preserved": True}
        if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
            self.save_traces(self._summary_status, "EventSummaryStatus", "json")
        return result

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """Execute one event reconstruction agent stage."""

        build_input = state["build_input"]
        context_assets = state.get("context_assets")
        target_stage, target_episode, episode_budget, extra = self._prompt_context_for_agent(
            state, agent_name
        )
        prompt_kwargs = self._build_prompt_kwargs(
            build_input=build_input,
            agent_name=agent_name,
            context_assets=context_assets,
            target_stage=target_stage,
            target_episode=target_episode,
            episode_budget=episode_budget,
            **extra,
        )
        system_msg, user_msg = self._format_agent_messages(agent_name, prompt_kwargs)
        savename = self._agent_save_name(state, agent_name)
        relation_guard = None
        if agent_name == "EpisodeReconstructor":
            relation_guard = CounterpartyEvidenceGuard(
                prompt_kwargs["Content"],
                self._latest_agent_result(state, "ParticipantReconstructor")["participants"],
                infer=lambda system, user, name, validator: self._infer_and_parse_json(
                    "CounterpartyEvidenceReview", system, user, {}, name, validator=validator),
                save=lambda data, name: self._save_agent_result(data, name), name=savename)

        def validate_output(payload):
            if agent_name == "EpisodeReconstructor" and isinstance(payload, dict):
                _, _, _, target, _ = self._get_episode_by_sequence_index(
                    self._get_event_skeleton(state), self._current_episode_sequence_index(state))
                bound = bind_episode_scope(payload, target)
                if bound != payload:
                    self._save_agent_result({"original": copy.deepcopy(payload),
                        "target_scope": episode_scope(target)}, "EpisodeScopeBinding-" + savename)
                    payload.clear()
                    payload.update(bound)
            self._validate_agent_output(state, agent_name, payload)
            if relation_guard is not None:
                relation_guard(payload)

        if agent_name == "EventDescriptionReconstructor":
            parsed_result = self._infer_event_overview(state, system_msg, user_msg,
                prompt_kwargs, savename, validate_output)
        else:
            parsed_result = self._infer_and_parse_json(
                agent_name,
                system_msg,
                user_msg,
                prompt_kwargs,
                savename,
                validator=validate_output,
                temporal_reviewer=(lambda error, candidate: self._review_episode_scope(
                    state, agent_name, user_msg, savename, error, candidate))
                    if agent_name in {"ParticipantReconstructor", "TransactionReconstructor", "EpisodeReconstructor"} else None,
            )
        meta: dict[str, Any] | None = None
        if agent_name in {
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        }:
            event_skeleton = self._get_event_skeleton(state)
            sequence_index = self._current_episode_sequence_index(state)
            stage_index, episode_index, _, _, locator = self._get_episode_by_sequence_index(
                event_skeleton,
                sequence_index,
            )
            plan_entry = self._get_episode_execution_plan_entry(
                state.get("episode_execution_plan"),
                stage_index,
                episode_index,
            )
            meta = {
                "episode_locator": locator,
                "execution_mode": self._episode_execution_mode(plan_entry),
                "transaction_step_skipped": self._transaction_step_skipped(plan_entry),
            }
            if plan_entry:
                for key in (
                    "participant_tier",
                    "transaction_tier",
                    "episode_detail_tier",
                    "conflict_guard",
                    "compactness_hint",
                ):
                    if key in plan_entry:
                        meta[key] = plan_entry[key]
        self._append_agent_result(state, agent_name, parsed_result, meta)
        if meta:
            self._save_agent_result({agent_name: parsed_result, "_meta": meta}, savename)
        if agent_name == "SkeletonChecker":
            state["episode_execution_plan"] = self._build_episode_execution_plan(
                build_input,
                parsed_result,
                context_assets=context_assets,
            )
            self._save_agent_result(state["episode_execution_plan"], "EpisodeExecutionPlan")
        if agent_name == "ParticipantReconstructor" and getattr(self, "save_dir", None):
            self.save_traces(participant_registry(state["agent_results"]), "ParticipantIdentityMap", "json")
        return state

    def _route_after_participant_reconstructor(self, state: AgentState):
        event_skeleton = self._get_event_skeleton(state)
        sequence_index = self._current_episode_sequence_index(state)
        stage_index, episode_index, _, _, _ = self._get_episode_by_sequence_index(
            event_skeleton,
            sequence_index,
        )
        plan_entry = self._get_episode_execution_plan_entry(
            state.get("episode_execution_plan"),
            stage_index,
            episode_index,
        )
        if self._transaction_step_skipped(plan_entry):
            return "EpisodeReconstructor"
        return "TransactionReconstructor"

    def get_completed_stage_index(self, state: AgentState) -> int:
        event_skeleton = self._get_event_skeleton(state)
        episodes_completed = state["agent_executed"].count("EpisodeReconstructor")
        cumulative_episodes = 0
        for stage_index, stage in enumerate(event_skeleton.get("stages", []) or []):
            cumulative_episodes += len(stage.get("episodes", []) or [])
            if episodes_completed == cumulative_episodes:
                return stage_index
        return -1

    def _route_after_episode_reconstructor(self, state: AgentState):
        event_skeleton = self._get_event_skeleton(state)
        total_episodes = sum(
            len(stage.get("episodes", []) or [])
            for stage in event_skeleton.get("stages", []) or []
        )
        executed_episodes = state["agent_executed"].count("EpisodeReconstructor")
        completed_stage_index = self.get_completed_stage_index(state)
        executed_stage_descriptions = state["agent_executed"].count(
            "StageDescriptionReconstructor"
        )
        if (
            completed_stage_index != -1
            and completed_stage_index == executed_stage_descriptions
        ):
            return "StageDescriptionReconstructor"
        if executed_episodes < total_episodes:
            return "ParticipantReconstructor"
        return END

    def _route_after_stage_description_reconstructor(self, state: AgentState):
        event_skeleton = self._get_event_skeleton(state)
        total_stages = len(event_skeleton.get("stages", []) or [])
        executed_stage_descriptions = state["agent_executed"].count(
            "StageDescriptionReconstructor"
        )
        if executed_stage_descriptions < total_stages:
            return "ParticipantReconstructor"
        return "EventDescriptionReconstructor"

    def graph(self):
        """Construct the context-aware event reconstruction graph when available."""

        graph = StateGraph(SparseAgentState)
        if not hasattr(graph, "add_conditional_edges"):
            return None
        for agent_name in (
            "SkeletonReconstructor",
            "SkeletonChecker",
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
            "StageDescriptionReconstructor",
            "EventDescriptionReconstructor",
        ):
            graph.add_node(agent_name, partial(self.execute_agent, agent_name=agent_name))
        graph.set_entry_point("SkeletonReconstructor")
        graph.add_edge("SkeletonReconstructor", "SkeletonChecker")
        graph.add_edge("SkeletonChecker", "ParticipantReconstructor")
        graph.add_conditional_edges(
            "ParticipantReconstructor",
            self._route_after_participant_reconstructor,
            {
                "TransactionReconstructor": "TransactionReconstructor",
                "EpisodeReconstructor": "EpisodeReconstructor",
            },
        )
        graph.add_edge("TransactionReconstructor", "EpisodeReconstructor")
        graph.add_conditional_edges(
            "EpisodeReconstructor",
            self._route_after_episode_reconstructor,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "StageDescriptionReconstructor": "StageDescriptionReconstructor",
                END: END,
            },
        )
        graph.add_conditional_edges(
            "StageDescriptionReconstructor",
            self._route_after_stage_description_reconstructor,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "EventDescriptionReconstructor": "EventDescriptionReconstructor",
            },
        )
        graph.add_edge("EventDescriptionReconstructor", END)
        return graph.compile()

    def _run_state_machine(self, state: AgentState) -> AgentState:
        state = self.execute_agent(state, "SkeletonReconstructor")
        state = self.execute_agent(state, "SkeletonChecker")
        event_skeleton = self._get_event_skeleton(state)
        total_episodes = sum(
            len(stage.get("episodes", []) or [])
            for stage in event_skeleton.get("stages", []) or []
        )
        for _ in range(total_episodes):
            state = self.execute_agent(state, "ParticipantReconstructor")
            if self._route_after_participant_reconstructor(state) == "TransactionReconstructor":
                state = self.execute_agent(state, "TransactionReconstructor")
            state = self.execute_agent(state, "EpisodeReconstructor")
            if (
                self._route_after_episode_reconstructor(state)
                == "StageDescriptionReconstructor"
            ):
                state = self.execute_agent(state, "StageDescriptionReconstructor")
        state = self.execute_agent(state, "EventDescriptionReconstructor")
        return state

    def _unwrap_agent_payload(self, payload: object, agent_name: str) -> object:
        if isinstance(payload, dict) and agent_name in payload:
            return payload[agent_name]
        return payload

    def integrate_results(self, state: AgentState) -> dict[str, Any]:
        """Integrate agent outputs into a final EventCascade dictionary."""

        final_cascade = copy.deepcopy(self._get_event_skeleton(state))
        episode_execution_plan = state.get("episode_execution_plan") or {"episodes": []}
        episode_locator_map = self._result_locator_map(state, "EpisodeReconstructor")
        episode_meta_map = self._result_locator_meta_map(state, "EpisodeReconstructor")
        participant_locator_map = self._result_locator_map(
            state, "ParticipantReconstructor"
        )
        transaction_locator_map = self._result_locator_map(
            state, "TransactionReconstructor"
        )
        episode_results = [
            item["EpisodeReconstructor"]
            for item in state.get("agent_results", [])
            if "EpisodeReconstructor" in item
        ]
        participant_results = [
            item["ParticipantReconstructor"]
            for item in state.get("agent_results", [])
            if "ParticipantReconstructor" in item
        ]
        transaction_results = [
            item["TransactionReconstructor"]
            for item in state.get("agent_results", [])
            if "TransactionReconstructor" in item
        ]

        episode_idx = 0
        transaction_idx = 0
        for stage_index, stage in enumerate(final_cascade.get("stages", []) or []):
            for episode_index, episode in enumerate(stage.get("episodes", []) or []):
                locator = self._episode_locator(
                    stage_index,
                    episode_index,
                    self._scalar_value(stage.get("stage_id")),
                    self._scalar_value(episode.get("episode_id")),
                )
                locator_key = self._episode_locator_key(locator)
                episode_result = episode_locator_map.get(locator_key)
                if (
                    episode_result is None
                    and not episode_locator_map
                    and episode_idx < len(episode_results)
                ):
                    episode_result = episode_results[episode_idx]
                participant_result = participant_locator_map.get(locator_key)
                if (
                    participant_result is None
                    and not participant_locator_map
                    and episode_idx < len(participant_results)
                ):
                    participant_result = participant_results[episode_idx]
                plan_entry = self._get_episode_execution_plan_entry(
                    episode_execution_plan,
                    stage_index,
                    episode_index,
                )
                episode_meta = episode_meta_map.get(locator_key, {})
                execution_mode = (
                    episode_meta.get("execution_mode")
                    or (self._episode_execution_mode(plan_entry) if plan_entry else None)
                )
                transaction_skipped = self._transaction_step_skipped(
                    plan_entry or episode_meta,
                    execution_mode=execution_mode,
                )
                transaction_result = transaction_locator_map.get(locator_key)
                if (
                    transaction_result is None
                    and not transaction_locator_map
                    and not transaction_skipped
                    and transaction_idx < len(transaction_results)
                ):
                    transaction_result = transaction_results[transaction_idx]

                if isinstance(episode_result, dict):
                    episode.update(episode_result)
                if isinstance(participant_result, dict) and (
                    not isinstance(episode_result, dict)
                    or not isinstance(episode_result.get("participants"), list)
                ):
                    episode["participants"] = participant_result.get("participants", [])
                if transaction_skipped:
                    episode["transactions"] = []
                elif isinstance(transaction_result, dict):
                    if (
                        not isinstance(episode_result, dict)
                        or not isinstance(episode_result.get("transactions"), list)
                        or not episode_result["transactions"]
                    ):
                        episode["transactions"] = transaction_result.get("transactions", [])
                    if not transaction_locator_map:
                        transaction_idx += 1
                else:
                    episode["transactions"] = []
                episode_idx += 1

        stage_description_results = [
            item["StageDescriptionReconstructor"]
            for item in state.get("agent_results", [])
            if "StageDescriptionReconstructor" in item
        ]
        for index, stage in enumerate(final_cascade.get("stages", []) or []):
            if index < len(stage_description_results):
                descriptions = stage_description_results[index].get("descriptions", [])
                stage["descriptions"] = descriptions

        event_description = self._latest_agent_result(
            state, "EventDescriptionReconstructor"
        )
        if isinstance(event_description, dict) and "descriptions" in event_description:
            final_cascade["descriptions"] = event_description["descriptions"]
        return final_cascade

    def _replay_episode_locator_from_filename(
        self,
        filename: str,
        event_skeleton: dict[str, Any] | None,
    ) -> dict[str, object] | None:
        match = _REPLAY_STAGE_EPISODE_SUFFIX.search(filename)
        if not match:
            return None
        stage_index = int(match.group("stage"))
        episode_index = int(match.group("episode"))
        stage = ((event_skeleton or {}).get("stages", []) or [None])[stage_index]
        episode = (stage.get("episodes", []) or [None])[episode_index] if stage else None
        return self._episode_locator(
            stage_index,
            episode_index,
            self._scalar_value((stage or {}).get("stage_id")),
            self._scalar_value((episode or {}).get("episode_id")),
        )

    def integrate_from_files(self, *, strict=False) -> dict[str, Any]:
        """Reconstruct the final EventCascade from saved agent result files."""

        if not hasattr(self, "save_dir") or not os.path.exists(self.save_dir):
            raise FileNotFoundError(f"Save directory {getattr(self, 'save_dir', None)} does not exist.")

        manifest_path = Path(self.save_dir) / "RunManifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        if manifest.get("person_pipeline_version") == "canonical-person-v1":
            from finmy.person_epg.compat_projection import project_person_epg
            from finmy.subject_graph.compat import to_event_cascade
            return to_event_cascade(project_person_epg(self.integrate_person_from_files(strict=strict)))
        contract_version = manifest.get("construction_contract_version", 1)
        if type(contract_version) is not int or contract_version not in {1, CONSTRUCTION_CONTRACT_VERSION}:
            raise ValueError("Unsupported construction contract version")
        if strict:
            if manifest.get("status") != "completed":
                raise ValueError("Strict replay requires a completed run")
            recorded = manifest.get("artifact_sha256")
            if not isinstance(recorded, dict) or not recorded:
                raise ValueError("Strict replay requires artifact hashes")
            actual = self._artifact_hashes()
            if actual != recorded:
                raise ValueError("Replay artifacts are incomplete or changed (hash mismatch)")

        dummy_state = self._load_saved_state(contract_version)
        plan_path = os.path.join(self.save_dir, "EpisodeExecutionPlan-Result.json")
        if strict or os.path.isfile(plan_path):
            self._validate_replay_completeness(dummy_state)
        cascade = self.integrate_results(dummy_state)
        if strict or os.path.isfile(plan_path):
            validate_cascade(cascade)
        if contract_version == CONSTRUCTION_CONTRACT_VERSION:
            report = construction_report(cascade)
            if strict:
                recorded = json.loads((Path(self.save_dir) / "ConstructionCheck.json").read_text())
                if report != recorded:
                    raise ValueError("Replay construction checks differ from saved report")
        return cascade

    def _load_saved_state(self, contract_version=CONSTRUCTION_CONTRACT_VERSION):
        """Read only accepted role artifacts; raw failed responses are never replayed."""
        indexed_files: list[tuple[int, str, str]] = []
        for filename in os.listdir(self.save_dir):
            if not filename.endswith("-Result.json"):
                continue
            parts = filename.removesuffix("-Result.json").split("-")
            if len(parts) < 2 or parts[0] not in get_agent_prompts()[0]:
                continue
            try:
                index = int(parts[1])
            except ValueError:
                continue
            indexed_files.append((index, parts[0], filename))
        if not indexed_files:
            raise FileNotFoundError(f"No result files found in {self.save_dir}")

        loaded_results: list[tuple[int, str, str, object, object]] = []
        for index, agent_name, filename in sorted(indexed_files):
            with open(os.path.join(self.save_dir, filename), "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            result = self._unwrap_agent_payload(payload, agent_name)
            loaded_results.append((index, agent_name, filename, payload, result))

        checked_skeleton = None
        reconstructed_skeleton = None
        for _, agent_name, _, _, result in loaded_results:
            if agent_name == "SkeletonChecker":
                checked_skeleton = result
            elif agent_name == "SkeletonReconstructor":
                reconstructed_skeleton = result
        event_skeleton = checked_skeleton or reconstructed_skeleton

        agent_results: list[dict[str, Any]] = []
        for _, agent_name, filename, payload, result in loaded_results:
            entry: dict[str, Any] = {agent_name: result, "_replay_filename": filename}
            meta = (
                dict(payload.get("_meta", {}))
                if isinstance(payload, dict) and isinstance(payload.get("_meta"), dict)
                else {}
            )
            locator = meta.get("episode_locator") or self._replay_episode_locator_from_filename(
                filename,
                event_skeleton,
            )
            if locator is not None:
                meta["episode_locator"] = locator
            if meta:
                entry["_meta"] = meta
            agent_results.append(entry)

        plan_path = os.path.join(self.save_dir, "EpisodeExecutionPlan-Result.json")
        plan = {"episodes": []}
        if os.path.isfile(plan_path):
            with open(plan_path, encoding="utf-8") as fh:
                plan = json.load(fh)
        dummy_state: AgentState = {
            "agent_results": agent_results,
            "agent_executed": [next(iter(item)) for item in agent_results],
            "episode_execution_plan": plan,
            "construction_contract_version": contract_version,
        }
        return dummy_state

    def _artifact_hashes(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(Path(self.save_dir).glob("*.json"))
                if path.name not in {"RunManifest.json", "GanttStatus.json"}}

    def _validate_replay_completeness(self, state, *, include_event_description=True):
        skeleton = self._get_event_skeleton(state)
        validate_role("SkeletonChecker", skeleton)
        expected = ["SkeletonReconstructor", "SkeletonChecker"]
        for si, stage in enumerate(skeleton["stages"]):
            for ei, _ in enumerate(stage["episodes"]):
                expected.append("ParticipantReconstructor")
                plan = self._get_episode_execution_plan_entry(state["episode_execution_plan"], si, ei)
                if not plan:
                    raise ValueError("Replay is missing an episode execution plan")
                if not self._transaction_step_skipped(plan):
                    expected.append("TransactionReconstructor")
                expected.append("EpisodeReconstructor")
            expected.append("StageDescriptionReconstructor")
        if include_event_description:
            expected.append("EventDescriptionReconstructor")
        if sorted(state["agent_executed"]) != sorted(expected):
            raise ValueError("Replay role sequence is incomplete or duplicated")
        queues = {role: [item for item in state["agent_results"] if role in item] for role in set(expected)}
        ordered = [queues[role].pop(0) for role in expected]
        state["agent_results"] = ordered
        state["agent_executed"] = expected
        replay = {"agent_results": [], "agent_executed": [],
                  "episode_execution_plan": state["episode_execution_plan"],
                  "construction_contract_version": state.get("construction_contract_version", 1)}
        for role, item in zip(expected, state["agent_results"]):
            if item["_replay_filename"] != self._agent_save_name(replay, role) + "-Result.json":
                raise ValueError("Replay filename does not match its role or episode")
            self._validate_agent_output(replay, role, item[role])
            if role in {"ParticipantReconstructor", "TransactionReconstructor", "EpisodeReconstructor"}:
                _, _, _, _, locator = self._get_episode_by_sequence_index(
                    skeleton, replay["agent_executed"].count("EpisodeReconstructor"))
                if item.get("_meta", {}).get("episode_locator") != locator:
                    raise ValueError("Replay locator does not match the checked skeleton")
            replay["agent_results"].append(item)
            replay["agent_executed"].append(role)

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the full context-aware event reconstruction pipeline."""

        validate_input(build_input)
        reconstruction = read_reconstruction(self.build_config)
        if getattr(self, "_run_started", False):
            raise RuntimeError("Create a new builder for each run; implicit resume is not supported")
        self._run_started = True
        self._call_records = []
        self._prior_call_count = 0
        self._temporal_conflicts = []
        self._organization_validation_errors = []
        inputs, manifest = run_identity(build_input, self.build_config)
        manifest["builder_type"] = self.builder_type
        manifest["construction_contract_version"] = CONSTRUCTION_CONTRACT_VERSION
        manifest["evidence_contract_version"] = EVIDENCE_CONTRACT_VERSION
        if reconstruction["mode"] == "person":
            from .person_organization import ORGANIZATION_CONTRACT_VERSION
            from .organization_batches import ORGANIZATION_EXECUTION_VERSION
            manifest["person_organization_contract_version"] = ORGANIZATION_CONTRACT_VERSION
            manifest["organization_execution_version"] = ORGANIZATION_EXECUTION_VERSION
            manifest["person_pipeline_version"] = "canonical-person-v1"
        persist = bool(getattr(self, "save_dir", None) and os.path.isdir(self.save_dir))
        if persist:
            if os.path.exists(os.path.join(self.save_dir, "RunManifest.json")):
                raise RuntimeError("Run directory already contains a manifest")
            self.save_traces(inputs, "BuildInput", "json")
            self.save_traces(manifest, "RunManifest", "json")
        started = time.perf_counter()
        output = None
        try:
            if reconstruction["mode"] == "person":
                # Person facts have their own lifecycle; a legacy event skeleton
                # is neither the factual source nor an extraction prerequisite.
                output = BuildOutput(result={"cost": []}, logs=[], extras={})
                output = self._complete_person(build_input, output, reconstruction["subject"])
            else:
                output = self._run_validated(build_input)
            manifest.update(status="completed", event_id=(
                output.extras["person_epg"]["graph"]["graph_id"]
                if reconstruction["mode"] == "person" else output.event_cascades["event_id"]))
            return output
        except BaseException as exc:
            manifest.update(status="failed", error_type=type(exc).__name__, error_message=str(exc))
            # Accepted roles are durable artifacts, not a completed graph. Give
            # callers an explicit checkpoint boundary without claiming that
            # arbitrary partial extraction has an automatic resume path.
            interruption = {
                "status": "checkpointed_incomplete", "error_type": type(exc).__name__,
                "accepted_result_artifacts": sorted({row["save_name"] + "-Result.json"
                    for row in self._call_records if row.get("status") in {"accepted", "recovered"}}),
                "pending_candidate_artifacts": sorted({row["pending_candidate_artifact"]
                    for row in self._call_records if row.get("pending_candidate_artifact")}),
                "recovery_scope": "canonical_person_reorganization"
                    if reconstruction["mode"] == "person" else "manual_extraction_recovery",
                "final_artifact_allowed": False,
            }
            if self._call_records:
                last_call = self._call_records[-1]
                interruption["last_call"] = {key: last_call[key] for key in
                    ("agent", "save_name", "status", "error_type") if key in last_call}
            manifest["interruption"] = interruption
            if persist:
                try:
                    self.save_traces(interruption, "BuildInterruption", "json")
                except OSError as save_error:
                    interruption["checkpoint_write_error_type"] = type(save_error).__name__
                    logging.getLogger(__name__).warning('Could not save BuildInterruption (%s)',
                        type(save_error).__name__)
            raise
        finally:
            if hasattr(self, "_summary_status"):
                manifest["event_summary"] = copy.deepcopy(self._summary_status)
            manifest.update(elapsed_seconds=time.perf_counter() - started,
                            usage=summarize_calls(self._call_records))
            if persist:
                try:
                    manifest["artifact_sha256"] = self._artifact_hashes()
                    self.save_traces(manifest, "RunManifest", "json")
                except OSError as save_error:
                    if manifest["status"] != "failed":
                        raise
                    logging.getLogger(__name__).warning('Could not finalize failed RunManifest (%s)',
                        type(save_error).__name__)

            if manifest["status"] == "completed" and output is not None:
                output.extras.update(builder_type=self.builder_type,
                                     run_directory=getattr(self, "save_dir", None),
                                     elapsed_seconds=manifest["elapsed_seconds"],
                                     usage=copy.deepcopy(manifest["usage"]))

    def _complete_person(self, build_input, output, subject, *, package=None, canonical_checkpoint=None):
        """Canonical facts first, then organization and independent exports.

        ``package`` imports paid-for legacy facts. It is never trusted as a
        completed canonical checkpoint merely because its JSON is valid.
        """
        from finmy.person_epg.sparse_adapter import build_person_facts, ground_person_evidence
        from finmy.person_epg.compat_projection import project_person_epg
        from finmy.person_epg.validation import validate_person_epg
        from .person_organization import apply_organization
        from .organization_batches import organize_person_plan
        storyline_plan = (getattr(build_input.user_query, "extras", None) or {}).get("storyline_plan")
        from .person_fact_pipeline import build_canonical_facts, canonical_input_hash
        mapping = {"mode": "canonical_person", "legacy_import": False}
        imported_mapping = None
        if package is None and output.event_cascades:
            package, imported_mapping = build_person_facts(output.event_cascades, build_input, subject)
            mapping["legacy_import"] = True
        elif package is not None:
            mapping["legacy_import"] = canonical_checkpoint is None
        def save_canonical(data, name):
            if getattr(self, "save_dir", None) and os.path.isdir(self.save_dir):
                self.save_traces(data, name, "json")
        checkpoint = canonical_checkpoint or {}
        audit = checkpoint.get("audit", {})
        cached = checkpoint.get("package")
        reusable = (audit.get("version") == "canonical-person-v1"
                    and audit.get("status") == "completed"
                    and audit.get("phase") == "completed"
                    and audit.get("input_sha256") == canonical_input_hash(build_input, subject, storyline_plan)
                    and cached is not None and audit.get("package_sha256") == digest(cached)
                    and validate_person_epg(cached)["valid"])
        if reusable:
            package, audit = copy.deepcopy(cached), copy.deepcopy(audit)
        else:
            package, audit = build_canonical_facts(build_input, subject,
                infer=lambda system, user, name, validator: self._infer_person_phase(
                    "PersonFacts", system, user, name, validator),
                save=save_canonical, seed=package, checkpoint=canonical_checkpoint,
                storyline_plan=storyline_plan,
                output_language=self._event_config_value("output_language", "English"))
        save_canonical(package, "PersonCanonicalFacts")
        save_canonical(audit, "PersonCanonicalAudit")
        if imported_mapping is not None:
            save_canonical(imported_mapping, "PersonLegacyImportMap")
        mapping.update(canonical_input_sha256=audit.get("input_sha256"),
                       canonical_package_sha256=audit.get("package_sha256"),
                       activity_ids=[r["activity_id"] for r in package["activity"]],
                       source_document_ids=[r["document_id"] for r in package["source_document"]],
                       operations_artifact="PersonCanonicalAudit.json")
        save_canonical(mapping, "PersonMappingReport")
        if not package.get("activity"):
            raise ValueError("No usable person facts were extracted. Source text and the factual checkpoint "
                             "were preserved; inspect PersonCanonicalAudit.json and resume this run.")
        organization_options = {"storyline_plan": storyline_plan} if storyline_plan is not None else {}
        from .organization_resume import OrganizationResume
        organization_resume = OrganizationResume(self)
        plan = organize_person_plan(
            package, {}, subject,
            self._event_config_value("output_language", "English"),
            infer=organization_resume.infer,
            save=self._save_agent_result,
            **organization_options,
        )
        self._save_agent_result(plan, "PersonOrganization")
        person, organization = apply_organization(package, plan)
        from .person_overview import complete_overview
        person, self._summary_status = complete_overview(person, plan,
            infer=lambda system, user, name, validator: self._infer_person_phase(
                "PersonOverview", system, user, name, validator),
            save=save_canonical,
            output_language=self._event_config_value("output_language", "English"))
        evidence = ground_person_evidence(person)
        validation = validate_person_epg(person)
        policy = self._event_config_value("evidence_policy", "report")
        blocked = policy == "strict" and evidence["unmatched_quote_count"] > 0
        acceptance = {
            "contract_version": 1, "policy": policy,
            "structure_passed": validation["valid"],
            "quote_check_passed": evidence["unmatched_quote_count"] == 0,
            "unmatched_quotes": evidence["unmatched_quote_count"],
            "fields_without_quotes": len(evidence["fields_without_quotes"]),
            "episode_scope_conflicts": len(getattr(self, "_temporal_conflicts", [])),
            "semantic_approval": False,
            "final_artifact_allowed": validation["valid"] and not blocked,
            "status": "quote_gate_blocked" if blocked else "draft_requires_content_review",
        }
        acceptance["fact_status"] = audit.get("status", "partial")
        if audit.get("status") != "completed" and not blocked:
            acceptance["status"] = "partial_facts_requires_review"
        persist = bool(getattr(self, "save_dir", None) and os.path.isdir(self.save_dir))
        if persist:
            for name, data in (("CandidatePersonEPG", person), ("PersonMappingReport", mapping),
                               ("PersonOrganizationReport", organization),
                               ("PersonEvidenceCheck", evidence), ("PersonAcceptance", acceptance)):
                self.save_traces(data, name, "json")
        pending_keys = ("pending_occurrence_ids", "pending_activity_ids", "pending_event_ids")
        if any(plan.get(key) for key in pending_keys):
            for key in pending_keys:
                if plan.get(key):
                    acceptance[key] = list(plan[key])
            if not blocked:
                acceptance["status"] = "partial_organization_requires_review"
            if persist:
                self.save_traces(acceptance, "PersonAcceptance", "json")
        if not validation["valid"]:
            raise ValueError("Person EPG validation failed: " + json.dumps(validation["errors"][:5]))
        if blocked:
            raise ValueError("Person EPG contains quotes absent or ambiguous in the supplied sources")
        projection = None
        legacy_cascade = None
        projection_status = {"status": "completed"}
        try:
            projection = project_person_epg(person)
            from finmy.subject_graph.compat import to_event_cascade
            legacy_cascade = to_event_cascade(projection)
        except (ValueError, TypeError) as error:
            # The legacy projection has stricter temporal containers than the
            # native person schema. Its failure is an export outcome, not grounds
            # for deleting a validated native graph or suppressing its HTML.
            projection_status = {"status": "failed", "error_type": type(error).__name__,
                                 "message": str(error), "native_person_preserved": True}
            projection = None
            legacy_cascade = None
        if persist:
            self.save_traces(person, "FinalPersonEPG", "json")
            self.save_traces(projection_status, "SubjectProjectionStatus", "json")
            if projection is not None:
                self.save_traces(projection, "FinalSubjectGraph", "json")
            if legacy_cascade is not None:
                self.save_traces(legacy_cascade, "FinalEventCascade", "json")
            # Rendering is an independent presentation outcome, not a fact mutation.
            render_status = {"status": "completed"}
            try:
                from finmy.person_epg.visualizer import render_person_epg
                render_person_epg(person, Path(self.save_dir) / "FinalPersonEPG.html")
            except Exception as exc:
                render_status = {"status": "failed", "error_type": type(exc).__name__}
            self.save_traces(render_status, "PersonRenderStatus", "json")
        output.subject_graph = projection
        output.event_cascades = legacy_cascade
        output.logs.append("PersonOrganization")
        output.extras["agent_executed"] = [*output.extras.get("agent_executed", []), "PersonOrganization"]
        output.extras.update(person_epg=person, subject_graph=projection,
                             person_pipeline_version="canonical-person-v1",
                             canonical_facts=audit, event_summary=copy.deepcopy(self._summary_status),
                             compat_projection=projection_status,
                             person_acceptance=acceptance, person_organization=organization,
                             calls=copy.deepcopy(self._call_records))
        if isinstance(output.result, dict):
            output.result["cost"] = copy.deepcopy(self._call_records)
        return output

    def integrate_person_from_files(self, *, strict=True):
        """Rebuild the person package from source artifacts without model calls."""
        from finmy.person_epg.sparse_adapter import build_person_facts, ground_person_evidence
        from finmy.person_epg.compat_projection import project_person_epg
        from finmy.person_epg.validation import validate_person_epg
        from finmy.generic import UserQueryInput, DataSample
        from .person_organization import apply_organization, ORGANIZATION_CONTRACT_VERSION

        root = Path(self.save_dir)
        manifest = json.loads((root / "RunManifest.json").read_text(encoding="utf-8"))
        version = manifest.get("person_organization_contract_version")
        if type(version) is not int or version != ORGANIZATION_CONTRACT_VERSION:
            raise ValueError("Unsupported person organization contract version")
        config = {"builder_type": "SparseRagBuilder", **manifest["effective_config"]}
        reconstruction = read_reconstruction(config)
        if reconstruction["mode"] != "person":
            raise ValueError("This run does not record a Sparse person reconstruction")
        inputs = json.loads((root / "BuildInput.json").read_text(encoding="utf-8"))
        if strict and (digest(inputs) != manifest.get("input_sha256")
                       or digest(manifest["effective_config"]) != manifest.get("config_sha256")):
            raise ValueError("Replay input or effective configuration hash mismatch")
        build_input = BuildInput(UserQueryInput(**inputs["user_query"]),
                                 [DataSample(**item) for item in inputs["samples"]])
        canonical = manifest.get("person_pipeline_version") == "canonical-person-v1"
        if canonical:
            if strict and self._artifact_hashes() != manifest.get("artifact_sha256"):
                raise ValueError("Canonical person artifacts are incomplete or changed")
            package = json.loads((root / "PersonCanonicalFacts.json").read_text(encoding="utf-8"))
            audit = json.loads((root / "PersonCanonicalAudit.json").read_text(encoding="utf-8"))
            from .person_fact_pipeline import canonical_input_hash
            storyline = (getattr(build_input.user_query, "extras", None) or {}).get("storyline_plan")
            if (audit.get("version") != "canonical-person-v1"
                    or audit.get("input_sha256") != canonical_input_hash(build_input, reconstruction["subject"], storyline)
                    or audit.get("package_sha256") != digest(package)):
                raise ValueError("Canonical fact checkpoint does not match the recorded inputs")
            mapping = json.loads((root / "PersonMappingReport.json").read_text(encoding="utf-8"))
        else:
            # Read-only replay of pre-canonical artifacts remains supported.
            cascade = self.integrate_from_files(strict=strict)
            package, mapping = build_person_facts(cascade, build_input, reconstruction["subject"])
            repair_path = root / "PersonFactRepair-Result.json"
            if repair_path.exists():
                from .person_fact_repair import replay_facts
                package = replay_facts(package, json.loads(repair_path.read_text(encoding="utf-8")))
        plan = json.loads((root / "PersonOrganization-Result.json").read_text(encoding="utf-8"))
        person, organization = apply_organization(package, plan)
        if canonical:
            from .person_overview import apply_overview
            overview = json.loads((root / "PersonOverviewResult.json").read_text(encoding="utf-8"))
            final_events = [{"event_id": r["event_id"], "label": r["label"], "summary": r["summary"]}
                            for r in plan["events"]]
            if overview.get("input_sha256") != digest(final_events):
                raise ValueError("Overview was generated for different event memberships")
            person = apply_overview(person, overview["fields"])
        evidence = ground_person_evidence(person)
        if not validate_person_epg(person)["valid"]:
            raise ValueError("Replayed Person EPG is invalid")
        # Run provenance stores absent optional sections as null.
        replay_config = {key: value for key, value in config.items()
                         if key not in {"sparse_builder_config", "event_builder_config"} or value is not None}
        policy = sparse_options(replay_config)
        if policy.get("evidence_policy", "report") not in {"report", "strict"}:
            raise ValueError("Unsupported replay evidence policy")
        if policy.get("evidence_policy", "report") == "strict" and evidence["unmatched_quote_count"]:
            raise ValueError("Replayed Person EPG fails the strict evidence policy")
        if strict:
            comparisons = [("FinalPersonEPG", person), ("PersonEvidenceCheck", evidence),
                           ("PersonMappingReport", mapping), ("PersonOrganizationReport", organization)]
            status_path = root / "SubjectProjectionStatus.json"
            projection_status = json.loads(status_path.read_text()) if status_path.exists() else {}
            if projection_status.get("status") == "failed":
                if (root / "FinalSubjectGraph.json").exists():
                    raise ValueError("Failed projection must not have a final legacy graph")
            else:
                comparisons.append(("FinalSubjectGraph", project_person_epg(person)))
            for name, actual in comparisons:
                recorded = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
                if recorded != actual:
                    raise ValueError(f"Replayed {name} does not match the saved artifact")
        return person

    def _run_validated(self, build_input):
        context_assets = self._build_private_context_assets(build_input)
        agent_system_msgs, agent_user_msgs = self._get_agent_prompts()
        state: AgentState = {
            "build_input": build_input,
            "context_assets": context_assets,
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": agent_system_msgs,
            "agent_user_msgs": agent_user_msgs,
            "episode_execution_plan": {"episodes": []},
            "stage_sparse_cache": {},
            "construction_contract_version": CONSTRUCTION_CONTRACT_VERSION,
        }
        final_state = self._run_state_machine(state)
        return self._finalize_extraction(build_input, final_state, context_assets)

    def _finalize_extraction(self, build_input, final_state, context_assets=None):
        final_state["cost"] = copy.deepcopy(self._call_records)
        cascade_dict = self.integrate_results(final_state)
        persist = bool(getattr(self, "save_dir", None) and os.path.isdir(self.save_dir))
        if persist:
            self.save_traces(cascade_dict, "CandidateEventCascade", "json")
        validate_cascade(cascade_dict)
        checks = construction_report(cascade_dict)
        evidence = grounded_evidence_report(cascade_dict, build_input.samples, build_input.user_query)
        review = quality_review_report(cascade_dict, build_input.samples, evidence)
        policy = self._event_config_value("evidence_policy", "report")
        blocked = policy == "strict" and evidence["unmatched_quote_count"] > 0
        acceptance = {"evidence_contract_version": EVIDENCE_CONTRACT_VERSION, "policy": policy,
                      "candidate_generated": True, "structure_passed": True,
                      "quote_check_passed": evidence["unmatched_quote_count"] == 0,
                      "unmatched_quotes": evidence["unmatched_quote_count"],
                      "fields_without_quotes": len(evidence["fields_without_quotes"]),
                      "review_candidates": len(review["issues"]),
                      "final_artifact_allowed": not blocked, "semantic_approval": False,
                      "status": "quote_gate_blocked" if blocked else "draft_requires_content_review"}
        if persist:
            self.save_traces(checks, "ConstructionCheck", "json")
            self.save_traces(evidence, "EvidenceCheck", "json")
            self.save_traces(review, "QualityReview", "json")
            self.save_traces(acceptance, "AcceptanceDecision", "json")
        if blocked:
            raise ValueError("Final graph contains quotes absent from the supplied source texts")
        if hasattr(self, "save_dir") and getattr(self, "save_dir", None):
            if os.path.isdir(self.save_dir):
                self.save_traces(cascade_dict, "FinalEventCascade", "json")
        return BuildOutput(
            event_cascades=cascade_dict,
            result=final_state,
            logs=list(final_state["agent_executed"]),
            extras={
                "builder_type": self.builder_type,
                "agent_executed": list(final_state["agent_executed"]),
                "context_asset_summary": summarize_context_assets(context_assets) if context_assets else {},
                "event_summary": copy.deepcopy(getattr(self, "_summary_status", {})),
                "episode_execution_plan": final_state.get("episode_execution_plan"),
                "calls": copy.deepcopy(self._call_records),
                "episode_scope_conflicts": copy.deepcopy(getattr(self, "_temporal_conflicts", [])),
                "acceptance": acceptance,
            },
        )
