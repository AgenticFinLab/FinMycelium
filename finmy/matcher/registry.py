from typing import Dict, Callable
import logging

from .base import BaseMatcher
from .lm_match import LLMMatcher
from .re_match import ReMatch
from .lx_match import KWMatcher, LMMatcher as LXMatcher, VectorMatcher


# Matcher factory dictionary
matcher_factory: Dict[str, Callable] = {
    "llm": LLMMatcher,
    "re": ReMatch,
    "lx_keyword": KWMatcher,
    "lx_llm": LXMatcher,
    "lx_vector": VectorMatcher,
}


def get(config: dict) -> BaseMatcher:
    """Get a matcher"""
    logging.info("Creating matcher with config: %s", config)
    matcher = matcher_factory[config["matcher_type"]](config)
    logging.info("Created matcher: %s", matcher)
    return matcher
