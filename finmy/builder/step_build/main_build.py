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


We do not introduce the idea of the multi-agent system, we indeed have several agents working together to complete the task.
"""

from pathlib import Path
import re
import json
import os
from datetime import datetime
from typing import Dict, Any, TypedDict, List, Optional

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.builder.step_build import prompts
from finmy.converter import read_text_data_from_block
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
)


class _EventState(TypedDict, total=False):
    """Event state used across the graph"""

    build_input: BuildInput
    response: 
    messages: List[Any]


# Obtain all text content under the structure.py
_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parents[1] / "structure.py"
)
# Skeleton for guiding layout extraction
_SKELETON_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "EventCascade": None,
        "EventStage": ["stage_id", "name", "index_in_event", "episodes"],
        "Episode": ["episode_id", "name", "index_in_stage"],
    },
)


class StepWiseEventBuilder(BaseBuilder):
    """A builder to build the financial event in a step-by-step manner."""

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

    def _compose(self, description: str, keywords: str, content: str) -> Dict[str, Any]:
        # Provide the skeleton-relevant schema block to the system prompt
        sys_prompt = prompts.EventLayoutCreatorSys.format(
            STRUCTURE_SPEC=_SKELETON_SPEC or _STRUCTURE_SPEC
        )
        return {
            "system_msg": sys_prompt.replace("{", "{{").replace("}", "}}"),
            "user_msg": prompts.EventLayoutCreatorUser,
            "description": description,
            "keywords": keywords,
            "content": content,
        }

    def _llm(self, state: _EventStructureState) -> str:
        output: InferOutput = self.lm_api.run(
            infer_input=InferInput(
                system_msg=state["system_msg"], user_msg=state["user_msg"]
            ),
            Description=state.get("description", ""),
            Keywords=state.get("keywords", ""),
            Content=state.get("content", ""),
        )
        return output.response

    def _parse(self, response_text: str) -> Dict[str, Any]:
        text = response_text.strip()
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m2 = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
            if not m2:
                raise ValueError("No JSON found in LLM response")
            return json.loads(max(m2, key=len))

    def create_layout(
        self, description: str, keywords: str, content: str
    ) -> Dict[str, Any]:
        state = self._compose(description, keywords, content)
        resp = self._llm(state)
        event_json = self._parse(resp)
        return event_json

    def load_samples(self, build_input: BuildInput) -> str:
        contents = []
        for s in build_input.samples:
            try:
                contents.append(read_text_data_from_block(s.location))
            except Exception:
                continue
        return "\n\n".join(contents)

    def graph(self):
        """The graph is not used; a single function `create_layout` is provided."""
        raise NotImplementedError(
            "Use `create_layout(description, keywords, content)` for layout generation."
        )

    def build(self, build_input: BuildInput) -> BuildOutput:
        description = build_input.user_query.query_text or ""
        keywords_list = build_input.user_query.key_words or []
        keywords = ", ".join(keywords_list)
        content = self.load_samples(build_input)
        event_json = self.create_layout(description, keywords, content)
        saved_dir = self.save_event_structure(event_json)
        return BuildOutput(result={"saved_dir": saved_dir, "event_json": event_json})


# LangGraph is not required for the simplified single-step layout creation.
