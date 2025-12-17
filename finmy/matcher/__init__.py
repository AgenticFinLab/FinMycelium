"""
Matcher module for content matching and summarization.

This module provides:
- Summarizers: Extract keywords and summarize queries
- Matchers: Match content against queries using various strategies
- Registry pattern for dynamic component selection
"""

import logging
from typing import List, Dict, Any, Callable

from .base import BaseMatcher, MatchInput, MatchOutput, MatchItem
from .summarizer import (
    BaseSummarizer,
    SummarizedUserQuery,
    KWLMSummarizer,
    KWRuleSummarizer,
)
from .lm_match import LLMMatcher
from .re_match import ReMatch
from .lx_match import KWMatcher, LMMatcher as LXMatcher, VectorMatcher


# ============================================================================
# Registry Factory Pattern Implementation
# ============================================================================


class Registry:
    """
    Generic registry for factory pattern implementation.

    This registry allows registering and retrieving classes by name,
    enabling dynamic component selection based on configuration.
    """

    def __init__(self, name: str):
        """Initialize a registry with a name for identification."""
        self.name = name
        self._registry: Dict[str, Callable] = {}

    def register(self, name: str | None = None, factory: Callable | None = None):
        """
        Register a factory function for a given name.

        Supports two usage patterns:
        - As a decorator with explicit name:
              @registry.register("llm")
              def create_llm(config): ...
        - As a decorator using function name as key:
              @registry.register
              def llm(config): ...

        Args:
            name: The identifier for this implementation (optional when used as bare decorator)
            factory: A callable that creates an instance (usually provided implicitly by decorator)
        """

        # Used as bare decorator: @registry.register
        if callable(name) and factory is None:
            func = name
            key = func.__name__
            if key in self._registry:
                logging.warning(
                    f"Registry '{self.name}': Overwriting existing entry '{key}'"
                )
            self._registry[key] = func
            return func

        # Used as @registry.register("name")
        def decorator(func: Callable):
            key = name or func.__name__
            if key in self._registry:
                logging.warning(
                    f"Registry '{self.name}': Overwriting existing entry '{key}'"
                )
            self._registry[key] = func
            return func

        # When used directly as function: register("name", factory)
        if factory is not None:
            return decorator(factory)

        return decorator

    def get(self, name: str, *args, **kwargs):
        """
        Create an instance using the registered factory.

        Args:
            name: The identifier of the implementation to use
            *args, **kwargs: Arguments passed to the factory function

        Returns:
            An instance created by the registered factory

        Raises:
            ValueError: If the name is not registered
        """
        if name not in self._registry:
            available = ", ".join(self._registry.keys())
            raise ValueError(
                f"Registry '{self.name}': '{name}' not found. "
                f"Available options: {available}"
            )
        factory = self._registry[name]
        return factory(*args, **kwargs)

    def list_available(self) -> List[str]:
        """Return a list of all registered names."""
        return list(self._registry.keys())


# ============================================================================
# Summarizer Registry
# ============================================================================

_summarizer_registry = Registry("Summarizer")


@_summarizer_registry.register("kw_lm")
def _create_kw_lm_summarizer(config: Dict[str, Any]) -> BaseSummarizer:
    """Create a KWLMSummarizer instance."""
    llm_name = config.get("llm_name", "ARK/doubao-seed-1-6-flash-250828")
    return KWLMSummarizer({"llm_name": llm_name})


@_summarizer_registry.register("kw_rule")
def _create_kw_rule_summarizer(config: Dict[str, Any]) -> BaseSummarizer:
    """Create a KWRuleSummarizer instance."""
    return KWRuleSummarizer(config or {})


# ============================================================================
# Matcher Registry
# ============================================================================

_matcher_registry = Registry("Matcher")


@_matcher_registry.register("llm")
def _create_llm_matcher(config: Dict[str, Any]) -> BaseMatcher:
    """Create an LLMMatcher instance."""
    lm_name = config.get("lm_name", "ARK/doubao-seed-1-6-flash-250828")
    return LLMMatcher(lm_name=lm_name, config=config)


@_matcher_registry.register("re")
def _create_re_matcher(config: Dict[str, Any]) -> BaseMatcher:
    """Create a ReMatch (regex-based) instance."""
    return ReMatch(config=config)


@_matcher_registry.register("lx_keyword")
def _create_lx_keyword_matcher(config: Dict[str, Any]) -> BaseMatcher:
    """Create a KWMatcher (LlamaIndex keyword-based) instance."""
    return KWMatcher(config=config)


@_matcher_registry.register("lx_llm")
def _create_lx_llm_matcher(config: Dict[str, Any]) -> BaseMatcher:
    """Create an LMMatcher (LlamaIndex LLM-based) instance."""
    return LXMatcher(config=config)


@_matcher_registry.register("lx_vector")
def _create_lx_vector_matcher(config: Dict[str, Any]) -> BaseMatcher:
    """Create a VectorMatcher (LlamaIndex vector-based) instance."""
    return VectorMatcher(config=config)


# ============================================================================
# Public API
# ============================================================================


def get_summarizer_registry() -> Registry:
    """Get the summarizer registry."""
    return _summarizer_registry


def get_matcher_registry() -> Registry:
    """Get the matcher registry."""
    return _matcher_registry


__all__ = [
    # Base classes
    "BaseMatcher",
    "BaseSummarizer",
    "MatchInput",
    "MatchOutput",
    "MatchItem",
    "SummarizedUserQuery",
    # Implementations
    "KWLMSummarizer",
    "KWRuleSummarizer",
    "LLMMatcher",
    "ReMatch",
    "KWMatcher",
    "LXMatcher",
    "VectorMatcher",
    # Registry
    "Registry",
    "get_summarizer_registry",
    "get_matcher_registry",
]
