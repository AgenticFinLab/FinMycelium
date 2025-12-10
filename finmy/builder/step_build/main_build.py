"""
Implementation of the financial event reconstruction by applying a step-by-step approach, which contains the following steps:

1. Enable an LLM to generate a overall event structure
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]


2. Based on the overall structure, generate the first stage' episodes:
    2.1 Reconstruct the first episode.
    2.2 ....

3. Based on the overall structure, generate the second stage's episodes:
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
    event_responses: DefaultDict[str, Any] = defaultdict(dict)
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


class EventSkeletonBuilder(BaseBuilder):
    """LangGraph-based event skeleton builder (single-node minimal implementation)

    - Uses a single node `create_layout` to assemble prompts, call the model, and parse JSON
    - Graph structure: `START → create_layout → END`
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

        # Obtain the layout config
        self.layout_config = config["layout_creator"]
        # First set the llm with the generation config from the layout
        # because the layout creator will be the first step.
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=self.layout_config["generation_config"],
        )
        # Obtain the core folder to save all results
        self.output_dir = config["output_dir"]
        os.makedirs(self.output_dir, exist_ok=True)

    def create_layout(self, state: EventState) -> EventState:
        """Single node: generate event skeleton JSON and write into state

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
        sys_prompt = prompts.EventLayoutCreatorSys.format(
            STRUCTURE_SPEC=_SKELETON_SPEC,
        )
        # Escape curly braces to prevent downstream formatting altering schema content
        system_msg = sys_prompt.replace("{", "{{").replace("}", "}}")
        user_msg = prompts.EventLayoutCreatorUser
        print(system_msg)
        print(user_msg)
        # Execute model call
        output: InferOutput = self.lm_api.run(
            infer_input=InferInput(system_msg=system_msg, user_msg=user_msg),
            Description=build_ipt.user_query.query_text,
            Keywords=build_ipt.user_query.key_words,
            Content="\n".join([sample.content for sample in build_ipt.samples]),
        )
        # Ensure default dict exists for event responses
        state.setdefault("event_responses", defaultdict(dict))
        # Parse JSON and write into state
        state["event_responses"]["event_skeleton"] = extract_json_response(
            output.response
        )
        return state

    def graph(self) -> CompiledStateGraph[EventState]:
        """Build a single-node LangGraph state machine"""
        g = StateGraph(EventState)
        # Nodes
        g.add_node("create_layout", self.create_layout)
        # Edges: START → create_layout → END
        g.add_edge(START, "create_layout")
        g.add_edge("create_layout", END)
        return g.compile()

    def build(self, build_input: BuildInput) -> BuildOutput:
        """Compile and run the graph, return save path and event JSON"""
        app = self.graph()
        # Initial state: pass BuildInput only; node will populate event_json
        initial = {"build_input": build_input}
        final_state = app.invoke(initial)
        event_skeleton = final_state["event_responses"]["event_skeleton"]
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
