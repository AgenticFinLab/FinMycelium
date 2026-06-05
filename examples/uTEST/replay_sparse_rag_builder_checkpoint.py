"""Inspect and replay saved SparseRagBuilder checkpoint directories.

This helper intentionally stays lightweight: it reads existing builder output
files, summarizes skeleton/final cascade counts, and can replay saved agent
results through SparseRagBuilder.integrate_from_files without calling an LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def count_stages_and_episodes(cascade: dict[str, Any]) -> dict[str, int | None]:
    stages = cascade.get("stages")
    if not isinstance(stages, list):
        return {"stage_count": None, "episode_count": None}

    episode_count = 0
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        episodes = stage.get("episodes")
        if isinstance(episodes, list):
            episode_count += len(episodes)
    return {"stage_count": len(stages), "episode_count": episode_count}


def matching_files(directory: Path, patterns: tuple[str, ...]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for item in directory.glob(pattern):
            if item in seen:
                continue
            candidates.append(item)
            seen.add(item)
    return candidates


def latest_matching_file(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    candidates = matching_files(directory, patterns)
    if not candidates:
        return None
    result_candidates = [
        item for item in candidates if item.name.endswith("-Result.json")
    ]
    preferred = result_candidates or candidates
    return max(preferred, key=lambda item: (item.stat().st_mtime, item.name))


def latest_skeleton_file(directory: Path) -> Path | None:
    checker = latest_matching_file(
        directory,
        ("SkeletonChecker*-Result.json", "SkeletonChecker-*.json"),
    )
    if checker is not None:
        return checker
    return latest_matching_file(
        directory,
        ("SkeletonReconstructor*-Result.json", "SkeletonReconstructor-*.json"),
    )


def final_checkpoint_file(directory: Path) -> Path | None:
    final_file = directory / "FinalEventCascade.json"
    if final_file.exists():
        return final_file
    integrated_file = directory / "IntegratedEventCascade.json"
    if integrated_file.exists():
        return integrated_file
    return None


def load_json_counts(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {"path": None, "stage_count": None, "episode_count": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {"path": str(path), "stage_count": None, "episode_count": None}

    counts = count_stages_and_episodes(payload if isinstance(payload, dict) else {})
    return {
        "path": str(path),
        "stage_count": counts["stage_count"],
        "episode_count": counts["episode_count"],
    }


def summarize_checkpoint_dir(checkpoint_dir: Path | str) -> dict[str, object]:
    directory = Path(checkpoint_dir)
    skeleton_file = latest_skeleton_file(directory)
    final_file = final_checkpoint_file(directory)
    return {
        "checkpoint_dir": str(directory),
        "skeleton": load_json_counts(skeleton_file),
        "final": load_json_counts(final_file),
    }


def build_output_dirs(root: Path | str) -> list[Path]:
    directory = Path(root)
    if not directory.exists():
        return []
    return sorted(
        [
            item
            for item in directory.iterdir()
            if item.is_dir() and item.name.startswith("build_output_")
        ],
        key=lambda item: (item.stat().st_mtime, item.name),
    )


def has_usable_checkpoint(checkpoint_dir: Path | str) -> bool:
    summary = summarize_checkpoint_dir(checkpoint_dir)
    skeleton = summary["skeleton"]
    final = summary["final"]
    return (
        isinstance(skeleton.get("stage_count"), int)
        and skeleton["stage_count"] > 0
        and isinstance(skeleton.get("episode_count"), int)
        and skeleton["episode_count"] > 0
        and isinstance(final.get("stage_count"), int)
        and final["stage_count"] > 0
        and isinstance(final.get("episode_count"), int)
        and final["episode_count"] > 0
    )


def latest_valid_build_output_dir(root: Path | str) -> Path | None:
    directory = Path(root)
    if directory.is_dir() and has_usable_checkpoint(directory):
        return directory
    for candidate in reversed(build_output_dirs(directory)):
        if has_usable_checkpoint(candidate):
            return candidate
    return None


def summarize_latest_checkpoint(root: Path | str) -> dict[str, object]:
    checkpoint_dir = latest_valid_build_output_dir(root)
    if checkpoint_dir is None:
        return {
            "checkpoint_dir": None,
            "skeleton": {"path": None, "stage_count": None, "episode_count": None},
            "final": {"path": None, "stage_count": None, "episode_count": None},
        }
    return summarize_checkpoint_dir(checkpoint_dir)


def replay_checkpoint_dir(checkpoint_dir: Path | str) -> dict[str, Any]:
    from finmy.builder.sparse_build.main_build import SparseRagBuilder

    builder = SparseRagBuilder.__new__(SparseRagBuilder)
    builder.save_dir = str(Path(checkpoint_dir))
    return builder.integrate_from_files()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or replay SparseRagBuilder checkpoint directories."
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Checkpoint directory or a parent directory containing build_output_* dirs.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay the selected checkpoint with SparseRagBuilder.integrate_from_files.",
    )
    args = parser.parse_args(argv)

    summary = summarize_latest_checkpoint(args.root)
    output: dict[str, object] = {"summary": summary}
    if args.replay and summary["checkpoint_dir"]:
        output["replayed"] = replay_checkpoint_dir(str(summary["checkpoint_dir"]))

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
