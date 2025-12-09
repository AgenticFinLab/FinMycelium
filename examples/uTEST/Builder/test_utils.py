"""
Tests for finmy.builder.utils: load_python_text and extract_dataclass_blocks.

Purpose:
- Verify that builder-wide Python source aggregation works and returns content
  suitable for schema parsing (via load_python_text).
- Verify dataclass extraction in two modes:
  - mode="all": all @dataclass blocks are returned
  - mode="single": target dataclass blocks plus transitive dependencies

How to run:
- With pytest installed, run: python examples/uTest/Builder/test_utils.py
- Alternatively integrate into your test suite runner.
"""

from pathlib import Path

from finmy.builder.utils import load_python_text, extract_dataclass_blocks


def test_load_python_text_default_builder_dir():
    """Ensure default loading aggregates builder/*.py into a non-empty string.

    This exercises the default behavior (no path provided) which concatenates all
    Python files inside finmy/builder. We expect schema files to contain
    '@dataclass' definitions, so we assert presence for a basic sanity check.
    """
    spec = load_python_text()
    assert isinstance(spec, str) and len(spec) > 0
    assert "@dataclass" in spec


def test_extract_all_from_builder_schema():
    """Extract all dataclasses from structure.py and assert key classes exist.

    We target the canonical schema file and validate presence of top-level
    containers that downstream prompts depend on.
    """
    spec = load_python_text(
        path=Path(__file__).resolve().parents[3] / "finmy" / "builder" / "structure.py"
    )
    blocks = extract_dataclass_blocks(spec, mode="all")
    assert "class EventCascade" in blocks
    assert "class EventStage" in blocks
    assert "class Episode" in blocks


def test_extract_single_episode_dependencies():
    """Extract episode with its transitive dataclass dependencies.

    The Episode definition references Participant, Action, Transaction,
    Interaction via its field type annotations. In 'single' mode, these should
    be included automatically by dependency resolution.
    """
    spec = load_python_text(
        path=Path(__file__).resolve().parents[3] / "finmy" / "builder" / "structure.py"
    )
    blocks = extract_dataclass_blocks(spec, mode="single", target_classes=["Episode"])
    assert "class Episode" in blocks
    assert "class Participant" in blocks
    assert "class Action" in blocks
    assert "class Transaction" in blocks
    assert "class Interaction" in blocks


def test_extract_from_inline_spec_union_and_optional():
    """Validate union types (PEP 604) and Optional dependency resolution.

    Holder depends on Alpha and Beta via a union type, and Alpha via Optional.
    The extractor should include both Alpha and Beta when targeting Holder.
    """
    spec = """
from dataclasses import dataclass
from typing import Optional

@dataclass
class Alpha:
    a: int

@dataclass
class Beta:
    b: int

@dataclass
class Holder:
    item: Alpha | Beta
    maybe: Optional[Alpha] = None
"""
    blocks = extract_dataclass_blocks(spec, mode="single", target_classes=["Holder"])
    assert "class Holder" in blocks
    assert "class Alpha" in blocks
    assert "class Beta" in blocks
