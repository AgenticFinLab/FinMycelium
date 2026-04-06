"""Create and inspect a single-node README benchmark checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


DEFAULT_ROOT = Path(
    "/home/lenovo/projects/AgenticFinLab/.local-runtime/finmy-readme-main/outputs/builder"
)
BENCHMARK_QUERY_TEXT = "What is the case involving fraud and money laundering by Qian Zhimin?"
BENCHMARK_KEY_WORDS = ["fraud", "money laundering", "investigators property purchases"]


def _workspace_root(root: Path) -> Path:
    if (root / "configs" / "run-pipeline.yml").exists():
        return root
    if root.name == "builder" and root.parent.name == "outputs" and len(root.parents) >= 2:
        return root.parents[1]
    return root


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


def _matching_files(directory: Path, patterns: tuple[str, ...]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for item in directory.glob(pattern):
            if item not in seen:
                candidates.append(item)
                seen.add(item)
    return candidates


def _build_output_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []

    build_dirs = [
        item for item in root.iterdir() if item.is_dir() and item.name.startswith("build_output_")
    ]
    return sorted(build_dirs, key=lambda item: (item.stat().st_mtime, item.name))


def _latest_matching_file(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    candidates = _matching_files(directory, patterns)
    if not candidates:
        return None

    result_candidates = [
        item for item in candidates if item.name.endswith("-Result.json")
    ]
    preferred_candidates = result_candidates or candidates
    return max(preferred_candidates, key=lambda item: (item.stat().st_mtime, item.name))


def _has_usable_checkpoint(directory: Path) -> bool:
    skeleton_file = _latest_matching_file(
        directory,
        ("SkeletonReconstructor*-Result.json", "SkeletonReconstructor-*.json"),
    )
    final_file = _latest_matching_file(
        directory,
        ("FinalEventCascade.json", "IntegratedEventCascade.json"),
    )
    return skeleton_file is not None and final_file is not None


def _latest_valid_build_output_dir(root: Path) -> Path | None:
    build_dirs = _build_output_dirs(root)
    if not build_dirs:
        return None

    for candidate in reversed(build_dirs):
        if _has_usable_checkpoint(candidate):
            return candidate
    return None


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


def _summarize_checkpoint_dir(checkpoint_dir: Path) -> dict[str, object]:
    skeleton_file = _latest_matching_file(
        checkpoint_dir,
        ("SkeletonReconstructor*-Result.json", "SkeletonReconstructor-*.json"),
    )
    final_file = _latest_matching_file(
        checkpoint_dir,
        ("FinalEventCascade.json", "IntegratedEventCascade.json"),
    )

    return {
        "checkpoint_dir": str(checkpoint_dir),
        "skeleton": _load_json_counts(skeleton_file),
        "final": _load_json_counts(final_file),
    }


def _load_readme_contents(workspace_root: Path, limit: int = 3) -> list[str]:
    data_path = workspace_root / "cache" / "data-blocks" / "text_block_0.json"
    if not data_path.exists():
        return []

    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        return []

    signals = (
        "qian",
        "zhimin",
        "bitcoin",
        "money laundering",
        "laundering",
        "fraud",
        "cryptoqueen",
        "blue sky",
        "guardian",
        "cnn",
        "cps",
        "investigators",
        "property",
        "purchases",
    )
    candidates: list[tuple[int, int, str]] = []
    fallback: list[str] = []
    seen: set[str] = set()

    for item in payload.values():
        text = item.get("text") if isinstance(item, dict) else None
        if not isinstance(text, str):
            continue

        normalized = " ".join(text.split())
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        fallback.append(normalized)

        lower = normalized.lower()
        score = sum(1 for token in signals if token in lower)
        if score > 0:
            candidates.append((score, len(normalized), normalized))

    if candidates:
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [item[2][:5000] for item in candidates[:limit]]

    return [text[:5000] for text in fallback[:limit]]


def _load_readme_checkpoint_config(workspace_root: Path) -> dict[str, Any]:
    config_path = workspace_root / "configs" / "run-pipeline.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing README pipeline config: {config_path}")

    import yaml

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise ValueError(f"Unexpected config format in {config_path}")

    config = dict(config)
    config.setdefault("matcher_config", {})
    config["matcher_config"]["use_matcher"] = False
    config.setdefault("builder_config", {})
    config["builder_config"]["save_folder"] = str(workspace_root / "outputs" / "builder")
    return config


def create_fresh_readme_checkpoint(root: Path) -> Path:
    """Create a new checkpoint directory by running only SkeletonReconstructor."""

    workspace_root = _workspace_root(root)

    from finmy.summarizer.summarizer import SummarizedUserQuery
    from finmy.pipeline import FinmyPipeline

    config = _load_readme_checkpoint_config(workspace_root)
    pipeline = FinmyPipeline(config)

    contents = _load_readme_contents(workspace_root)
    if not contents:
        raise ValueError(f"No benchmark contents found under {workspace_root / 'cache'}")

    user_query = pipeline.create_and_store_user_query(
        BENCHMARK_QUERY_TEXT,
        BENCHMARK_KEY_WORDS,
    )
    raw_data_records = pipeline.create_raw_data_records(contents)
    summarized_query = SummarizedUserQuery(
        summarization=BENCHMARK_QUERY_TEXT,
        key_words=list(BENCHMARK_KEY_WORDS),
    )
    meta_samples = pipeline._process_matching(raw_data_records, summarized_query)
    pipeline.store_meta_samples(meta_samples)
    build_input = pipeline.create_build_input(
        user_query,
        meta_samples,
        attach_context_assets=True,
    )

    builder = pipeline.builder
    if builder is None:
        raise RuntimeError("Pipeline did not initialize a builder")

    agent_system_msgs, agent_user_msgs = builder._get_agent_prompts()
    state: dict[str, Any] = {
        "build_input": build_input,
        "agent_results": [],
        "agent_executed": [],
        "cost": [],
        "agent_system_msgs": agent_system_msgs,
        "agent_user_msgs": agent_user_msgs,
        "skeleton_retry_count": 0,
        "skeleton_validation_reason": "",
    }

    state = builder.execute_agent(state, "SkeletonReconstructor")
    final_cascade = builder.integrate_results(state)
    builder.save_traces(final_cascade, save_name="FinalEventCascade", file_format="json")
    restored_cascade = builder.integrate_from_files()
    builder.save_traces(
        restored_cascade,
        save_name="IntegratedEventCascade",
        file_format="json",
    )
    return Path(builder.save_dir)


def summarize_latest_builder_output(root: Path) -> dict[str, object]:
    """Summarize the newest `build_output_*` directory under `root`."""

    latest_dir = _latest_valid_build_output_dir(root)
    summary: dict[str, object] = {
        "root": str(root),
        "builder_output_count": 0,
        "latest_builder_dir": None,
        "skeleton": {"path": None, "stage_count": None, "episode_count": None},
        "final": {"path": None, "stage_count": None, "episode_count": None},
    }

    if latest_dir is None:
        return summary

    summary["builder_output_count"] = len(_build_output_dirs(root))
    summary["latest_builder_dir"] = str(latest_dir)
    checkpoint_summary = _summarize_checkpoint_dir(latest_dir)
    summary["skeleton"] = checkpoint_summary["skeleton"]
    summary["final"] = checkpoint_summary["final"]
    return summary


def replay_latest_readme_checkpoint(
    root: Path,
    checkpoint_creator: Callable[[Path], Path] | None = None,
) -> dict[str, object]:
    """Create a fresh README checkpoint and return its summary."""

    creator = checkpoint_creator or create_fresh_readme_checkpoint
    checkpoint_dir = creator(root)
    if checkpoint_dir is None:
        raise RuntimeError("Checkpoint creator did not return a directory")

    return {
        "checkpoint_dir": str(checkpoint_dir),
        "summary": _summarize_checkpoint_dir(checkpoint_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a fresh README checkpoint and summarize the result."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root directory that contains build_output_* folders.",
    )
    args = parser.parse_args()
    checkpoint = replay_latest_readme_checkpoint(args.root)
    print(json.dumps(checkpoint, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
