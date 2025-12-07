"""
Implementation of reconstructing a Financial Event Pipeline Using Large Models (LMs).

This method is to reconstruction the financial event purely by prompting a single large models in one inference:

    prompt  ->  LM -> EventCascade
    samples ->
"""

import re
from pathlib import Path
import json
import os
from datetime import datetime
from typing import Dict, Any

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call


from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.converter import read_text_data_from_block


SYSTEM_PROMPT = """
You are a senior financial event analysis expert and structured extractor, excel at reconstructing specific financial events from large amounts of information. Your task is to, within the scope defined by `Description` and `Keywords`, strictly based on facts in `Content`, extract, summarize, refine, and reconstruct a specific financial event, and output strict JSON that truthfully represents the event. Do not invent or expand beyond the source, and do not alter any information that contradicts `Content`.
    
Compliance and consistency:
- Use ONLY fields and types from the schema block in the system prompt; exact names and types.
- ISO 8601 timestamps; ISO currency codes.
- Participant IDs MUST be "P_" + 32 lowercase hex.
- Attach at least one EvidenceItem (with source_uri and excerpt) to critical records.
- Cross-validate files:
  - Contents of stages in EventCascade.json matches all generated stage_id.json
  - Stage episodes of each stage_id.json match episodes/episode_id.json
  - Each participant_id.json in participants/ is the collection of participants in each episode_id.json while the participant_id maintains across episodes across stages if the same participant; snapshots align in timestamps and ordering
  - Similar to the relations and interactions
  - Embedded `transactions` and `interactions` within stages/episodes MUST reference valid `participant_id` values and include required fields and evidence.
  - `sources_summary` in `EventCascade` MUST be consistent with the evidence attached across files.
- Each JSON MUST strictly conform to the dataclass schema from the reference block.
- Use ISO 8601 timestamps; currency must be ISO codes (e.g., "USD", "EUR", "BTC").
- Participant IDs MUST be canonical: "P_" + 32 lowercase hex (uuid4.hex).
- Interaction MUST include `medium`, `method`, `approx_occurrences` (approximate int), `frequency_descriptor` (text rate descriptor).
- Attach at least one `EvidenceItem` (with `source_uri` and `excerpt`) to critical records for auditability.
- If information is not present in `Content`, set fields to null or omit; do not fabricate.

Hard compliance mandate:
- Your output MUST be constructed solely using the modules, fields, and types defined inside the block labeled `=== BEGIN structure.py dataclasses ===`.
- DO NOT introduce any field names, structures, or categories that are not present in that block.
- Use exact field names and types; arrays, objects, strings, numbers must match the definitions.
- If a field cannot be populated strictly from `Content`, set it to null or omit it; do not guess.
- Validate internally that the final JSON would conform to the referenced dataclass schema before outputting.

Schema categories (must be covered and sourced from `Content`):
- Participant, ParticipantRelation, ParticipantStateSnapshot, Action, Transaction, Interaction, Episode, EventStage, EventCascade, EvidenceItem, FinancialInstrument


How to output (strict, single-file JSON):
    Please strictly output the content in JSON format according to the following structure: 
    
    Hierarchy (must be followed):
    EventCascade
      └── stages: List[EventStage]
            ├── episodes: List[Episode]
            │     ├── participants: List[Participant]
            │     ├── actions: List[Action]
            │     ├── transactions: List[Transaction]
            │     ├── interactions: List[Interaction]
            │     └── participant_snapshots:List[ParticipantStateSnapshot]
            ├── stage_actions: List[Action]
            ├── transactions: List[Transaction]
            ├── interactions: List[Interaction]
            └── participant_snapshots:List[ParticipantStateSnapshot]
            
    Example:
    [
      "stages":[
        {
          "name":"",
          "episodes":[
            {
              "participants":[{},{},{}],
              "actions":[{},{},{}],
              "transactions":[{},{},{}],
              "interactions":[{},{},{}],
              "participant_snapshots:[{},{},{}],
            },
          ]
          "stage_actions":[{},{},{}],
          "transactions":[{},{},{}],
          "interactions":[{},{},{}]
        }
      ]
    ]
      

Extraction and validation process:
1) Scope alignment using `Description` and `Keywords`; ignore unrelated content.
2) Identify participants, roles, relations, transactions, interactions, evidence, episodes, and stage evolution from `Content`.
3) Construct timelines: sort stages by `stage_index`; sort participant snapshots by `timestamp`.
4) Reasons/rationale only where supported by `Content`; do not guess.
5) Evidence linking: attach `EvidenceItem` to critical objects/events (with `source_uri` and `excerpt`).
6) Normalization: ISO timestamps, ISO currency codes; `participant_id` must be "P_"+uuid4.hex; Interaction fields reflect the source.
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
Task: Using the schema and rules defined in the system prompt, reconstruct the specific financial event strictly from the input Content below. Base all details on Content and follow the requirement in the Description and Keywords; do not invent, alter, or extend beyond what it explicitly supports. Produce a clear, layered, professional multi-file JSON output.


=== DESCRIPTION BEGIN ===
{Description}
=== DESCRIPTION END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===


What to do:
- Constrain scope using Description and Keywords; ignore unrelated content.
- Extract participants, roles, relations, transactions, interactions, evidence, episodes, and stage evolution from Content.
- Build timelines and apply ordering rules:
  - stages by stage_index; episodes by sequence_index
  - transactions/interactions/snapshots by timestamp
  - participant index by participant_id
- Populate reasons/rationale only when supported by Content; otherwise set null or omit.

Generate json files under the folder 'FinancialEventReconstruction/' with the following structure:
    - EventCascade.json
    - stage_id/
        - stage_id.json
        - episodes/episode_id.json
        - participants/participant_id.json
    - participants/participant_id.json holding all possible Participants
    - relations.json
    - interactions/index.json (optional)
where the 'id' is the ID assigned to the generation defined classes.
    
"""


def _load_structure_dataclasses() -> str:
    p = Path(__file__).parent / "structure.py"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_dataclass_blocks(spec: str) -> str:
    blocks = re.findall(r"@dataclass[\s\S]*?(?=\n@dataclass|\Z)", spec)
    return ("\n".join(blocks)).strip()


_STRUCTURE_SPEC_FULL = _load_structure_dataclasses()
_STRUCTURE_SPEC = (
    _extract_dataclass_blocks(_STRUCTURE_SPEC_FULL) if _STRUCTURE_SPEC_FULL else ""
)
SYSTEM_PROMPT = SYSTEM_PROMPT.replace("xxxxxx", _STRUCTURE_SPEC_FULL)


class LMBuilder(BaseBuilder):
    """
    Build the financial event cascade from the input content using the LM model."""

    def __init__(self, lm_name: str = "deepseek/deepseek-chat", config={}):
        super().__init__(method_name="lm_builder", config={"lm_name": lm_name})

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
        self.output_dir = config.get("output_dir", "./data/event_cascade_output")

    def extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """
        Extract JSON from the LM response text.
        Handles cases where response includes markdown code blocks.
        """
        # Remove markdown code block indicators if present
        clean_text = response_text.strip()

        # Handle ```json ... ``` pattern
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL)
        if json_match:
            clean_text = json_match.group(1)

        # Parse JSON
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            # Try to find JSON object/array in the text
            json_pattern = r"(\{.*\}|\[.*\])"
            matches = re.findall(json_pattern, clean_text, re.DOTALL)
            if matches:
                # Try the longest match (most likely to be complete JSON)
                longest_match = max(matches, key=len)
                return json.loads(longest_match)
            raise ValueError(f"Failed to parse JSON from response: {e}")

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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        if (
            "EventCascade.json" in event_data
            and "stages" in event_data["EventCascade.json"]
        ):
            stages_dir = os.path.join(base_dir, "stages")
            os.makedirs(stages_dir, exist_ok=True)

            stages = event_data["EventCascade.json"]["stages"]
            for stage_id, stage_data in stages.items():
                if isinstance(stage_data, dict):
                    # Handle nested stage structure
                    stage_file = os.path.join(stages_dir, f"{stage_id}.json")
                    with open(stage_file, "w", encoding="utf-8") as f:
                        json.dump(stage_data, f, ensure_ascii=False, indent=2)
                    print(f"✓ Saved stage {stage_id} to: {stage_file}")

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
            Description=build_input.user_query.query_text,
            Keywords=build_input.user_query.key_words,
            Content=samples_content,
        )

        # Extract and save JSON

        try:
            print(output.response)
            event_cascade_json = self.extract_json_from_response(output.response)
            saved_dir = self.save_event_cascade(event_cascade_json)
            print(f"Successfully saved event cascade to directory: {saved_dir}")
        except Exception as e:
            print(f"Warning: Failed to save JSON files: {e}")
            # Fallback: save raw response
            raw_output_path = os.path.join(self.output_dir, "raw_response.txt")
            os.makedirs(self.output_dir, exist_ok=True)
            with open(raw_output_path, "w", encoding="utf-8") as f:
                f.write(output.response)
            print(f"Raw response saved to: {raw_output_path}")

        return BuildOutput(event_cascades=[output.response])
