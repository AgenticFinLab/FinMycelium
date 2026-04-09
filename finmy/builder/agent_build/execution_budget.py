"""Stage-aware execution budget planning for sparse-RAG routing.

The planner is intentionally small and deterministic. It uses only local signals
from the build input, stage names, episode names, and passive evidence assets to
assign conservative execution tiers.
"""

from __future__ import annotations

from typing import Any

__all__ = ["_complexity_bucket", "build_stage_aware_execution_budget"]


_TIMELINE_HINTS = {
    "date",
    "dates",
    "timeline",
    "chronology",
    "chronological",
    "sequence",
    "order",
    "legal",
    "court",
    "hearing",
    "trial",
    "filing",
    "appeal",
    "review",
}

_CONFLICT_HINTS = {
    "conflict",
    "conflicting",
    "overlap",
    "overlapping",
    "ambiguous",
    "inconsistent",
    "contradictory",
    "dispute",
    "source overlap",
    "multiple accounts",
}


def _complexity_bucket(score: int) -> str:
    if score <= 1:
        return "low"
    if score == 2:
        return "medium"
    return "high"


def _scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("value", "text", "name", "title"):
            if key in value:
                return _scalar_text(value[key])
        return " ".join(_scalar_text(item) for item in value.values()).strip()
    if isinstance(value, (list, tuple, set)):
        return " ".join(_scalar_text(item) for item in value).strip()
    return str(value)


def _lower_text(value: Any) -> str:
    return _scalar_text(value).lower()


def _get_bundle(build_input: Any):
    return getattr(build_input, "context_assets", None)


def _get_cards(build_input: Any) -> list[Any]:
    bundle = _get_bundle(build_input)
    if bundle is None:
        return []
    return list(getattr(bundle, "evidence_cards", []) or [])


def _query_text(build_input: Any) -> str:
    user_query = getattr(build_input, "user_query", None)
    if user_query is None:
        return ""
    query_text = _scalar_text(getattr(user_query, "query_text", ""))
    keywords = " ".join(getattr(user_query, "key_words", []) or [])
    return f"{query_text} {keywords}".strip()


def _build_context_text(build_input: Any) -> str:
    parts: list[str] = [_query_text(build_input)]
    samples = getattr(build_input, "samples", []) or []
    parts.extend(_scalar_text(getattr(sample, "content", "")) for sample in samples)
    for card in _get_cards(build_input):
        parts.append(_scalar_text(getattr(card, "title", "")))
        parts.append(_scalar_text(getattr(card, "excerpt", "")))
    return " ".join(part for part in parts if part).lower()


def _has_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _stage_signal_score(build_input: Any, stage: dict[str, Any]) -> int:
    episode_text = " ".join(_lower_text(episode.get("name")) for episode in stage.get("episodes", []) or [])
    card_text = " ".join(
        part
        for card in _get_cards(build_input)
        for part in (
            _lower_text(getattr(card, "title", "")),
            _lower_text(getattr(card, "excerpt", "")),
            " ".join(getattr(card, "quality_flags", []) or []),
        )
        if part
    )
    stage_text = f"{_lower_text(stage.get('name'))} {episode_text} {card_text}".strip()
    score = 0
    if _has_any(stage_text, _TIMELINE_HINTS):
        score += 2
    if _has_any(stage_text, _CONFLICT_HINTS):
        score += 2
    if "legal" in stage_text and "timeline" in stage_text:
        score += 1
    if len(stage.get("episodes", []) or []) > 1:
        score += 1
    if any(
        "source_overlap" in (getattr(card, "quality_flags", []) or [])
        or "conflict_heavy" in (getattr(card, "quality_flags", []) or [])
        for card in _get_cards(build_input)
    ):
        score += 1
    return score


def _episode_signal_score(build_input: Any, stage: dict[str, Any], episode: dict[str, Any]) -> int:
    episode_text = " ".join(
        [
            _lower_text(stage.get("name")),
            _lower_text(episode.get("name")),
            " ".join(
                part
                for card in _get_cards(build_input)
                for part in (
                    _lower_text(getattr(card, "title", "")),
                    _lower_text(getattr(card, "excerpt", "")),
                    " ".join(getattr(card, "quality_flags", []) or []),
                )
                if part
            ),
        ]
    )
    score = 0
    if _has_any(episode_text, _TIMELINE_HINTS):
        score += 1
    if _has_any(episode_text, _CONFLICT_HINTS):
        score += 2
    if "legal" in episode_text and "timeline" in episode_text:
        score += 1
    if any(hint in episode_text for hint in ("court hearing", "timeline review", "legal proceedings")):
        score += 1
    if any(
        "source_overlap" in (getattr(card, "quality_flags", []) or [])
        or "conflict_heavy" in (getattr(card, "quality_flags", []) or [])
        for card in _get_cards(build_input)
    ):
        score += 1
    return score


def _participant_tier(score: int, conflict_guard: str) -> str:
    if conflict_guard == "strict":
        return "compact" if score <= 2 else "standard"
    if score <= 1:
        return "minimal"
    if score <= 3:
        return "compact"
    return "standard"


def _transaction_tier(score: int, conflict_guard: str) -> str:
    if conflict_guard == "strict":
        return "compact" if score <= 2 else "standard"
    if score <= 1:
        return "minimal"
    if score <= 3:
        return "compact"
    return "standard"


def _episode_detail_tier(stage_bucket: str, episode_score: int) -> str:
    if stage_bucket == "high" or episode_score >= 2:
        return "standard"
    return "compact"


def _conflict_guard(episode_text: str, build_input: Any) -> str:
    if _has_any(episode_text, _CONFLICT_HINTS):
        return "strict"
    for card in _get_cards(build_input):
        flags = set(getattr(card, "quality_flags", []) or [])
        if {"source_overlap", "conflict_heavy", "ambiguous_source"} & flags:
            return "strict"
        if len(getattr(card, "time_hints", []) or []) > 1 and len(getattr(card, "entity_hints", []) or []) > 0:
            return "strict"
    return "standard"


def build_stage_aware_execution_budget(build_input: Any, event_skeleton: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic execution budget for a skeleton.

    Returns a structure with stage summaries and per-episode budgets keyed by
    ``(stage_id, episode_id)``.
    """

    stages: list[dict[str, Any]] = []
    episodes: dict[tuple[str, str], dict[str, Any]] = {}

    for stage in (event_skeleton or {}).get("stages", []) or []:
        stage_id = _scalar_text(stage.get("stage_id")) or ""
        stage_name = _scalar_text(stage.get("name")) or stage_id
        episode_items = list(stage.get("episodes", []) or [])
        stage_score = _stage_signal_score(build_input, stage)
        stage_bucket = _complexity_bucket(stage_score)
        timeline_complexity = "high" if stage_bucket == "high" else stage_bucket

        stages.append(
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "timeline_complexity": timeline_complexity,
                "complexity_score": stage_score,
                "episode_count": len(episode_items),
            }
        )

        for episode in episode_items:
            episode_id = _scalar_text(episode.get("episode_id")) or ""
            episode_name = _scalar_text(episode.get("name")) or episode_id
            episode_score = _episode_signal_score(build_input, stage, episode)
            episode_text = f"{_lower_text(stage.get('name'))} {_lower_text(episode.get('name'))}"
            conflict_guard = _conflict_guard(episode_text, build_input)
            participant_tier = _participant_tier(episode_score, conflict_guard)
            transaction_tier = _transaction_tier(episode_score, conflict_guard)
            episode_detail_tier = _episode_detail_tier(stage_bucket, episode_score)
            mode = "full" if episode_score >= 2 or conflict_guard == "strict" else "light"

            episodes[(stage_id, episode_id)] = {
                "stage_id": stage_id,
                "episode_id": episode_id,
                "episode_name": episode_name,
                "participant_tier": participant_tier,
                "transaction_tier": transaction_tier,
                "episode_detail_tier": episode_detail_tier,
                "conflict_guard": conflict_guard,
                "mode": mode,
            }

    return {"stages": stages, "episodes": episodes}
