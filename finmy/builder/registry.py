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
    "lm": LMBuilder,
    "class_build": ClassEventBuilder,
    "agent_build": AgentEventBuilder,
}


def get(config: dict) -> BaseBuilder:
    """Get a builder"""
    logging.info("Creating builder with config: %s", config)
    builder = builder_factory[config["builder_type"]](build_config=config)
    logging.info("Created builder: %s", builder)
    return builder
