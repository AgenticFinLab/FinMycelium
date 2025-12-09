"""
Tests for finmy.builder.utils: load_python_text and extract_dataclass_blocks.

Purpose:
- In main, explicitly specify the structure.py path, load it via load_python_text, and print a snippet.
- Use the returned code_text as the input to extract_dataclass_blocks, and test both "all" and "single" modes.

How to run:
- Run directly: python examples/uTEST/Builder/test_utils.py
"""

from pathlib import Path

from finmy.builder.utils import (
    load_python_text,
    extract_dataclass_blocks,
    filter_dataclass_fields,
)


def test_load_python_text_structure_path() -> str:
    """Explicitly specify structure.py path, load and return the code_text, with basic assertions."""
    structure_path = (
        Path(__file__).resolve().parents[3] / "finmy" / "builder" / "structure.py"
    )
    code_text = load_python_text(path=structure_path)

    assert isinstance(code_text, str) and len(code_text) > 0
    assert "@dataclass" in code_text
    return code_text


def test_extract_all_from_code_text(code_text: str):
    """Extract all dataclass blocks from the given code_text and assert key classes exist."""
    blocks = extract_dataclass_blocks(code_text, mode="all")
    assert "class EventCascade" in blocks
    assert "class EventStage" in blocks
    assert "class Episode" in blocks


def test_extract_single_episode_dependencies(code_text: str):
    """Extract Episode and its transitive dataclass dependencies from the given code_text."""
    blocks = extract_dataclass_blocks(
        code_text, mode="single", target_classes=["Episode"]
    )
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


def test_filter_stage_episode_minimal(code_text: str):
    """
    Test the code of filtering out the unnecessary fields of the dataclass.
    """
    filtered = filter_dataclass_fields(
        code_text,
        {
            "EventStage": ["stage_id", "name", "index_in_event"],
            "Episode": ["episode_id", "name", "index_in_stage"],
            "EventCascade": [],
        },
    )
    print(filtered)
    assert "class EventStage" in filtered
    assert (
        "stage_id" in filtered and "name" in filtered and "index_in_event" in filtered
    )
    assert "Descriptive name" in filtered
    assert "Zero-based index" in filtered
    assert "episodes:" not in filtered
    assert "class Episode" in filtered
    assert (
        "episode_id" in filtered and "name" in filtered and "index_in_stage" in filtered
    )
    assert "Locally unique identifier" in filtered
    assert "Zero-based index within the owning stage" in filtered
    assert "Example:" in filtered
    assert (
        "participants:" not in filtered
        and "transactions:" not in filtered
        and "interactions:" not in filtered
    )


if __name__ == "__main__":
    failures = []
    try:
        code_text = test_load_python_text_structure_path()
        print("[PASS] test_load_python_text_structure_path")
    except Exception as e:
        print(f"[FAIL] test_load_python_text_structure_path: {e}")
        failures.append("test_load_python_text_structure_path")

    try:
        test_extract_all_from_code_text(code_text)
        print("[PASS] test_extract_all_from_code_text")
    except Exception as e:
        print(f"[FAIL] test_extract_all_from_code_text: {e}")
        failures.append("test_extract_all_from_code_text")

    try:
        test_extract_single_episode_dependencies(code_text)
        print("[PASS] test_extract_single_episode_dependencies")
    except Exception as e:
        print(f"[FAIL] test_extract_single_episode_dependencies: {e}")
        failures.append("test_extract_single_episode_dependencies")

    try:
        test_extract_from_inline_spec_union_and_optional()
        print("[PASS] test_extract_from_inline_spec_union_and_optional")
    except Exception as e:
        print(f"[FAIL] test_extract_from_inline_spec_union_and_optional: {e}")
        failures.append("test_extract_from_inline_spec_union_and_optional")

    try:
        test_filter_stage_episode_minimal(code_text)
        print("[PASS] test_filter_stage_episode_minimal")
    except Exception as e:
        print(f"[FAIL] test_filter_stage_episode_minimal: {e}")
        failures.append("test_filter_stage_episode_minimal")

    raise SystemExit(1 if failures else 0)
