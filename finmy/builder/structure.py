"""
Define the structure of the financial event cascade by providing base entities and containers for financial event reconstruction.

Structure overview:
- Participant: identity and stable attributes of entities involved
- ParticipantRelation: explicit relationship edge between participants
- Action: discrete behaviors recorded within episodes
- Transaction: financial transfers between participants
- Episode: coherent sub-phase within a stage holding participants, relations, transactions
- EventStage: one phase of the event, holding episodes and stage-level metadata
- EventCascade: top-level container, holding ordered stages and event-level metadata
- VerifiableField: wrapper ensuring a field value is directly grounded in source content

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
from typing import Optional, Any, Dict, List, TypeVar, Generic


T = TypeVar("T")


@dataclass
class VerifiableField(Generic[T]):
    """Field wrapper that requires direct grounding in original source content.

    Purpose:
    - Ensure the assigned `value` is strictly supported by the source contents
    - Capture selection criteria and normalization context for auditability

    Fields:
    - value: assigned value strictly derived from source content (typed via Generic[T])
    - evidence_source_contents: list of source contents supporting this value
    - reasons: list of reasons for the source contents selection and the value assignment
    - confidence: confidence score in [0.0, 1.0] reflecting confidence of applying reasons for the source content selection as the evidence.
    - extras: extension metadata (e.g., unit, normalization, selection_method, match_score)

    Example:
    VerifiableField[float](
      value=10000.0,
      evidence_source_contents=["... $10,000 transfer ..."],
      reasons=["exact keyword match"],
      confidence=0.9,
      extras={"unit": "USD", "normalized": True},
    )
    """

    # Assigned value strictly derived from source content
    value: T
    # Verbatim evidence supporting the value; must include exact source content
    # Should be exact original text snippet (no rewriting) that supports the value above; clearly include the precise source text that justifies it.
    evidence_source_contents: List[str] = field(default_factory=list)
    # Encapsulated explanation for why evidence_source_contents are selected as evidence and how its support justifies the assigned value.
    # reasons should indicate selection and support criteria (e.g., exact keyword match, direct quote/claim, numeric data, named entity, explicit timeframe, etc....) to present detailed rationals.
    reasons: List[str] = field(default_factory=list)
    # Confidence score in [0.0, 1.0] reflecting confidence of applying reasons for the source content selection as the evidence.
    confidence: Optional[float] = None
    # Additional information of this field
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParticipantRelation:
    """Relationship between two participants. The content may include explicit, implicit relations (e.g., shared ownership, joint venture, or common control), any type of interactions, communications, or cooperations.

    Example:

    Bidirectional example:
    {
      "from_participant_id": "P_X",
      "to_participant_id": "P_Y",
      "description": "X and Y share a common parent company (public registry verified)",
      "relation_type": VerifiableField[str](
        value="affiliated_with",
        evidence_source_content=["parent company: ..."],
        reasons=["shared ownership", "Registry shows common parent entity with explicit affiliation"],
        confidence=0.85
      ),
      "is_bidirectional": true,
      "start_time": None,
      "end_time": None,
      "attributes": {"registry_country": VerifiableField[str](value="UK")}
    }
    """

    # Source participant (edge origin) — references Participant.participant_id.
    from_participant_id: str
    # Target participant (edge destination) — references Participant.participant_id.
    to_participant_id: str
    # Natural-language description of the relation (verbatim or quoted from source when available).
    description: Optional[VerifiableField[str]] = None
    # Relation label (e.g., 'member_of', 'client_of', 'counterparty'); grounded in source content.
    relation_type: VerifiableField[str] = field(
        default_factory=lambda: VerifiableField(value="unspecified")
    )
    # Whether the relation is symmetric (e.g., 'affiliated_with').
    is_bidirectional: bool = False
    # Temporal bounds when the relation holds as mentioned in the source content.
    start_time: Optional[VerifiableField[str]] = None
    end_time: Optional[VerifiableField[str]] = None
    # Arbitrary metadata for this relation (e.g., contract/jurisdiction), each value grounded in source.
    attributes: Dict[str, VerifiableField[Any]] = field(default_factory=dict)


# ============================================================================
# DOMAIN ENTITIES: Financial constructs and actions
# ============================================================================


@dataclass
class FinancialInstrument:
    """Financial instrument used or referenced in the event.

    Example:
    {
      "description": VerifiableField[str](value="bond"),
      "attributes": {"issuer": VerifiableField[str](value="ACME"), "coupon": VerifiableField[float](value=0.05), "maturity": VerifiableField[str](value="2030-12-31")}
    }
    """

    # Instrument description of what and which type of instrument is used
    description: VerifiableField[str] = field(
        default_factory=lambda: VerifiableField(value="unspecified")
    )
    # Static/semi-static attribute map; examples: issuer, coupon, maturity; include only facts directly supported by evidence and normalize units/formats.
    attributes: Dict[str, VerifiableField[Any]] = field(default_factory=dict)


@dataclass
class Transaction:
    """Financial transfer between participants.

    Example:
    {
      "timestamp": VerifiableField[str](value="2025-01-01T12:00:00Z"),
      "details": [VerifiableField[str](value="USD 10,000 wire"), VerifiableField[str](value="settlement: SWIFT")],
      "from_participant_id": "P_A",
      "to_participant_id": "P_B",
      "instrument": FinancialInstrument(...)
    }
    """

    # Transaction occurrence time (wall-clock); provide the most credible timestamp; use UTC.
    timestamp: Optional[VerifiableField[str]] = None
    # Transaction details presented by the descriptions between two participants
    details: List[VerifiableField[str]] = field(default_factory=list)
    # Payer participant identifier; references `Participant.participant_id`; do not use names or aliases.
    from_participant_id: str = ""
    # Payee participant identifier; references `Participant.participant_id`; if unknown, leave empty and explain in `extras`.
    to_participant_id: str = ""
    # Related financial instrument; optional; describes the vehicle of transfer (e.g., bond payment, token transfer).
    instrument: Optional[FinancialInstrument] = None


@dataclass
class Action:
    """The specific action executed by one participant.

    Example:
    {
      "timestamp": VerifiableField[str](value="2025-01-02T09:00:00Z"),
      "details": [VerifiableField[str](value="broadcast_message"), VerifiableField[str](value="Guaranteed 30% monthly returns"), VerifiableField[str](value="channel: platform_feed")]
    }
    """

    # Chronological context.
    timestamp: Optional[VerifiableField[str]] = None
    # Details of one participant's action (each item grounded in source).
    details: List[VerifiableField[str]] = field(default_factory=list)


# ============================================================================
# MICRO: Participant Identity — Stable attributes, relations, and background
# ============================================================================
@dataclass
class Participant:
    """Participant involved in the financial event.

    Example:
    {
      "participant_id": "P_3f2a1c4b6d7e8f90123456789abcdeff",
      "name": VerifiableField[str](value="Credit Suisse"),
      "participant_type": "organization",
      "base_role": VerifiableField[str](value="issuer"),
      "attributes": {"location": VerifiableField[str](value="Zurich"), "industry": VerifiableField[str](value="banking"), "tags": VerifiableField[List[str]](value=["tier1"])},
      "actions": {"broadcast_message": [Action(timestamp=VerifiableField[str](value="2025-01-02T09:00:00Z"), details=[VerifiableField[str](value="Guaranteed 30% monthly returns"), VerifiableField[str](value="channel: platform_feed")])]}
    }
    """

    # Guidance: Do not enumerate every participant except for key persons and specific entities.
    # For large cohorts of similar participants, represent them as a single "group participant".
    # Use `participant_type` to indicate the cohort category and `attributes`/`tags` to describe
    # the group's scope, characteristics, and provenance.

    # Unique, immutable identifier (e.g., UUID, hashed ID, semantic key).
    # must be in canonical form: "P_" + 32 lowercase hex characters
    # Regex: ^P_[a-f0-9]{32}$
    # Example: - P_3f2a1c4b6d7e8f90123456789abcdeff
    participant_id: str

    # Specific, concrete financial entity name (e.g., "Credit Suisse", "瑞信").
    name: VerifiableField[str] = field(
        default_factory=lambda: VerifiableField(value="unspecified")
    )

    # High-level category.
    # Examples: 'individual', 'organization', 'social_media_platform', 'government_agency'.
    # For large cohorts, prefer a group category (e.g., 'retail_investor_group', 'marketing_bot_group')
    # and describe scope via attributes/tags (e.g., size band, region, platform).
    participant_type: str

    # Primary functional role in this event.
    # Examples: 'victim', 'perpetrator', 'influencer', 'media', 'regulator', 'bystander'.
    base_role: VerifiableField[str] = field(
        default_factory=lambda: VerifiableField(value="unknown")
    )

    # Static or semi-static descriptive properties.
    # Examples:
    #   - Individuals: {"age_group": "30-40", "education": "bachelor", "location": "Shanghai"}
    #   - Organizations: {"industry": "fintech", "employee_count": 50}
    attributes: Dict[str, VerifiableField[Any]] = field(default_factory=dict)

    # Actions executed by this participant.
    actions: Dict[str, List[Action]] = field(default_factory=dict)


# ============================================================================
# MESO: Coherent phase in event development
# ============================================================================
@dataclass
class Episode:
    """A coherent episode within a stage.

    Episodes group participants, transactions, and snapshots that share a tighter temporal window or thematic focus than the surrounding stage.
    They enable fine-grained modeling without losing stage-level aggregation.

    Example:
    {
      "episode_id": "E1",
      "name": VerifiableField[str](value="Private Pitch"),
      "description": VerifiableField[str](value="Targeted promises to select investors"),
      "index_in_stage": 0,
      "start_time": VerifiableField[str](value="2025-01-03T10:00:00Z"),
      "end_time": VerifiableField[str](value="2025-01-03T12:00:00Z"),
      "details": [VerifiableField[str](value="Key investors received targeted promises")],
      "participants": [Participant(...)],
      "transactions": [Transaction(...)],
      "confidence_score": 0.8
    }
    """

    # Locally unique identifier for referencing and storage; avoid semantic identifiers to reduce ambiguity.
    episode_id: str
    # Name; human-readable semantic label; grounded via verifiable source content.
    name: VerifiableField[str]
    # Short description that supplements the episode name; less granular than `details`.
    description: Optional[VerifiableField[str]] = None
    # Zero-based index within the owning stage; used for ordering and timeline reconstruction.
    index_in_stage: int = 0

    # Detailed description summarizing the episode's theme and key activities.
    details: List[VerifiableField[str]] = field(default_factory=list)

    # Start time; earliest evidence or activity; None if uncertain.
    start_time: Optional[VerifiableField[str]] = None
    # End time; latest evidence or activity; None if ongoing or boundaries are unclear.
    end_time: Optional[VerifiableField[str]] = None

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
      "name": VerifiableField[str](value="Amplification"),
      "description": VerifiableField[str](value="Promotions spread rapidly across channels"),
      "index_in_event": 2,
      "start_time": VerifiableField[str](value="2025-01-01T00:00:00Z"),
      "end_time": None,
      "details": [VerifiableField[str](value="Rapid spread of promotional messages")],
      "episodes": [Episode(...)]
    }
    """

    stage_id: str

    # Descriptive name (e.g., 'Bait Deployment', 'Amplification').
    name: VerifiableField[str]
    # Short description that supplements the stage name; less granular than `details`.
    description: Optional[VerifiableField[str]] = None

    # Zero-based index (ensures correct ordering) of this stage in
    # the event.
    index_in_event: int = 0

    # Detailed and concise natural-language summary of this stage’s essence.
    details: List[VerifiableField[str]] = field(default_factory=list)

    # Earliest timestamp of activity or evidence in this stage.
    start_time: Optional[VerifiableField[str]] = None

    # Latest timestamp (may be None for ambiguous boundaries).
    end_time: Optional[VerifiableField[str]] = None

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
      "description": VerifiableField[str](value="A scheme with promised high returns and broad online promotion"),
      "event_type": "financial_fraud",
      "details": [VerifiableField[str](value="A high-yield scheme promoted across social platforms")],
      "start_time": VerifiableField[str](value="2025-01-01T00:00:00Z"),
      "end_time": VerifiableField[str](value="2025-01-10T00:00:00Z"),
      "stages": [EventStage(...)],
      "confidence_score": 0.75,
      "domain_context": "Post-pandemic digital finance boom in SEA"
    }
    """

    # Globally unique identifier (e.g., 'fraud_crypto_2025_001').
    event_id: str

    # Human-readable title summarizing the event (verbatim when available).
    title: Optional[VerifiableField[str]] = None
    # Short description that supplements the event title; less granular than `details`.
    description: Optional[VerifiableField[str]] = None

    # Categorical label from domain sources (verbatim when available).
    event_type: Optional[VerifiableField[str]] = None

    details: List[VerifiableField[str]] = field(default_factory=list)

    # Earliest timestamp across all evidence and participant activity.
    start_time: Optional[VerifiableField[str]] = None

    # Latest timestamp (None if ongoing or unresolved).
    end_time: Optional[VerifiableField[str]] = None

    # Ordered sequence of event phases.
    stages: List[EventStage] = field(default_factory=list)
