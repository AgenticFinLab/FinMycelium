from typing import Dict, Callable

from .base import BaseMatcher
from .lm_match import LLMMatcher
from .re_match import ReMatch
from .lx_match import KWMatcher, LMMatcher as LXMatcher, VectorMatcher


# Matcher factory dictionary
matcher_factory: Dict[str, Callable] = {
    "llm": lambda config: LLMMatcher(
        lm_name=config["lm_name"],
        config=config,
    ),
    "re": lambda config: ReMatch(config=config),
    "lx_keyword": lambda config: KWMatcher(config=config),
    "lx_llm": lambda config: LXMatcher(config=config),
    "lx_vector": lambda config: VectorMatcher(config=config),
}


def get(config: dict) -> BaseMatcher:
    """Get a matcher"""
    matcher_type = config["matcher_type"]
    if matcher_type not in matcher_factory:
        available = ", ".join(matcher_factory.keys())
        raise ValueError(
            f"Matcher '{matcher_type}' not found. Available options: {available}"
        )
    return matcher_factory[matcher_type](config)
