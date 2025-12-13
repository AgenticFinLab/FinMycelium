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


class EventState(MessagesState):
    """State schema for the LangGraph run"""

    build_input: BuildInput
    step_results: DefaultDict[str, Any] = defaultdict(dict)
    messages: List[Any]


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

    def __init__(
        self,
        lm_name: str = "deepseek/deepseek-chat",
        config: Dict[str, Any] = None,
    ):
        super().__init__(
            method_name="step_wise_builder", config={"lm_name": lm_name, **config}
        )

        # Obtain the layout reconstructor config
        self.layout_config = config["layout_reconstructor"]
        # First set the llm with the generation config from the layout
        # because the layout reconstructor will be the first step.
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=self.layout_config["generation_config"],
        )
        # Obtain the core folder to save all results
        self.output_dir = config["output_dir"]
        os.makedirs(self.output_dir, exist_ok=True)

    def reconstruct_layout(self, state: EventState) -> EventState:
        """Single node: reconstruct event skeleton JSON and write into state

        Steps:
        1) Get samples, that is the source content from the 'build_input'
        2) Inject schema (skeleton-filtered) into system prompt
        3) Escape curly braces in the system prompt to avoid `.format` conflicts
        4) Run LLM inference and parse JSON via the centralized utility
        5) Write the parsed result to `event_json`
        """
        build_ipt = state["build_input"]
        # Compose prompts (system prompt carries skeleton schema; user prompt carries IO fields)
        # Inject skeleton-filtered schema text into the system prompt
        sys_prompt = prompts.EventLayoutReconstructorSys.format(
            STRUCTURE_SPEC=_SKELETON_SPEC,
        )
        # Escape curly braces to prevent downstream formatting altering schema content
        system_msg = sys_prompt.replace("{", "{{").replace("}", "}}")
        user_msg = prompts.EventLayoutReconstructorUser
        # Execute model call
        output: InferOutput = self.lm_api.run(
            infer_input=InferInput(system_msg=system_msg, user_msg=user_msg),
            Description=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
        )
        # Ensure default dict exists for event responses
        state.setdefault("step_results", defaultdict(dict))
        # Parse JSON and write into state
        state["step_results"]["event_skeleton"] = extract_json_response(output.response)
        return state

    def graph(self) -> CompiledStateGraph[EventState]:
        """Build a single-node LangGraph state machine"""
        g = StateGraph(EventState)
        # Nodes
        g.add_node("reconstruct_layout", self.reconstruct_layout)
        # Edges: START → create_layout → END
        g.add_edge(START, "reconstruct_layout")
        g.add_edge("reconstruct_layout", END)
        return g.compile()

    def build(self, build_input: BuildInput) -> BuildOutput:
        """Compile and run the graph, return save path and event JSON"""
        app = self.graph()
        # Initial state: pass BuildInput only; node will populate event_json
        initial = {"build_input": build_input}
        final_state = app.invoke(initial)
        event_skeleton = final_state["step_results"]["event_skeleton"]
        # Save the event skeleton
        with open(
            os.path.join(self.output_dir, "event_skeleton.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(event_skeleton, f, ensure_ascii=False, indent=2)

        return BuildOutput(
            result={
                "saved_dir": self.output_dir,
                "event_skeleton": event_skeleton,
            }
        )


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

    def reconstruct_episode(self, state: EventState) -> EventState:
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
        event_skeleton = state["step_results"]["event_skeleton"]

        # Resolve targeting hints (stage/episode indices) without .get
        extras = build_ipt.extras
        stage_index = (
            int(extras["target_stage_index"]) if "target_stage_index" in extras else 0
        )
        target_episode_index = (
            extras["target_episode_index"] if "target_episode_index" in extras else None
        )
        stages = event_skeleton["stages"] if "stages" in event_skeleton else []
        if not isinstance(stages, list) or not stages:
            return state
        if stage_index < 0 or stage_index >= len(stages):
            stage_index = 0
        stage = stages[stage_index]
        episodes = stage["episodes"] if "episodes" in stage else []
        # Select the episode stub: prefer explicit index match, else first with `index_in_stage`
        stub = None
        if isinstance(episodes, list) and episodes:
            if target_episode_index is None:
                for ep in episodes:
                    if isinstance(ep, dict) and "index_in_stage" in ep:
                        stub = ep
                        break
                if stub is None and isinstance(episodes[0], dict):
                    stub = episodes[0]
            else:
                for ep in episodes:
                    if (
                        isinstance(ep, dict)
                        and "index_in_stage" in ep
                        and ep["index_in_stage"] == target_episode_index
                    ):
                        stub = ep
                        break
        if not isinstance(stub, dict):
            return state
        # Extract TARGET skeleton fields
        ep_id = stub["episode_id"] if "episode_id" in stub else ""
        raw_name = stub["name"] if "name" in stub else ""
        name_val = raw_name["value"] if isinstance(raw_name, dict) else (raw_name or "")
        raw_desc = stub["description"] if "description" in stub else ""
        desc_val = raw_desc["value"] if isinstance(raw_desc, dict) else (raw_desc or "")
        idx_val = (
            stub["index_in_stage"]
            if "index_in_stage" in stub and stub["index_in_stage"] is not None
            else 0
        )
        # Inject full Schema into system prompt and escape braces to avoid `.format` conflicts
        sys_prompt = prompts.EpisodeReconstructorSys.format(
            STRUCTURE_SPEC=_EPISODE_SPEC
        )
        system_msg = sys_prompt.replace("{", "{{").replace("}", "}}")
        user_msg = prompts.EpisodeReconstructorUser
        # Execute inference with contextual variables
        output: InferOutput = self.episode_api.run(
            infer_input=InferInput(system_msg=system_msg, user_msg=user_msg),
            Description=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
            EPISODE_ID=ep_id,
            EPISODE_NAME=name_val,
            INDEX_IN_STAGE=idx_val,
            EPISODE_DESCRIPTION=desc_val,
            StageSkeleton=json.dumps(stage, ensure_ascii=False, indent=2),
        )
        # Parse strict JSON response and persist
        episode_obj = extract_json_response(output.response)
        stage_id = stage["stage_id"] if "stage_id" in stage else f"S{stage_index}"
        ep_key = ep_id or f"E{idx_val}"
        store = state.setdefault("episode_responses", defaultdict(dict))
        if "episode_reconstructions" not in store:
            store["episode_reconstructions"] = defaultdict(dict)
        store["episode_reconstructions"][stage_id][ep_key] = episode_obj
        # Save to disk for external inspection/use
        episodes_dir = os.path.join(self.output_dir, "episodes")
        os.makedirs(episodes_dir, exist_ok=True)
        with open(
            os.path.join(episodes_dir, f"{stage_id}_{ep_key}.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(episode_obj, f, ensure_ascii=False, indent=2)
        return state

    def graph(self) -> CompiledStateGraph[EventState]:
        """Compile single-node graph: START → reconstruct_episode → END."""
        g = StateGraph(EventState)
        g.add_node("reconstruct_episode", self.reconstruct_episode)
        g.add_edge(START, "reconstruct_episode")
        g.add_edge("reconstruct_episode", END)
        return g.compile()

    def build(self, build_input: BuildInput) -> BuildOutput:
        """Run the episode reconstruction graph and return outputs.

        - Accepts `BuildInput` (user query, samples, extras).
        - Returns `BuildOutput.result` with saved directory and episode responses.
        """
        app = self.graph()
        initial = {"build_input": build_input}
        final_state = app.invoke(initial)
        responses = (
            final_state["episode_responses"]
            if "episode_responses" in final_state
            else {}
        )
        return BuildOutput(
            result={
                "saved_dir": self.output_dir,
                "episode_responses": responses,
            }
        )
