"""
Implementation of the financial event reconstruction by applying a step-by-step approach, which contains the following steps:

1. Enable an LLM to generate a overall event structure
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]


2. Based on the overall structure, reconstruct the first stage' episodes:
    2.1 Reconstruct the first episode.
    2.2 ....

3. Based on the overall structure, reconstruct the second stage's episodes:
    3.1 Reconstruct the first episode.
    3.2 ....

....

4. [Loop] Check if the quality of the reconstructed episodes meets the requirements.
    - If not, go back to the previous step and try to improve the reconstruction.
    - If yes, accept the episode and move to the next one.

5. [Loop] Check if the each part of the reconstruction strictly relies on the source content.
    - If not, go back to the previous step and try to improve the reconstruction.
    - If yes, accept the episode and move to the next one.

We do not introduce the idea of the multi-agent system, we indeed have several agents working together to complete the task.
"""

import os
import json
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, DefaultDict

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.builder.step_build import prompts
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
    extract_json_response,
)
from finmy.builder.base import AgentState


# Obtain all text content under the structure.py
_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parents[1] / "structure.py"
)
# Read dataclass definitions from structure.py to embed schema text in prompts
# Skeleton for guiding layout extraction
_SKELETON_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "SourceReferenceEvidence": [],
        "VerifiableField": [],
        "EventCascade": [],
        "EventStage": ["stage_id", "name", "index_in_event", "episodes"],
        "Episode": ["episode_id", "name", "index_in_stage"],
    },
)

_EPISODE_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "SourceReferenceEvidence": [],
        "VerifiableField": [],
        "Episode": [],
    },
)


class EventSkeletonBuilder(BaseBuilder):
    """LangGraph-based event skeleton builder (single-node minimal implementation)

    - Uses a single node `reconstruct_layout` to assemble prompts, call the model, and parse JSON
    - Graph structure: `START → reconstruct_layout → END`
    - Persists output to `output_dir/event_{timestamp}/event_cascade.json`
    """

    def execute_agent(self, state: AgentState) -> AgentState:
        """Single node: reconstruct event skeleton JSON and write into state

        Steps:
        1) Get samples, that is the source content from the 'build_input'
        2) Inject schema (skeleton-filtered) into system prompt
        3) Escape curly braces in the system prompt to avoid `.format` conflicts
        4) Run LLM inference and parse JSON via the centralized utility
        5) Write the parsed result to `event_json`
        """
        t0 = time.time()
        build_ipt = state["build_input"]
        num_executed = len(state["agent_executed"])
        execution_idx = num_executed + 1

        agent_names = list(state["agent_system_msgs"])
        cur_name = agent_names[execution_idx - 1]

        # Compose prompts (system prompt carries skeleton schema; user prompt carries IO fields)
        # Inject skeleton-filtered schema text into the system prompt
        sys_prompt = prompts.EventLayoutReconstructorSys.format(
            STRUCTURE_SPEC=_SKELETON_SPEC,
        )
        # Escape curly braces to prevent downstream formatting altering schema content
        system_msg = sys_prompt.replace("{", "{{").replace("}", "}}")
        user_msg = prompts.EventLayoutReconstructorUser
        # Execute model call
        out: InferOutput = self.agents_lm.run(
            infer_input=InferInput(system_msg=system_msg, user_msg=user_msg),
            Description=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
        )

        savename = self.get_save_name(cur_name, len(state["agent_executed"]) + 1)
        self.save_traces({cur_name: out.to_dict()}, savename, "json")
        state["agent_results"].append({cur_name: out.response})
        state["cost"].append({cur_name: {"latency": time.time() - t0}})
        state["agent_executed"].append(cur_name)
        return {
            "build_input": build_ipt.to_dict(),
            "agent_results": state["agent_results"],
            "agent_executed": state["agent_executed"],
            "cost": state["cost"],
            "agent_system_msgs": state["agent_system_msgs"],
            "agent_user_msgs": state["agent_user_msgs"],
        }

    def graph(self) -> CompiledStateGraph[AgentState]:
        """Build a single-node LangGraph state machine"""
        g = StateGraph(AgentState)
        # Nodes
        g.add_node("reconstruct_layout", self.execute_agent)
        # Edges: START → create_layout → END
        g.add_edge(START, "reconstruct_layout")
        g.add_edge("reconstruct_layout", END)
        return g.compile()


class EpisodeReconstructionBuilder(BaseBuilder):
    """Builder for reconstructing a single TARGET Episode using StageSkeleton and text evidence.

    Responsibilities:
    - Read the previously generated `event_skeleton` (EventCascade → stages → episodes).
    - Select the target stage and episode stub (id, name, index, optional description).
    - Prompt the model with `EpisodeReconstructorSys/User` to produce a complete Episode JSON per Schema.
    - Persist outputs in memory and as JSON files for downstream consumption.

    Configuration:
    - Uses `config["episode_reconstructor"]["generation_config"]` if provided;
      falls back to `layout_reconstructor.generation_config` when absent.
    - Writes episode JSONs into `<output_dir>/episodes/`.

    Inputs:
    - `BuildInput.extras["event_skeleton"]`: optional direct pass of the skeleton when not in state.
    - `BuildInput.extras["target_stage_index"]`: integer, selects the stage (default 0).
    - `BuildInput.extras["target_episode_index"]`: integer, selects episode by `index_in_stage` (default first).

    Outputs:
    - `state["episode_responses"]["episode_reconstructions"][stage_id][episode_id]` → Episode JSON.
    - File saved at `<output_dir>/episodes/{stage_id}_{episode_id}.json`.
    """

    def __init__(
        self,
        lm_name: str = "deepseek/deepseek-chat",
        config: Dict[str, Any] = None,
    ):
        super().__init__(
            method_name="episode_reconstruction",
            config={"lm_name": lm_name, **config},
        )
        self.episode_config = config["episode_reconstructor"]

        gen_conf = (
            self.episode_config["generation_config"]
            if "generation_config" in self.episode_config
            else {}
        )
        self.episode_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=gen_conf,
        )
        self.output_dir = config["output_dir"]
        os.makedirs(self.output_dir, exist_ok=True)

    def reconstruct_episode(self, state: AgentState) -> AgentState:
        """Single node that reconstructs the TARGET Episode.

        Steps:
        1) Locate `event_skeleton` from state or `BuildInput.extras`.
        2) Choose target stage and episode stub by indices (or first available).
        3) Compose system/user prompts with Schema injection and contextual variables.
        4) Run LLM inference and parse response as strict Episode JSON.
        5) Persist result into `episode_responses` and save to disk.
        """
        build_ipt = state["build_input"]
        # Read skeleton from previous step
        event_skeleton = state["SkeletonAgent"]

        # Inject full Schema into system prompt and escape braces to avoid `.format` conflicts
        sys_prompt = prompts.EpisodeReconstructorSys.format(
            STRUCTURE_SPEC=_EPISODE_SPEC
        )
        system_msg = sys_prompt.replace("{", "{{").replace("}", "}}")
        user_msg = prompts.EpisodeReconstructorUser
        # Execute inference with contextual variables
        output: InferOutput = self.episode_api.run(
            infer_input=InferInput(
                system_msg=system_msg,
                user_msg=user_msg,
            ),
            Description=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
        )
        # Parse strict JSON response and persist
        episode_obj = extract_json_response(output.response)

        return state

    def graph(self) -> CompiledStateGraph[AgentState]:
        """Compile single-node graph: START → reconstruct_episode → END."""
        g = StateGraph(AgentState)
        g.add_node("reconstruct_episode", self.reconstruct_episode)
        g.add_edge(START, "reconstruct_episode")
        g.add_edge("reconstruct_episode", END)
        return g.compile()
