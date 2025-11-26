"""
Implementation of the base builder to be used by all subsequent builders.

It should be emphasized that the `BaseBuilder` is built on the large models as it is impossible for the human to build a pipeline manually or even based on some algorithms.
"""

import time
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

from finmy.generic import MetaSample


# ============================================================================
# MICRO: Participant Identity — Stable attributes, relations, and background
# ============================================================================
@dataclass
class Participant:
    """Participant involved in the financial event."""

    # Unique, immutable identifier (e.g., UUID, hashed ID, semantic key).
    participant_id: str

    # Human-readable name (may be anonymized).
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

    # Social/functional ties to other participants *in this event*.
    # Key: participant_id of another participant.
    # Value: relation type (e.g., "friend", "member_of", "client_of", "follower_of").
    broader_relations: Dict[str, str] = field(default_factory=dict)

    # Stable cognitive or behavioral dispositions influencing decisions.
    # Examples: {"risk_tolerance": "high", "credibility_threshold": 0.4}
    preferences: Dict[str, Any] = field(default_factory=dict)

    # Prior events or historical context shaping current behavior.
    # Examples: {"past_scam_victim": True, "crypto_investment_history": ["BTC_2021"]}
    experiences: Dict[str, Any] = field(default_factory=dict)

    # Flexible container for any additional structured or unstructured metadata.
    # Use for domain-specific extensions, model outputs, or temporary annotations.
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # In large-scale scenarios (millions of participants), store Participant records
    # in a database table (e.g., PostgreSQL, MongoDB) with participant_id as primary key.
    # Avoid embedding full Participant objects in memory-heavy structures.


@dataclass
class Action:
    """Discrete action executed by one participant and affecting others."""

    # Unique identifier for this action instance.
    action_id: str

    # Participants responsible for triggering the action.
    executor_participant_ids: List[str] = field(default_factory=list)

    # Primary target entity IDs affected by the action (can include executor).
    target_participant_ids: List[str] = field(default_factory=list)

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

    # IDs of actions that directly influenced this state snapshot
    # Each entry references Action.action_id.
    influencing_action_ids: List[str] = field(default_factory=list)

    # Participant's subjective understanding of the event's true nature.
    # Values: 'unknowing', 'suspicious', 'aware', 'whistleblower'.
    awareness_level: str = "unknowing"

    # Optional semantic tags describing situational context.
    # Examples: ["late_night", "mobile_app", "peer_pressure"]
    context_tags: List[str] = field(default_factory=list)

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
class ParticipantTrajectory:
    """Trajectory of a participant's state snapshots over time."""

    # ID of the participant whose trajectory this is.
    participant_id: str

    # Chronologically ordered list of state snapshots (by timestamp).
    trajectory: List[ParticipantStateSnapshot]

    # Index of the EventStage when this participant first became active.
    entry_stage: int

    # Index of the EventStage after which they disengaged (if applicable).
    exit_stage: Optional[int] = None

    # Optional: Sequence of roles over stages (e.g., ["victim", "whistleblower"]).
    role_evolution: List[str] = field(default_factory=list)

    # Flexible container for trajectory-level metadata (e.g., clustering label, risk score).
    extras: Dict[str, Any] = field(default_factory=dict)

    # NOTE ON SCALABILITY:
    # For large N, avoid storing full trajectory lists in memory.
    # Instead:
    #   - Store trajectory metadata (entry/exit, role_evolution) in a main table
    #   - Store actual snapshots in a separate time-series store
    #   - Load trajectories on-demand using participant_id


# ============================================================================
# MESO: Coherent phase in event development
# ============================================================================
@dataclass
class EventStage:
    """Stage of the event development."""

    # Descriptive name (e.g., 'Bait Deployment', 'Amplification').
    name: str

    # Zero-based sequence number (ensures correct ordering).
    stage_index: int

    # Earliest timestamp of activity or evidence in this stage.
    start_time: datetime

    # Latest timestamp (may be None for ambiguous boundaries).
    end_time: Optional[datetime] = None

    # Concise natural-language summary of this stage’s essence.
    description: str

    # Salient sub-events that define the phase.
    key_events: List[str] = field(default_factory=list)

    # IDs of participants behaviorally active in this stage.
    active_participants: List[str] = field(default_factory=list)

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
    """Whole event cascade reconstruction."""

    # Globally unique identifier (e.g., 'fraud_crypto_2025_001').
    id: str

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

    # All unique entities involved (identity + background).
    participants: List[Participant] = field(default_factory=list)

    # Time-evolving behaviors of participants.
    participant_trajectories: List[ParticipantTrajectory] = field(default_factory=list)

    # Breakdown of source types and counts.
    # Example: {"news_articles": 24, "government_reports": 2}
    sources_summary: Dict[str, int] = field(default_factory=dict)

    # How this cascade was built.
    # Expected: 'manual', 'llm_extracted', 'hybrid'.
    reconstruction_method: str = "manual"

    # Estimated reliability (0.0 = speculative, 1.0 = fully verified).
    confidence_score: float = 0.0

    # Broader context framing the event.
    # Example: "Post-pandemic digital finance boom in Southeast Asia".
    domain_context: str = ""

    # Flexible container for event-level metadata (e.g., tags, version, curator ID).
    extras: Dict[str, Any] = field(default_factory=dict)

    # Internal lookup tables for performance (not persisted; rebuilt on load).
    #   - participant_id → Participant
    #   - participant_id → ParticipantTrajectory
    #   - stage_index → EventStage
    _participant_registry: Dict[str, Participant] = field(
        default_factory=dict, repr=False, init=False
    )
    _trajectory_index: Dict[str, ParticipantTrajectory] = field(
        default_factory=dict, repr=False, init=False
    )
    _stage_index: Dict[int, EventStage] = field(
        default_factory=dict, repr=False, init=False
    )

    # NOTE ON SCALABILITY FOR EVENT CASCADE:
    # For small/medium events (< 10k participants), serialize entire object to JSON/Parquet.
    # For large-scale events:
    #   - Store EventCascade metadata (id, title, stages, etc.) in a main table
    #   - Store Participants in a separate 'participants' table
    #   - Store Trajectories as references; store snapshots in time-series store
    #   - Use lazy loading: reconstruct full cascade on-demand from database
    # Consider formats: Apache Parquet (columnar), Delta Lake, or graph databases (Neo4j) for relations.

    def __post_init__(self) -> None:
        # Rebuild internal indexes after deserialization or construction.
        self._participant_registry = {p.participant_id: p for p in self.participants}
        self._trajectory_index = {
            t.participant_id: t for t in self.participant_trajectories
        }
        self._stage_index = {s.stage_index: s for s in self.stages}

    def get_participant(self, participant_id: str) -> Optional[Participant]:
        """Retrieve participant identity by ID."""
        return self._participant_registry.get(participant_id)

    def get_trajectory(
        self,
        participant_id: str,
    ) -> Optional[ParticipantTrajectory]:
        """Retrieve full behavioral trajectory by ID."""
        return self._trajectory_index.get(participant_id)

    def get_stage(self, stage_index: int) -> Optional[EventStage]:
        """Retrieve event stage by index."""
        return self._stage_index.get(stage_index)

    def get_participants_in_stage(self, stage_index: int) -> List[Participant]:
        """Get all participant identities active in a given stage."""
        stage = self.get_stage(stage_index)
        if not stage:
            return []
        return [
            self._participant_registry[pid]
            for pid in stage.active_participants
            if pid in self._participant_registry
        ]

    def get_trajectories_in_stage(
        self, stage_index: int
    ) -> List[ParticipantTrajectory]:
        """Get all trajectories active in a given stage."""
        stage = self.get_stage(stage_index)
        if not stage:
            return []
        return [
            self._trajectory_index[pid]
            for pid in stage.active_participants
            if pid in self._trajectory_index
        ]


@dataclass
class BuildInput:
    """Input format of the pipeline builder."""

    samples: List[MetaSample]
    configs: Dict[str, Any] = field(default_factory=dict)
    time_cost: Optional[float] = None
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildOutput:
    """Input format of the pipeline builder."""

    event_cascades: List[EventCascade] = field(default_factory=list)
    result: Optional[Any] = None
    logs: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


class BaseBuilder(ABC):
    """Base class for event cascade builders."""

    def __init__(
        self,
        config: Optional[dict] = None,
        method_name: Optional[str] = None,
    ):
        self.config = config
        self.method_name = method_name

    @abstractmethod
    def build(self, build_input: BuildInput) -> BuildOutput:
        """Build the event cascades from the input samples."""

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the builder pipeline."""
        start = time.time()
        output = self.build(build_input)
        output.extras["time_cost"] = time.time() - start
        return output
