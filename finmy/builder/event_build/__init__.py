"""Context-aware event builder package."""

from typing import Any

__all__ = ["ContextEventBuilder"]


def __getattr__(name: str) -> Any:
    if name == "ContextEventBuilder":
        from .main_build import ContextEventBuilder

        return ContextEventBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
