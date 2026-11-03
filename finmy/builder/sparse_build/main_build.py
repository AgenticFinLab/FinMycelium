"""Sparse RAG enhanced event reconstruction builder."""

from __future__ import annotations

import copy
import hashlib
import json
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

from .context_assets import (
    EvidenceAssetBundle,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
    summarize_context_assets,
)
from .contracts import (
    CONSTRUCTION_CONTRACT_VERSION, check_temporal_scope, compact_values,
    construction_report, episode_scope, participant_registry, stage_scope,
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
from .runtime import run_identity, summarize_calls, validate_config, validate_input
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
        return (
            build_config.get(self.event_config_key)
            or build_config.get(self.legacy_event_config_key)
            or {}
        )

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
        return (
            system_prompts[agent_name].format(**prompt_kwargs),
            user_prompts[agent_name].format(**prompt_kwargs),
        )

    def _parse_json_response(self, response_text: str) -> Any:
        clean_text = (response_text or "").strip()
        code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.S)
        if code_block_match:
            clean_text = code_block_match.group(1).strip()
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            object_match = re.search(r"(\{.*\}|\[.*\])", clean_text, re.S)
            if object_match:
                return json.loads(object_match.group(1))
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
                return json.loads(candidate)
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
    ) -> Any:
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
            if len(self._call_records) >= max_calls:
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
                self._save_call_ledger()
                raise ValueError(f"{agent_name}: incomplete or non-text completion")
            if not response_text.strip():
                record["status"] = "empty_response"
                self._save_call_ledger()
                raise ValueError(f"{agent_name}: empty completion")
            try:
                parsed = self._parse_json_response(response_text)
                if isinstance(parsed, str):
                    raise ValueError("Response did not contain JSON")
                if validator is not None:
                    validator(parsed)
                self._save_agent_result(parsed, savename)
                record["status"] = "accepted"
                self._save_call_ledger()
                return parsed
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if agent_name in self._JSON_SYNTACTIC_RECOVERY_AGENTS:
                    try:
                        recovered = self._recover_syntactic_json_response(response_text)
                        if validator is not None:
                            validator(recovered)
                        self._save_agent_result(recovered, savename)
                        record["status"] = "recovered"
                        self._save_call_ledger()
                        return recovered
                    except ValueError as recovery_exc:
                        last_error = recovery_exc
                record.update(status="invalid_output", error_type=type(last_error).__name__)
                self._save_call_ledger()
                if attempt >= max_attempts:
                    raise ValueError(
                        f"{agent_name} returned invalid output after {attempt} attempt(s): {last_error}"
                    ) from exc
                current_user_msg = self._build_json_retry_user_msg(user_msg, agent_name) + f"\nValidation issue: {last_error}\n"

        raise ValueError(f"{agent_name} returned invalid JSON: {last_error}")

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
            return "", "", None, {"EventCascade": compact_values(self.integrate_results(state))}

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
        parsed_result = self._infer_and_parse_json(
            agent_name,
            system_msg,
            user_msg,
            prompt_kwargs,
            savename,
            validator=lambda payload: self._validate_agent_output(state, agent_name, payload),
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

        indexed_files: list[tuple[int, str, str]] = []
        for filename in os.listdir(self.save_dir):
            if not filename.endswith("-Result.json"):
                continue
            parts = filename.removesuffix("-Result.json").split("-")
            if len(parts) < 2:
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

    def _artifact_hashes(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(Path(self.save_dir).glob("*.json"))
                if path.name not in {"RunManifest.json", "GanttStatus.json"}}

    def _validate_replay_completeness(self, state):
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
        if getattr(self, "_run_started", False):
            raise RuntimeError("Create a new builder for each run; implicit resume is not supported")
        self._run_started = True
        self._call_records = []
        inputs, manifest = run_identity(build_input, self.build_config)
        manifest["construction_contract_version"] = CONSTRUCTION_CONTRACT_VERSION
        manifest["evidence_contract_version"] = EVIDENCE_CONTRACT_VERSION
        persist = bool(getattr(self, "save_dir", None) and os.path.isdir(self.save_dir))
        if persist:
            if os.path.exists(os.path.join(self.save_dir, "RunManifest.json")):
                raise RuntimeError("Run directory already contains a manifest")
            self.save_traces(inputs, "BuildInput", "json")
            self.save_traces(manifest, "RunManifest", "json")
        started = time.perf_counter()
        try:
            output = self._run_validated(build_input)
            manifest.update(status="completed", event_id=output.event_cascades["event_id"])
            return output
        except BaseException as exc:
            manifest.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            manifest.update(elapsed_seconds=time.perf_counter() - started,
                            usage=summarize_calls(self._call_records))
            if persist:
                manifest["artifact_sha256"] = self._artifact_hashes()
                self.save_traces(manifest, "RunManifest", "json")

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
                "context_asset_summary": summarize_context_assets(context_assets),
                "episode_execution_plan": final_state.get("episode_execution_plan"),
                "calls": copy.deepcopy(self._call_records),
                "acceptance": acceptance,
            },
        )
