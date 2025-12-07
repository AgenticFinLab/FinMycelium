"""
Define the structure of the financial event cascade by providing base entities and containers for financial event reconstruction.

Structure overview:
- Participant: identity and stable attributes of entities involved
- ParticipantRelation: explicit relationship edge between participants
- ParticipantState: time-stamped dynamic state and actions of a participant
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
        │     └── participant_snapshots: { participant_id → [ParticipantState] }
        ├── stage_actions: List[Action]
        ├── transactions: List[Transaction]
        ├── interactions: List[Interaction]
        └── participant_snapshots: { participant_id → [ParticipantState] }

Derived trajectory (on demand):
  participant_id → collect snapshots across stages/episodes → sort by timestamp → trajectory
"""

from datetime import datetime

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class EvidenceItem:
    """Evidence reference anchoring an action/transaction/interaction.

    Notes:
    - `source_content` MUST be the exact original text from the given source
      (no paraphrasing or summarization).
    - Use `source_type` to categorize the source (e.g., news/report/platform_log).

    Example:
    {"source_type": "news",
     "source_content": "Company promised 30% monthly returns", "timestamp": datetime(...),
     "confidence": 0.8}
    """

    # Content category label (e.g., "news", "report", "platform_log").
    source_type: str = "unspecified"
    # Exact original text snippet (no rewriting) that supports a specific setting/assignment; clearly include the precise source text that justifies it.
    source_content: str = ""
    # Wall-clock time when the source content was published or logged.
    # Use UTC where possible; set to None if unknown. Prefer the most relevant
    # timestamp (e.g., article publish time over crawl time).
    timestamp: Optional[datetime] = None
    # Confidence score in [0.0, 1.0] reflecting trustworthiness and relevance
    # of this evidence. Example: 0.9 for official filings; 0.5 for anonymous claims.
    confidence: Optional[float] = None
    # Short factors (1–5 items) explaining why this evidence is relevant.
    # Examples: ["explicit rate claim", "named issuer", "official filing"].
    reasons: List[str] = field(default_factory=list)
    # Analyst note connecting the evidence to the conclusion/setting in this record.
    # Free-text explanation; may reference the specific field being supported.
    rationale: str = ""
    # Flexible extension map. Suggested keys: "supported_field" (e.g., "Transaction.amount"),
    # "support_scope" ("direct"|"indirect"|"contextual"), "char_span" ([start,end]),
    # "paragraph_index" (int), "language" (e.g., "en").
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParticipantRelation:
    """Relationship between two participants.

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
      "evidence": [EvidenceItem(source_type="report", source_content="contract signed on ...")]
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
      "evidence": [EvidenceItem(source_type="registry", source_content="parent company: ...")]
    }
    """

    # Source participant (edge origin) — references Participant.participant_id.
    from_participant_id: str
    # Target participant (edge destination) — references Participant.participant_id.
    to_participant_id: str
    # Natural-language description of the relation.
    description: str = ""
    # Relation label (e.g., 'member_of', 'client_of', 'counterparty').
    relation_type: str = "unspecified"
    # Whether the relation is symmetric (e.g., 'affiliated_with').
    is_bidirectional: bool = False
    # Temporal bounds when the relation holds.
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # Optional numeric score representing relation intensity (0.0–1.0).
    strength: Optional[float] = None
    # Current state: 'active', 'inactive', 'suspended', 'terminated'.
    status: str = "active"
    # Domain-specific tags describing context (e.g., 'contractual', 'regulatory').
    tags: List[str] = field(default_factory=list)
    # Arbitrary metadata for this relation (e.g., contract/jurisdiction).
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Concise factors explaining why the relation is recorded.
    reasons: List[str] = field(default_factory=list)
    # Analyst explanation connecting evidence to this relation.
    rationale: str = ""
    # Evidence items backing this relation (exact source_content segments).
    evidence: List[EvidenceItem] = field(default_factory=list)
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
      "reasons": ["used in funding transaction"],
      "rationale": "Coupon schedule aligns with transfer timing",
      "evidence": [EvidenceItem(source_type="report", source_content="Bond prospectus states coupon 5%...")],
      "extras": {"jurisdiction": "US"}
    }
    """

    instrument_id: str
    instrument_type: str = "unspecified"
    attributes: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    rationale: str = ""
    # Evidence items supporting inclusion/relevance of this instrument.
    # Use to ground attributes or instrument usage in exact source content.
    evidence: List[EvidenceItem] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Financial transfer between participants.

    Example:
    {"timestamp": datetime(...), "amount": 10000.0, "currency": "USD",
     "from_participant_id": "P_A", "to_participant_id": "P_B",
     "instrument": FinancialInstrument(...),
     "evidence": [EvidenceItem(source_type="news",
                                source_content="Company promised 30% monthly returns",
                                timestamp=datetime(...),
                                confidence=0.8)]}
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


@dataclass
class Action:
    """Discrete action executed by one participant and affecting others.

    Example:
    {
      "timestamp": datetime(...),
      "action_type": "broadcast_message",
      "description": "Guaranteed 30% monthly returns",
      "reasons": ["promotion", "marketing"],
      "outcomes": ["increased signups"],
      "related_state_snapshots": [],
      "evidence": [EvidenceItem(source_type="social_media", source_content="Join now for 30% monthly returns!")],
      "extras": {"channel": "platform_feed"}
    }
    """

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

    # Evidence items backing this action; include exact source_content segments.
    evidence: List[EvidenceItem] = field(default_factory=list)

    # Flexible metadata container for downstream models.
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE:
    # For high-volume pipelines, store Action documents separately and only resolve
    # related_state_snapshots on-demand to avoid heavy in-memory graphs.


# Represents an immutable, timestamped observation of a participant's dynamic state
# at a specific moment during the event. Captures behavioral, cognitive, and contextual
# attributes as recorded or inferred from evidence (e.g., news, logs, reports).
@dataclass
class ParticipantState:
    """Snapshot of a participant's state at a specific timestamp.

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
      "evidence": [EvidenceItem(source_type="news", source_content="User reported suspicious behavior...")],
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
    # references to avoid heavy graphs. Actions also reference states via
    # Action.related_state_snapshots for bidirectional traceability.
    related_actions: List[Action] = field(default_factory=list)

    # Participant's subjective understanding of the event's true nature.
    # Values: 'unknowing', 'suspicious', 'aware', 'whistleblower'.
    awareness_level: str = "unknowing"

    # Optional semantic tags describing situational context.
    # Examples: ["late_night", "mobile_app", "peer_pressure"]
    context_tags: List[str] = field(default_factory=list)

    # Confidence score and supporting evidence for this snapshot.
    # confidence: 0.0–1.0; evidence: EvidenceItem list with exact source_content.
    confidence: Optional[float] = None
    # Evidence items grounding this snapshot; include precise source_content segments.
    evidence: List[EvidenceItem] = field(default_factory=list)

    # Flexible container for any additional data (e.g., model confidence, source_content).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # State snapshots can number in billions for large events.
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
      "evidence": [EvidenceItem(source_type="news", source_content="Credit Suisse announced ...")],
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
    # Each relation captures type, directionality, temporal bounds, strength,
    # status, tags/attributes, reasons/rationale, and evidence (EvidenceItem) for auditability.
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
    evidence: List[EvidenceItem] = field(default_factory=list)

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
      "evidence": [EvidenceItem(source_type="news", source_content="...")],
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
    participant_snapshots: Dict[str, List[ParticipantState]] = field(
        default_factory=dict
    )
    actions: List[Action] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    interactions: List[Interaction] = field(default_factory=list)
    # Evidence items backing this episode; include exact source_content segments.
    evidence: List[EvidenceItem] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventStage:
    """Stage of the event development.

    Example:
    {
      "stage_id": "S1", "name": "Amplification", "stage_index": 2,
      "group_metrics": {"new_victims": 120}
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
    evidence: List[EvidenceItem] = field(default_factory=list)
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
