"""
Define the structure of the financial event cascade by providing base entities and containers for financial event reconstruction.

Structure overview:
- Participant: identity and stable attributes of entities involved
- ParticipantRelation: explicit relationship edge between participants
- ParticipantStateSnapshot: time-stamped dynamic state and actions of a participant
- Action: atomic behaviors recorded within snapshots/stages/episodes
- Transaction: financial transfers between participants with evidence
- Interaction: messages/broadcasts among participants with reasons/rationale
- Episode: coherent sub-phase within a stage
- EventStage: one phase of the event, holding participants and per-stage snapshots
- EventCascade: top-level container, holding ordered stages and event-level metadata

Relationship Among Event, Stage, Episode, and Participant:
- Event: A financial shock with significant market impact (e.g., a major default, regulatory sanction, market crash, or sudden policy change).
- Stage: A continuous time interval in the event's evolution, defined by a unified dominant logic or system state. The number and naming of stages should be determined flexibly based on the event itself—do not force predefined templates.
- Episode: A key sub-event within a stage. Each episode must be:
(1) Concrete (with clear timestamp, actor, and action),
(2) Causal (explains subsequent market or institutional responses), and
(3) Capital-market relevant (impacts asset prices, risk, or liquidity).
- Participant: An entity associated with an episode, labeled by its financial role

Usage notes:
- Trajectories are derived on demand by merging snapshots per `participant_id`
  across stage-level and episode-level `participant_snapshots`, then sorting by
  `timestamp`.
- Builders assemble `EventCascade` using LMs or rules and avoid duplicating
  participant lists outside stages to reduce redundancy.
- Most entities include `reasons` and `rationale` fields to capture causal
  explanations and analyst notes for transparency and auditability.

Diagram:

EventCascade
  └── stages: List[EventStage]
        ├── episodes: List[Episode]
        │     ├── participants: List[Participant]
        │     ├── actions: List[Action]
        │     ├── transactions: List[Transaction]
        │     ├── interactions: List[Interaction]
        │     └── participant_snapshots: { participant_id → [ParticipantStateSnapshot] }
        ├── stage_actions: List[Action]
        ├── transactions: List[Transaction]
        ├── interactions: List[Interaction]
        └── participant_snapshots: { participant_id → [ParticipantStateSnapshot] }

Derived trajectory (on demand):
  participant_id → collect snapshots across stages/episodes → sort by timestamp → trajectory
"""

from datetime import datetime

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


# ============================================================================
# MICRO: Participant Identity — Stable attributes, relations, and background
# ============================================================================
@dataclass
class Participant:
    """Participant involved in the financial event.

    ID format requirement:
    - participant_id must be in canonical form: "P_" + 32 lowercase hex characters
      Regex: ^P_[a-f0-9]{32}$

    Example:
    - P_3f2a1c4b6d7e8f90123456789abcdeff

    Fields:
    - participant_id: canonical unique ID (see format above)
    - entity: specific and concrete financial entity name (e.g., "Credit Suisse", "瑞信");
      must not be a generic category or placeholder
    - name: human-readable name (may be anonymized)
    - participant_type: entity category, e.g., "individual", "organization"
    - base_role: primary role in this event, e.g., "victim", "perpetrator"
    - attributes: static/semi-static properties, e.g., {"location": "Shanghai"}
    - relations: explicit relationship edges to other participants (see ParticipantRelation)
    - preferences: stable dispositions, e.g., {"risk_tolerance": "high"}
    - experiences: prior context shaping current behavior
    - aliases: alternative names for entity resolution
    - source_ids: platform-specific identifiers, e.g., {"weibo": "uid_123"}
    - extras: extension placeholder for downstream models
    """

    # Unique, immutable identifier (e.g., UUID, hashed ID, semantic key).
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

    # Alternative names and platform-specific identifiers for entity resolution.
    # Examples:
    #   aliases: ["ACME Ltd.", "ACME Holdings"]
    #   source_ids: {"weibo": "uid_123", "douyin": "sec_abc", "bilibili": "mid_456"}
    aliases: List[str] = field(default_factory=list)
    source_ids: Dict[str, str] = field(default_factory=dict)

    # Explicit relationship edges to other participants in this event.
    # Each relation captures type, directionality, temporal bounds, strength,
    # status, tags/attributes, reasons/rationale, and evidence_sources for auditability.
    relations: List["ParticipantRelation"] = field(default_factory=list)

    # Stable cognitive or behavioral dispositions influencing decisions.
    # Examples: {"risk_tolerance": "high", "credibility_threshold": 0.4}
    preferences: Dict[str, Any] = field(default_factory=dict)

    # Prior events or historical context shaping current behavior.
    # Examples: {"past_scam_victim": True, "crypto_investment_history": ["BTC_2021"]}
    experiences: Dict[str, Any] = field(default_factory=dict)

    # Flexible container for any additional structured or unstructured metadata.
    # Use for domain-specific extensions, model outputs, or temporary annotations.
    extras: Dict[str, Any] = field(default_factory=dict)

    # Validation note:
    # - participant_id regex and entity specificity are documented here but enforced
    #   by builders at runtime. This module intentionally contains no methods.

    # NOTE ON SCALABILITY:
    # In large-scale scenarios (millions of participants), store Participant records
    # in a database table (e.g., PostgreSQL, MongoDB) with participant_id as primary key.
    # Avoid embedding full Participant objects in memory-heavy structures.


@dataclass
class ParticipantRelation:
    """Relationship between two participants.

    Fields:
    - from_participant_id: source participant_id
    - to_participant_id: target participant_id
    - description: optional natural-language description of the relation
    - relation_type: label of the relation
      Examples: "member_of", "client_of", "counterparty", "affiliated_with",
                "controls", "influences", "whistleblows_on"
    - is_bidirectional: whether the relation is symmetric (e.g., "affiliated_with")
    - start_time/end_time: temporal bounds for when the relation holds
    - strength: optional numeric score for relation intensity (e.g., 0.0–1.0)
    - status: current state of the relation
      Examples: "active", "inactive", "suspended", "terminated"
    - tags: domain-specific tags describing relation context
      Examples: ["contractual", "regulatory", "social", "financial"]
    - attributes: arbitrary metadata for the relation
      Examples: {"contract_id": "C-2025-001", "jurisdiction": "HK"}
    - reasons: concise factors explaining why the relation is recorded
    - rationale: analyst explanation connecting evidence to this relation
    - evidence_sources: references supporting the existence of this relation
      Examples: ["https://regulator.site/filing/123", "file:///reports/audit.pdf"]
    - extras: extension placeholder for downstream models

    Example:
    {
      "from_participant_id": "P_A",
      "to_participant_id": "P_B",
      "description": "A 是 B 的客户，存在长期付费关系",
      "relation_type": "client_of",
      "is_bidirectional": false,
      "start_time": datetime(...),
      "strength": 0.8,
      "status": "active",
      "tags": ["financial"],
      "attributes": {"contract_id": "C-2025-001"},
      "reasons": ["service agreement signed"],
      "rationale": "Observed formal KYC onboarding and recurring payments",
      "evidence_sources": ["https://regulator.site/filing/123"]
    }

    Bidirectional example:
    {
      "from_participant_id": "P_X",
      "to_participant_id": "P_Y",
      "description": "X 与 Y 存在共同母公司，从公司注册信息可验证",
      "relation_type": "affiliated_with",
      "is_bidirectional": true,
      "tags": ["corporate"],
      "reasons": ["shared ownership structure"],
      "rationale": "Public registry shows common parent entity",
      "evidence_sources": ["file:///registry/records.csv"]
    }
    """

    from_participant_id: str
    to_participant_id: str
    description: str = ""
    relation_type: str = "unspecified"
    is_bidirectional: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    strength: Optional[float] = None
    status: str = "active"
    tags: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    evidence_sources: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """Discrete action executed by one participant and affecting others."""

    # Chronological context.
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # High-level label (e.g., 'transfer_funds', 'broadcast_message').
    action_type: str = "unspecified"

    # Natural language description or snippet from evidence.
    description: str = ""

    # Motivations or triggers inferred from evidence (ER attribute: 原因).
    reasons: List[str] = field(default_factory=list)

    # Immediate consequences or outputs (ER attribute: 结果).
    outcomes: List[str] = field(default_factory=list)

    # References to the state snapshots this action belongs to.
    # Note: This list may include snapshots from multiple participants involved in the action.
    related_state_snapshots: List["ParticipantStateSnapshot"] = field(
        default_factory=list
    )

    # Evidence backing this action (URLs, doc ids, etc.).
    evidence_sources: List[str] = field(default_factory=list)

    # Flexible metadata container for downstream models.
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE:
    # For high-volume pipelines, store Action documents separately and only resolve
    # related_state_snapshots on-demand to avoid heavy in-memory graphs.


# ============================================================================
# DOMAIN ENTITIES: Financial constructs and interactions
# ============================================================================
@dataclass
class FinancialInstrument:
    """Financial instrument used or referenced in the event.

    Fields:
    - instrument_id: unique identifier of the instrument (e.g., ticker, token id)
    - instrument_type: type label, examples: "token", "stock", "bond", "contract"
    - attributes: arbitrary metadata of the instrument (key-value), e.g.,
      {"issuer": "CompanyA", "chain": "Ethereum", "maturity": "2026-06-30"}
    - reasons: factors for inclusion/relevance in the event
    - rationale: analyst explanation for how the instrument relates to actions/transactions
    - extras: extension placeholder for downstream models

    Example:
    {"instrument_id": "US1234567890", "instrument_type": "bond",
     "attributes": {"issuer": "ACME", "coupon": 0.05, "maturity": "2030-12-31"}}
    """

    instrument_id: str
    instrument_type: str = "unspecified"
    attributes: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceItem:
    """Evidence reference anchoring an action/transaction/interaction.

    Fields:
    - source_uri: where the evidence is stored (URL, file path)
    - source_type: type label, examples: "news", "report", "platform_log"
    - excerpt: short text snippet summarizing relevant content
    - timestamp: when the evidence was published or logged
    - confidence: model or analyst confidence in this evidence (0.0–1.0)
    - reasons: list of short factors explaining relevance
    - rationale: analyst note connecting evidence to model conclusions
    - extras: extension placeholder

    Example:
    {"source_uri": "https://news.site/article/abc", "source_type": "news",
     "excerpt": "Company promised 30% monthly returns", "timestamp": datetime(...),
     "confidence": 0.8}
    """

    source_uri: str
    source_type: str = "unspecified"
    excerpt: str = ""
    timestamp: Optional[datetime] = None
    confidence: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Financial transfer between participants.

    Fields:
    - timestamp: when the transfer occurred
    - amount: transfer amount (float)
    - currency: currency code, e.g., "USD", "EUR", "BTC"
    - from_participant_id: sender participant_id
    - to_participant_id: receiver participant_id
    - instrument: optional instrument related to the transfer (e.g., token/contract)
    - reasons/rationale: causal explanation for the transfer
    - evidence: list of evidence items supporting this record
    - extras: extension placeholder

    Example:
    {"timestamp": datetime(...), "amount": 10000.0, "currency": "USD",
     "from_participant_id": "P_A", "to_participant_id": "P_B",
     "instrument": FinancialInstrument(...), "evidence": [EvidenceItem(...)]}
    """

    timestamp: datetime
    amount: float
    currency: str = "USD"
    from_participant_id: str = ""
    to_participant_id: str = ""
    instrument: Optional[FinancialInstrument] = None
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    evidence: List[EvidenceItem] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Interaction:
    """Message or broadcast exchanged among participants.

    Fields:
    - timestamp: when the communication happened
    - medium: channel, examples: "social_media", "email", "chat"
    - method: specific interaction method on the medium
      Examples: "private_message", "group_chat", "public_post", "live_stream",
                "phone_call", "meeting"
    - approx_occurrences: approximate count of discrete messages/posts represented
    - frequency_descriptor: textual rate description, e.g., "每周数次", "高频", "偶发"
    - sender_id: participant_id of the sender
    - receiver_ids: list of participant_ids (empty if broadcast)
    - summary: short content summary (or LLM-generated synopsis)
    - thread_id: conversation/thread identifier when available
    - reply_to_id: message id that this interaction replies to (if any)
    - reasons/rationale: intent and causal context of the interaction
    - evidence: list of evidence items
    - extras: extension placeholder

    Example:
    {"timestamp": datetime(...), "medium": "social_media", "method": "public_post", "sender_id": "P_X",
     "receiver_ids": ["P_A", "P_B"], "summary": "Guaranteed 30% monthly returns",
     "approx_occurrences": 10, "frequency_descriptor": "每周数次",
      "evidence": [EvidenceItem(...)]}
    """

    timestamp: datetime
    medium: str = "unspecified"
    method: str = "unspecified"
    sender_id: str = ""
    receiver_ids: List[str] = field(default_factory=list)
    summary: str = ""
    approx_occurrences: Optional[int] = None
    frequency_descriptor: str = ""
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    evidence: List[EvidenceItem] = field(default_factory=list)
    thread_id: Optional[str] = None
    reply_to_id: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# MICRO → TEMPORAL: State evolution of a single participant
# ============================================================================
# Represents an immutable, timestamped observation of a participant's dynamic state
# at a specific moment during the event. Captures behavioral, cognitive, and contextual
# attributes as recorded or inferred from evidence (e.g., news, logs, reports).
@dataclass
class ParticipantStateSnapshot:
    """Snapshot of a participant's state at a specific timestamp."""

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

    actions: List[Action] = field(default_factory=list)

    # Participant's subjective understanding of the event's true nature.
    # Values: 'unknowing', 'suspicious', 'aware', 'whistleblower'.
    awareness_level: str = "unknowing"

    # Optional semantic tags describing situational context.
    # Examples: ["late_night", "mobile_app", "peer_pressure"]
    context_tags: List[str] = field(default_factory=list)

    # Confidence score and supporting evidence for this snapshot.
    # confidence: 0.0–1.0; evidence_sources: URLs or file references.
    confidence: Optional[float] = None
    evidence_sources: List[str] = field(default_factory=list)

    # Flexible container for any additional data (e.g., model confidence, source excerpt).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # State snapshots can number in billions for large events.
    # Store in time-series databases (e.g., InfluxDB) or partitioned Parquet/ORC files.
    # Index by (participant_id, timestamp) for fast trajectory reconstruction.


# ============================================================================
# MICRO → MESO: Full behavioral trajectory of one participant
# ============================================================================
@dataclass
class StageActivity:
    """Aggregated view of a participant's roles and timing within a stage.

    Fields:
    - stage_index: zero-based index of the stage this activity belongs to
    - start_time/end_time: participant-specific temporal bounds inside the stage
    - roles: list of role labels observed for the participant in this stage
      Examples: ["victim", "promoter", "operator"]

    Example:
    {
      "stage_index": 1,
      "start_time": datetime(...),
      "end_time": datetime(...),
      "roles": ["influencer", "promoter"]
    }
    """

    stage_index: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    roles: List[str] = field(default_factory=list)


# ============================================================================
# MESO: Coherent phase in event development
# ============================================================================
@dataclass
class Episode:
    """A coherent episode within a stage.

    Episodes group participants, actions, transactions, interactions, and
    snapshots that share a tighter temporal window or thematic focus than the
    surrounding stage. They enable fine-grained modeling without losing
    stage-level aggregation.

    Fields:
    - episode_id: unique label for the episode within a stage
    - name: human-readable title
    - sequence_index: index ordering episodes within the stage (0-based)
    - start_time/end_time: temporal bounds of the episode
    - description: concise summary of the episode
    - participants: entities involved in this episode
    - participant_snapshots: per-participant snapshots observed here
      Format: { participant_id → [ParticipantStateSnapshot] }
    - actions: actions aggregated or recorded in this episode
    - transactions: financial transfers recorded in this episode
    - interactions: participant interactions recorded in this episode
    - evidence_sources: references supporting this episode
    - tags: thematic labels for grouping/analysis (e.g., ["promotion", "whitelist"])
    - confidence_score: 0.0–1.0 indicating reliability of this episode
    - extras: extension placeholder

    Example:
    {
      "episode_id": "E1",
      "name": "Private Pitch",
      "sequence_index": 0,
      "start_time": datetime(...),
      "end_time": datetime(...),
      "description": "Key investors received targeted promises",
      "participants": [Participant(...)],
      "participant_snapshots": {"P_A": [ParticipantStateSnapshot(...), ...]},
      "actions": [Action(...)],
      "transactions": [Transaction(...)],
      "interactions": [Interaction(...)],
      "evidence_sources": ["https://news.site/article/abc"],
      "extras": {"analyst_notes": "high-pressure sales tactics"}
    }
    """

    episode_id: str
    name: str = ""
    sequence_index: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: str = ""

    participants: List[Participant] = field(default_factory=list)
    participant_snapshots: Dict[str, List[ParticipantStateSnapshot]] = field(
        default_factory=dict
    )
    actions: List[Action] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    interactions: List[Interaction] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventStage:
    """Stage of the event development.

    Fields:
    - name: stage name, e.g., "Bait Deployment", "Amplification"
    - stage_index: zero-based index ordering stages
    - start_time/end_time: temporal boundaries of the stage
    - description: concise natural-language summary
    - stage_highlights: salient sub-events defining this phase
    - stage_actions: actions aggregated or recorded in this stage
    - transactions: financial transfers recorded in this stage
    - interactions: participant interactions recorded in this stage
    - participants: entities involved in this stage
    - participant_snapshots: per-participant snapshots observed in this stage
    - group_metrics: aggregated metrics derived from participants or actions
    - systemic_indicators: signals of broader instability
    - stage_drivers: underlying forces/conditions
    - evidence_sources: references supporting this stage
    - tags: thematic labels for grouping/analysis (e.g., ["promotion", "exit"])
    - confidence_score: 0.0–1.0 indicating reliability of this stage
    - extras: extension placeholder

    Example:
    {
      "name": "Amplification", "stage_index": 2,
      "transactions": [{"amount": 250000.0, "currency": "USD", ...}],
      "interactions": [{"medium": "social_media", "summary": "Guaranteed returns", ...}],
      "participants": [Participant(...)],
      "participant_snapshots": {"P_A": [ParticipantStateSnapshot(...), ...]},
      "group_metrics": {"new_victims": 120}
    }
    """

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

    # Salient sub-events or highlights that define this phase.
    stage_highlights: List[str] = field(default_factory=list)

    # Stage-level actions/transactions/communications
    stage_actions: List[Action] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    interactions: List[Interaction] = field(default_factory=list)

    # Episodes nested within this stage
    episodes: List[Episode] = field(default_factory=list)

    participants: List[Participant] = field(default_factory=list)

    participant_snapshots: Dict[str, List[ParticipantStateSnapshot]] = field(
        default_factory=dict
    )

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

    # URLs, report IDs, or references supporting this stage.
    evidence_sources: List[str] = field(default_factory=list)
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

    Fields:
    - event_id: global unique identifier (e.g., "fraud_crypto_2025_001")
    - title: human-readable event title
    - event_type: categorical label, e.g., "financial_fraud", "rumor_spread"
    - start_time/end_time: global temporal bounds of the event
    - total_impact: quantitative/qualitative consequences
      Examples: {"total_victims": 2400, "total_financial_loss_usd": 3_200_000}
    - systemic_risk_indicators: high-level signals of disruption
      Examples: ["loss_of_trust_in_sector", "regulatory_intervention"]
    - root_causes: fundamental enablers/causes for the event
      Examples: ["regulatory_gap", "digital_literacy_deficit"]
    - stages: ordered sequence of phases (sorted by stage_index)
    - sources_summary: breakdown of source types and counts
      Example: {"news_articles": 24, "government_reports": 2}
    - confidence_score: estimated reliability (0.0–1.0)
    - domain_context: broader context framing the event
    - extras: extension placeholder

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
