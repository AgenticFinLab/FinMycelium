"""
Step-wise financial event reconstruction using a multi-agent pipeline with explicit
state management and schema-constrained prompts.

Overview:
- Input: `BuildInput` containing `UserQueryInput` and a list of `DataSample`s (source text).
- Output: Fully assembled `EventCascade` with stages, episodes, participants, transactions,
  relations, and grounded descriptions at stage and event levels.

Execution Flow:
1) Skeleton Reconstruction
   - Agent: `SkeletonReconstructor`
   - Goal: Produce an `EventCascade` skeleton (Stages -> Episodes) strictly from `Content`
     using `VerifiableField` for applicable fields.
   - Note: Only structure fields are generated (no descriptions at this step).

2) Skeleton Verification
   - Agent: `SkeletonChecker`
   - Goal: Audit and correct the initial skeleton.
   - Input: `ProposedSkeleton` from step 1, plus `Content`, `Query`, `Keywords`.
   - Action: Validates time hierarchy, consistency, and completeness. Corrects errors while strictly maintaining JSON structure.
   - Critical: The output of this agent becomes the definitive skeleton for all subsequent steps.

3) Episode Loop (per episode in CORRECTED skeleton order)
   a) `ParticipantReconstructor`
      - Identifies and reconstructs episode participants (including `Action`s).
      - Reuses participant IDs across episodes via already reconstructed participants.
   b) `TransactionReconstructor`
      - Reconstructs financial transactions among the episode’s participants.
      - Ensures `from_participant_id`/`to_participant_id` refer to valid participants.
   c) `EpisodeReconstructor`
      - Produces a complete `Episode` (relations, descriptions, timestamps).
      - Emits placeholders for `participants` and `transactions` to avoid duplication,
        which are later replaced during integration.

4) Description Reconstruction
   - `StageDescriptionReconstructor`: Runs once after finishing all episodes within a stage.
     Produces grounded stage `descriptions` based on reconstructed episodes plus source content.
   - `EventDescriptionReconstructor`: Runs once after all stages are completed.
     Produces grounded event `descriptions` based on the full cascade plus source content.

5) Integration
   - `integrate_results`: Consolidates all agent outputs into a complete `EventCascade`.
     Replaces episode placeholders with actual participants/transactions, attaches stage
     and event descriptions, and preserves the skeleton’s ordering.
   - `integrate_from_files`: Reads saved `*-Result.json` artifacts, reconstructs
     `agent_results` sequence, and delegates to `integrate_results` to assemble the final cascade.

Architecture:
- Orchestration: `LangGraph` (`StateGraph`) with conditional routing:
  Skeleton -> SkeletonChecker -> (Participant -> Transaction -> Episode)* -> StageDescription (per-stage) -> EventDescription -> END.
- Schema text: Derived from `structure.py`, filtered per-agent scope via `filter_dataclass_fields`.
- State: `AgentState` carries prompts, inputs, and incremental results throughout the pipeline.
"""

import time
import copy
import os
import json
import logging
from functools import partial
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput
from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
    extract_json_response,
    run_single_inference,
)
from finmy.builder.base import AgentState
from finmy.builder.agent_build.structure import Episode
from finmy.context.local_context_builder import (
    LocalContextBuilder,
    LocalContextRequest,
)
from finmy.builder.agent_build.prompts import *

logger = logging.getLogger(__name__)

# Obtain all text content under the structure.py
_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parent / "structure.py"
)
# Read dataclass definitions from structure.py to embed schema text in prompts
# Skeleton for guiding layout extraction
_SKELETON_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "VerifiableField": [],
        "EventCascade": [
            "event_id",
            "title",
            "event_type",
            "start_time",
            "end_time",
            "stages",
        ],
        "EventStage": [
            "stage_id",
            "name",
            "index_in_event",
            "start_time",
            "end_time",
            "episodes",
        ],
        "Episode": ["episode_id", "name", "index_in_stage", "start_time", "end_time"],
    },
)

_PARTICIPANT_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "Participant": [],
        "Action": [],
        "VerifiableField": [],
    },
)

_TRANSACTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "Transaction": [],
        "VerifiableField": [],
    },
)


_EPISODE_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "ParticipantRelation": [],
        "Action": [],
        "Transaction": [],
        "VerifiableField": [],
        "Episode": [],
    },
)


_STAGE_DESCRIPTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "EventStage": [],
        "VerifiableField": [],
    },
)


_EVENT_DESCRIPTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "EventCascade": [],
        "VerifiableField": [],
    },
)


class AgentEventBuilder(BaseBuilder):
    """Integrated builder that performs the full event reconstruction pipeline:
    1. SkeletonReconstruction: Generates the overall event structure (EventCascade).
    2. SkeletonChecker: Validates and corrects the skeleton structure and timeline.
    3. Loop over Episodes (based on Checked Skeleton):
        a. ParticipantReconstruction: Identifies participants for the current episode.
        b. TransactionReconstructor: Reconstructs transactions for the current episode.
        c. EpisodeReconstruction: Reconstructs the full episode using the skeleton, participants, and transactions.
    4. StageDescriptionReconstructor:
        - Runs after completing all episodes within a stage.
        - Produces grounded `descriptions` for the stage using reconstructed episodes plus source content.
    5. EventDescriptionReconstructor:
        - Runs after all stages are complete.
        - Produces grounded `descriptions` for the entire event using the full cascade plus source content.
    """

    _SHADOW_LOCAL_CONTEXT_AGENTS = {"SkeletonReconstructor", "SkeletonChecker"}

    def _get_agent_prompts(self):
        """Initialize system and user prompts for all agents."""
        agent_system_msgs = {}
        agent_user_msgs = {}

        # Skeleton
        agent_system_msgs["SkeletonReconstructor"] = EventLayoutReconstructorSys
        agent_user_msgs["SkeletonReconstructor"] = EventLayoutReconstructorUser

        agent_system_msgs["SkeletonChecker"] = SkeletonCheckerSys
        agent_user_msgs["SkeletonChecker"] = SkeletonCheckerUser

        # Participant
        agent_system_msgs["ParticipantReconstructor"] = ParticipantReconstructorSys
        agent_user_msgs["ParticipantReconstructor"] = ParticipantReconstructorUser

        # Transaction
        agent_system_msgs["TransactionReconstructor"] = TransactionReconstructorSys
        agent_user_msgs["TransactionReconstructor"] = TransactionReconstructorUser

        # Episode
        agent_system_msgs["EpisodeReconstructor"] = EpisodeReconstructorSys
        agent_user_msgs["EpisodeReconstructor"] = EpisodeReconstructorUser

        # Stage Description
        agent_system_msgs["StageDescriptionReconstructor"] = (
            StageDescriptionReconstructorSys
        )
        agent_user_msgs["StageDescriptionReconstructor"] = (
            StageDescriptionReconstructorUser
        )

        # Event Description
        agent_system_msgs["EventDescriptionReconstructor"] = (
            EventDescriptionReconstructorSys
        )
        agent_user_msgs["EventDescriptionReconstructor"] = (
            EventDescriptionReconstructorUser
        )

        return agent_system_msgs, agent_user_msgs

    def _latest_agent_result(self, state: AgentState, agent_name: str):
        for res in reversed(state["agent_results"]):
            if agent_name in res:
                return res[agent_name]
        return None

    def _get_event_skeleton(self, state: AgentState) -> dict:
        skeleton = self._latest_agent_result(state, "SkeletonChecker")
        if skeleton is not None:
            return skeleton
        skeleton = self._latest_agent_result(state, "SkeletonReconstructor")
        if skeleton is not None:
            return skeleton
        raise ValueError("No skeleton result found in builder state")

    def _episode_locator(
        self,
        stage_index: int,
        episode_index: int,
        stage_id: str | None = None,
        episode_id: str | None = None,
    ) -> dict[str, object]:
        """Return a stable, explicit episode locator used across routing and integration."""
        locator = {
            "stage_index": stage_index,
            "episode_index": episode_index,
        }
        if stage_id is not None:
            locator["stage_id"] = stage_id
        if episode_id is not None:
            locator["episode_id"] = episode_id
        return locator

    def _iter_skeleton_episodes(self, event_skeleton: dict):
        for stage_index, stage in enumerate(event_skeleton.get("stages", []) or []):
            stage_id = stage.get("stage_id", "")
            for episode_index, episode in enumerate(stage.get("episodes", []) or []):
                yield stage_index, episode_index, stage, episode, self._episode_locator(
                    stage_index,
                    episode_index,
                    stage_id,
                    episode.get("episode_id", ""),
                )

    def _current_episode_sequence_index(self, state: AgentState) -> int:
        """Return the current global episode sequence index."""
        return state["agent_executed"].count("EpisodeReconstructor")

    def _get_episode_by_sequence_index(
        self,
        event_skeleton: dict,
        sequence_index: int,
    ):
        """Resolve a structural episode by its global sequence order."""
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
        event_skeleton: dict,
    ) -> dict[str, object]:
        """Build a cheap per-episode routing plan from the validated skeleton.

        The first slice only needs a coarse, deterministic mode split:
        episodes that look money-dense should stay on the full path, while the
        rest can use the light path.
        """
        bundle = getattr(build_input, "context_assets", None)
        cards = getattr(bundle, "evidence_cards", []) or []
        has_money_signal = any(
            bool(getattr(card, "money_hints", None))
            or "money_dense" in (getattr(card, "quality_flags", None) or [])
            for card in cards
        )
        money_tokens = {
            "cash",
            "fund",
            "funds",
            "launder",
            "laundering",
            "payment",
            "transfer",
            "property",
            "asset",
            "assets",
            "money",
            "wire",
        }

        plan_entries: list[dict[str, object]] = []
        for (
            stage_index,
            episode_index,
            stage,
            episode,
            locator,
        ) in self._iter_skeleton_episodes(event_skeleton):
            episode_name = self._scalar_value(episode.get("name", "")).lower()
            stage_name = self._scalar_value(stage.get("name", "")).lower()
            combined_text = f"{stage_name} {episode_name}"
            money_dense = has_money_signal and any(
                token in combined_text for token in money_tokens
            )
            mode = "full" if money_dense else "light"
            plan_entries.append(
                {
                    "locator": locator,
                    "stage_index": stage_index,
                    "episode_index": episode_index,
                    "mode": mode,
                    "detail_tier": "standard" if mode == "full" else "compact",
                }
            )

        return {"episodes": plan_entries}

    def _get_episode_execution_plan_entry(
        self,
        episode_execution_plan: dict[str, object] | None,
        stage_index: int,
        episode_index: int,
    ) -> dict[str, object] | None:
        """Find the execution-plan record for a skeleton episode using explicit coordinates."""
        if not episode_execution_plan:
            return None

        for entry in episode_execution_plan.get("episodes", []) or []:
            locator = entry.get("locator", {}) if isinstance(entry, dict) else {}
            if (
                locator.get("stage_index") == stage_index
                and locator.get("episode_index") == episode_index
            ):
                return entry
        return None

    def _episode_locator_key(self, locator: dict[str, object] | None):
        if not isinstance(locator, dict):
            return None
        stage_id = locator.get("stage_id")
        episode_id = locator.get("episode_id")
        if stage_id is not None and episode_id is not None:
            return ("ids", stage_id, episode_id)
        stage_index = locator.get("stage_index")
        episode_index = locator.get("episode_index")
        if stage_index is not None and episode_index is not None:
            return ("indices", stage_index, episode_index)
        return None

    def _result_locator_map(
        self,
        state: AgentState,
        agent_name: str,
    ) -> dict[tuple[object, ...], dict]:
        locator_map: dict[tuple[object, ...], dict] = {}
        for item in state["agent_results"]:
            if agent_name not in item:
                continue
            locator_key = self._episode_locator_key(
                item.get("_meta", {}).get("episode_locator")
            )
            if locator_key is not None:
                locator_map[locator_key] = item[agent_name]
        return locator_map

    def _result_locator_meta_map(
        self,
        state: AgentState,
        agent_name: str,
    ) -> dict[tuple[object, ...], dict]:
        locator_map: dict[tuple[object, ...], dict] = {}
        for item in state["agent_results"]:
            if agent_name not in item:
                continue
            locator_key = self._episode_locator_key(
                item.get("_meta", {}).get("episode_locator")
            )
            if locator_key is not None:
                locator_map[locator_key] = item.get("_meta", {})
        return locator_map

    def _reconstruct_episode_execution_plan_from_results(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        """Infer episode execution modes from a replayed agent result sequence."""
        try:
            event_skeleton = self._get_event_skeleton(state)
        except ValueError:
            return {"episodes": []}

        plan_entries: list[dict[str, object]] = []
        episode_seq_idx = 0
        transaction_seen_for_current_episode = False

        for result in state["agent_results"]:
            if "TransactionReconstructor" in result:
                transaction_seen_for_current_episode = True

            if "EpisodeReconstructor" not in result:
                continue

            (
                stage_index,
                episode_index,
                stage,
                episode,
                locator,
            ) = self._get_episode_by_sequence_index(event_skeleton, episode_seq_idx)
            if stage_index is None:
                break

            mode = "full" if transaction_seen_for_current_episode else "light"
            plan_entries.append(
                {
                    "locator": locator,
                    "stage_index": stage_index,
                    "episode_index": episode_index,
                    "mode": mode,
                    "detail_tier": "standard" if mode == "full" else "compact",
                }
            )
            episode_seq_idx += 1
            transaction_seen_for_current_episode = False

        return {"episodes": plan_entries}

    def _route_after_participant_reconstructor(self, state: AgentState):
        """Route light episodes around TransactionReconstructor."""
        event_skeleton = self._get_event_skeleton(state)
        current_episode_idx = self._current_episode_sequence_index(state)
        (
            stage_index,
            episode_index,
            _stage,
            _episode,
            _locator,
        ) = self._get_episode_by_sequence_index(event_skeleton, current_episode_idx)
        if stage_index is None:
            raise ValueError("Could not determine episode for participant routing")
        plan_entry = self._get_episode_execution_plan_entry(
            state.get("episode_execution_plan"),
            stage_index,
            episode_index,
        )
        mode = plan_entry.get("mode", "full") if plan_entry else "full"
        return "EpisodeReconstructor" if mode == "light" else "TransactionReconstructor"

    def _build_local_context_package(self, state: AgentState, agent_name: str):
        """Build local context for reconstruction paths and skeleton shadow mode.

        This helper stays intentionally narrow and only serves agents that already
        work with additive local evidence, plus the shadow-mode skeleton agents.
        """
        if agent_name not in {
            "SkeletonReconstructor",
            "SkeletonChecker",
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
            "StageDescriptionReconstructor",
        }:
            return None

        bundle = state["build_input"].context_assets
        if bundle is None or not bundle.evidence_cards:
            return None

        if self._should_use_shadow_local_context(agent_name):
            request = LocalContextRequest(
                agent_name=agent_name,
                query_text=state["build_input"].user_query.query_text,
                key_words=state["build_input"].user_query.key_words,
            )
            return LocalContextBuilder().build(request, bundle)

        event_skeleton = self._get_event_skeleton(state)
        if agent_name == "StageDescriptionReconstructor":
            stage_idx = state["agent_executed"].count(agent_name)
            if stage_idx >= len(event_skeleton["stages"]):
                return None
            target_stage = event_skeleton["stages"][stage_idx]
            request = LocalContextRequest(
                agent_name=agent_name,
                query_text=state["build_input"].user_query.query_text,
                key_words=state["build_input"].user_query.key_words,
                target_stage=self._field_value(target_stage.get("name")),
            )
            return LocalContextBuilder().build(request, bundle)

        current_count = self._current_episode_sequence_index(state)
        target_stage, latest_episode = self.extract_latest_episode(
            event_skeleton, current_count
        )
        if not latest_episode:
            return None

        request = LocalContextRequest(
            agent_name=agent_name,
            query_text=state["build_input"].user_query.query_text,
            key_words=state["build_input"].user_query.key_words,
            target_stage=self._field_value(target_stage.get("name")) if target_stage else "",
            target_episode=self._field_value(latest_episode.get("name")),
        )
        return LocalContextBuilder().build(request, bundle)

    def _should_use_shadow_local_context(self, agent_name: str) -> bool:
        return agent_name in self._SHADOW_LOCAL_CONTEXT_AGENTS

    def _attach_local_context_prompt_kwargs(self, prompt_kwargs: dict, local_context) -> None:
        prompt_kwargs["RetrievedContext"] = (
            local_context.rendered_context if local_context else ""
        )
        prompt_kwargs["RetrievedContextSummary"] = (
            json.dumps(local_context.summary, ensure_ascii=False)
            if local_context
            else "{}"
        )
        prompt_kwargs["RetrievedContextQueryBundle"] = (
            json.dumps(
                getattr(local_context, "query_bundle", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )
            if local_context
            else "{}"
        )
        prompt_kwargs["RetrievedContextBudgetSummary"] = (
            json.dumps(
                getattr(local_context, "budget_summary", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )
            if local_context
            else "{}"
        )
        prompt_kwargs["RetrievedContextMemory"] = (
            json.dumps(
                getattr(local_context, "memory", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )
            if local_context
            else "{}"
        )

    def _render_compact_content(self, build_input: BuildInput) -> str:
        """Render source content in a whitespace-normalized form for additive prompts."""
        return "\n".join(
            sample.content.strip()
            for sample in build_input.samples
            if isinstance(sample.content, str) and sample.content.strip()
        )

    def _scalar_value(self, field):
        """Extract a plain scalar from a verifiable field, dict wrapper, or primitive."""
        if hasattr(field, "value"):
            return field.value
        if isinstance(field, dict):
            return field.get("value", "unknown")
        return field if isinstance(field, (str, int, float, bool)) else "unknown"

    def _render_target_episode_context(self, target_episode: Episode) -> str:
        """Serialize a compact target episode summary for additive prompts."""
        participant_ids = []
        for participant in getattr(target_episode, "participants", []) or []:
            if isinstance(participant, dict):
                participant_id = participant.get("participant_id")
            else:
                participant_id = getattr(participant, "participant_id", None)
            if participant_id:
                participant_ids.append(participant_id)

        transaction_ids = []
        for transaction in getattr(target_episode, "transactions", []) or []:
            if isinstance(transaction, dict):
                transaction_id = transaction.get("transaction_id")
            else:
                transaction_id = getattr(transaction, "transaction_id", None)
            if transaction_id:
                transaction_ids.append(transaction_id)

        compact_context = {
            "episode_id": getattr(target_episode, "episode_id", "unknown"),
            "name": self._scalar_value(getattr(target_episode, "name", "unknown")),
            "index_in_stage": getattr(target_episode, "index_in_stage", "unknown"),
            "start_time": self._scalar_value(getattr(target_episode, "start_time", "unknown")),
            "end_time": self._scalar_value(getattr(target_episode, "end_time", "unknown")),
            "participant_ids": participant_ids,
            "transaction_ids": transaction_ids,
        }
        return json.dumps(
            compact_context,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _render_episode_target_context_text(self, target_episode: Episode) -> str:
        """Render the episode target context as compact text for safer JSON output."""
        participant_ids = []
        for participant in getattr(target_episode, "participants", []) or []:
            if isinstance(participant, dict):
                participant_id = participant.get("participant_id")
            else:
                participant_id = getattr(participant, "participant_id", None)
            if participant_id:
                participant_ids.append(participant_id)

        transaction_ids = []
        for transaction in getattr(target_episode, "transactions", []) or []:
            if isinstance(transaction, dict):
                transaction_id = transaction.get("transaction_id")
            else:
                transaction_id = getattr(transaction, "transaction_id", None)
            if transaction_id:
                transaction_ids.append(transaction_id)

        lines = [
            f"Episode ID: {getattr(target_episode, 'episode_id', 'unknown')}",
            f"Episode Name: {self._scalar_value(getattr(target_episode, 'name', 'unknown'))}",
            f"Episode Index In Stage: {getattr(target_episode, 'index_in_stage', 'unknown')}",
            f"Episode Start Time: {self._scalar_value(getattr(target_episode, 'start_time', 'unknown'))}",
            f"Episode End Time: {self._scalar_value(getattr(target_episode, 'end_time', 'unknown'))}",
            f"Participant IDs: {', '.join(participant_ids) if participant_ids else 'none'}",
            f"Transaction IDs: {', '.join(transaction_ids) if transaction_ids else 'none'}",
        ]
        return "\n".join(lines)

    def _attach_compact_heavy_agent_prompt_kwargs(
        self,
        prompt_kwargs: dict,
        build_input: BuildInput,
        target_episode: Episode,
    ) -> None:
        prompt_kwargs["CompactContent"] = self._render_compact_content(build_input)
        prompt_kwargs["TargetEpisodeContext"] = self._render_target_episode_context(
            target_episode
        )

    def _render_compact_stage_context(self, stage: dict) -> str:
        """Render the stage skeleton as compact text for safer model consumption."""
        episode_lines = []
        for episode in stage.get("episodes", []) or []:
            if isinstance(episode, dict):
                episode_id = episode.get("episode_id", "unknown")
                episode_name = self._scalar_value(episode.get("name", "unknown"))
            else:
                episode_id = getattr(episode, "episode_id", "unknown")
                episode_name = self._scalar_value(getattr(episode, "name", "unknown"))
            episode_lines.append(f"- {episode_id}: {episode_name}")

        lines = [
            f"Stage ID: {stage.get('stage_id', 'unknown')}",
            f"Stage Name: {self._scalar_value(stage.get('name', 'unknown'))}",
            f"Stage Index In Event: {stage.get('index_in_event', 'unknown')}",
            f"Stage Start Time: {self._scalar_value(stage.get('start_time', 'unknown'))}",
            f"Stage End Time: {self._scalar_value(stage.get('end_time', 'unknown'))}",
            "Episodes:",
            *(episode_lines or ["- none"]),
        ]
        return "\n".join(lines)

    def _rewrite_heavy_agent_user_msg_template(
        self, agent_name: str, user_msg_template: str
    ) -> str:
        """Swap bulky prompt placeholders for compact ones without changing kwargs."""
        rewritten = user_msg_template.replace("{Content}", "{CompactContent}")
        rewritten = rewritten.replace("{TargetEpisode}", "{TargetEpisodeContext}")
        if agent_name == "EpisodeReconstructor":
            rewritten = rewritten.replace("{StageSkeleton}", "{StageSkeletonContext}")
        return rewritten

    def _is_unknown_value(self, value: str) -> bool:
        return not isinstance(value, str) or not value.strip() or value.strip().lower() == "unknown"

    def _field_value(self, field) -> str:
        if isinstance(field, dict):
            return field.get("value", "unknown")
        return "unknown"

    def _validate_event_skeleton(self, skeleton: dict) -> tuple[bool, str]:
        stages = skeleton.get("stages", [])
        if len(stages) < 1:
            return False, "no_stages"
        if self._is_unknown_value(self._field_value(skeleton.get("title"))):
            return False, "unknown_event_title"
        total_episodes = sum(len(stage.get("episodes", [])) for stage in stages)
        if total_episodes < 1:
            return False, "no_episodes"
        if any(len(stage.get("episodes", [])) < 1 for stage in stages):
            return False, "empty_stage_detected"
        stage_has_signal = any(
            not all(
                self._is_unknown_value(self._field_value(stage.get(key)))
                for key in ("name", "start_time", "end_time")
            )
            for stage in stages
        )
        if not stage_has_signal:
            return False, "unknown_stage_fields"
        episode_has_signal = any(
            not all(
                self._is_unknown_value(self._field_value(episode.get(key)))
                for key in ("name", "start_time", "end_time")
            )
            for stage in stages
            for episode in stage.get("episodes", [])
        )
        if not episode_has_signal:
            return False, "unknown_episode_fields"
        return True, ""

    def _content_has_signal(self, build_input: BuildInput) -> bool:
        return any(
            isinstance(sample.content, str) and sample.content.strip()
            for sample in build_input.samples
        )

    def _validation_error_message(self, reason: str, has_content: bool) -> str:
        if not has_content:
            return "Insufficient source content to reconstruct a valid event skeleton"
        mapping = {
            "no_stages": "Invalid event skeleton: no stages or episodes reconstructed",
            "no_episodes": "Invalid event skeleton: no stages or episodes reconstructed",
            "empty_stage_detected": "Invalid event skeleton: a stage contains no episodes",
            "unknown_event_title": "Invalid event skeleton: event title is unknown",
            "unknown_stage_fields": "Invalid event skeleton: stage key fields are semantically empty",
            "unknown_episode_fields": "Invalid event skeleton: episode key fields are semantically empty",
        }
        return mapping.get(reason, f"Invalid event skeleton: {reason}")

    def _raise_validation_error(self, reason: str, has_content: bool) -> None:
        message = self._validation_error_message(reason, has_content=has_content)
        logger.error(message)
        raise ValueError(message)

    def _route_after_skeleton_reconstructor(self, state: AgentState):
        skeleton = self._get_event_skeleton(state)
        is_valid, reason = self._validate_event_skeleton(skeleton)
        if is_valid:
            return "SkeletonChecker"
        if not self._content_has_signal(state["build_input"]):
            self._raise_validation_error(reason, has_content=False)
        return "SkeletonChecker"

    def _route_after_skeleton_checker(self, state: AgentState):
        skeleton = self._get_event_skeleton(state)
        is_valid, reason = self._validate_event_skeleton(skeleton)
        if is_valid:
            return "ParticipantReconstructor"
        has_content = self._content_has_signal(state["build_input"])
        # The checker node persists each failed attempt, so a count of 1 still
        # leaves one retry available for the graph to take.
        if has_content and state.get("skeleton_retry_count", 0) < 2:
            return "SkeletonReconstructor"
        self._raise_validation_error(reason, has_content=has_content)

    def extract_latest_episode(
        self,
        event_skeleton: dict,
        num_episodes: int,
    ):
        """
        Extract the latest episode from the event skeleton based on the num_episodes.
        """
        idx = 0
        for stage in event_skeleton["stages"]:
            for episode in stage["episodes"]:
                if idx == num_episodes:
                    return stage, episode
                idx += 1
        return None, None

    def get_completed_stage_index(self, state: AgentState) -> int:
        """
        Determines if a stage has just been completed based on the number of executed episodes.
        Returns the index of the completed stage, or -1 if no stage boundary was just crossed.
        """
        event_skeleton = self._get_event_skeleton(state)
        # Count total episodes completed so far (assuming EpisodeReconstructor is the last step per episode loop)
        episodes_completed = state["agent_executed"].count("EpisodeReconstructor")

        cumulative_episodes = 0
        for i, stage in enumerate(event_skeleton["stages"]):
            num_episodes_in_stage = len(stage["episodes"])
            cumulative_episodes += num_episodes_in_stage

            # If the total completed equals the cumulative count at the end of this stage,
            # we just finished this stage.
            # NOTE: We need to ensure we don't return True if we've already processed this stage's description.
            # But the graph logic will handle that by routing.
            # Here we just want to know "Are we at a boundary?"
            if episodes_completed == cumulative_episodes:
                return i

        return -1

    def _collect_reconstructed_participants_structure(self, state: AgentState):
        """Build a full EventCascade-shaped structure from the Skeleton result,
        and inject already reconstructed participants into the corresponding episodes
        in sequence order.

        Returns a deep-copied EventCascade object with participants filled.
        Note: This creates a fresh copy of the skeleton. For episodes not yet processed,
        participants will be empty (as initialized in the skeleton), ensuring safety.
        """
        event_skeleton = self._get_event_skeleton(state)
        skeleton_copy = copy.deepcopy(event_skeleton)

        pr_results = [
            e["ParticipantReconstructor"]
            for e in state["agent_results"]
            if "ParticipantReconstructor" in e
        ]
        idx = 0
        for st in skeleton_copy["stages"]:
            for ep in st["episodes"]:
                if idx < len(pr_results):
                    ep["participants"] = pr_results[idx]["participants"]
                else:
                    ep["participants"] = []
                idx += 1
        return skeleton_copy

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """
        Executes a single step (Agent) in the reconstruction pipeline.

        This function handles the prompt construction, context retrieval, and state management
        for all agents: Skeleton, Participant, Transaction, and Episode Reconstructors.

        Key Logic:
        - **SkeletonReconstructor**: Runs once at the start to define the roadmap.
        - **ParticipantReconstructor**:
            - Runs for each episode.
            - Uses `_collect_reconstructed_participants_structure` to provide context of
              previously identified participants across stages for ID consistency.
        - **TransactionReconstructor**:
            - Runs for each episode *after* ParticipantReconstructor.
            - Retrieves the *just-generated* participants from `state["agent_results"][-1]`
              to ensure transactions link valid IDs.
        - **EpisodeReconstructor**:
            - Runs for each episode *after* TransactionReconstructor.
            - Retrieves transactions from `state["agent_results"][-1]` and
              participants from `state["agent_results"][-2]` to fully populate the episode.

        Args:
            state (AgentState): The current accumulation of build inputs and results.
            agent_name (str): The name of the agent to execute (bound via `partial` in the graph).

        Returns:
            AgentState: Updated state with the new agent result appended.
        """
        t0 = time.time()
        build_ipt = state["build_input"]
        state.setdefault("skeleton_retry_count", 0)
        state.setdefault("skeleton_validation_reason", "")
        state.setdefault("episode_execution_plan", {"episodes": []})

        # Common prompt arguments
        prompt_kwargs = {
            "Query": build_ipt.user_query.query_text,
            "Keywords": build_ipt.user_query.key_words,
            "Content": "\n".join([sample.content for sample in build_ipt.samples]),
        }

        shadow_local_context = None
        if self._should_use_shadow_local_context(agent_name):
            shadow_local_context = self._build_local_context_package(state, agent_name)
            self._attach_local_context_prompt_kwargs(prompt_kwargs, shadow_local_context)
            if (
                agent_name == "SkeletonReconstructor"
                and shadow_local_context is not None
                and shadow_local_context.retrieval_status == "sufficient"
            ):
                prompt_kwargs["Content"] = ""
            elif (
                agent_name == "SkeletonChecker"
                and shadow_local_context is not None
                and shadow_local_context.retrieval_status == "sufficient"
            ):
                prompt_kwargs["Content"] = ""

        # Retrieve templates
        sys_msg_template = state["agent_system_msgs"][agent_name]
        user_msg_template = state["agent_user_msgs"][agent_name]
        if agent_name in {
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        }:
            user_msg_template = self._rewrite_heavy_agent_user_msg_template(
                agent_name, user_msg_template
            )

        savename_suffix = ""
        sys_msg = ""

        # Logic branching based on agent_name
        if agent_name == "SkeletonReconstructor":
            sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_SKELETON_SPEC)

        elif agent_name == "SkeletonChecker":
            skeleton_result = self._latest_agent_result(
                state, "SkeletonReconstructor"
            )
            if skeleton_result is None:
                raise ValueError(
                    "SkeletonChecker requires a prior SkeletonReconstructor result"
                )
            prompt_kwargs["ProposedSkeleton"] = json.dumps(
                skeleton_result, default=str, indent=2
            )
            sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_SKELETON_SPEC)

        elif agent_name == "StageDescriptionReconstructor":
            # Identify which stage we just finished
            # We can rely on the number of times StageDescriptionReconstructor has run?
            # Or recalculate using get_completed_stage_index logic, but we need the exact stage index.
            # Since the graph routes here only when a stage is done, and we process stages sequentially:
            # The index of the stage to process is equal to the number of times this agent has already run.

            stage_idx = state["agent_executed"].count("StageDescriptionReconstructor")
            savename_suffix = f"-Stage{stage_idx}"
            event_skeleton = self._get_event_skeleton(state)

            # We need to construct the "TargetStage" with all episodes filled in.
            # First, get the skeleton of the target stage
            if stage_idx < len(event_skeleton["stages"]):
                target_stage_skeleton = copy.deepcopy(
                    event_skeleton["stages"][stage_idx]
                )

                # Now populate it with the actual reconstructed episodes
                # We need to find the global episode indices for this stage
                start_ep_idx = 0
                for i in range(stage_idx):
                    start_ep_idx += len(event_skeleton["stages"][i]["episodes"])

                # Collect reconstructed episodes
                reconstructed_episodes = []
                for j in range(len(target_stage_skeleton["episodes"])):
                    global_ep_idx = start_ep_idx + j
                    # Find the result for this episode.
                    # EpisodeReconstructor results are in state["agent_results"]
                    # We need to filter for EpisodeReconstructor outputs
                    ep_results = [
                        r["EpisodeReconstructor"]
                        for r in state["agent_results"]
                        if "EpisodeReconstructor" in r
                    ]

                    if global_ep_idx < len(ep_results):
                        reconstructed_episodes.append(ep_results[global_ep_idx])

                # Replace episodes in skeleton with fully reconstructed ones
                target_stage_skeleton["episodes"] = reconstructed_episodes

                prompt_kwargs["TargetStage"] = json.dumps(
                    target_stage_skeleton, default=str, indent=2
                )

                local_context = self._build_local_context_package(state, agent_name)
                self._attach_local_context_prompt_kwargs(prompt_kwargs, local_context)

            sys_msg = sys_msg_template.format(
                STRUCTURE_SPEC=_STAGE_DESCRIPTION_SPEC,
            )

        elif agent_name == "EventDescriptionReconstructor":
            # Construct the full EventCascade with all reconstructed data
            # similar to integrate_results but without the final descriptions yet

            # Start with skeleton
            event_skeleton = self._get_event_skeleton(state)
            full_cascade = copy.deepcopy(event_skeleton)

            # Collect all episodes
            ep_results = [
                r["EpisodeReconstructor"]
                for r in state["agent_results"]
                if "EpisodeReconstructor" in r
            ]

            # Fill them into the cascade
            ep_cursor = 0
            for stage in full_cascade["stages"]:
                num_eps = len(stage["episodes"])
                stage["episodes"] = ep_results[ep_cursor : ep_cursor + num_eps]
                ep_cursor += num_eps

                # Also potentially inject the stage descriptions if we want the event summarizer to see them?
                # The user didn't explicitly ask for this, but it helps.
                # Let's find StageDescriptionReconstructor results
                sd_results = [
                    r["StageDescriptionReconstructor"]
                    for r in state["agent_results"]
                    if "StageDescriptionReconstructor" in r
                ]

                # Match stage descriptions to stages
                # Assuming sequential execution matches order
                current_stage_idx = full_cascade["stages"].index(stage)
                if current_stage_idx < len(sd_results):
                    sd_res = sd_results[current_stage_idx]
                    stage["descriptions"] = sd_res["descriptions"]

            prompt_kwargs["EventCascade"] = json.dumps(
                full_cascade, default=str, indent=2
            )

            sys_msg = sys_msg_template.format(
                STRUCTURE_SPEC=_EVENT_DESCRIPTION_SPEC,
            )

        elif agent_name in [
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        ]:
            # Retrieve definitive skeleton (prioritizing Checker result)
            event_skeleton = self._get_event_skeleton(state)

            # Determine which episode we are on using the global episode cursor.
            current_count = self._current_episode_sequence_index(state)
            (
                stage_index,
                episode_index,
                belong_state,
                latest_episode,
                locator,
            ) = self._get_episode_by_sequence_index(event_skeleton, current_count)

            if not latest_episode:
                # Should not happen if logic is correct, but good to handle
                raise ValueError(f"Could not find episode for count {current_count}")

            target_episode = Episode(**latest_episode)
            plan_entry = self._get_episode_execution_plan_entry(
                state.get("episode_execution_plan"),
                stage_index,
                episode_index,
            )
            execution_mode = plan_entry.get("mode", "full") if plan_entry else "full"
            detail_tier = (
                plan_entry.get("detail_tier", "standard") if plan_entry else "standard"
            )

            prompt_kwargs["EpisodeLocator"] = locator
            prompt_kwargs["EpisodeExecutionMode"] = execution_mode
            prompt_kwargs["TransactionDetailTier"] = detail_tier

            savename_suffix = f"-Stage{stage_index}-Episode{episode_index}"

            if agent_name == "ParticipantReconstructor":
                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_PARTICIPANT_SPEC)
                prompt_kwargs["TargetEpisode"] = target_episode
                prompt_kwargs["ReconstructedParticipants"] = (
                    self._collect_reconstructed_participants_structure(state)
                )
                self._attach_compact_heavy_agent_prompt_kwargs(
                    prompt_kwargs,
                    build_ipt,
                    target_episode,
                )
                local_context = self._build_local_context_package(state, agent_name)
                self._attach_local_context_prompt_kwargs(prompt_kwargs, local_context)

            elif agent_name == "TransactionReconstructor":
                # Get participants from the immediately preceding step (ParticipantReconstructor)
                last_result = state["agent_results"][-1]
                participants_data = last_result["ParticipantReconstructor"]
                target_episode.participants = participants_data["participants"]

                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_TRANSACTION_SPEC)
                prompt_kwargs["TargetEpisode"] = target_episode
                self._attach_compact_heavy_agent_prompt_kwargs(
                    prompt_kwargs,
                    build_ipt,
                    target_episode,
                )
                local_context = self._build_local_context_package(state, agent_name)
                self._attach_local_context_prompt_kwargs(prompt_kwargs, local_context)

            elif agent_name == "EpisodeReconstructor":
                # Light episodes skip TransactionReconstructor and inherit the
                # participant output directly from the previous node.
                if execution_mode == "light":
                    participants_data = state["agent_results"][-1][
                        "ParticipantReconstructor"
                    ]
                    transactions_data = {"transactions": []}
                else:
                    # Get transactions from the immediately preceding step (TransactionReconstructor)
                    last_result = state["agent_results"][-1]
                    transactions_data = last_result["TransactionReconstructor"]

                    # Get participants from the step before that (ParticipantReconstructor)
                    second_last_result = state["agent_results"][-2]
                    participants_data = second_last_result["ParticipantReconstructor"]

                target_episode.transactions = transactions_data["transactions"]
                target_episode.participants = participants_data["participants"]

                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_EPISODE_SPEC)
                prompt_kwargs["StageSkeleton"] = belong_state
                prompt_kwargs["StageSkeletonContext"] = self._render_compact_stage_context(
                    belong_state
                )
                prompt_kwargs["TargetEpisode"] = target_episode
                self._attach_compact_heavy_agent_prompt_kwargs(
                    prompt_kwargs,
                    build_ipt,
                    target_episode,
                )
                prompt_kwargs["TargetEpisodeContext"] = (
                    self._render_episode_target_context_text(target_episode)
                )
                local_context = self._build_local_context_package(state, agent_name)
                self._attach_local_context_prompt_kwargs(prompt_kwargs, local_context)

        # Escape braces for format if needed.
        # We escape them because the downstream inference engine (LangChain)
        # treats the system message as a template and will try to substitute variables.
        # Since we just injected a JSON schema containing braces, we must escape them.
        sys_msg = sys_msg.replace("{", "{{").replace("}", "}}")

        out: InferOutput = run_single_inference(
            self.agents_lm,
            InferInput(system_msg=sys_msg, user_msg=user_msg_template),
            **prompt_kwargs,
        )
        result = out.response

        # Persist traces
        savename = (
            self.get_save_name(agent_name, len(state["agent_executed"]) + 1)
            + savename_suffix
        )
        self.save_traces({agent_name: out.to_dict()}, savename, "json")

        parsed_result = extract_json_response(result)
        self.save_traces(parsed_result, f"{savename}-Result", "json")

        # Update state
        result_entry = {agent_name: parsed_result}
        if agent_name in {
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        }:
            result_entry["_meta"] = {
                "episode_locator": locator,
                "execution_mode": execution_mode,
                "detail_tier": detail_tier,
            }
        state["agent_results"].append(result_entry)
        state["cost"].append({agent_name: {"latency": time.time() - t0}})
        state["agent_executed"].append(agent_name)

        if agent_name in {"SkeletonReconstructor", "SkeletonChecker"}:
            is_valid, reason = self._validate_event_skeleton(parsed_result)
            state["skeleton_validation_reason"] = reason
            if (
                agent_name == "SkeletonChecker"
                and is_valid
                and not (state.get("episode_execution_plan", {}).get("episodes") or [])
            ):
                state["episode_execution_plan"] = self._build_episode_execution_plan(
                    build_ipt,
                    parsed_result,
                )
            if agent_name == "SkeletonChecker" and not is_valid:
                has_content = self._content_has_signal(state["build_input"])
                if has_content:
                    # Persist the consumed attempt on the node return path so
                    # conditional routing reads stable state instead of mutating it.
                    state["skeleton_retry_count"] += 1
        return state

    def graph(self) -> CompiledStateGraph:
        """
        Constructs and compiles the LangGraph state machine for the reconstruction pipeline.

        Workflow Overview:
        The pipeline reconstructs a financial event cascade in a hierarchical and sequential manner:

        1. **SkeletonReconstructor**:
           - **Start Node**.
           - Generates the high-level `EventCascade` structure (Stages -> Episodes) based on user query and content.
           - Defines the roadmap for the entire reconstruction.

        2. **SkeletonChecker**:
           - Runs immediately after SkeletonReconstructor.
           - Audits the proposed skeleton against Content and Schema.
           - Corrects time inconsistencies, hierarchy issues, and completeness.
           - **Crucial**: Its output serves as the authoritative ground truth for all downstream agents.

        3. **Episode Loop (Participant -> Transaction -> Episode)**:
           - Iterates through each episode defined in the **verified** skeleton.
           - **ParticipantReconstructor**: Identifies participants for the current episode.
           - **TransactionReconstructor**: Identifies transactions, linking the participants.
           - **EpisodeReconstructor**: Synthesizes full episode details (time, description, relations).

        4. **StageDescription Loop**:
           - **Trigger Condition**: After an episode is completed (`EpisodeReconstructor`), the system checks if a stage boundary is reached.
           - **StageDescriptionReconstructor**:
             - Runs *only* when all episodes in a specific stage are fully reconstructed.
             - Synthesizes a high-level description for that stage based on its completed episodes.
             - **Routing**:
               - If more stages exist: Loops back to `ParticipantReconstructor` to start the next stage's first episode.
               - If all stages are done: Proceeds to `EventDescriptionReconstructor`.

        5. **EventDescriptionReconstructor**:
           - **Final Node** (before END).
           - Runs after all stages and episodes are fully reconstructed.
           - Synthesizes the global event description based on the complete cascade.

        Returns:
            CompiledStateGraph[AgentState]: The compiled LangGraph ready for execution.
        """
        g = StateGraph(AgentState)

        # ============================================================================
        # 1. Add Nodes
        # ============================================================================

        # Skeleton: Generates the initial structure
        g.add_node(
            "SkeletonReconstructor",
            partial(self.execute_agent, agent_name="SkeletonReconstructor"),
        )
        g.add_node(
            "SkeletonChecker",
            partial(self.execute_agent, agent_name="SkeletonChecker"),
        )

        # Episode Level Agents
        g.add_node(
            "ParticipantReconstructor",
            partial(self.execute_agent, agent_name="ParticipantReconstructor"),
        )
        g.add_node(
            "TransactionReconstructor",
            partial(self.execute_agent, agent_name="TransactionReconstructor"),
        )
        g.add_node(
            "EpisodeReconstructor",
            partial(self.execute_agent, agent_name="EpisodeReconstructor"),
        )

        # Summarization Agents
        g.add_node(
            "StageDescriptionReconstructor",
            partial(self.execute_agent, agent_name="StageDescriptionReconstructor"),
        )
        g.add_node(
            "EventDescriptionReconstructor",
            partial(self.execute_agent, agent_name="EventDescriptionReconstructor"),
        )

        # ============================================================================
        # 2. Set Entry Point and Basic Linear Edges
        # ============================================================================

        g.set_entry_point("SkeletonReconstructor")

        g.add_conditional_edges(
            "SkeletonReconstructor",
            self._route_after_skeleton_reconstructor,
            {
                "SkeletonChecker": "SkeletonChecker",
            },
        )

        g.add_conditional_edges(
            "SkeletonChecker",
            self._route_after_skeleton_checker,
            {
                "SkeletonReconstructor": "SkeletonReconstructor",
                "ParticipantReconstructor": "ParticipantReconstructor",
            },
        )

        # Intra-Episode Flow: route light episodes directly to EpisodeReconstructor.
        g.add_conditional_edges(
            "ParticipantReconstructor",
            self._route_after_participant_reconstructor,
            {
                "TransactionReconstructor": "TransactionReconstructor",
                "EpisodeReconstructor": "EpisodeReconstructor",
            },
        )
        g.add_edge("TransactionReconstructor", "EpisodeReconstructor")

        # ============================================================================
        # 3. Conditional Logic (Routing)
        # ============================================================================

        def _route(state: AgentState):
            """
            Determines the next step after an Episode is reconstructed.

            Logic:
            1. Check if the just-completed episode marks the end of a stage.
            2. If yes, and we haven't generated the description for that stage yet -> Go to `StageDescriptionReconstructor`.
            3. If no (mid-stage), or stage description already done (unlikely path but safe) -> Check if there are more episodes.
            4. If more episodes exist -> Go to `ParticipantReconstructor` (next episode).
            5. If all episodes done -> (Fallback) END.
               (Note: Usually routed via StageDescriptionReconstructor -> EventDescriptionReconstructor).
            """
            # Check total episodes in the plan
            event_skeleton = self._get_event_skeleton(state)
            total_episodes = sum(
                len(stage["episodes"]) for stage in event_skeleton["stages"]
            )
            executed_episodes = state["agent_executed"].count("EpisodeReconstructor")

            # Check if a stage was just completed
            completed_stage_idx = self.get_completed_stage_index(state)

            # Count how many stage descriptions we have already generated
            executed_stage_descs = state["agent_executed"].count(
                "StageDescriptionReconstructor"
            )

            # Condition 1: End of a Stage -> Generate Stage Description
            # We check `completed_stage_idx != -1` (a stage just finished)
            # AND `completed_stage_idx == executed_stage_descs` (we haven't done this stage's desc yet)
            # Example: Finished Stage 0 (idx=0). executed_stage_descs=0. 0==0 -> True.
            if (
                completed_stage_idx != -1
                and completed_stage_idx == executed_stage_descs
            ):
                return "StageDescriptionReconstructor"

            # Condition 2: Not a stage boundary (or already handled), check for next episode
            if executed_episodes < total_episodes:
                return "ParticipantReconstructor"

            # Fallback (should ideally reach EventDescription via _route_from_stage_desc)
            return END

        def _route_from_stage_desc(state: AgentState):
            """
            Determines the next step after a Stage Description is generated.

            Logic:
            1. Check if there are more stages remaining.
            2. If yes -> Go to `ParticipantReconstructor` (Start first episode of next stage).
            3. If no (all stages done) -> Go to `EventDescriptionReconstructor` (Final Summary).
            """
            event_skeleton = self._get_event_skeleton(state)
            total_stages = len(event_skeleton["stages"])
            executed_stages = state["agent_executed"].count(
                "StageDescriptionReconstructor"
            )

            if executed_stages < total_stages:
                # Start next stage's first episode
                return "ParticipantReconstructor"
            else:
                # All stages done, generate global event description
                return "EventDescriptionReconstructor"

        # Route from EpisodeReconstructor
        g.add_conditional_edges(
            "EpisodeReconstructor",
            _route,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "StageDescriptionReconstructor": "StageDescriptionReconstructor",
                END: END,
            },
        )

        # Route from StageDescriptionReconstructor
        g.add_conditional_edges(
            "StageDescriptionReconstructor",
            _route_from_stage_desc,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "EventDescriptionReconstructor": "EventDescriptionReconstructor",
            },
        )

        # Final Step: Event Description -> END
        g.add_edge("EventDescriptionReconstructor", END)

        return g.compile()

    def integrate_results(self, state: AgentState) -> dict:
        """
        Integrates all agent results into the final EventCascade structure.
        """
        # 1. Start with the skeleton
        final_cascade = copy.deepcopy(self._get_event_skeleton(state))
        episode_execution_plan = state.get("episode_execution_plan")
        if not (episode_execution_plan and episode_execution_plan.get("episodes")):
            episode_execution_plan = self._reconstruct_episode_execution_plan_from_results(
                state
            )

        episode_result_locator_map = self._result_locator_map(state, "EpisodeReconstructor")
        episode_meta_locator_map = self._result_locator_meta_map(
            state, "EpisodeReconstructor"
        )
        participant_result_locator_map = self._result_locator_map(
            state, "ParticipantReconstructor"
        )
        transaction_result_locator_map = self._result_locator_map(
            state, "TransactionReconstructor"
        )

        # 2. Collect Transaction results
        tr_results = [
            r["TransactionReconstructor"]
            for r in state["agent_results"]
            if "TransactionReconstructor" in r
        ]

        # Also collect Participant results to reattach after Episode update
        p_results = [
            r["ParticipantReconstructor"]
            for r in state["agent_results"]
            if "ParticipantReconstructor" in r
        ]

        # 3. Collect Episode results
        er_results = [
            r["EpisodeReconstructor"]
            for r in state["agent_results"]
            if "EpisodeReconstructor" in r
        ]

        # Populate episodes in order
        ep_idx = 0
        transaction_idx = 0
        for stage_index, stage in enumerate(final_cascade["stages"]):
            for episode_index, episode in enumerate(stage["episodes"]):
                locator_key = self._episode_locator_key(
                    self._episode_locator(
                        stage_index,
                        episode_index,
                        stage.get("stage_id"),
                        episode.get("episode_id"),
                    )
                )
                episode_result = (
                    episode_result_locator_map.get(locator_key)
                    if episode_result_locator_map
                    else (er_results[ep_idx] if ep_idx < len(er_results) else None)
                )
                participant_result = (
                    participant_result_locator_map.get(locator_key)
                    if participant_result_locator_map
                    else (p_results[ep_idx] if ep_idx < len(p_results) else None)
                )
                transaction_result = (
                    transaction_result_locator_map.get(locator_key)
                    if transaction_result_locator_map
                    else (
                        tr_results[transaction_idx]
                        if transaction_idx < len(tr_results)
                        else None
                    )
                )

                if episode_result is not None:
                    # Replace with the fully reconstructed episode
                    episode.update(episode_result)

                    plan_entry = self._get_episode_execution_plan_entry(
                        episode_execution_plan,
                        stage_index,
                        episode_index,
                    )
                    execution_mode = "full"
                    if plan_entry:
                        execution_mode = plan_entry.get("mode", "full")
                    elif locator_key in episode_meta_locator_map:
                        execution_mode = episode_meta_locator_map[locator_key].get(
                            "execution_mode", "full"
                        )

                    # Ensure transactions are attached for full episodes only.
                    if execution_mode == "full":
                        if (
                            "transactions" not in episode
                            or not episode["transactions"]
                            or isinstance(episode["transactions"], str)
                        ):
                            if transaction_result is not None:
                                episode["transactions"] = transaction_result.get(
                                    "transactions", []
                                )
                        if not transaction_result_locator_map:
                            transaction_idx += 1
                    elif (
                        "transactions" not in episode
                        or isinstance(episode["transactions"], str)
                    ):
                        episode["transactions"] = []
                    # Ensure participants are attached (EpisodeReconstructor uses placeholders)
                    if "participants" not in episode or isinstance(
                        episode["participants"], str
                    ):
                        if participant_result is not None:
                            episode["participants"] = participant_result.get(
                                "participants", []
                            )
                ep_idx += 1

        # 4. Integrate StageDescriptionReconstructor results
        sd_results = [
            r["StageDescriptionReconstructor"]
            for r in state["agent_results"]
            if "StageDescriptionReconstructor" in r
        ]

        # Map results to stages sequentially
        for i, stage in enumerate(final_cascade["stages"]):
            if i < len(sd_results):
                res = sd_results[i]
                stage["descriptions"] = res["descriptions"]

        # 5. Integrate EventDescriptionReconstructor results
        ed_results = [
            r["EventDescriptionReconstructor"]
            for r in state["agent_results"]
            if "EventDescriptionReconstructor" in r
        ]

        if ed_results:
            # Should be only one
            res = ed_results[-1]
            final_cascade["descriptions"] = res["descriptions"]

        return final_cascade

    def integrate_from_files(self) -> dict:
        """
        Reconstructs the EventCascade from saved result files in the save directory.
        Scans for files ending with '-Result.json'.
        """
        # Scan directory
        files_map = {}
        if not os.path.exists(self.save_dir):
            raise FileNotFoundError(f"Save directory {self.save_dir} does not exist.")

        for filename in os.listdir(self.save_dir):
            if filename.endswith("-Result.json"):
                # Split by '-' to get metadata
                # Format: AgentName-Index[-Suffix...]-Result.json
                parts = filename.split("-")

                # We expect at least AgentName and Index
                if len(parts) >= 2:
                    agent_name = parts[0]
                    try:
                        idx = int(parts[1])
                        files_map[idx] = (agent_name, filename)
                    except ValueError:
                        # Skip files where the second part is not an integer index
                        continue

        # Sort by index to maintain execution order
        sorted_indices = sorted(files_map.keys())

        # Check if we have results
        if not sorted_indices:
            raise FileNotFoundError(f"No result files found in {self.save_dir}")

        # Read files and reconstruct agent_results
        agent_results = []

        for idx in sorted_indices:
            agent_name, filename = files_map[idx]
            filepath = os.path.join(self.save_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            agent_results.append({agent_name: data})

        # Create a dummy state
        # integrate_results only needs state["agent_results"]
        dummy_state = {"agent_results": agent_results}

        return self.integrate_results(dummy_state)

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the builder pipeline."""
        # 1. Get prompts
        agent_system_msgs, agent_user_msgs = self._get_agent_prompts()

        # 2. Build initial state
        state = {
            "build_input": build_input,
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": agent_system_msgs,
            "agent_user_msgs": agent_user_msgs,
            "episode_execution_plan": {"episodes": []},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        # 3. Compile graph
        app = self.graph()

        # 4. Run graph
        # Increase recursion limit if needed, though default is usually 25
        # For long events, we might need more.
        config = self.build_config["graph_config"]
        final_state = app.invoke(state, config=config)

        # 5. Integrate results
        cascade_dict = self.integrate_results(final_state)
        self.save_traces(
            cascade_dict,
            save_name="FinalEventCascade",
            file_format="json",
        )
        restored_cascade = self.integrate_from_files()
        self.save_traces(
            restored_cascade,
            save_name="IntegratedEventCascade",
            file_format="json",
        )
        # 6. Construct BuildOutput
        # We wrap the result in BuildOutput.
        # Note: cascade_dict is a dictionary matching EventCascade structure.
        return BuildOutput(
            event_cascades=cascade_dict,
            result=final_state,
            logs=final_state["agent_executed"],
            extras=None,
        )
