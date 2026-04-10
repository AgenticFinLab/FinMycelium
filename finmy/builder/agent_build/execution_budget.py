"""Stage-aware execution budget planning for sparse-RAG routing.

The planner is intentionally small and deterministic. It uses only local signals
from the build input, stage names, episode names, and passive evidence assets to
assign conservative execution tiers.
"""

from __future__ import annotations

import re
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


def _has_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _text_tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _lower_text(value)))


def _card_text(card: Any) -> str:
    parts = [
        _lower_text(getattr(card, "title", "")),
        _lower_text(getattr(card, "excerpt", "")),
        " ".join(getattr(card, "time_hints", []) or []),
        " ".join(getattr(card, "entity_hints", []) or []),
        " ".join(getattr(card, "action_hints", []) or []),
        " ".join(getattr(card, "money_hints", []) or []),
        " ".join(getattr(card, "quality_flags", []) or []),
    ]
    return " ".join(part for part in parts if part).strip()


def _relevant_cards(build_input: Any, local_text: str) -> list[Any]:
    local_tokens = _text_tokens(local_text)
    if not local_tokens:
        return []

    relevant: list[Any] = []
    for card in _get_cards(build_input):
        card_text = _card_text(card)
        if local_tokens & _text_tokens(card_text):
            relevant.append(card)
    return relevant


def _stage_signal_score(build_input: Any, stage: dict[str, Any]) -> int:
    episode_text = " ".join(_lower_text(episode.get("name")) for episode in stage.get("episodes", []) or [])
    stage_text = f"{_lower_text(stage.get('name'))} {episode_text}".strip()
    relevant_cards = _relevant_cards(build_input, stage_text)
    card_text = " ".join(_card_text(card) for card in relevant_cards)
    stage_text = f"{stage_text} {card_text}".strip()
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
        for card in relevant_cards
    ):
        score += 1
    if any("money_dense" in (getattr(card, "quality_flags", []) or []) for card in relevant_cards):
        score += 2
    return score


def _episode_signal_score(build_input: Any, stage: dict[str, Any], episode: dict[str, Any]) -> int:
    episode_text = f"{_lower_text(stage.get('name'))} {_lower_text(episode.get('name'))}".strip()
    relevant_cards = _relevant_cards(build_input, episode_text)
    card_text = " ".join(_card_text(card) for card in relevant_cards)
    episode_text = f"{episode_text} {card_text}".strip()
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
        for card in relevant_cards
    ):
        score += 1
    if any("money_dense" in (getattr(card, "quality_flags", []) or []) for card in relevant_cards):
        score += 2
    return score


def _episode_detail_signal_score(stage: dict[str, Any], episode: dict[str, Any]) -> int:
    episode_text = f"{_lower_text(stage.get('name'))} {_lower_text(episode.get('name'))}".strip()
    score = 0
    if _has_any(episode_text, _TIMELINE_HINTS):
        score += 1
    if _has_any(episode_text, _CONFLICT_HINTS):
        score += 2
    if "legal" in episode_text and "timeline" in episode_text:
        score += 1
    if any(hint in episode_text for hint in ("court hearing", "timeline review", "legal proceedings")):
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


def _episode_detail_tier(stage_bucket: str, episode_score: int, conflict_guard: str) -> str:
    if conflict_guard == "strict":
        return "standard"
    if stage_bucket == "high":
        return "standard"
    if episode_score >= 3:
        return "standard"
    return "compact"


def _conflict_guard(episode_text: str, build_input: Any) -> str:
    relevant_cards = _relevant_cards(build_input, episode_text)
    conflict_signal_hits = 0
    for card in relevant_cards:
        flags = set(getattr(card, "quality_flags", []) or [])
        if {"source_overlap", "conflict_heavy", "ambiguous_source"} & flags:
            conflict_signal_hits += 1
    if conflict_signal_hits >= 2:
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
            episode_detail_score = _episode_detail_signal_score(stage, episode)
            episode_detail_tier = _episode_detail_tier(stage_bucket, episode_detail_score, conflict_guard)
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
