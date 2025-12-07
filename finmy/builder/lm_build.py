"""
Implementation of reconstructing a Financial Event Pipeline Using Large Models (LMs).

This method is to reconstruction the financial event purely by prompting a single large models in one inference:

    prompt  ->  LM -> EventCascade
    samples ->
"""

import re
from pathlib import Path
from typing import Any

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call


from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.converter import read_text_data_from_block


SYSTEM_PROMPT = """
You are a senior financial event analysis expert and structured extractor, excel at reconstructing specific financial events from large amounts of information. Your task is to, within the scope defined by `Description` and `Keywords`, strictly based on facts in `Content`, extract, summarize, refine, and reconstruct a specific financial event, and output strict JSON that truthfully represents the event. Do not invent or expand beyond the source, and do not alter any information that contradicts `Content`.

Output requirements (strict JSON only):
- Output multiple JSON files; no prose, Markdown, or code fences.
- Emit each file as a header line followed by a single JSON object:
  === file: <path/to/file.json> ===
  { ...one JSON object conforming to a dataclass... }
- Mandatory file: EventCascade.json containing a valid `EventCascade`.
 - Required structured modules (emit as needed based on Content):
   - EventCascade.json → one `EventCascade` (mandatory)
   - stages/stage_{i}.json → one `EventStage` per stage
   - episodes/episode_{id}.json → one `Episode` per episode
   - participants/{participant_id}.json → one `Participant` plus `ParticipantStateSnapshot` list per participant
- Cross-file consistency and verification:
  - The `EventCascade.stages` list MUST align with emitted `stages/stage_{i}.json` files (same `stage_index`, `name`).
  - Episodes referenced in stage content MUST align with emitted `episodes/episode_{id}.json` files (`sequence_index`, `start_time`/`end_time`).
  - All `participant_id` values referenced anywhere MUST have a corresponding `participants/{participant_id}.json`; snapshots match timestamps and ordering rules.
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

Hierarchy (must be followed):
EventCascade
  └── stages: List[EventStage]
        ├── episodes: List[Episode]
        │     ├── participants: List[Participant]
        │     ├── actions: List[Action]
        │     ├── transactions: List[Transaction]
        │     ├── interactions: List[Interaction]
        │     └── participant_snapshots
        ├── stage_actions: List[Action]
        ├── transactions: List[Transaction]
        ├── interactions: List[Interaction]
        └── participant_snapshots

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

How to output (strict, multi-file JSON):
- Emit each file as:
  === file: <path/to/file.json> ===
  { ...one strict JSON object conforming to a dataclass... }
- Mandatory:
  - === file: EventCascade.json ===
    { ...EventCascade object... }
- Also emit, as needed for layered clarity:
  - === file: stages/stage_{i}.json ===
    { ...EventStage object... }
  - === file: episodes/episode_{id}.json ===
    { ...Episode object... }
  - === file: participants/{participant_id}.json ===
    { "participant": ...Participant..., "snapshots": [ ...ParticipantStateSnapshot... ] }
  - === file: relations.json ===
    { "relations": [ ...ParticipantRelation... ] }
  - Optionally (if helpful): === file: interactions/index.json ===
    { "interactions": [ ...Interaction... ] }

Compliance and consistency:
- Use ONLY fields and types from the schema block in the system prompt; exact names and types.
- ISO 8601 timestamps; ISO currency codes.
- Participant IDs MUST be "P_" + 32 lowercase hex.
- Attach at least one EvidenceItem (with source_uri and excerpt) to critical records.
- Cross-validate files:
  - EventCascade.stages matches stages/stage_{i}.json (stage_index, name)
  - Stage episodes match episodes/episode_{id}.json (sequence_index, start/end time)
  - Each participant_id has a participants/{participant_id}.json; snapshots align in timestamps and ordering
  - Embedded transactions/interactions reference valid participant_id and include required fields/evidence
  - EventCascade.sources_summary is to count the number of evidence items across files
- Output only the JSON files in the format above; no extra text.
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

    def load_samples(self, build_input: BuildInput) -> Any:
        """Load the specific content of samples from the files."""
        # For the input of the lm-based builder, we need to combine the content of the samples into a long string.
        samples_content = "\n\n".join(
            [
                read_text_data_from_block(sample.location)
                for sample in build_input.samples
            ]
        )
        print(samples_content)
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
        return BuildOutput(event_cascades=[output.response])
