"""
Define the structure of the financial event cascade by providing base entities and containers for financial event reconstruction.

Structure overview:
- Participant: identity and stable attributes of entities involved
- ParticipantRelation: explicit relationship edge between participants (e.g., affiliation, control, counterparty)
- Action: discrete behaviors performed by a participant (timestamped details)
- Transaction: financial transfers between participants
- Episode: coherent sub-phase within a stage holding participants, relations, and transactions
- EventStage: one phase of the event, holding episodes and stage-level metadata
- EventCascade: top-level container, holding ordered stages and event-level metadata
- VerifiableField: wrapper ensuring a field value is directly grounded in source content with evidence and reasons

Relationship Among Event, Stage, Episode, and Participant:
- Event: A financial shock with significant market impact (e.g., a major default, regulatory sanction, market crash, or sudden policy change).
- Stage: A continuous time interval in the event's evolution, defined by a unified dominant logic or system state. The number and naming of stages should be determined flexibly based on the event itself—do not force predefined templates.
- Episode: A key sub-event within a stage. Each episode must be:
(1) Concrete (with clear timestamp, actor, and action),
(2) Causal (explains subsequent market or institutional responses), and
(3) Capital-market relevant (impacts asset prices, risk, or liquidity).
- Participant: An entity associated with an episode, labeled by its financial role

Diagram:

EventCascade
  └── stages: List[EventStage]
        └── episodes: List[Episode]
              ├── participants: List[Participant]
              ├── participant_relations: List[ParticipantRelation]
              ├── transactions: List[Transaction]

"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class VerifiableField:
    """Field wrapper that requires direct grounding in original source content.

    Purpose:
    - Ensure the assigned `value` is strictly supported by the source contents
    - Capture selection criteria and normalization context for auditability

    Fields:
    - value: assigned value strictly derived from source content (string)
    - evidence_source_contents: list of exact source snippets supporting this value
    - reasons: list explaining why sources were selected and how they justify the value
    - confidence: confidence score in [0.0, 1.0] reflecting certainty of assignment

    Example:
    VerifiableField(
      value="$10000.0",
      evidence_source_contents=["... $10,000 transfer ..."],
      reasons=["exact keyword match: '$10,000 transfer'", "named entities present"],
      confidence=0.9
    )
    """

    # Assigned value strictly derived from source content
    value: str
    # Verbatim evidence supporting the value; must include exact source content
    # Provide exact original text snippets (no rewriting) that justify the assigned value.
    evidence_source_contents: List[str] = field(default_factory=list)
    # Encapsulated explanation for why evidence_source_contents are selected as evidence and how its support justifies the assigned value.
    # reasons should indicate selection and support criteria (e.g., exact keyword match, direct quote/claim, numeric data, named entity, explicit timeframe, etc....) to present detailed rationals.
    reasons: List[str] = field(default_factory=list)
    # Confidence score in [0.0, 1.0] reflecting confidence of applying reasons for the source content selection as the evidence.
    confidence: Optional[float] = None


@dataclass
class ParticipantRelation:
    """Relationship between two participants.

    Includes explicit or implicit relations (e.g., shared ownership, control, client-of),
    as well as documented collaborations or communications where they establish a linkage.

    Example:

    Bidirectional example:
    {
      "from_participant_id": "P_2",
      "to_participant_id": "P_4",
      "relation_name": VerifiableField(value="ownership affiliation"),
      "descriptions": [
        VerifiableField(value="X and Y share a common parent company (public registry verified)")
      ],
      "relation_type": VerifiableField(
        value="affiliated with",
        evidence_source_contents=["parent company: ..."],
        reasons=["shared ownership", "Registry shows common parent entity with explicit affiliation"],
        confidence=0.85
      ),
      "is_bidirectional": true,
      "start_time": None,
      "end_time": None
    }
    """

    # Source participant (edge origin) — references Participant.participant_id.
    from_participant_id: str
    # Target participant (edge destination) — references Participant.participant_id.
    to_participant_id: str
    # Human-readable label for the relation semantics (e.g., 'ownership affiliation', 'client relationship').
    # Use a normal phrase without underscores; must be grounded in source content.
    relation_name: VerifiableField = field(
        default_factory=lambda: VerifiableField(
            value="unspecified",
            reasons=["insufficient information in source content"],
        )
    )
    # Descriptions of the relation, each value grounded in source.
    descriptions: Optional[List[VerifiableField]] = None
    # Relation type label (e.g., 'member of', 'client of', 'counterparty'); use a normal phrase without underscores; grounded in source content.
    relation_type: VerifiableField = field(
        default_factory=lambda: VerifiableField(value="unspecified")
    )
    # Temporal bounds when the relation holds as mentioned in the source content.
    start_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    end_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )


@dataclass
class Transaction:
    """Financial transfer between participants.

    Example:
    {
      "name": VerifiableField(value="wire transfer"),
      "transaction_type": VerifiableField(value="payment"),
      "timestamp": VerifiableField(value="2025-01-01T12:00:00Z"),
      "details": [VerifiableField(value="USD 10,000 wire"), VerifiableField(value="settlement: SWIFT")],
      "from_participant_id": "P_1",
      "to_participant_id": "P_2",
      "instruments": [VerifiableField(value="bond", evidence_source_contents=["... bond payment ..."])]
    }
    """

    # Transaction name (e.g., 'wire transfer', 'token swap', 'bond coupon').
    # Use a normal, human-readable phrase without underscores; grounded in source content.
    name: VerifiableField
    # Transaction type (e.g., 'payment', 'settlement', 'funding transfer').
    # Use a normal, human-readable phrase without underscores; grounded in source content.
    transaction_type: VerifiableField = field(
        default_factory=lambda: VerifiableField(
            value="unspecified",
            reasons=["insufficient information in source content"],
        )
    )
    # Transaction occurrence time (wall-clock); provide the most credible timestamp; use UTC.
    timestamp: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    # Transaction details presented by the descriptions between two participants
    details: List[VerifiableField] = field(default_factory=list)
    # Payer participant identifier; references `Participant.participant_id`; do not use names or aliases.
    from_participant_id: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    # Payee participant identifier; references `Participant.participant_id`.
    to_participant_id: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    # Related instruments/tools; optional; describes the vehicle of transfer (e.g., bond payment, token transfer).
    instruments: Optional[List[VerifiableField]] = None


@dataclass
class Action:
    """The specific action executed by one participant.

    Example:
    {
      "name": VerifiableField(value="broadcast message"),
      "timestamp": VerifiableField(value="2025-01-02T09:00:00Z"),
      "details": [VerifiableField(value="Guaranteed 30% monthly returns"), VerifiableField(value="channel: platform_feed")]
    }
    """

    # Action name (e.g., 'broadcast message', 'pitch'); grounded in source content to label the action type/style/meaning.... succinctly.
    name: VerifiableField

    # Chronological context.
    timestamp: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    # Details of one participant's action (each item grounded in source).
    details: List[VerifiableField] = field(default_factory=list)


# ============================================================================
# MICRO: Participant Identity — Stable attributes, relations, and background
# ============================================================================
@dataclass
class Participant:
    """Participant involved in the financial event.

    Example:
    {
      "participant_id": "P_3",
      "name": VerifiableField(value="Credit Suisse"),
      "participant_type": "organization",
      "base_role": VerifiableField(value="issuer"),
      "attributes": {
        "location": VerifiableField(value="Zurich"),
        "industry": VerifiableField(value="banking"),
        "tags": VerifiableField(value="tier1")
      },
      "actions": [
        Action(
          name=VerifiableField(value="broadcast_message"),
          timestamp=VerifiableField(value="2025-01-02T09:00:00Z"),
          details=[
            VerifiableField(value="Guaranteed 30% monthly returns"),
            VerifiableField(value="channel: platform_feed")
          ]
        )
      ]
    }
    """

    # Guidance: Do not enumerate every participant except for key persons and specific entities.
    # For large cohorts of similar participants, represent them as a single "group participant".
    # Use `participant_type` to indicate the cohort category and `attributes`/`tags` to describe
    # the group's scope, characteristics, and provenance.

    # Unique, immutable identifier, must be in canonical form: "P_" + integer
    # Example: P_1
    participant_id: str

    # Specific, concrete financial entity name (e.g., "Credit Suisse", "瑞信").
    name: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # High-level category (string).
    # Examples: "individual", "organization", "social_media_platform", "government_agency".
    # For large cohorts, prefer a group category (e.g., "retail_investor_group", "marketing_bot_group")
    # and describe scope via attributes/tags (e.g., size band, region, platform).
    participant_type: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Primary functional role in this event.
    # Examples: 'victim', 'perpetrator', 'influencer', 'media', 'regulator', 'bystander'.
    base_role: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Static or semi-static descriptive properties grounded in source content.
    # Examples:
    #   - Individuals: {"age_group": VerifiableField(value="30-40"), "location": VerifiableField(value="Shanghai")}
    #   - Organizations: {"industry": VerifiableField(value="fintech"), "employee_count": VerifiableField(value="50")}
    attributes: Dict[str, VerifiableField] = field(default_factory=dict)

    # Actions executed by this participant.
    actions: List[Action] = field(default_factory=list)


# ============================================================================
# MESO: Coherent phase in event development
# ============================================================================
@dataclass
class Episode:
    """A coherent episode within a stage.

    Episodes group participants, relations, and transactions that share a tighter
    temporal window or thematic focus than the surrounding stage.
    They enable fine-grained modeling without losing stage-level aggregation.

    Example:
    {
      "episode_id": "E1",
      "name": VerifiableField(value="Private Pitch"),
      "index_in_stage": 0,
      "descriptions": [
        VerifiableField(value="Targeted promises to select investors"),
        VerifiableField(value="Private pitch to select investors.")
      ],
      "start_time": VerifiableField(value="2025-01-03T10:00:00Z"),
      "end_time": VerifiableField(value="2025-01-03T12:00:00Z"),
      "participants": [Participant(...)],
      "participant_relations": [ParticipantRelation(...)],
      "transactions": [Transaction(...)]
    }
    """

    # Locally unique identifier for referencing and storage; avoid semantic identifiers to reduce ambiguity.
    # Must follow the format "E" + integer, incrementing sequentially based on the episode order.
    episode_id: str
    # Name; human-readable semantic label; grounded via verifiable source content.
    name: VerifiableField
    # Zero-based index within the owning stage; used for ordering and timeline reconstruction.
    index_in_stage: int
    # Detailed and concise information from source content presenting the episode’s essence across aspects. Provide multiple items when supported by sources; each item is a grounded, verifiable statement.
    descriptions: List[VerifiableField] = None

    # Start time; earliest evidence or activity; unknown if uncertain.
    start_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )
    # End time; latest evidence or activity; unknown if ongoing or boundaries are unclear.
    # Set to "unknown" if end time is not available in the source content.
    end_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # List of entities participating in this episode; directly relevant `Participant` records.
    participants: List[Participant] = field(default_factory=list)

    # Explicit relationship edges among participants in this event.
    participant_relations: List[ParticipantRelation] = field(default_factory=list)

    # Financial transfers within this episode; linked to participants/instruments.
    transactions: List[Transaction] = field(default_factory=list)


@dataclass
class EventStage:
    """Stage of the event development.

    Example:
    {
      "stage_id": "S1",
      "name": VerifiableField(value="Amplification"),
      "index_in_event": 2,
      "descriptions": [
        VerifiableField(value="Promotions spread rapidly across channels"),
        VerifiableField(value="Rapid spread of promotional messages")
      ],
      "start_time": VerifiableField(value="2025-01-01T00:00:00Z"),
      "end_time": VerifiableField(value="unknown", reasons=["insufficient information in source content"]),
      "episodes": [Episode(...)]
    }
    """

    # Unique identifier for referencing and storage; avoid semantic identifiers to reduce ambiguity.
    # Must follow the format "S" + integer, incrementing sequentially based on the stage order.
    stage_id: str
    # Descriptive name (e.g., 'Bait Deployment', 'Amplification').
    name: VerifiableField
    # Zero-based index (ensures correct ordering) of this stage in the event.
    index_in_event: int

    # Detailed and concise information from source content presenting the stage’s essence across aspects. Provide multiple items when supported; each item is a grounded, verifiable statement.
    descriptions: List[VerifiableField]

    # Earliest timestamp of activity or evidence in this stage.
    # Set to "unknown" if start time is not available in the source content.
    start_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Latest timestamp (may be None for ambiguous boundaries).
    # Set to "unknown" if end time is not available in the source content.
    end_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Episodes nested within this stage
    episodes: List[Episode] = field(default_factory=list)


# ============================================================================
# MACRO: Complete event reconstruction — the top-level container
# ============================================================================
@dataclass
class EventCascade:
    """Whole event cascade reconstruction.

    Example:
    {
      "event_id": "fraud_crypto_2025_001",
      "title": "High-yield Crypto Scheme",
      "event_type": VerifiableField(value="financial_fraud"),
      "descriptions": [
        VerifiableField(value="A scheme with promised high returns and broad online promotion"),
        VerifiableField(value="A high-yield scheme promoted across social platforms")
      ],
      "start_time": VerifiableField(value="2025-01-01T00:00:00Z"),
      "end_time": VerifiableField(value="2025-01-10T00:00:00Z"),
      "stages": [EventStage(...)]
    }
    """

    # Globally unique identifier (e.g., 'fraud_crypto_2025_001').
    # A short, unique string to identify this specific event instance.
    # It should ideally combine the event type, a key entity or location, and a year/sequence.
    # Examples:
    # - "ponzi_madoff_2008"
    # - "bankrun_svb_2023"
    # - "insider_trading_galleon_2009"
    event_id: str

    # Human-readable title summarizing the event (verbatim when available).
    # This should be a clear, descriptive headline.
    # Examples:
    # - "Collapse of FTX Exchange"
    # - "Bernie Madoff Investment Scandal"
    # - "Silver Thursday Market Manipulation"
    title: VerifiableField

    # Categorical label from domain sources (verbatim when available).
    # Represents the primary classification of the financial event.
    # Examples:
    # - "Ponzi Scheme"
    # - "Bank Run"
    # - "Market Manipulation"
    # - "Accounting Fraud"
    # - "Sovereign Default"
    event_type: VerifiableField

    # Detailed and concise information from source content presenting the event’s essence across aspects. Provide multiple items when supported; each item is a grounded, verifiable statement.
    descriptions: List[VerifiableField]

    # Earliest timestamp across all evidence and participant activity.
    # Set to "unknown" if start time is not available in the source content.
    start_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Latest timestamp (None if ongoing or unresolved).
    # Set to "unknown" if end time is not available in the source content.
    end_time: Optional[VerifiableField] = field(
        default_factory=lambda: VerifiableField(
            value="unknown",
            reasons=["insufficient information in source content"],
        )
    )

    # Ordered sequence of event phases.
    stages: List[EventStage] = field(default_factory=list)
