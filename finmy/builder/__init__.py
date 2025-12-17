"""
Builder module for financial event reconstruction.

This module provides:
- Builders: Reconstruct financial events from matched samples
- Registry pattern for dynamic component selection
"""

import logging
from typing import List, Dict, Any, Callable

from .base import BaseBuilder, BuildInput, BuildOutput


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
              @registry.register("lm")
              def create_lm(config): ...
        - As a decorator using function name as key:
              @registry.register
              def lm(config): ...

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
# Builder Registry
# ============================================================================

_builder_registry = Registry("Builder")


@_builder_registry.register("lm")
def _create_lm_builder(config: Dict[str, Any]) -> BaseBuilder:
    """Create an LMBuilder instance."""
    # Local import to avoid circular import with finmy.converter
    from .lm_build import LMBuilder

    return LMBuilder(config=config)


@_builder_registry.register("class_lm")
def _create_class_lm_builder(config: Dict[str, Any]) -> BaseBuilder:
    """Create a ClassLMBuilder instance."""
    # Local import to avoid circular import with finmy.converter
    from .class_build.main_build import ClassLMBuilder

    return ClassLMBuilder(config=config)


# ============================================================================
# Public API
# ============================================================================


def get_builder_registry() -> Registry:
    """Get the builder registry."""
    return _builder_registry


__all__ = [
    # Base classes
    "BaseBuilder",
    "BuildInput",
    "BuildOutput",
    # Registry
    "Registry",
    "get_builder_registry",
]
