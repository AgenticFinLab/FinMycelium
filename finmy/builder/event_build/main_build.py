"""Context-aware financial event reconstruction builder."""

from __future__ import annotations

import json
import re
from typing import Any

from lmbase.inference.base import InferInput

from finmy.builder.base import AgentState, BaseBuilder, BuildInput, BuildOutput
from finmy.builder.utils import run_single_inference

from .context_assets import (
    EvidenceAssetBundle,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
    summarize_context_assets,
)
from .execution_budget import episode_budget_prompt_vars
from .local_context_builder import LocalContextBuilder, LocalContextRequest
from .prompts import get_agent_prompts
from .renderers import render_context_asset_summary


class ContextEventBuilder(BaseBuilder):
    """Independent builder entry point for context-aware event reconstruction."""

    builder_type = "ContextEventBuilder"
    build_input_fields = ("user_query", "samples")
    required_build_config_keys = (
        "agents",
        "lm_type",
        "lm_name",
        "generation_config",
        "save_folder",
    )
    event_config_key = "event_builder_config"

    def _get_agent_prompts(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return system and user prompt templates for all event agents."""

        return get_agent_prompts()

    def _event_config(self) -> dict[str, Any]:
        build_config = getattr(self, "build_config", None) or {}
        return build_config.get(self.event_config_key, {}) or {}

    def _event_config_value(self, key: str, default: Any) -> Any:
        return self._event_config().get(key, default)

    def _build_private_context_assets(
        self,
        build_input: BuildInput,
    ) -> EvidenceAssetBundle:
        """Derive private context assets from the existing BuildInput shape."""

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
        return "\n\n".join(sample.content or "" for sample in build_input.samples)

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
            "STRUCTURE_SPEC": "",
        }
        kwargs.update(budget_vars)
        kwargs.update({key: str(value) for key, value in extra_kwargs.items()})
        return kwargs

    def _format_agent_messages(
        self,
        agent_name: str,
        prompt_kwargs: dict[str, str],
    ) -> tuple[str, str]:
        """Format system and user prompt templates for one agent."""

        system_prompts, user_prompts = self._get_agent_prompts()
        if agent_name not in system_prompts or agent_name not in user_prompts:
            raise ValueError(f"Unknown ContextEventBuilder agent: {agent_name}")
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

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """Execute one event reconstruction agent stage."""
        build_input = state["build_input"]
        context_assets = state.get("context_assets")
        prompt_kwargs = self._build_prompt_kwargs(
            build_input=build_input,
            agent_name=agent_name,
            context_assets=context_assets,
        )
        system_msg, user_msg = self._format_agent_messages(agent_name, prompt_kwargs)
        output = run_single_inference(
            self.agents_lm,
            InferInput(system_msg=system_msg, user_msg=user_msg),
            **prompt_kwargs,
        )
        response_text = getattr(output, "response", output)
        parsed_result = self._parse_json_response(str(response_text))
        state["agent_results"].append({agent_name: parsed_result})
        state["agent_executed"].append(agent_name)
        state.setdefault("cost", [])
        return state

    def graph(self):
        """Construct the context-aware event reconstruction graph."""
        return None

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the context-aware event reconstruction pipeline."""
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
        }
        state = self.execute_agent(state, "SkeletonReconstructor")
        result = state["agent_results"][-1]["SkeletonReconstructor"]
        return BuildOutput(
            event_cascades=result,
            result=result,
            logs=["Executed SkeletonReconstructor with ContextEventBuilder."],
            extras={
                "builder_type": self.builder_type,
                "agent_executed": list(state["agent_executed"]),
                "context_asset_summary": summarize_context_assets(context_assets),
            },
        )
