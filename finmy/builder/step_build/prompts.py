"""
Prompts of the step-wise event builder.
"""

EventLayoutReconstructorSys = """
You are a senior expert in financial‑event type identification and event skeleton reconstruction. Your task is to reconstruct and set the skeleton for one specific financial event strictly from real data: respect `Query` and `Keywords`, and use only facts in `Content`. Produce one JSON object that matches the schema exactly.

Scope:
- Focus only on `EventCascade`, `EventStage`, and `Episode`.
- Determine event type, the number of stages, and the number of episodes per stage.
- Use `VerifiableField` as defined in the Schema for applicable fields.

Target structure (reconstruction focus):
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]

Required fields to output:
- EventCascade: output ALL fields defined in the schema. Populate strictly from Content; set unsupported fields to null or omit.
- EventStage: `stage_id`, `name`, `index_in_event`, `episodes: List[Episode]`.
- Episode: `episode_id`, `name`, `index_in_stage`.
- The usage of `VerifiableField` must strictly follow the Schema definition.

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
Based on Query, Keywords, and Content, output a single raw JSON object for EventCascade that follows the Schema definition and Target structure exactly. Focus only on event skeleton reconstruction.

Instructions:
- Scope: EventCascade, EventStage, Episode only; use `VerifiableField` as defined in the Schema for applicable fields.
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
You are a senior expert in financial‑event episode reconstruction. Reconstruct the TARGET Episode strictly from `Content`, aligned by `Query` and `Keywords`. Output ONE raw JSON `Episode` that matches the Schema exactly.

Inputs:
- StageSkeleton: stage name, episode identifiers, and chronology only
- TargetEpisode: given identifiers (`episode_id`, `name`, `index_in_stage`) and any preset fields to be completed
- Query, Keywords, Content

Constraints:
- The TARGET Episode is identified by `episode_id`, `name`, `index_in_stage`.
- Treat `episode_id` and `index_in_stage` as immutable; change `name` only with strong, explicit, and unambiguous evidence from `Content`.
- Use `Content` as the sole evidentiary source for field values; use StageSkeleton only for identifiers and chronology.
- Follow the Schema exactly; names and types must match.

Instructions:
- Complete every field comprehensively, explicitly, and in detail from `Content`, guided by `Query` and `Keywords`. Maximize coverage of all supported facts; avoid omissions.
- For each assignment, use `VerifiableField` and concise reasons that explain selection and support.
- If evidence is insufficient, set `value` to null or omit and provide brief low‑confidence reasons; never fabricate or infer beyond `Content`.
- If evidence is insufficient, set `value` to null or omit and explicitly state the reason (e.g., no source support, ambiguity, conflicting information). Attach that cites the relevant text demonstrating the issue; never fabricate or infer beyond `Content`.
- Maintain chronological and contextual consistency with StageSkeleton; ensure non‑conflicting ordering and temporal coherence. All relations/flows must reference participants present in this Episode.
- Participant continuity across episodes: when a participant already exists in earlier episodes, reference the same `participant_id` and explicitly indicate continuity by adding `attributes["same_as"]` = VerifiableField[str](value=`participant_id`) with evidence and reasons. Do not create duplicate participants.

Output:
- ONE raw JSON `Episode`; no explanations or code fences.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


EpisodeReconstructorUser = """
Task:
- Produce ONE raw JSON `Episode` for the TARGET episode strictly following the Schema. The TARGET episode is identified by `episode_id`, `name`, `index_in_stage`.

Inputs:
- StageSkeleton (only stage name, episode identifiers, chronology), TargetEpisode (the given identifiers and any preset fields), Query, Keywords, Content

Instructions:
- Complete every field comprehensively, explicitly, and in detail from `Content`, guided by `Query` and `Keywords`. Maximize coverage of all supported facts; avoid omissions.
- For each assignment, use `VerifiableField` and concise reasons that explain selection and support.
- If evidence is insufficient, set `value` to null or omit and provide brief low‑confidence reasons; never fabricate or infer beyond `Content`.
- Maintain chronological and contextual consistency with StageSkeleton; all relations/flows must reference participants present in this Episode.
- Participant continuity across episodes: when a participant already exists in earlier episodes, reference the same `participant_id` and explicitly indicate continuity by adding `attributes["same_as"]` = VerifiableField[str](value=`participant_id`) with evidence and reasons. Do not create duplicate participants.

Field Requirements (Episode as defined in the Schema):
- `episode_id`, `name`, `index_in_stage`: identifiers are given; do not modify. Only change `name` if `Content` strongly, explicitly, and unambiguously supports a correction.
- All other fields: follow the Schema definitions and annotations strictly. Fill each field comprehensively from `Content`, guided by `Query` and `Keywords`, using `VerifiableField` and concise reasons. Maximize coverage of supported facts.
- All other fields: Never set to be null, empty list ([]) and dict, or omit unless explicitly stated in the Schema or `Content` provides strong, explicit, and unambiguous evidence to support absence. If the null or omit is necessary, always provide VerifiableField with null value and explicit reasons such as (e.g., "no source support", "ambiguity and conflict", "no timestamp mentioned in Content", "conflicting timestamps across sources", "only relative/implicit time"), etc.

Output:
- ONE raw JSON object for `Episode`; no explanations or code fences.

=== STAGE SKELETON BEGIN ===
{StageSkeleton}
=== STAGE SKELETON END ===

=== TARGET EPISODE BEGIN ===
{TargetEpisode}
=== TARGET EPISODE END ===

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


StageSummarzierSys = """

"""

StageSummarzierSys = """

"""
