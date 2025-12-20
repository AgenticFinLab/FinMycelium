"""
Matcher Registry
================

This module implements the Registry and Factory pattern for the Matcher component.
It provides a centralized mechanism to instantiate different types of matchers based on
runtime configuration.

Key Features:
- **Factory Pattern**: Decouples the creation of specific matcher classes from their usage.
- **Config-Driven**: Selects and initializes matchers using a configuration dictionary.
- **Extensibility**: New matchers can be added to the `matcher_factory` to be made available.

Supported Matchers:
- **LLMMatcher** (`llm`): General-purpose matcher using Large Language Models.
- **ReMatch** (`re`): Rule-based matcher using Regular Expressions.
- **KWMatcher** (`lx_keyword`): Keyword-based matcher (LlamaIndex integration).
- **LXMatcher** (`lx_llm`): LLM-based matcher (LlamaIndex integration).
- **VectorMatcher** (`lx_vector`): Semantic matcher using vector embeddings.

Usage:
    config = {"matcher_type": "llm", ...}
    matcher = registry.get(config)
"""

from typing import Dict, Callable
import logging

from .base import BaseMatcher
from .lm_match import LLMMatcher
from .lx_match import KWMatcher, LMMatcher as LXMatcher, VectorMatcher


# Matcher factory dictionary
matcher_factory: Dict[str, Callable] = {
    "LLMMatcher": LLMMatcher,
    "KWMatcher": KWMatcher,
    "LXMatcher": LXMatcher,
    "VectorMatcher": VectorMatcher,
}


def get(matcher_config: dict) -> BaseMatcher:
    """Get a matcher."""
    matcher_type = matcher_config["matcher_type"]
    if matcher_type not in matcher_factory:
        raise ValueError(
            f"Unknown matcher type: {matcher_type} in {matcher_factory.keys()}"
        )
    logging.info("Creating matcher: %s.", matcher_type)
    matcher = matcher_factory[matcher_type](matcher_config)
    return matcher
