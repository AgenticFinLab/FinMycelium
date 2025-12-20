"""
Summarizer Registry
===================

This module implements the Registry and Factory pattern for the Summarizer component.
It provides a centralized mechanism to instantiate different types of summarizers based on
runtime configuration.

Key Features:
- **Factory Pattern**: Decouples the creation of specific summarizer classes from their usage.
- **Config-Driven**: Selects and initializes summarizers using a configuration dictionary.
- **Extensibility**: New summarizers can be added to the `summarizer_factory` to be made available.

Supported Summarizers:
- **KWLMSummarizer**: Summarizer based on Large Language Models (LLM) focused on keywords.
- **KWRuleSummarizer**: Rule-based summarizer focused on keywords.

Usage:
    config = {"summarizer_type": "KWLMSummarizer", ...}
    summarizer = registry.get(config)
"""

from typing import Dict, Callable
import logging

from .summarizer import BaseSummarizer, KWLMSummarizer, KWRuleSummarizer


# Summarizer factory dictionary
summarizer_factory: Dict[str, Callable] = {
    "KWLMSummarizer": KWLMSummarizer,
    "KWRuleSummarizer": KWRuleSummarizer,
}


def get(summarizer_config: dict) -> BaseSummarizer:
    """Get a summarizer."""
    summarizer_type = summarizer_config["summarizer_type"]
    if summarizer_type not in summarizer_factory:
        raise ValueError(
            f"Unknown summarizer type: {summarizer_type} in {summarizer_factory.keys()}"
        )
    logging.info("Creating summarizer: %s.", summarizer_type)
    summarizer = summarizer_factory[summarizer_type](summarizer_config)
    return summarizer
