"""Stage-aware execution budget planning for sparse_build sparse routing."""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "_complexity_bucket",
    "build_stage_aware_execution_budget",
    "episode_budget_prompt_vars",
    "render_episode_budget_summary",
]

_TIMELINE_HINTS = {
    "date",
    "dates",
    "timeline",
    "chronology",
    "sequence",
    "legal",
    "court",
    "hearing",
    "trial",
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


def _text_tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _lower_text(value)))


def _get_bundle(build_input: Any, context_assets: Any = None) -> Any:
    if context_assets is not None:
        return context_assets
    return getattr(build_input, "context_assets", None)


def _get_cards(build_input: Any, context_assets: Any = None) -> list[Any]:
    bundle = _get_bundle(build_input, context_assets)
    if bundle is None:
        return []
    return list(getattr(bundle, "evidence_cards", []) or [])


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


def _relevant_cards(build_input: Any, local_text: str, context_assets: Any = None) -> list[Any]:
    local_tokens = _text_tokens(local_text)
    if not local_tokens:
        return []
    relevant: list[Any] = []
    for card in _get_cards(build_input, context_assets):
        if local_tokens & _text_tokens(_card_text(card)):
            relevant.append(card)
    return relevant


def _has_any(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _stage_signal_score(
    build_input: Any,
    stage: dict[str, Any],
    context_assets: Any = None,
) -> int:
    episode_text = " ".join(
        _lower_text(episode.get("name")) for episode in stage.get("episodes", []) or []
    )
    local_text = f"{_lower_text(stage.get('name'))} {episode_text}".strip()
    relevant_cards = _relevant_cards(build_input, local_text, context_assets)
    card_text = " ".join(_card_text(card) for card in relevant_cards)
    stage_text = f"{local_text} {card_text}".strip()
    score = 0
    if _has_any(stage_text, _TIMELINE_HINTS):
        score += 2
    if _has_any(stage_text, _CONFLICT_HINTS):
        score += 2
    if len(stage.get("episodes", []) or []) > 1:
        score += 1
    if any("money_dense" in (getattr(card, "quality_flags", []) or []) for card in relevant_cards):
        score += 3
    if any(
        {"source_overlap", "conflict_heavy", "ambiguous_source"}
        & set(getattr(card, "quality_flags", []) or [])
        for card in relevant_cards
    ):
        score += 1
    return score


def _episode_signal_score(
    build_input: Any,
    stage: dict[str, Any],
    episode: dict[str, Any],
    context_assets: Any = None,
) -> int:
    local_text = f"{_lower_text(stage.get('name'))} {_lower_text(episode.get('name'))}"
    relevant_cards = _relevant_cards(build_input, local_text, context_assets)
    card_text = " ".join(_card_text(card) for card in relevant_cards)
    episode_text = f"{local_text} {card_text}".strip()
    score = 0
    if _has_any(episode_text, _TIMELINE_HINTS):
        score += 1
    if _has_any(episode_text, _CONFLICT_HINTS):
        score += 2
    if any("money_dense" in (getattr(card, "quality_flags", []) or []) for card in relevant_cards):
        score += 3
    if any(getattr(card, "money_hints", []) for card in relevant_cards):
        score += 1
    if any(
        {"source_overlap", "conflict_heavy", "ambiguous_source"}
        & set(getattr(card, "quality_flags", []) or [])
        for card in relevant_cards
    ):
        score += 1
    return score


def _conflict_guard(
    build_input: Any,
    episode_text: str,
    context_assets: Any = None,
) -> str:
    relevant_cards = _relevant_cards(build_input, episode_text, context_assets)
    hits = 0
    for card in relevant_cards:
        flags = set(getattr(card, "quality_flags", []) or [])
        if {"source_overlap", "conflict_heavy", "ambiguous_source"} & flags:
            hits += 1
    return "strict" if hits >= 2 else "standard"


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


def _episode_detail_tier(stage_bucket: str, conflict_guard: str) -> str:
    if conflict_guard == "strict" or stage_bucket == "high":
        return "standard"
    return "compact"


def _compactness_hint(mode: str, transaction_tier: str, episode_detail_tier: str) -> str:
    if mode == "full":
        return "Use complete participant and transaction detail grounded in primary content."
    if transaction_tier == "minimal" and episode_detail_tier == "compact":
        return "Keep reconstruction compact; include only directly supported essentials."
    return "Use compact detail and avoid unsupported elaboration."


def build_stage_aware_execution_budget(
    build_input: Any,
    event_skeleton: dict[str, Any],
    context_assets: Any = None,
) -> dict[str, Any]:
    """Build a deterministic execution budget for a skeleton."""

    stages: list[dict[str, Any]] = []
    episodes: dict[tuple[str, str], dict[str, Any]] = {}

    for stage in (event_skeleton or {}).get("stages", []) or []:
        stage_id = _scalar_text(stage.get("stage_id")) or ""
        stage_name = _scalar_text(stage.get("name")) or stage_id
        episode_items = list(stage.get("episodes", []) or [])
        stage_score = _stage_signal_score(build_input, stage, context_assets)
        stage_bucket = _complexity_bucket(stage_score)
        stages.append(
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "timeline_complexity": "high" if stage_bucket == "high" else stage_bucket,
                "complexity_score": stage_score,
                "episode_count": len(episode_items),
            }
        )

        for episode in episode_items:
            episode_id = _scalar_text(episode.get("episode_id")) or ""
            episode_name = _scalar_text(episode.get("name")) or episode_id
            episode_score = _episode_signal_score(
                build_input, stage, episode, context_assets
            )
            episode_text = f"{_lower_text(stage.get('name'))} {_lower_text(episode.get('name'))}"
            conflict_guard = _conflict_guard(build_input, episode_text, context_assets)
            participant_tier = _participant_tier(episode_score, conflict_guard)
            transaction_tier = _transaction_tier(episode_score, conflict_guard)
            episode_detail_tier = _episode_detail_tier(stage_bucket, conflict_guard)
            mode = "light"
            if conflict_guard == "strict":
                mode = "full"
            elif stage_bucket == "high" and episode_score >= 2:
                mode = "full"
            elif episode_score >= 3:
                mode = "full"
            episodes[(stage_id, episode_id)] = {
                "stage_id": stage_id,
                "episode_id": episode_id,
                "episode_name": episode_name,
                "participant_tier": participant_tier,
                "transaction_tier": transaction_tier,
                "episode_detail_tier": episode_detail_tier,
                "conflict_guard": conflict_guard,
                "mode": mode,
                "compactness_hint": _compactness_hint(
                    mode, transaction_tier, episode_detail_tier
                ),
            }

    return {"stages": stages, "episodes": episodes}


def episode_budget_prompt_vars(episode_budget: dict[str, Any] | None) -> dict[str, str]:
    """Map an episode budget entry into explicit prompt variable names."""

    budget = episode_budget or {}
    return {
        "EpisodeExecutionMode": _scalar_text(budget.get("mode")) or "light",
        "TransactionDetailTier": _scalar_text(budget.get("transaction_tier")) or "minimal",
        "EpisodeDetailTier": _scalar_text(budget.get("episode_detail_tier")) or "compact",
        "ConflictGuard": _scalar_text(budget.get("conflict_guard")) or "standard",
        "EpisodeCompactnessHint": _scalar_text(budget.get("compactness_hint"))
        or "Keep reconstruction compact; include only directly supported essentials.",
    }


def render_episode_budget_summary(episode_budget: dict[str, Any] | None) -> str:
    prompt_vars = episode_budget_prompt_vars(episode_budget)
    return "\n".join(
        [
            "episode_execution_budget:",
            f"  mode={prompt_vars['EpisodeExecutionMode']}",
            f"  transaction_tier={prompt_vars['TransactionDetailTier']}",
            f"  episode_detail_tier={prompt_vars['EpisodeDetailTier']}",
            f"  conflict_guard={prompt_vars['ConflictGuard']}",
            f"  compactness_hint={prompt_vars['EpisodeCompactnessHint']}",
        ]
    )
