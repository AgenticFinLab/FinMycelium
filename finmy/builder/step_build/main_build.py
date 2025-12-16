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

import time
from pathlib import Path
from typing import List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput
from finmy.builder.base import BaseBuilder
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
    extract_json_response,
)
from finmy.builder.base import AgentState
from finmy.builder.structure import Episode

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
        "Participant": [],
        "ParticipantRelation": [],
        "Action": [],
        "FinancialInstrument": [],
        "Transaction": [],
        "Interaction": [],
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

        # Organize the system and user prompts
        system_msg = state["agent_system_msgs"][cur_name]
        user_msg = state["agent_user_msgs"][cur_name]
        system_msg = system_msg.format(STRUCTURE_SPEC=_SKELETON_SPEC)
        # Escape curly braces
        system_msg = system_msg.replace("{", "{{").replace("}", "}}")
        # Execute model call
        out: InferOutput = self.agents_lm.run(
            infer_input=InferInput(system_msg=system_msg, user_msg=user_msg),
            Query=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
        )
        result = out.response
        savename = self.get_save_name(cur_name, len(state["agent_executed"]) + 1)
        self.save_traces({cur_name: out.to_dict()}, savename, "json")
        self.save_traces(extract_json_response(result), f"{savename}-Result", "json")
        state["agent_results"].append({cur_name: result})
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

    def extract_latest_episode(
        self,
        event_skeleton: dict,
        num_episodes: int,
    ):
        """
        Extract the latest episode from the event skeleton based on the num_episodes.

        Args:
            event_skeleton (dict): The event skeleton to extract the latest episode from.
            num_episodes (int): The number of episodes that have been reconstructed.

        Returns:
            tuple: A tuple containing the belong_state and latest_episode.
        """
        idx = 0
        for stage in event_skeleton["stages"]:
            for episode in stage["episodes"]:
                if idx == num_episodes + 1:
                    return stage, episode
                idx += 1
        return None, None

    def execute_agent(self, state: AgentState) -> AgentState:
        """
        Single node that reconstructs the TARGET Episode.

        Steps:
        1) Locate `event_skeleton` from state or `BuildInput.extras`.
        2) Choose target stage and episode stub by indices (or first available).
        3) Compose system/user prompts with Schema injection and contextual variables.
        4) Run LLM inference and parse response as strict Episode JSON.
        5) Persist result into `episode_responses` and save to disk.
        """

        t0 = time.time()
        build_ipt = state["build_input"]
        num_executed = len(state["agent_executed"])

        cur_name = "EpisodeReconstructor"

        # Read skeleton from the skeleton reconstructor
        event_skeleton = state["agent_results"][0]["SkeletonReconstructor"]

        # Get how many episodes have been reconstructed
        num_episodes = state["agent_executed"].count(cur_name)

        belong_state, latest_episode = self.extract_latest_episode(
            event_skeleton, num_episodes
        )

        target_episode = Episode(**latest_episode)
        print(target_episode)
        # Organize the system and user prompts
        sys_msg = state["agent_system_msgs"][cur_name]
        user_msg = state["agent_user_msgs"][cur_name]
        sys_msg = sys_msg.format(STRUCTURE_SPEC=_EPISODE_SPEC)
        # Escape curly braces
        sys_msg = sys_msg.replace("{", "{{").replace("}", "}}")

        # Execute inference with contextual variables
        out: InferOutput = self.agents_lm.run(
            infer_input=InferInput(
                system_msg=sys_msg,
                user_msg=user_msg,
            ),
            Query=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
            StageSkeleton=belong_state,
            TargetEpisode=target_episode,
        )
        result = out.response

        # Obtain the stage
        savename = self.get_save_name(cur_name, num_executed + 1)
        savename = f"{savename}-Stage{belong_state["index_in_event"]}-Episode{target_episode.index_in_stage}"
        self.save_traces({cur_name: out.to_dict()}, savename, "json")
        self.save_traces(extract_json_response(result), f"{savename}-Result", "json")
        state["agent_results"].append({cur_name: result})
        state["cost"].append({cur_name: {"latency": time.time() - t0}})
        state["agent_executed"].append(cur_name)
        return {
            "build_input": build_ipt,
            "agent_results": state["agent_results"],
            "agent_executed": state["agent_executed"],
            "cost": state["cost"],
            "agent_system_msgs": state["agent_system_msgs"],
            "agent_user_msgs": state["agent_user_msgs"],
        }

    def graph(self) -> CompiledStateGraph[AgentState]:
        """
        Compile graph with conditional loop: START → reconstruct_episode → [continue/end].
        """
        g = StateGraph(AgentState)
        g.add_node("reconstruct_episode", self.execute_agent)
        g.add_edge(START, "reconstruct_episode")

        def _route(state: AgentState) -> str:
            skeleton = state["agent_results"][0]["SkeletonReconstructor"]
            # Count the total number of episodes in the skeleton
            total = sum([len(stage["episodes"]) for stage in skeleton["stages"]])
            # Count the number of episode reconstruction agent executed
            # minus 1 for the SkeletonReconstructor
            num_processed = len(state["agent_executed"]) - 1

            return "end" if num_processed >= total else "repeat"

        g.add_conditional_edges(
            "reconstruct_episode",
            _route,
            {
                "repeat": "reconstruct_episode",
                "end": END,
            },
        )
        return g.compile()
