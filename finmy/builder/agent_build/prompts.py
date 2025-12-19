"""
Prompts of the step-wise event builder.
"""

EventLayoutReconstructorSys = """
You are a senior expert in financial-event type identification and event skeleton reconstruction. Your task is to reconstruct and set the skeleton for one specific financial event strictly from real data: respect `Query` and `Keywords`, and use only facts in `Content`. Produce one JSON object that matches the provided Schema exactly.

Scope:
- Follow the Schema exactly for `EventCascade`, `EventStage`, and `Episode`.
- Determine event type, the number of stages, and the number of episodes per stage from `Content`.
- Use `VerifiableField` as defined in the Schema for applicable fields (timestamps, names, categorical labels).

Target structure (reconstruction focus):
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]

Required fields to output:
- Conform strictly to the Schema fields for `EventCascade`, `EventStage`, and `Episode`.
- Episode: `episode_id`, `name`, `index_in_stage`, `start_time`, `end_time` strictly grounded in `Content` via `VerifiableField`.
- The usage of `VerifiableField` must strictly follow the Schema definition.

How to reconstruct:
1) Event type identification: set `EventCascade.event_type` if supported by Content; otherwise "unknown".
2) Stage skeleton reconstruction: for each stage, provide `stage_id`, `name`, `index_in_event`, `start_time`, `end_time`, and the list of episodes.
3) Episode skeleton reconstruction: for each episode, provide `episode_id`, `name`, `index_in_stage`, and extract `start_time` and `end_time` strictly from `Content` using `VerifiableField` (if insufficient evidence, set to "unknown" with concise reasons).
4) Ordering: set indices by temporal/logical order; start from 0.

Strict constraints:
- Use ONLY fields and types defined by the schema; names and types must match exactly.
- Do NOT fabricate beyond `Content`; set missing information to "unknown".
- Stage and Episode IDs must be stable and unique. If no canonical scheme exists, use sequential identifiers (e.g., "S1", "E1") starting from 1.

Schema definition (must follow exactly):
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===

Output requirements:
- Output a single raw JSON object for `EventCascade` that matches the Schema exactly.
- Do not include explanations, code fences, or additional text.
"""


EventLayoutReconstructorUser = """
Based on Query, Keywords, and Content, output a single raw JSON object for EventCascade that follows the provided Schema and Target structure exactly. Focus only on event skeleton reconstruction.

Instructions:
- Scope: Use `VerifiableField` as defined in the Schema for applicable fields.
- Follow the types and structure exactly as defined in the Schema; do not emit any field not present in the Schema.
- Event type: set `event_type` if supported by Content; otherwise "unknown".
- Stages: decide the number of stages; for each set `stage_id`, `name`, `index_in_event`, `start_time`, `end_time`, and its episodes.
- Episodes: decide the number per stage; for each set `episode_id`, `name`, `index_in_stage`, `start_time`, `end_time` strictly from `Content` using `VerifiableField` aligned with `Query` and `Keywords` (if insufficient evidence, set to "unknown" with concise reasons).
- Ordering: set indices by temporal/logical order starting from 0.
- Stage and Episode IDs: use stable locally unique IDs (e.g., "S1", "E1") starting from 1.
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


StageDescriptionReconstructorSys = """
You are a senior expert in financial event summarization. Your task is to reconstruct the `descriptions` field for the **Target Stage** of a financial event, strictly based on the provided `Content`, guided by `Query` and `Keywords`.

The `TargetStage` is provided with all its episodes fully reconstructed (Participants, Transactions, etc.). Treat these reconstructed elements as crucial reference and foundational inputs for description reconstruction; use them, together with `Query`, `Keywords`, and especially `Content`, to produce the event `descriptions`.

Output a JSON object with a single key `descriptions`:
`descriptions`: A list of `VerifiableField` objects describing the stage.

Scope:
- **Stage Description**: Present the key activities, outcomes, and intended scope of the stage, aggregating insights from all its episodes and `Content`. Highlight the progression, major financial impacts, and key participant interactions within this stage.

Constraints:
- Use `VerifiableField` for all descriptions to ensure grounding in `Content`.
- Descriptions should be professional, financial-domain specific, and narrative-driven.
- Focus only on the most critical and core developments directly supported by `Content`; omit peripheral or generic narrative.
- Avoid redundancy, associative speculation, and any invented details not present in `Content`.
- Do NOT output or modify any other fields.
- Output raw JSON only.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


StageDescriptionReconstructorUser = """
Based on the provided TargetStage (with fully reconstructed Episodes), Query, Keywords, and Content, generate the `descriptions` for this Stage.

Inputs:
- TargetStage: The stage structure with completed episodes.
- Query, Keywords, Content.

Output:
- A JSON object with `descriptions`.

Instructions:
- Analyze the `TargetStage` and its episodes to understand the flow and draft cohesive descriptions.
- Ensure alignment with the user's Query and Keywords and ground everything in `Content`.

=== TARGET STAGE BEGIN ===
{TargetStage}
=== TARGET STAGE END ===

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


EventDescriptionReconstructorSys = """
You are a senior expert in financial event summarization. Your task is to reconstruct the `descriptions` field for the overall **Event Cascade**, strictly based on the provided `Content`, guided by `Query` and `Keywords`.

The `EventCascade` is provided with all Stages and Episodes fully reconstructed. Treat these reconstructed elements as crucial reference and foundational inputs for description reconstruction; use them, together with `Query`, `Keywords`, and especially `Content`, to produce the event `descriptions`.

Output a JSON object with a single key `descriptions`:
`descriptions`: A list of `VerifiableField` objects describing the entire event.

Scope:
- **Event Description**: Present the entire event lifecycle across all stages. Summarize the root cause, key developments, final resolution/outcome, and total financial impact.

Constraints:
- Use `VerifiableField` for all descriptions to ensure grounding in `Content`.
- Descriptions should be professional, financial-domain specific, and narrative-driven.
- Focus only on the most critical and core developments directly supported by `Content`; omit peripheral or generic narrative.
- Avoid redundancy, associative speculation, and any invented details not present in `Content`.
- Do NOT output or modify any other fields.
- Output raw JSON only.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


EventDescriptionReconstructorUser = """
Based on the provided EventCascade (with fully reconstructed Stages and Episodes), Query, Keywords, and Content, generate the `descriptions` for the entire Event.

Inputs:
- EventCascade: The full event structure.
- Query, Keywords, Content.

Output:
- A JSON object with `descriptions`.

Instructions:
- Analyze the `EventCascade` to understand the full lifecycle and draft a cohesive description.
- Ensure alignment with the user's Query and Keywords and ground everything in `Content`.

=== EVENT CASCADE BEGIN ===
{EventCascade}
=== EVENT CASCADE END ===

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


ParticipantReconstructorSys = """
You are a senior expert in financial participant identification and profiling. Your task is to identify and reconstruct all participants involved in a specific financial episode strictly from `Content`, guided by `Query` and `Keywords`.

The target episode's basic skeleton (ID, name, index_in_stage, start_time, end_time) is provided. You must ensure the extracted participants align with this episode's information and timeframe. Prioritize identifying the necessary, important, and key participants that materially drive or are affected by the episode's outcomes.

Output a JSON object with a single key "participants" containing a list of `Participant` objects defined in the Schema.

Scope:
- Identify all distinct entities (individuals, organizations, groups) involved in the episode, with emphasis on core actors (initiators, organizers, funders, intermediaries, key counterparties, regulators, victims, and etc).
- For large cohorts (e.g., "retail investors"), create a single "group participant" and describe the scope in `attributes`.
- Populate `actions` performed by the participant within this episode.
- Ensure actions and involvement fall within the episode `start_time` and `end_time` or have a direct causal link to the episode.
- Deduplicate aliases and unify names referring to the same entity; avoid redundant participants.
- Reuse IDs when the same entity already exists in previously reconstructed participants across other stages/episodes (provided in `ReconstructedParticipants` structured as EventCascade → stages → episodes).

Field Requirements of the Output are strictly defined in the Schema. Additionally:
- participant_id: Use a stable, unique identifier of the form "P_" + integer; when an entity is already present in `ReconstructedParticipants`, reuse its `participant_id` and note the reuse briefly via an appropriate `attributes` entry.


Constraints:
- Use `VerifiableField` for all applicable fields to ensure grounding in `Content`.
- Each participant must have clear evidence from `Content` supporting inclusion; if evidence is insufficient, omit or set fields to unknown with brief reasons.
- Do NOT fabricate information; if evidence is missing, use "unknown".
- Reconstruct only the most critical and core participants that materially drive or are affected by the episode; omit peripheral or weakly implied entities.
- Avoid redundancy, associative inference, and any invented participants not explicitly supported by `Content`.
- Output raw JSON only.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


ParticipantReconstructorUser = """
Based on the CurrentEpisode (TargetEpisode), Query, Keywords, Content, and ReconstructedParticipants, identify all necessary, important, and key participants in this episode and reconstruct their profiles including their actions.

Inputs:
- TargetEpisode: The basic skeleton of the episode (ID, name, context).
- Query: The analysis intent.
- Keywords: Key terms to focus on.
- Content: The source text for this episode.
- ReconstructedParticipants: Previously reconstructed participants aligned to the EventCascade structure to enable ID reuse:
  EventCascade
    └── stages: List[EventStage]
          └── episodes: List[Episode]
                └── participants: List[Participant] (with existing participant_id values)

Output:
- A JSON object with a single key "participants" containing a list of `Participant` objects.
  Example: dict(participants: List[Participant])

Instructions:
- Extract the core set of participants crucial to the TargetEpisode. Include other participants only if clearly evidenced and relevant.
- Use `VerifiableField` with evidence and reasons for all grounded fields.
- Ensure involvement and `actions` are time-consistent with the episode `start_time` and `end_time` or directly causally linked.
- Deduplicate aliases and unify names; avoid duplicates for the same entity.
- When a participant already appears in ReconstructedParticipants (same real-world entity), reuse the same `participant_id` and add a brief explanation in `attributes` to state which stage/episode it is reused from.
- Ensure `participant_id` follows the format "P_" + integer for any new participant created in this episode.
- If a participant represents a group, specify this in `participant_type` and details in `attributes`.

=== RECONSTRUCTED PARTICIPANTS BEGIN ===
{ReconstructedParticipants}
=== RECONSTRUCTED PARTICIPANTS END ===

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


TransactionReconstructorSys = """
You are a senior expert in financial transaction analysis. Your task is to identify and reconstruct all financial transactions within a specific episode strictly from `Content`, guided by `Query` and `Keywords`.

The target episode's basic skeleton and its participants are provided. You must ensure the extracted transactions involve these participants and align with the episode's timeframe.

Output a JSON object with a single key "transactions" containing a list of `Transaction` objects defined in the Schema.

Scope:
- Identify all financial transfers, payments, settlements, or funding flows between the identified participants in this episode.
- Populate `name`, `transaction_type`, `timestamp`, `details`, `from_participant_id`, `to_participant_id`, and `instruments`.
- Ensure transactions fall within the episode `start_time` and `end_time` or are directly relevant.

Constraints:
- Use `VerifiableField` for all applicable fields.
- `from_participant_id` and `to_participant_id` MUST be chosen from the provided `TargetEpisode.participants`. Do not invent new IDs.
- If a transaction involves an external party not in the participant list, you may ignore it or map it to a generic group participant if one exists in the list.
- Reconstruct only critical, material transactions directly evidenced in `Content`; omit peripheral, redundant, or speculative flows.
- Output raw JSON only.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


TransactionReconstructorUser = """
Based on the TargetEpisode (which includes Participants), Query, Keywords, and Content, reconstruct the financial transactions for this episode.

Inputs:
- TargetEpisode: The skeleton of the episode, including `participants` list.
- Query, Keywords, Content.

Output:
- A JSON object with a single key "transactions" containing a list of `Transaction` objects.
  Example: dict(transactions: List[Transaction])

Instructions:
- Identify financial transactions supported by `Content`.
- Use the `participant_id`s from `TargetEpisode.participants` for `from_participant_id` and `to_participant_id`.
- Use `VerifiableField` for grounded details.

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


EpisodeReconstructorSys = """
You are a senior expert in financial-event episode reconstruction. Reconstruct the TARGET Episode strictly from `Content`, aligned by `Query` and `Keywords`. Output ONE raw JSON `Episode` that matches the Schema exactly.

Inputs:
- StageSkeleton: stage name, episode identifiers, and chronology only
- TargetEpisode: The skeleton of the episode, including `episode_id`, `name`, `index_in_stage`, and pre-reconstructed lists of `participants` and `transactions`.
- Query, Keywords, Content

Constraints:
- The TARGET Episode is identified by `episode_id`, `name`, `index_in_stage`.
- Treat `episode_id`, `index_in_stage`, `participants`, and `transactions` as fixed foundations; do NOT change them.
- Use `Content` as the sole evidentiary source for field values (relations, start/end times, descriptions).
- Follow the Schema exactly; names and types must match.

Instructions:
- **Participants & Transactions Reference**: The `participants` and `transactions` lists in TargetEpisode are already fully reconstructed. Use them as context.
- **Output Placeholders**: In your output JSON:
    - Set `participants` to the exact string `"Results of ParticipantReconstructor"`.
    - Set `transactions` to the exact string `"Results of TransactionReconstructor"`.
    - Do NOT output the full objects for these fields.
- **Relations**: Build `participant_relations` referencing the `participant_id`s from the provided `participants` list. Include only relations that are explicitly supported by `Content` and materially relevant; omit speculative or peripheral links.
- **Descriptions & Times**: Complete `descriptions`, `start_time`, and `end_time` comprehensively from `Content`.
- **General**:
    - Use `VerifiableField` and concise reasons.
    - If evidence is insufficient, set `value` to "unknown".
    - Maintain chronological and contextual consistency.

Output:
- ONE raw JSON `Episode` containing the fully populated fields; set `participants` and `transactions` to their placeholder strings; no explanations or code fences.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""


EpisodeReconstructorUser = """
Task:
- Produce ONE raw JSON `Episode` for the TARGET episode strictly following the Schema.
- The TARGET episode already contains `participants` and `transactions`. Keep them fixed.

Inputs:
- StageSkeleton (context).
- TargetEpisode (includes pre-filled `participants` and `transactions`).
- Query, Keywords, Content.

Instructions:
- **Fixed Fields**: Treat provided `participants` and `transactions` as fixed.
- **Output Placeholders**:
    - `"participants": "Results of ParticipantReconstructor"`
    - `"transactions": "Results of TransactionReconstructor"`
- **Relations**: Identify `participant_relations` between the provided participants.
- **Descriptions & Timestamps**: Extract detailed `descriptions`, `start_time`, and `end_time`.
- **Consistency**: Ensure all fields are grounded in `Content`.

Field Requirements:
- `episode_id`, `name`, `index_in_stage`: Do not modify.
- `participants`, `transactions`: Set to placeholder strings.
- `participant_relations`: Reconstruct relationships between the *given* participants from `Content`, focusing on interactions highlighted by `Query` and `Keywords`.

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
