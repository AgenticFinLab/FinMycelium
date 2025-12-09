"""
Prompts of the step-wise event builder.
"""

EventLayoutCreatorSys = """
You are tasked to propose an overall event structure strictly from the provided Content and within the schema. Output a single JSON object that conforms to the dataclasses from the reference block and only includes fields supported by the source.

Hard rules:
- Use only fields/types from the schema block.
- Populate fields only when supported by Content; otherwise set null or omit.
- Participant IDs must be canonical if present: "P_" + 32 lowercase hex.

Target structure:
EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]
              ├── participants: List[Participant]
              ├── participant_relations: List[ParticipantRelation]
              ├── actions: { participant_id → List[Action] }
              ├── transactions: List[Transaction]
              └── interactions: List[Interaction]

Schema reference:
=== BEGIN structure.py dataclasses ===
{STRUCTURE_SPEC}
=== END structure.py dataclasses ===
"""


EventLayoutCreatorUser = """
Generate the overall EventCascade JSON strictly from Content, focusing on defining stages and episode containers. Do not invent details beyond Content.

=== DESCRIPTION BEGIN ===
{Description}
=== DESCRIPTION END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===
""".strip()
