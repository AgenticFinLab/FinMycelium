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

import re
import json
import os
from datetime import datetime
from typing import Dict, Any, TypedDict

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.builder.step_build import prompts
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
    load_python_text,
    extract_dataclass_blocks,
)


_STRUCTURE_SPEC_FULL = load_python_text()
_STRUCTURE_SPEC = (
    extract_dataclass_blocks(_STRUCTURE_SPEC_FULL, mode="all")
    if _STRUCTURE_SPEC_FULL
    else ""
)


class StepWiseEventBuilder(BaseBuilder):
    def __init__(
        self,
        lm_name: str = "deepseek/deepseek-chat",
        config: Dict[str, Any] = {},
    ):
        super().__init__(
            method_name="step_wise_builder", config={"lm_name": lm_name, **config}
        )
        cfg = config.get("layout_creator", {})
        generation_config = cfg.get("generation_config", {})
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=generation_config,
        )
        self.output_dir = cfg.get("output_dir", "./data/event_structure_output")

    def _compose(self, description: str, keywords: str, content: str) -> Dict[str, Any]:
        sys_prompt = prompts.EventLayoutCreatorSys.format(
            STRUCTURE_SPEC=_STRUCTURE_SPEC_FULL
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

    def save_event_structure(self, event_data: Dict[str, Any]) -> str:
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

    def load_samples(self, build_input: BuildInput) -> str:
        contents = []
        for s in build_input.samples:
            try:
                contents.append(read_text_data_from_block(s.location))
            except Exception:
                continue
        return "\n\n".join(contents)

    def build(self, build_input: BuildInput) -> BuildOutput:
        description = build_input.user_query.query_text or ""
        keywords_list = build_input.user_query.key_words or []
        keywords = ", ".join(keywords_list)
        content = self.load_samples(build_input)
        state = self._compose(description, keywords, content)
        resp = self._llm(state)
        event_json = self._parse(resp)
        saved_dir = self.save_event_structure(event_json)
        return BuildOutput(result={"saved_dir": saved_dir, "event_json": event_json})
