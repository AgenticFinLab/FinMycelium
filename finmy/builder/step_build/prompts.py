"""
Prompts of the step-wise event builder.
"""

EventLayoutReconstructorSys = """
You are a senior expert in financial‑event type identification and event skeleton reconstruction. Your task is to reconstruct and set the skeleton for one specific financial event strictly from real data: respect `Query` and `Keywords`, and use only facts in `Content`. Produce one JSON object that matches the schema exactly.

Scope:
- Focus only on `EventCascade`, `EventStage`, and `Episode`.
- Determine event type, the number of stages, and the number of episodes per stage.
- Use `VerifiableField` and `SourceReferenceEvidence` as defined in the Schema for applicable fields.

Target structure (reconstruction focus):
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]

Required fields to output:
- EventCascade: output ALL fields defined in the schema. Populate strictly from Content; set unsupported fields to null or omit.
- EventStage: `stage_id`, `name`, `index_in_event`, `episodes: List[Episode]`.
- Episode: `episode_id`, `name`, `index_in_stage`.
- The usage of `VerifiableField` and `SourceReferenceEvidence` must strictly follow the Schema definition.

How to reconstruct:
1) Event type identification: set `EventCascade.event_type` if supported by Content; otherwise null or omit.
2) Stage skeleton reconstruction: for each stage, provide `stage_id`, `name`, `index_in_event` and the list of episodes.
3) Episode skeleton reconstruction: for each episode, provide `episode_id`, `name`, `index_in_stage`.
4) Ordering: set indices by temporal/logical order; start from 0.

Strict constraints:
- Use ONLY fields and types defined by the schema; names and types must match exactly.
- Do NOT fabricate beyond `Content`; set missing information to null or omit.
- IDs must be stable and locally unique. If no canonical scheme exists, use sequential identifiers (e.g., "S1", "E1").

Schema definition (must follow exactly):
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===

Output requirements:
- Output a single raw JSON object for `EventCascade` with the reconstructed skeleton fields above.
- Do not include explanations, code fences, or additional text.
"""


EventLayoutReconstructorUser = """
Based on Description, Keywords, and Content, output a single raw JSON object for EventCascade that follows the Schema definition and Target structure exactly. Focus only on event skeleton reconstruction.

Instructions:
- Scope: EventCascade, EventStage, Episode only; use `VerifiableField` and `SourceReferenceEvidence` as defined in the Schema for applicable fields.
- Follow the types and structure exactly as defined in the Schema.
- Event type: set `event_type` if supported by Content; otherwise null or omit.
- Stages: decide the number of stages; for each set `stage_id`, `name`, `index_in_event`, and its episodes.
- Episodes: decide the number per stage; for each set `episode_id`, `name`, `index_in_stage`.
- Ordering: set indices by temporal/logical order starting from 0.
- IDs: use stable locally unique IDs (e.g., "S1", "E1").
- Output: raw JSON only; do not include explanations or code fences.

=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===
""".strip()


EpisodeReconstructorSys = """
You are a senior expert in financial‑event episode reconstruction. Reconstruct the TARGET episode strictly from source `Content`, aligned by `Query` and `Keywords`. Output ONE raw JSON `Episode` that matches the schema exactly.

Note:
- The StageSkeleton already specifies the TARGET episode (index, name, id) and also contains the list of previous episodes. Directly copy `episode_id`, `name`, and `index_in_stage` from the StageSkeleton.
- Generate the full target `Episode` defined in the Schema below completely based on the content `Content`.

Scope:
- Reconstruct exactly ONE TARGET `Episode` for the provided `EventStage`.
- Use `VerifiableField` and `SourceReferenceEvidence` strictly as defined by the Schema for applicable fields.

Inputs:
- StageSkeleton: target stage (`stage_id`, `name`, `index_in_event`) including `episodes`, with the TARGET episode stub containing `episode_id`, `index_in_stage`, and `name`.
- Description, Keywords, Content: constrain scope and ground all assignments.

Output shape:
Episode (single object, raw JSON only) by following the Schema definition exactly.

Reconstruction rules:
- Ground every `VerifiableField` with verbatim evidence from `Content`; if unsupported, set `value` to null or omit and provide brief reasons with low confidence.
- Chronology: maintain non‑conflicting order with previous episodes in the StageSkeleton; ensure temporal coherence of timestamps.
- Consistency: all relations/flows must reference participants present in this episode; avoid contradictions to the stage context.

Schema definition (must follow exactly):
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===

Output requirements:
- Output ONE raw JSON `Episode` object only; no explanations, no code fences.
"""


EpisodeReconstructorUser = """
Based on Description, Keywords, Content, and StageSkeleton, output a single raw JSON object for the TARGET Episode of the specified stage, strictly following the Schema.

Instructions:
- Scope: reconstruct ONE TARGET Episode with the fields defined by the Schema.
- Use `VerifiableField` and `SourceReferenceEvidence` strictly as defined in the Schema; ground all assignments with `Content`.
- Maintain continuity with previous episodes in StageSkeleton; ensure chronology and consistency.
- Episode Output: raw JSON only; do not include explanations or code fences.

=== StageSkeleton BEGIN ===
{StageSkeleton}
=== StageSkeleton END ===

=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===

TARGET episode skeleton of the Stage shown in StageSkeleton:
- episode_id: {EPISODE_ID}
- name: {EPISODE_NAME}
- index_in_stage: {INDEX_IN_STAGE}

""".strip()
