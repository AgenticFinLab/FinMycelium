"""
Implementation of the Financial Event Cascade with a large model based multi-agent system.
"""

from typing import List
from dataclasses import dataclass


from finmy.builder.finance_define import (
    SupportedFinancialScenario,
    EpisodeType,
    ParticipantRole,
)


@dataclass
class FinanceScenarioRecognizer:
    """
    Represents a recognized canonical financial scenario.

    This dataclass encapsulates the core attributes of a financial scenario
    as identified from real-world event data. It is the output of a recognition process,
    not an agent or controller.
    """

    # The canonical scenario type, selected from a theory-grounded taxonomy
    # Example: "bank_run", "ponzi_scheme"
    scenario_type: SupportedFinancialScenario

    # A concise, precise definition of the scenario's mechanism
    # Example: "A collapse triggered by depositor panic leading to rapid withdrawal of funds."
    definition: str

    # The academic or regulatory foundation for this scenario
    # Example: "Diamond & Dybvig (1983) Bank Run Model"
    theoretical_basis: str

    # Ordered list of standard stages that define the scenario's evolution logic
    # Each stage is a short descriptive phrase capturing its economic function
    # Example: ["Latent Vulnerability Phase", "Loss of Confidence Trigger", "Liquidity Run", "Regulatory Intervention"]
    standard_stages: List[str]

    # Episode types most characteristic of this scenario
    # Used to guide extraction focus in event reconstruction
    # Example: ["MARKET_EVENT", "REG_ACTION", "DISCLOSURE"]
    key_episode_types: List[EpisodeType]

    # Participant roles that typically play central roles in this scenario
    # Example: ["ISSUER", "MARKET_AGENT", "REGULATOR"]
    key_participant_roles: List[ParticipantRole]

    # Observable indicators that signal this scenario is unfolding
    # These are factual, data-verifiable patterns
    # Example: ["sudden deposit outflow", "counterparty funding freeze", "equity price collapse with high volume"]
    signature_indicators: List[str]

    # Notable historical instances of this scenario
    # Format: "Event Name (Year)"
    # Example: ["Northern Rock Bank Run (2007)", "Silicon Valley Bank Collapse (2023)"]
    historical_examples: List[str]

    # Confidence score of the recognition match (if applicable)
    # Range: 0.0 (no match) to 1.0 (exact match)
    # Optional, as some recognition may be deterministic
    confidence: Optional[float] = None
