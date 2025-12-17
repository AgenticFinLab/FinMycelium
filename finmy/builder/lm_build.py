"""
Implementation of reconstructing a Financial Event Pipeline Using Large Models (LMs).

This method is to reconstruction the financial event purely by prompting a single large models in one inference:

    prompt  ->  LM -> EventCascade
    samples ->
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.converter import read_text_data_from_block
from finmy.builder.class_build.prompts import *
from finmy.builder.utils import (
    load_python_text,
    extract_dataclass_blocks,
    extract_json_response,
)


SYSTEM_PROMPT = """
You are a senior financial event analysis expert and structured extractor, excel at reconstructing specific financial events from large amounts of information. Your task is to, within the scope defined by `Query` and `Keywords`, strictly based on facts in `Content`, extract, summarize, refine, and reconstruct a specific financial event, and output strict JSON that truthfully represents the event. Do not invent or expand beyond the source, and do not alter any information that contradicts `Content`.
    
Compliance and consistency:
- Use ONLY fields and types from the schema block in the system prompt; exact names and types.
- ISO 8601 timestamps; ISO currency codes.
- Participant IDs MUST be "P_" + integer.
- Attach at least one source_content to critical records.
- Cross-validate files:
  - Contents of stages in EventCascade.json matches all generated stage_id.json
  - Stage episodes of each stage_id.json match episodes/episode_id.json
  - Each participant_id.json in participants/ is the collection of participants in each episode_id.json while the participant_id maintains across episodes across stages if the same participant; snapshots align in timestamps and ordering
  - Similar to the relations 
  - Embedded `transactions` within stages/episodes MUST reference valid `participant_id` values and include required fields and evidence.
  - `sources_summary` in `EventCascade` MUST be consistent with the evidence attached across files.
- Each JSON MUST strictly conform to the dataclass schema from the reference block.
- If information is not present in `Content`, set fields to null or omit; do not fabricate.

Hard compliance mandate:
- Your output MUST be constructed solely using the modules, fields, and types defined inside the block labeled `=== BEGIN structure.py dataclasses ===`.
- DO NOT introduce any field names, structures, or categories that are not present in that block.
- Use exact field names and types; arrays, objects, strings, numbers must match the definitions.
- If a field cannot be populated strictly from `Content`, set it to null or omit it; do not guess.
- Validate internally that the final JSON would conform to the referenced dataclass schema before outputting.

Schema categories (must be covered and sourced from `Content`):
- Participant, ParticipantRelation, Action, Transaction, Episode, EventStage, EventCascade, VerifiableField, FinancialInstrument


How to output (strict, single-file JSON):
    Please strictly output the EventCascade content in JSON format according to the following structure: 
    
    Hierarchy (must be followed):
    EventCascade
      └── stages: List[EventStage]
            └── episodes: List[Episode]
                  ├── participants: List[Participant]
                  ├── participant_relations: List[ParticipantRelation]
                  ├── transactions: List[Transaction]

Extraction and validation process:
1) Scope alignment using `Query` and `Keywords`; ignore unrelated content.
2) Identify participants, roles, relations, transactions, evidence, episodes, and stage evolution from `Content`.
3) Construct timelines: sort stages by `stage_index`; sort transactions by `timestamp`.
4) Reasons/rationale only where supported by `Content`; do not guess.
5) Evidence linking: attach source_content as the evidence to critical objects/events.
6) Normalization: ISO timestamps, ISO currency codes; `participant_id` must be "P_"+integer.
7) Consistency check: coherent fields, closed references, correct chronology, no contradictions.
8) Final output: strict JSON; missing items null or omitted;
9) Completeness Verification: Ensure field consistency, closed-loop references (all IDs exist and are traceable), correct chronological order, and absence of internal contradictions. 
10) Fill in each field only if the `Content` explicitly contains the corresponding value, information, or context; otherwise, leave the field as null or omit it entirely.
11) Do not extend beyond or alter the source content in any way.

Schema reference (authoritative; include verbatim dataclass content from predefined code; use as field and type specification; do not output code):
=== BEGIN structure.py dataclasses ===
xxxxxx
=== END structure.py dataclasses ===
"""

USER_PROMPT = """
Task: Using the schema and rules defined in the system prompt, reconstruct the specific financial event strictly from the input Content below. Base all details on Content and follow the requirement in the Description and Keywords; do not invent, alter, or extend beyond what it explicitly supports. Produce a clear, layered, professional JSON output.

=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===

Generate content in JSON format according to the SYSTEM_PROMPT schema.
"""


_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parents[1] / "structure.py"
)
_STRUCTURE_SPEC = (
    extract_dataclass_blocks(_STRUCTURE_SPEC_FULL, mode="all")
    if _STRUCTURE_SPEC_FULL
    else ""
)
SYSTEM_PROMPT = SYSTEM_PROMPT.replace("xxxxxx", _STRUCTURE_SPEC_FULL)


class LMBuilder(BaseBuilder):
    """
    Build the financial event cascade from the input content using the LM model."""

    def __init__(self, lm_name: str = "deepseek/deepseek-chat", config=None):
        super().__init__(method_name="lm_builder", build_config={"lm_name": lm_name})

        generation_config = (
            {} if "generation_config" not in config else config["generation_config"]
        )
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=generation_config,
        )

        self.system_prompt = (
            SYSTEM_PROMPT if "system_prompt" not in config else config["system_prompt"]
        )
        self.user_prompt = (
            USER_PROMPT if "user_prompt" not in config else config["user_prompt"]
        )

        # Add output directory configuration
        self.output_dir = config.get(
            "output_dir", "./examples/utest/Collector/test_files/event_cascade_output"
        )

    def save_event_cascade(
        self, event_cascade: Dict[str, Any], output_path: str = None
    ):
        """
        Save event cascade data to JSON files in a structured directory.

        Args:
            event_cascade: Parsed event cascade dictionary
            output_path: Base output directory (defaults to self.output_dir)
        """
        if output_path is None:
            output_path = self.output_dir

        # Create timestamped directory
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base_dir = os.path.join(output_path, f"event_cascade_{timestamp}")
        os.makedirs(base_dir, exist_ok=True)

        print(f"Saving event cascade to: {base_dir}")

        # Check structure - looking for FinancialEventReconstruction
        if "FinancialEventReconstruction" in event_cascade:
            event_data = event_cascade["FinancialEventReconstruction"]
        else:
            # Assume direct structure if key not found
            event_data = event_cascade

        # Save main event cascade file
        main_file = os.path.join(base_dir, "EventCascade.json")
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(event_data, f, ensure_ascii=False, indent=2)
        print(f"Saved main event cascade to: {main_file}")

        # Save stages separately if they exist in the structure
        if "stages" in event_data:
            stages_dir = os.path.join(base_dir, "stages")
            os.makedirs(stages_dir, exist_ok=True)

            stages = event_data["stages"]
            if isinstance(stages, list):
                for idx, stage in enumerate(stages):
                    if isinstance(stage, dict):
                        sid = stage.get("stage_id", f"S{idx+1}")
                        stage_file = os.path.join(stages_dir, f"{sid}.json")
                        with open(stage_file, "w", encoding="utf-8") as f:
                            json.dump(stage, f, ensure_ascii=False, indent=2)
                        print(f"✓ Saved stage {sid} to: {stage_file}")

        return base_dir

    def load_samples(self, build_input: BuildInput) -> Any:
        """Load the specific content of samples from the files."""
        # For the input of the lm-based builder, we need to combine the content of the samples into a long string.
        samples_content = "\n\n".join(
            [
                read_text_data_from_block(sample.location)
                for sample in build_input.samples
            ]
        )
        print(f"Loaded {len(build_input.samples)} samples")
        return samples_content

    def build(self, build_input: BuildInput) -> BuildOutput:
        """Build the event cascades from the input samples."""
        # We first need to convert the samples presented in the build input
        # to the format required by this function
        samples_content = self.load_samples(build_input)

        # Infer the llm API
        output: InferOutput = self.lm_api.run(
            infer_input=InferInput(
                system_msg=self.system_prompt.replace("{", "{{").replace("}", "}}"),
                user_msg=self.user_prompt,
            ),
            Query=build_input.user_query.query_text,
            Keywords=build_input.user_query.key_words,
            Content=samples_content,
        )

        # Extract and save JSON
        try:
            print(output.response)
            event_cascade_json = extract_json_response(output.response)
            saved_dir = self.save_event_cascade(event_cascade_json)
            print(f"Successfully saved event cascade to directory: {saved_dir}")
        except Exception as e:
            print(f"Warning: Failed to save JSON files: {e}")
            # Fallback: save raw response
            raw_output_path = os.path.join(
                self.output_dir, "build_out_raw_response.json"
            )
            os.makedirs(self.output_dir, exist_ok=True)
            with open(raw_output_path, "w", encoding="utf-8") as f:
                f.write(output.response)
            print(f"Raw response saved to: {raw_output_path}")

        return BuildOutput(event_cascades=[output.response])
