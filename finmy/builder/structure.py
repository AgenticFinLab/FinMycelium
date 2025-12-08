"""
Define the structure of the financial event cascade by providing base entities and containers for financial event reconstruction.

Structure overview:
- Participant: identity and stable attributes of entities involved
- ParticipantRelation: explicit relationship edge between participants
- ParticipantState: time-stamped dynamic state and actions of a participant
- Action: discrete behaviors recorded within states/episodes
- Transaction: financial transfers between participants with evidence
- Interaction: messages/broadcasts among participants with explanation metadata
- Episode: coherent sub-phase within a stage holding participants, states, actions, transactions, interactions
- EventStage: one phase of the event, holding episodes and stage-level metadata
- EventCascade: top-level container, holding ordered stages and event-level metadata
- SourceReferenceEvidence: exact source content support for records
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
              ├── actions: List[Action]
              ├── transactions: List[Transaction]
              ├── interactions: List[Interaction]
              └── participant_states: { participant_id → [ParticipantState] }

"""

from datetime import datetime

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, TypeVar, Generic


@dataclass
class FinancialExplain:
    """Explanatory metadata for why a record is configured in its current mode/state.

    Purpose:
    - Provide concrete justification for setting the record as-is (what, why, how)
    - Improve auditability by separating bullet-point reasons from detailed narrative rationale

    Fields:
    - reasons: concise bullet points capturing key justifications
    - rationale: detailed prose explaining the reasoning chain, assumptions, scope, and links to the generation, extraction, or summarization.

    Example:
    {"reasons": ["official filing"], "rationale": "Prospectus confirms coupon and maturity; issuer verified via registry"}
    """

    # Concise bullet points capturing the key justifications; treat as a checklist of factors.
    reasons: List[str] = field(default_factory=list)
    # Detailed prose laying out the reasoning chain, constraints/assumptions, and explicit links to assignment.
    rationale: str = ""


@dataclass
class SourceReferenceEvidence:
    """Evidence reference from the source content that supports anchoring an action/transaction/interaction.

    Example:
    {
      "source_type": "news",
      "source_content": "Company promised 30% monthly returns",
      "confidence": 0.8,
      "explain": {
        "reasons": [
          "exact keyword match: '30% monthly returns'",
          "named issuer present",
          "direct claim stating numeric rate"
        ],
        "rationale": "Selected as evidence because the text contains an exact keyword match and a direct numeric rate claim attributed to the issuer; selection verified via keyword match and semantic context; links to Transaction.amount via 'supported_field'."
      },
      "extras": {}
    }
    """

    # Content category label (e.g., "news", "report", "platform_log").
    source_type: str = "unspecified"
    # Exact original text snippet (no rewriting) that supports a specific setting/assignment; clearly include the precise source text that justifies it.
    source_content: str = ""

    # Encapsulated explanation for why this source_content was selected as evidence.
    # reasons should indicate selection criteria (e.g., exact keyword match, direct quote/claim, numeric data, named entity, explicit timeframe).
    # rationale should detail the selection method (e.g., keyword/regex/semantic), validation steps, and linkage to supported fields.
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Flexible extension map. Suggested keys: "supported_field" (e.g., "Transaction.amount"), "support_scope" ("direct"|"indirect"|"contextual"), "char_span" ([start,end]), "paragraph_index" (int), "language" (e.g., "en"), "selection_method" ("keyword"|"regex"|"semantic"), "match_score" (float).
    extras: Dict[str, Any] = field(default_factory=dict)
    # Confidence score in [0.0, 1.0] reflecting trustworthiness and relevance of this evidence. Example: 0.9 for official filings; 0.5 for anonymous claims.
    confidence: Optional[float] = None


T = TypeVar("T")


@dataclass
class VerifiableField(Generic[T]):
    """Field wrapper that requires direct grounding in original source content.

    Purpose:
    - Ensure the assigned `value` is strictly supported by exact text in `EvidenceItem.source_content`
    - Capture selection criteria and normalization context for auditability

    Fields:
    - value: assigned value strictly derived from source content (typed via Generic[T])
    - evidence: list of EvidenceItem with verbatim `source_content` supporting this value
    - explain: FinancialExplain describing why/how the value is set
    - confidence: optional reliability score for this assignment (0.0–1.0)
    - extras: extension metadata (e.g., unit, normalization, selection_method, match_score)

    Example:
    VerifiableField[float](
      value=10000.0,
      evidence=[SourceReferenceEvidence(source_type="bank_record", source_content:"... $10,000 transfer ...")],
      explain=FinancialExplain(reasons=["exact numeric present"], rationale="Amount is directly quoted from the bank record"),
      confidence=0.9,
      extras={"unit": "USD", "normalized": True, "selection_method": "keyword", "match_score": 0.96},
    )
    """

    # Assigned value strictly derived from source content
    value: T
    # Verbatim evidence supporting the value; must include exact source content
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Explanation describing why/how this value is set
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Reliability score (0.0–1.0) for the assignment
    confidence: Optional[float] = None
    # Extension metadata (e.g., unit, normalization, selection_method, match_score)
    extras: Dict[str, Any] = field(default_factory=dict)
    # No runtime type guard; rely on Generic[T] and static typing.


@dataclass
class ParticipantRelation:
    """Relationship between two participants.

    Example:
    {
      "from_participant_id": "P_A",
      "to_participant_id": "P_B",
      "description": "A is a long-term paying client of B",
      "relation_type": VerifiableField[str](
        value="client_of",
        evidence=[SourceReferenceEvidence(source_type="report", source_content="contract signed on ...")],
        explain=FinancialExplain(reasons=["explicit label present"], rationale="Relation label appears verbatim in the contract"),
        confidence=0.9,
        extras={"selection_method": "keyword", "match_score": 0.98}
      ),
      "is_bidirectional": false,
      "start_time": None,
      "end_time": None,
      "strength": 0.8,
      "tags": ["financial"],
      "attributes": {"contract_id": "C-2025-001"},
      "explain": {"reasons": ["service agreement signed"], "rationale": "Observed formal KYC onboarding and recurring payments"},
      "evidence": [SourceReferenceEvidence(source_type="report", source_content="contract signed on ...")],
      "extras": {"jurisdiction": "US"}
    }

    Bidirectional example:
    {
      "from_participant_id": "P_X",
      "to_participant_id": "P_Y",
      "description": "X and Y share a common parent company (public registry verified)",
      "relation_type": VerifiableField[str](
        value="affiliated_with",
        evidence=[SourceReferenceEvidence(source_type="registry", source_content="parent company: ...")],
        explain=FinancialExplain(reasons=["shared ownership"], rationale="Registry shows common parent entity with explicit affiliation"),
        confidence=0.85,
        extras={"selection_method": "keyword", "match_score": 0.95}
      ),
      "is_bidirectional": true,
      "start_time": None,
      "end_time": None,
      "tags": ["corporate"],
      "explain": {"reasons": ["shared ownership structure"], "rationale": "Public registry shows common parent entity"},
      "evidence": [SourceReferenceEvidence(source_type="registry", source_content="parent company: ...")],
      "extras": {"registry_country": "UK"}
    }
    """

    # Source participant (edge origin) — references Participant.participant_id.
    from_participant_id: str
    # Target participant (edge destination) — references Participant.participant_id.
    to_participant_id: str
    # Natural-language description of the relation.
    description: str = ""
    # Relation label (e.g., 'member_of', 'client_of', 'counterparty'); grounded in source content.
    relation_type: VerifiableField[str] = field(
        default_factory=lambda: VerifiableField(value="unspecified")
    )
    # Whether the relation is symmetric (e.g., 'affiliated_with').
    is_bidirectional: bool = False
    # Temporal bounds when the relation holds as mentioned in the source content.
    start_time: Optional[VerifiableField] = None
    end_time: Optional[VerifiableField] = None
    # Optional numeric score representing relation intensity (0.0–1.0).
    strength: Optional[float] = None
    # Domain-specific tags describing context (e.g., 'contractual', 'regulatory').
    tags: List[str] = field(default_factory=list)
    # Arbitrary metadata for this relation (e.g., contract/jurisdiction).
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Encapsulated explanation describing why this relation is recorded.
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Evidence items backing this relation (exact source_content segments).
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Extension placeholder for downstream models.
    extras: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# DOMAIN ENTITIES: Financial constructs and interactions, actions
# ============================================================================


@dataclass
class FinancialInstrument:
    """Financial instrument used or referenced in the event.

    Example:
    {
      "instrument_id": "US1234567890",
      "instrument_type": "bond",
      "attributes": {"issuer": "ACME", "coupon": 0.05, "maturity": "2030-12-31"},
      "explain": {"reasons": ["used in funding transaction"], "rationale": "Coupon schedule aligns with transfer timing"},
      "evidence": [SourceReferenceEvidence(source_type="report", source_content="Bond prospectus states coupon 5%...")],
      "extras": {"jurisdiction": "US"}
    }
    """

    # Unique identifier for the security/instrument (e.g., ISIN, CUSIP, ticker); used for cross-source alignment and deduplication.
    instrument_id: str
    # Instrument category label (e.g., 'bond', 'equity', 'derivative'); use a controlled vocabulary and avoid free text.
    instrument_type: str = "unspecified"
    # Static/semi-static attribute map; examples: issuer, coupon, maturity; include only facts directly supported by evidence and normalize units/formats.
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Encapsulated explanation describing why this instrument is included or how attributes are set.
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Evidence items with exact `source_content` supporting the instrument's existence or attributes; prefer authoritative sources.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Extension metadata for domain-specific details or downstream model outputs (e.g., parsing status, quality flags, normalization markers).
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Financial transfer between participants.

    Example:
    {
      "timestamp": datetime(...),
      "amount": 10000.0,
      "currency": "USD",
      "from_participant_id": "P_A",
      "to_participant_id": "P_B",
      "instrument": FinancialInstrument(...),
      "explain": {"reasons": ["bank record indicates transfer"], "rationale": "Direct match between bank record and participant IDs"},
      "evidence": [SourceReferenceEvidence(source_type="news", source_content="Company promised 30% monthly returns", timestamp=datetime(...), confidence=0.8)],
      "extras": {"settlement_channel": "SWIFT", "transaction_hash": null}
    }
    """

    # Transaction occurrence time (wall-clock); provide the most credible timestamp; use UTC.
    timestamp: datetime
    # Transaction amount (numeric); positive value; units implied by `currency`; record a single transfer when sources contain multiple splits.
    amount: float
    # Currency code (ISO 4217); default 'USD'; must correspond to `amount` and be normalized across sources.
    currency: str = "USD"
    # Payer participant identifier; references `Participant.participant_id`; do not use names or aliases.
    from_participant_id: str = ""
    # Payee participant identifier; references `Participant.participant_id`; if unknown, leave empty and explain in `extras`.
    to_participant_id: str = ""
    # Related financial instrument; optional; describes the vehicle of transfer (e.g., bond payment, token transfer).
    instrument: Optional[FinancialInstrument] = None
    # Encapsulated explanation describing why this transaction is recorded and its credibility basis.
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Evidence list with exact `source_content` directly supporting the transaction (e.g., on-chain tx, bank record, news report).
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Extended metadata; e.g., settlement channel, transaction hash, batch identifier, parsing status.
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Interaction:
    """Message or broadcast exchanged among participants.

    Example:
    {
      "timestamp": datetime(...),
      "medium": "social_media",
      "method": "public_post",
      "sender_id": "P_X",
      "receiver_ids": ["P_A", "P_B"],
      "summary": "Guaranteed 30% monthly returns",
      "approx_occurrences": 10,
      "frequency_descriptor": "several_per_week",
      "explain": {"reasons": ["high engagement"], "rationale": "Observed repeated posts with consistent claims"},
      "evidence": [SourceReferenceEvidence(source_type="social_media", source_content="Join now for 30% monthly returns!")],
      "thread_id": "thread_123",
      "reply_to_id": null,
      "extras": {"platform": "Weibo", "language": "zh"}
    }
    """

    # Interaction occurrence time; use UTC; if only publish time is available, note it in `extras`.
    timestamp: datetime
    # Medium (e.g., 'social_media', 'email', 'press'); controlled vocabulary; used for channel analysis.
    medium: str = "unspecified"
    # Method (e.g., 'public_post', 'dm', 'press_conference'); combined with `medium` to describe concrete form.
    method: str = "unspecified"
    # Sender participant identifier; references `Participant.participant_id`.
    sender_id: str = ""
    # Receiver participant identifiers; reference `Participant.participant_id`; empty means broadcast or undefined audience.
    receiver_ids: List[str] = field(default_factory=list)
    # Summary of the interaction; distills core information or claims; often a condensed version of evidence text.
    summary: str = ""
    # Approximate number of occurrences; for imprecise counts (e.g., repeated forwards or talks).
    approx_occurrences: Optional[int] = None
    # Frequency descriptor (e.g., 'daily', 'several_per_week'); characterizes behavior intensity and cadence.
    frequency_descriptor: str = ""
    # Encapsulated explanation describing why this interaction is recorded and how it relates to the event.
    explain: FinancialExplain = field(default_factory=FinancialExplain)
    # Evidence list with exact `source_content`; examples: original post text, email body, news passage.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Thread identifier; used to link social media/forum context; None means no explicit thread.
    thread_id: Optional[str] = None
    # Reply target identifier; indicates the upstream message this interaction responds to.
    reply_to_id: Optional[str] = None
    # Extended metadata; e.g., platform internal ID, crawl batch, language, model scores.
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """Discrete action executed by one participant and affecting others.

    Example:
    {
      "timestamp": datetime(...),
      "action_type": "broadcast_message",
      "description": "Guaranteed 30% monthly returns",
      "explain": {"reasons": ["promotion", "marketing"], "rationale": "Outbound messaging campaign"},
      "outcomes": ["increased signups"],
      "evidence": [SourceReferenceEvidence(source_type="social_media", source_content="Join now for 30% monthly returns!")],
      "extras": {"channel": "platform_feed"}
    }
    """

    # Chronological context.
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # High-level label (e.g., 'transfer_funds', 'broadcast_message').
    action_type: str = "unspecified"

    # Natural language description or snippet from evidence.
    description: str = ""

    # Encapsulated explanation for motivations or triggers inferred from evidence.
    explain: FinancialExplain = field(default_factory=FinancialExplain)

    # Immediate consequences or outputs (ER attribute: 结果).
    outcomes: List[str] = field(default_factory=list)

    # Evidence items backing this action; include exact source_content segments.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)

    # Flexible metadata container for downstream models.
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE:
    # For high-volume pipelines, store Action documents separately and resolve participant state references on-demand to avoid heavy in-memory graphs.


# Represents an immutable, timestamped observation of a participant's dynamic state
# at a specific moment during the event. Captures behavioral, cognitive, and contextual
# attributes as recorded or inferred from evidence (e.g., news, logs, reports).
@dataclass
class ParticipantState:
    """Participant state record at a specific timestamp.

    Example:
    {
      "participant_id": "P_3f2a1c4b6d7e8f90123456789abcdeff",
      "timestamp": datetime(...),
      "internal_state_attributes": {"trust_in_message": 0.85, "funds_committed_usd": 10000},
      "external_state_attributes": {"market_sentiment": "neutral"},
      "related_actions": [Action(...)],
      "awareness_level": "suspicious",
      "context_tags": ["mobile_app"],
      "confidence": 0.7,
      "evidence": [SourceReferenceEvidence(source_type="news", source_content="User reported suspicious behavior...")],
      "extras": {"note": "derived from platform logs"}
    }
    """

    # References a Participant.participant_id.
    participant_id: str

    # Exact time of this state observation.
    timestamp: datetime

    # Time-varying internal conditions.
    # Examples: {"trust_in_message": 0.85, "funds_committed_usd": 10000}
    internal_state_attributes: Dict[str, Any] = field(default_factory=dict)

    # Time-varying external conditions.
    # Examples: {"market_sentiment": "neutral", "news_coverage": "low"}
    external_state_attributes: Dict[str, Any] = field(default_factory=dict)

    # Actions that contributed to or occurred during this state. Use minimal
    # references to avoid heavy graphs. Actions may reference states for bidirectional traceability.
    related_actions: List[Action] = field(default_factory=list)

    # Participant's subjective understanding of the event's true nature.
    # Values: 'unknowing', 'suspicious', 'aware', 'whistleblower'.
    awareness_level: str = "unknowing"

    # Optional semantic tags describing situational context.
    # Examples: ["late_night", "mobile_app", "peer_pressure"]
    context_tags: List[str] = field(default_factory=list)

    # Confidence score and supporting evidence for this state.
    # confidence: 0.0–1.0; evidence: SourceReferenceEvidence list with exact source_content.
    confidence: Optional[float] = None
    # Evidence items grounding this state; include precise source_content segments.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)

    # Flexible container for any additional data (e.g., model confidence, source_content).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # Participant state records can number in billions for large events.
    # Store in time-series databases (e.g., InfluxDB) or partitioned Parquet/ORC files.
    # Index by (participant_id, timestamp) for fast trajectory reconstruction.


# ============================================================================
# MICRO: Participant Identity — Stable attributes, relations, and background
# ============================================================================
@dataclass
class Participant:
    """Participant involved in the financial event.

    Example:
    {
      "participant_id": "P_3f2a1c4b6d7e8f90123456789abcdeff",
      "entity": "Credit Suisse",
      "name": "Credit Suisse",
      "participant_type": "organization",
      "base_role": "issuer",
      "attributes": {"location": "Zurich", "industry": "banking"},
      "alias_handles": {"alias": ["瑞信", "CS"], "weibo": ["uid_123"]},
      "relations": [],
      "preferences": {"risk_tolerance": "medium"},
      "experiences": {"prior_events": ["2015 restructuring"]},
      "evidence": [SourceReferenceEvidence(source_type="news", source_content="Credit Suisse announced ...")],
      "extras": {"tags": ["tier1"]}
    }
    """

    # Unique, immutable identifier (e.g., UUID, hashed ID, semantic key).
    # must be in canonical form: "P_" + 32 lowercase hex characters
    # Regex: ^P_[a-f0-9]{32}$
    # Example: - P_3f2a1c4b6d7e8f90123456789abcdeff
    participant_id: str

    # Specific, concrete financial entity name (e.g., "Credit Suisse", "瑞信").
    entity: str

    # Human-readable name from the given content (cannot be anonymized).
    name: str = ""

    # High-level category.
    # Examples: 'individual', 'organization', 'social_media_platform', 'government_agency'.
    participant_type: str = "individual"

    # Primary functional role in this event.
    # Examples: 'victim', 'perpetrator', 'influencer', 'media', 'regulator', 'bystander'.
    base_role: str = "unknown"

    # Static or semi-static descriptive properties.
    # Examples:
    #   - Individuals: {"age_group": "30-40", "education": "bachelor", "location": "Shanghai"}
    #   - Organizations: {"industry": "fintech", "employee_count": 50}
    attributes: Dict[str, Any] = field(default_factory=dict)

    # Unified alias and platform handles to avoid ID interference and clarify resolution semantics.
    # Keys denote domains, e.g., "alias", "weibo", "douyin", "bilibili", "email".
    # Values are lists of normalized strings; the only canonical identifier remains `participant_id`.
    # Example: {"alias": ["ACME Ltd.", "ACME Holdings"], "weibo": ["uid_123"], "douyin": ["sec_abc"]}
    alias_handles: Dict[str, List[str]] = field(default_factory=dict)

    # Explicit relationship edges to other participants in this event.
    # Each relation captures type, directionality, temporal bounds, strength, status, tags/attributes, explain (FinancialExplain), and evidence (SourceReferenceEvidence) for auditability.
    relations: List[ParticipantRelation] = field(default_factory=list)

    # Stable cognitive or behavioral dispositions influencing decisions.
    # Examples: {"risk_tolerance": "high", "credibility_threshold": 0.4}
    preferences: Dict[str, Any] = field(default_factory=dict)

    # Prior events or historical context shaping current behavior.
    # Examples: {"past_scam_victim": True, "crypto_investment_history": ["BTC_2021"]}
    experiences: Dict[str, Any] = field(default_factory=dict)

    # Evidence items directly supporting this participant record.
    # Use when the existence, attributes, or roles of the participant are grounded
    # in specific source content; include exact `source_content` segments.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)

    # Flexible container for any additional structured or unstructured metadata.
    # Use for domain-specific extensions, model outputs, or temporary annotations.
    extras: Dict[str, Any] = field(default_factory=dict)

    # Validation note:
    # - participant_id regex and entity specificity are documented here but enforced by builders at runtime. This module intentionally contains no methods.

    # NOTE ON SCALABILITY:
    # In large-scale scenarios (millions of participants), store Participant records in a database table (e.g., PostgreSQL, MongoDB) with participant_id as primary key.
    # Avoid embedding full Participant objects in memory-heavy structures.


# ============================================================================
# MESO: Coherent phase in event development
# ============================================================================
@dataclass
class Episode:
    """A coherent episode within a stage.

    Episodes group participants, actions, transactions, interactions, and snapshots that share a tighter temporal window or thematic focus than the surrounding stage.
    They enable fine-grained modeling without losing stage-level aggregation.

    Example:
    {
      "episode_id": "E1",
      "name": "Private Pitch",
      "sequence_index": 0,
      "start_time": datetime(...),
      "end_time": datetime(...),
      "description": "Key investors received targeted promises",
      "participants": [Participant(...)],
      "participant_states": {"P_A": [ParticipantState(...)]},
      "actions": [Action(...)],
      "transactions": [Transaction(...)],
      "interactions": [Interaction(...)],
      "evidence": [SourceReferenceEvidence(source_type="news", source_content:"...")],
      "tags": ["high_pressure_sales"],
      "confidence_score": 0.8,
      "extras": {"analyst_notes": "high-pressure sales tactics"}
    }
    """

    # Locally unique identifier for referencing and storage; avoid semantic identifiers to reduce ambiguity.
    episode_id: str
    # Name; human-readable semantic label; not used for logical matching.
    name: str = ""
    # Zero-based index within the owning stage; used for ordering and timeline reconstruction.
    sequence_index: int = 0
    # Start time; earliest evidence or activity; None if uncertain.
    start_time: Optional[datetime] = None
    # End time; latest evidence or activity; None if ongoing or boundaries are unclear.
    end_time: Optional[datetime] = None
    # Short description summarizing the episode's theme and key activities.
    description: str = ""

    # List of entities participating in this episode; directly relevant `Participant` records.
    participants: List[Participant] = field(default_factory=list)
    # Participant state map: `participant_id -> List[ParticipantState]`; enables fine-grained temporal analysis.
    participant_states: Dict[str, List[ParticipantState]] = field(default_factory=dict)
    # Actions occurring within this episode; used to model causal chains.
    actions: List[Action] = field(default_factory=list)
    # Financial transfers within this episode; linked to participants/instruments.
    transactions: List[Transaction] = field(default_factory=list)
    # Messages/broadcasts within this episode; used for information diffusion analysis.
    interactions: List[Interaction] = field(default_factory=list)
    # Evidence supporting the episode's existence and boundaries; include exact `source_content`.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Thematic/semantic tags for clustering, filtering, and analysis; prefer controlled vocabularies.
    tags: List[str] = field(default_factory=list)
    # Confidence score (0.0–1.0); aggregate assessment of evidence quality, coverage, and consistency.
    confidence_score: float = 0.0
    # Extended metadata; e.g., reviewer, version, auto-summary, quality flags.
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventStage:
    """Stage of the event development.

    Example:
    {
      "stage_id": "S1",
      "name": "Amplification",
      "stage_index": 2,
      "start_time": datetime(...),
      "end_time": None,
      "description": "Rapid spread of promotional messages",
      "episodes": [Episode(...)],
      "stage_highlights": ["celebrity endorsement"],
      "group_metrics": {"new_victims": 120},
      "systemic_indicators": ["regulatory_attention"],
      "stage_drivers": ["media_amplification", "social_proof"],
      "evidence": [SourceReferenceEvidence(source_type:"news", source_content:"...")],
      "tags": ["amplification_phase"],
      "confidence_score": 0.7,
      "extras": {"llm_summary": "..."}
    }
    """

    stage_id: str

    # Descriptive name (e.g., 'Bait Deployment', 'Amplification').
    name: str

    # Zero-based sequence number (ensures correct ordering).
    stage_index: int

    # Earliest timestamp of activity or evidence in this stage.
    start_time: datetime

    # Latest timestamp (may be None for ambiguous boundaries).
    end_time: Optional[datetime] = None

    # Concise natural-language summary of this stage’s essence.
    description: Optional[str] = None

    # Episodes nested within this stage
    episodes: List[Episode] = field(default_factory=list)

    # Salient episodes, things, information, highlights, or etc. that define this stage.
    stage_highlights: List[str] = field(default_factory=list)

    # Aggregated statistics derived from participant trajectories.
    # Examples: {"new_victims": 120, "avg_trust_growth_rate": 0.05}
    group_metrics: Dict[str, Any] = field(default_factory=dict)

    # Signs that this stage contributed to broader instability.
    # Examples: ["regulatory_attention", "market_volatility_spike"]
    systemic_indicators: List[str] = field(default_factory=list)

    # Underlying forces or conditions that drove this stage's emergence or dynamics.
    # Examples:
    #   - ["information_asymmetry", "lack_of_regulation", "social_proof_mechanism"]
    #   - ["media_amplification", "algorithmic_bias", "economic_uncertainty"]
    stage_drivers: List[str] = field(default_factory=list)

    # Evidence items backing this stage; include exact source_content segments.
    evidence: List[SourceReferenceEvidence] = field(default_factory=list)
    # Explicit thematic labels for grouping/analysis
    tags: List[str] = field(default_factory=list)
    confidence_score: float = 0.0

    # Flexible container for stage-level annotations (e.g., LLM summary, analyst note).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # EventStage count is typically small (< 100 per event).
    # Can be stored as JSON or in a relational table with foreign keys to evidence.


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
      "event_type": "financial_fraud",
      "start_time": datetime(...),
      "end_time": datetime(...),
      "total_impact": {"total_victims": 2400, "total_financial_loss_usd": 3200000},
      "systemic_risk_indicators": ["regulatory_intervention"],
      "root_causes": ["regulatory_gap", "digital_literacy_deficit"],
      "stages": [EventStage(...)],
      "sources_summary": {"news_articles": 24},
      "confidence_score": 0.75,
      "domain_context": "Post-pandemic digital finance boom in SEA",
      "extras": {"curator_id": "analyst_001"}
    }
    """

    # Globally unique identifier (e.g., 'fraud_crypto_2025_001').
    event_id: str

    # Human-readable title summarizing the event.
    title: str

    # Categorical label from a domain ontology.
    # Examples: 'financial_fraud', 'rumor_spread', 'data_breach'.
    event_type: str

    # Earliest timestamp across all evidence and participant activity.
    start_time: datetime

    # Latest timestamp (None if ongoing or unresolved).
    end_time: Optional[datetime] = None

    # Final quantitative/qualitative consequences.
    # Examples: {"total_victims": 2400, "total_financial_loss_usd": 3_200_000}
    total_impact: Dict[str, Any] = field(default_factory=dict)

    # High-level signals of systemic disruption.
    # Examples: "loss_of_trust_in_sector", "regulatory_intervention".
    systemic_risk_indicators: List[str] = field(default_factory=list)

    # Fundamental root causes or systemic enablers of the entire event.
    # These explain *why the event was possible or likely to escalate*.
    # Examples:
    #   - ["regulatory_gap", "digital_literacy_deficit", "incentive_misalignment"]
    #   - ["platform_engagement_algorithms", "cross-border_jurisdictional_void"]
    root_causes: List[str] = field(default_factory=list)

    # Ordered sequence of event phases (sorted by stage_index).
    stages: List[EventStage] = field(default_factory=list)

    # Breakdown of source types and counts.
    # Example: {"news_articles": 24, "government_reports": 2}
    sources_summary: Dict[str, int] = field(default_factory=dict)

    # Estimated reliability (0.0 = speculative, 1.0 = fully verified).
    confidence_score: float = 0.0

    # Broader context framing the event.
    # Example: "Post-pandemic digital finance boom in Southeast Asia".
    domain_context: str = ""

    # Flexible container for event-level metadata (e.g., tags, version, curator ID).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY FOR EVENT CASCADE:
    # For small/medium events (< 10k participants), serialize entire object to JSON/Parquet.
    # For large-scale events:
    #   - Store EventCascade metadata (id, title, stages, etc.) in a main table
    #   - Store Participants in a separate 'participants' table
    #   - Store Trajectories as references; store snapshots in time-series store
    #   - Use lazy loading: reconstruct full cascade on-demand from database
    # Consider formats: Apache Parquet (columnar), Delta Lake, or graph databases (Neo4j) for relations.
