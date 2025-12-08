"""
Implementation of the Financial Event Cascade with a large model based multi-agent system.
"""

from typing import List, Optional, Dict
from dataclasses import dataclass


from finmy.builder.finance_define import (
    SupportedFinancialScenario,
    EpisodeType,
    ParticipantRole,
)


@dataclass
class FinanceScenario:
    """
    Represents a canonical financial scenario pattern derived from theory and historical precedent.

    ⚠️ CRITICAL: This is a DOMAIN PRIOR — NOT a template for reconstructing the current event.

    It describes how this scenario archetype has typically unfolded in the past,
    but the actual event may deviate, combine with other scenarios, or exhibit novel dynamics.

    Downstream agents MUST use observed event data as the primary source of truth.
    These fields should only be used to:
      - Guide plausibility checks
      - Prioritize evidence extraction
      - Suggest naming conventions
      - Fill gaps when data is sparse
    NEVER to suppress, override, or force-fit real-world observations.
    """

    # The canonical financial scenario type that best matches the event's economic mechanism.
    # This is a semantic anchor based on domain theory — not a rigid classification.
    # Example: "Bank Run", "Ponzi Scheme"
    scenario_type: SupportedFinancialScenario

    # A concise, mechanism-focused definition of the canonical scenario.
    # Describes the core economic logic that defines this archetype in historical cases.
    # ⚠️ Does NOT imply the current event exactly replicates this definition.
    # Example: "A self-fulfilling loss of confidence leading to mass withdrawal of funds from a solvent but illiquid institution."
    definition: str

    # Foundational academic theories, regulatory doctrines, or legal frameworks that conceptualize this scenario.
    # Provides intellectual grounding for why this pattern is considered canonical.
    # Example: "Diamond & Dybvig (1983) Bank Run Model; Minsky (1986) Financial Instability Hypothesis."
    theoretical_basis: str

    # Stages commonly observed in HISTORICAL instances of this scenario.
    # Each stage is a short phrase capturing its economic function (e.g., "Liquidity Run: Mass withdrawals exhaust liquid assets").
    # ⚠️ These are POSSIBLE structural elements — NOT a required sequence for the current event.
    # ⚠️ The actual event may have fewer, more, or differently ordered stages.
    # Example: ["Latent Vulnerability Phase", "Loss of Confidence Trigger", "Liquidity Run", "Regulatory Intervention"]
    standard_stages: List[str]

    # Episode types that FREQUENTLY appear in historical instances of this scenario.
    # Used to prioritize extraction focus in data-scarce environments.
    # ⚠️ Novel episode types observed in the current event MUST NEVER be excluded simply because they are not listed here.
    # Example: ["Large-Scale Redemption", "Auditor Resignation", "Central Bank Emergency Lending"]
    key_episode_types: List[EpisodeType]

    # Participant roles that COMMONLY play central functional roles in this scenario.
    # Reflects institutional patterns from past cases (e.g., "Deposit Insurance Agency" in bank runs).
    # ⚠️ The current event may involve unexpected roles (e.g., "Social Media Influencer" in crypto runs) — these must be preserved.
    # Example: ["Issuer", "Retail Investor", "Regulator", "Central Bank"]
    key_participant_roles: List[ParticipantRole]

    # Observable, data-verifiable indicators that have historically signaled this scenario.
    # Derived from forensic analyses of past events (e.g., "sudden deposit outflow" in bank runs).
    # ⚠️ Absence does not rule out the scenario; presence does not confirm it.
    # ⚠️ Use for early warning or validation — NOT as diagnostic criteria.
    # Example: ["Sudden spike in withdrawal requests", "Interbank funding freeze", "Equity price collapse with high volume"]
    signature_indicators: List[str]

    # Notable real-world events that exemplify this scenario archetype.
    # Serves as analogy anchors for contextual understanding and validation.
    # ⚠️ The current event is NOT required to match these examples.
    # Format: "Event Name (Year)"
    # Example: ["Northern Rock Bank Run (2007)", "Silicon Valley Bank Collapse (2023)"]
    historical_examples: List[str]

    # Confidence that the current event semantically aligns with this canonical scenario.
    # Range: 0.0 (no meaningful alignment) to 1.0 (near-identical mechanism).
    # ⚠️ Low confidence (<0.6) implies high novelty — downstream agents should rely primarily on data, not priors.
    # ⚠️ High confidence (>0.8) suggests strong template applicability — priors can guide naming and validation.
    # Optional, as some recognition methods may be deterministic.
    confidence: Optional[float] = None


@dataclass
class FinanceEventRecognizer:
    """
    Represents one real-world financial event whose evolution is influenced by
    multiple canonical financial scenarios acting at different stages or in parallel.

    ⚠️ This class does NOT model a "hybrid event type" — it models ONE EVENT
    through multiple explanatory lenses, each corresponding to a real segment of its lifecycle.

    Each FinanceScenario in scenario_segments is a DOMAIN PRIOR for that segment.
    Downstream agents must:
      - Derive actual event structure from observed data first
      - Use these priors only for guidance, validation, and prioritization
      - Never force the event into a pre-defined multi-scenario mold
    """

    # Human-readable name of the actual financial event being analyzed.
    # This refers to a single, real-world occurrence with clear temporal boundaries.
    # Example: "FTX Collapse (2022)", "Archegos Capital Blowup (2021)"
    event_name: str

    # List of canonical scenarios that collectively explain different segments of the event's evolution.
    # Each FinanceScenario describes a pattern that was ACTIVE during a phase of the event.
    # Segments may be sequential (early/mid/late) or overlapping (e.g., fraud + liquidity stress).
    # ⚠️ This is NOT a classification output — it is a multi-lens interpretation grounded in data.
    scenario_segments: List[FinanceScenario]

    # Optional overall confidence that the set of scenarios adequately explains the full event.
    # May be derived from individual segment confidences or expert judgment.
    # ⚠️ Use to calibrate reliance on priors: low confidence → trust data more; high confidence → use priors for coherence.
    overall_alignment_confidence: Optional[float] = None


@dataclass
class ParticipantManager:
    """
    Agent responsible for extracting participants from financial event content
    and managing their persistence via a database.

    RESPONSIBILITIES:
    1. Scan input content to identify participant entities and their roles.
    2. Interact with a persistent database to:
       - Retrieve existing canonical participants
       - Store newly discovered participants
    3. Maintain the current set of recognized participants for the event.

    DESIGN NOTE:
    This class does not include internal resolution maps or caches —
    those are handled by external functions or database queries.
    """

    # The textual content from which to extract participants
    data_content: List[str]

    # Database connection URI for participant persistence (e.g., PostgreSQL, MongoDB)
    # Example: "postgresql://user:pass@localhost/finance_kb"
    database_uri: Optional[str] = None

    # Database table or collection name for storing participants
    # Example: "financial_entities"
    participant_table: Optional[str] = "financial_participants"

    # Table Prefix used to store participants for different episodes of the event
    episode_table_prefix: Optional[str] = "episode_"


@dataclass
class StagePlanner:
    """
    Working state of the agent that defines the event's stage structure BEFORE episode extraction.

    PURPOSE:
    Hypothesize the number, order, and logic of stages based on the FinanceEventRecognizer prior.
    This provides a structural scaffold into which episodes will later be placed.

    KEY INSIGHT:
    In financial event reconstruction, we often know the "playbook" (e.g., Bank Run has 4 phases)
    before we fill in the specific acts. This agent defines that playbook.

    OUTPUT:
    A list of ReconstructedStage objects with:
      - stage_id
      - hypothesized name and logic
      - expected episode types and participant roles
    """

    # The domain prior that defines canonical scenario stages
    scenario_prior: "FinanceEventRecognizer"

    # The hypothesized stages for this event (created BEFORE episode extraction)
    # Each stage is a structural container waiting for episodes
    hypothesized_stages: List["ReconstructedStage"]

    # Confidence threshold to include a scenario segment's stages
    min_scenario_confidence_for_staging: Optional[float] = 0.5


@dataclass
class EpisodeExtractor:
    """
    Working state of the agent that extracts episodes INTO pre-defined stages.

    PURPOSE:
    Identify concrete episodes from evidence and assign them to the appropriate stage
    based on timing, content, and participant roles.

    KEY CHANGE:
    - Does NOT contain ParticipantManager
    - Instead, receives candidate_participants (resolved list) as input
    - Uses hypothesized_stages to guide episode-to-stage assignment

    WORKFLOW:
    1. Receive candidate_participants from ParticipantManager
    2. Extract episode with participant roles
    3. Assign episode to the most plausible hypothesized_stage
    """

    # Raw evidence content to extract from
    data_content: List["EvidenceItem"]

    # Domain prior for focus guidance
    scenario_prior: "FinanceEventRecognizer"

    # Pre-defined stage structure to fill (from StagePlanner)
    hypothesized_stages: List["ReconstructedStage"]

    # Resolved participants provided by ParticipantManager for this extraction context
    candidate_participants: List["CanonicalParticipant"]

    # Episodes already extracted and assigned to stages
    extracted_episodes: List["ExtractedEpisode"]

    # Current episode being processed
    current_episode: Optional["ExtractedEpisode"] = None

    # Minimum confidence to accept an episode
    min_extraction_confidence: Optional[float] = 0.5


@dataclass
class FactChecker:
    """
    Working state of the agent that validates episodes against original evidence.

    PURPOSE:
    Ensure every extracted episode is factually grounded in source data,
    eliminating hallucination, over-interpretation, or unsupported inference.

    KEY CONSTRAINTS:
    - Validates **one episode at a time**.
    - Rejects any claim that cannot be directly observed or logically inferred from evidence.
    - Preserves source provenance for every verified claim.
    - Confidence scores must reflect source reliability (e.g., SEC filing > social media).

    COLLABORATION:
    - Receives ExtractedEpisode from EpisodeExtractor
    - Cross-references against original data_content
    - Outputs VerifiedEpisode for StagePlanner
    """

    # Original evidence stream used for verification
    data_content: List["EvidenceItem"]

    # The episode under verification
    current_episode: Optional["ExtractedEpisode"] = None

    # Episodes that have passed verification
    verified_episodes: List["VerifiedEpisode"]

    # Minimum confidence required to accept an episode as verified
    min_verification_confidence: Optional[float] = 0.7

    # Optional: weights for source reliability (e.g., {"SEC": 1.0, "Twitter": 0.3})
    source_reliability_weights: Optional[Dict[str, float]] = None


@dataclass
class QualityReviewer:
    """
    Working state of the agent that performs final holistic validation.

    PURPOSE:
    Ensure the reconstructed event is causally sound, temporally consistent,
    and fully reflects all relevant scenario dynamics from the prior.

    KEY CONSTRAINTS:
    - If scenario_prior contains a segment with alignment_confidence > threshold,
      the reconstruction MUST reflect its dynamics.
    - Must flag over-reliance on priors (e.g., stages copied verbatim).
    - Final output must be both accurate (fact-checked) and complete (multi-scenario).
    - Quality warnings should be specific and actionable.

    COLLABORATION:
    - Receives ReconstructedStage list from StagePlanner
    - Compares against full FinanceEventRecognizer prior
    - Produces final ReconstructedEvent for output
    """

    # Reconstructed stages to audit
    reconstructed_stages: List["ReconstructedStage"]

    # Original domain prior for completeness validation
    scenario_prior: "FinanceEventRecognizer"

    # Final validated event output
    final_reconstructed_event: Optional["ReconstructedEvent"] = None

    # Minimum alignment confidence to require scenario coverage
    min_scenario_coverage_threshold: Optional[float] = 0.6

    # List of quality warnings (e.g., "missing_scenario_segment", "prior_overfitting")
    quality_warnings: Optional[List[str]] = None
