from typing import Dict, Callable

from .base import BaseBuilder
from .lm_build import LMBuilder
from .class_build.main_build import ClassLMBuilder

# ============================================================================
# Registry Factory Pattern Implementation
# ============================================================================

# Builder factory dictionary
builder_factory: Dict[str, Callable] = {
    "lm": LMBuilder,
    "class_lm": ClassLMBuilder,
}


def get(config: dict) -> BaseBuilder:
    """Get a builder"""
    builder_type = config["builder_type"]
    if builder_type not in builder_factory:
        available = ", ".join(builder_factory.keys())
        raise ValueError(
            f"Builder '{builder_type}' not found. Available options: {available}"
        )
    return builder_factory[builder_type](config)
