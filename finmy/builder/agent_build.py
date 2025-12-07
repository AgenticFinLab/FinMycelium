"""
Implementation of the Financial Event Cascade with a large model based multi-agent system.
"""

from typing import List, Optional
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
