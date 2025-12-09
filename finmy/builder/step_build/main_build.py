"""
Implementation of the financial event reconstruction by applying a step-by-step approach, which contains the following steps:

1. Enable an LLM to generate a overall event structure
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]
              ├── participants: List[Participant]
              ├── participant_relations: List[ParticipantRelation]
              ├── actions_by_participant: { participant_id → List[Action] }
              ├── transactions: List[Transaction]
              └── interactions: List[Interaction]

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


Although we do not introduce the idea of the multi-agent system, we indeed have several agents working together to complete the task.


"""

from pathlib import Path
import re
import json
import os
from datetime import datetime
from typing import Dict, Any, TypedDict, Optional

from langgraph.graph import StateGraph, END

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.converter import read_text_data_from_block


class _EventStructureState(TypedDict, total=False):
    system_msg: str
    user_msg: str
    description: str
    keywords: str
    content: str
    response_text: str
    event_json: Dict[str, Any]
    saved_dir: str


from finmy.builder.utils import (
    load_structure_dataclasses_text,
    extract_dataclass_blocks,
)


_STRUCTURE_SPEC_FULL = load_structure_dataclasses_text()
_STRUCTURE_SPEC = (
    extract_dataclass_blocks(_STRUCTURE_SPEC_FULL, mode="all")
    if _STRUCTURE_SPEC_FULL
    else ""
)


class StepWiseEventBuilder(BaseBuilder):
    """Use LangGraph to produce the initial event structure (EventCascade skeleton).

    Design notes:
    - The graph performs pure data flow (compose → llm → parse) with no file I/O side effects.
    - Persistence is handled by class methods, making it easy to replace or integrate external storage.
    - The prompt embeds `structure.py` dataclasses as a strict schema reference.
    """

    def __init__(
        self,
        lm_name: str = "deepseek/deepseek-chat",
        config: Dict[str, Any] = {},
    ):
        # Load configuration with sensible defaults to avoid KeyError
        self.layout_creator_config = config.get("layout_creator", {})
        generation_config = self.layout_creator_config.get("generation_config", {})

        # Initialize the LLM interface
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=generation_config,
        )

        # Output directory where the generated structure JSON files will be saved
        self.output_dir = self.layout_creator_config.get(
            "output_dir", "./data/event_structure_output"
        )

    def event_layout_node(self):
        """Node to generate the event layout JSON."""

    def compose_node(self, state: _EventStructureState) -> _EventStructureState:
        """Compose system prompt and user prompt with embedded schema."""
        sys_prompt = _SYSTEM_PROMPT.format(STRUCTURE_SPEC=_STRUCTURE_SPEC_FULL)
        return {
            **state,
            "system_msg": sys_prompt.replace("{", "{{").replace("}", "}}"),
            "user_msg": _USER_PROMPT,
        }

    def llm_node(self, state: _EventStructureState) -> _EventStructureState:
        """Call the LLM and return the raw text response."""
        output: InferOutput = self.lm_api.run(
            infer_input=InferInput(
                system_msg=state["system_msg"], user_msg=state["user_msg"]
            ),
            Description=state.get("description", ""),
            Keywords=state.get("keywords", ""),
            Content=state.get("content", ""),
        )
        return {**state, "response_text": output.response}

    def parse_node(self, state: _EventStructureState) -> _EventStructureState:
        """Parse JSON from the LLM response (supports ```json fenced block and fallback extraction)."""
        text = state.get("response_text", "").strip()
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m2 = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
            if not m2:
                raise ValueError("No JSON found in LLM response")
            data = json.loads(max(m2, key=len))
        return {**state, "event_json": data}

    def save_event_structure(self, event_data: Dict[str, Any]) -> str:
        """Save EventCascade.json and per-stage JSON files; returns the output directory."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.join(self.output_dir, f"event_structure_{ts}")
        os.makedirs(base_dir, exist_ok=True)
        main_file = os.path.join(base_dir, "EventCascade.json")
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(event_data, f, ensure_ascii=False, indent=2)
        if isinstance(event_data, dict) and "stages" in event_data:
            stages = event_data["stages"]
            stages_dir = os.path.join(base_dir, "stages")
            os.makedirs(stages_dir, exist_ok=True)
            if isinstance(stages, list):
                for idx, stage in enumerate(stages):
                    if isinstance(stage, dict):
                        sid = stage.get("stage_id", f"S{idx+1}")
                        with open(
                            os.path.join(stages_dir, f"{sid}.json"),
                            "w",
                            encoding="utf-8",
                        ) as f:
                            json.dump(stage, f, ensure_ascii=False, indent=2)
        return base_dir

    def FinancialEventStructureCreator(self):
        """Construct the LangGraph: compose → llm → parse → END.

        Persistence is not part of the graph; JSON saving is handled by `save_event_structure`.
        """
        graph = StateGraph(_EventStructureState)
        graph.add_node("compose", self.compose_node)
        graph.add_node("llm", self.llm_node)
        graph.add_node("parse", self.parse_node)
        graph.add_edge("compose", "llm")
        graph.add_edge("llm", "parse")
        graph.add_edge("parse", END)
        return graph.compile()

    def run(self, description: str, keywords: str, content: str) -> Dict[str, Any]:
        """Drive the flow: execute graph → save results → return metadata.

        Returns: {"saved_dir": <output_dir>, "event_json": <parsed object>}.
        """
        app = self.FinancialEventStructureCreator()
        final_state = app.invoke(
            {
                "description": description,
                "keywords": keywords,
                "content": content,
            }
        )
        event_json = final_state.get("event_json") or {}
        saved_dir = self.save_event_structure(event_json)
        return {"saved_dir": saved_dir, "event_json": event_json}
