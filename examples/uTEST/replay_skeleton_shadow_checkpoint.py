"""Inspect the latest builder checkpoint without running a full benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "EXPERIMENT" / "uTEST"


def _count_stages_and_episodes(cascade: dict[str, Any]) -> dict[str, int | None]:
    stages = cascade.get("stages")
    if not isinstance(stages, list):
        return {"stage_count": None, "episode_count": None}

    episode_count = 0
    for stage in stages:
        if isinstance(stage, dict):
            episodes = stage.get("episodes")
            if isinstance(episodes, list):
                episode_count += len(episodes)

    return {"stage_count": len(stages), "episode_count": episode_count}


def _latest_build_output_dir(root: Path) -> Path | None:
    if not root.exists():
        return None

    build_dirs = [
        item for item in root.iterdir() if item.is_dir() and item.name.startswith("build_output_")
    ]
    if not build_dirs:
        return None

    return max(build_dirs, key=lambda item: (item.stat().st_mtime, item.name))


def _latest_matching_file(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(directory.glob(pattern))

    if not candidates:
        return None

    return max(candidates, key=lambda item: (item.stat().st_mtime, item.name))


def _load_json_counts(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {"path": None, "stage_count": None, "episode_count": None}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    counts = _count_stages_and_episodes(payload if isinstance(payload, dict) else {})
    return {
        "path": str(path),
        "stage_count": counts["stage_count"],
        "episode_count": counts["episode_count"],
    }


def summarize_latest_builder_output(root: Path) -> dict[str, object]:
    """Summarize the newest `build_output_*` directory under `root`."""

    latest_dir = _latest_build_output_dir(root)
    summary: dict[str, object] = {
        "root": str(root),
        "builder_output_count": 0,
        "latest_builder_dir": None,
        "skeleton": {"path": None, "stage_count": None, "episode_count": None},
        "final": {"path": None, "stage_count": None, "episode_count": None},
    }

    if latest_dir is None:
        return summary

    build_dirs = [
        item for item in root.iterdir() if item.is_dir() and item.name.startswith("build_output_")
    ]
    summary["builder_output_count"] = len(build_dirs)
    summary["latest_builder_dir"] = str(latest_dir)

    skeleton_file = _latest_matching_file(latest_dir, ("SkeletonReconstructor*-Result.json",))
    final_file = _latest_matching_file(
        latest_dir,
        ("FinalEventCascade.json", "IntegratedEventCascade.json"),
    )

    summary["skeleton"] = _load_json_counts(skeleton_file)
    summary["final"] = _load_json_counts(final_file)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize the latest builder output checkpoint."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root directory that contains build_output_* folders.",
    )
    args = parser.parse_args()
    summary = summarize_latest_builder_output(args.root)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
