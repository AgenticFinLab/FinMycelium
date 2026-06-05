"""Sparse RAG builder package."""

from typing import Any

__all__ = ["SparseRagBuilder"]


def __getattr__(name: str) -> Any:
    if name == "SparseRagBuilder":
        from .main_build import SparseRagBuilder

        return SparseRagBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
