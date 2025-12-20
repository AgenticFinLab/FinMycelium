"""
Builder Registry
================

This module implements the Registry and Factory pattern for the Builder component.
It provides a centralized mechanism to instantiate different types of builders based on
runtime configuration.

Key Features:
- **Factory Pattern**: Decouples the creation of specific builder classes from their usage.
- **Config-Driven**: Selects and initializes builders using a configuration dictionary.
- **Extensibility**: New builders can be added to the `builder_factory` to be made available.

Supported Builders:
- **LMBuilder** (`lm`): Standard builder using single LM inference.
- **ClassLMBuilder** (`class_lm`): Builder that first classifies event type then uses specific prompts.
- **AgentEventBuilder** (`agent_build`): Advanced builder using a multi-agent system for event reconstruction.

Usage:
    config = {"builder_type": "agent_build", ...}
    builder = registry.get(config)
"""

from typing import Dict, Callable
import logging

from .base import BaseBuilder
from .lm_build import LMBuilder
from .class_build.main_build import ClassEventBuilder
from .agent_build.main_build import AgentEventBuilder

# ============================================================================
# Registry Factory Pattern Implementation
# ============================================================================

# Builder factory dictionary
builder_factory: Dict[str, Callable] = {
    "LMBuilder": LMBuilder,
    "ClassEventBuilder": ClassEventBuilder,
    "AgentEventBuilder": AgentEventBuilder,
}


def get(builder_config: dict) -> BaseBuilder:
    """Get a builder."""
    builder_type = builder_config["builder_type"]
    if builder_type not in builder_factory:
        raise ValueError(
            f"Unknown builder type: {builder_type} in {builder_factory.keys()}"
        )
    logging.info("Creating builder: %s.", builder_type)
    builder = builder_factory[builder_type](build_config=builder_config)
    return builder
