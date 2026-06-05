"""Render helpers for sparse_build passive evidence assets."""

from __future__ import annotations

from typing import Mapping

from .context_assets import EvidenceAssetBundle, EvidenceCard, EvidenceRetrievalPolicy


def render_retrieval_policy(policy: EvidenceRetrievalPolicy) -> str:
    return (
        f"max_cards={policy.max_cards}, "
        f"excerpt_char_limit={policy.excerpt_char_limit}, "
        f"max_card_tokens={policy.max_card_tokens}"
    )


def render_evidence_card(card: EvidenceCard) -> str:
    lines = [
        f"sample_id: {card.sample_id}",
        f"title: {card.title}",
        f"excerpt: {card.excerpt}",
        f"tokens: {', '.join(card.tokens)}",
    ]
    optional_fields = [
        ("time_hints", card.time_hints),
        ("entity_hints", card.entity_hints),
        ("action_hints", card.action_hints),
        ("money_hints", card.money_hints),
        ("quality_flags", card.quality_flags),
    ]
    for label, values in optional_fields:
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    return "\n".join(lines)


def render_context_asset_summary(summary: Mapping[str, int]) -> str:
    ordered_keys = [
        "evidence_card_count",
        "sample_id_count",
        "global_token_count",
        "query_token_count",
        "signal_card_count",
        "time_hint_count",
        "entity_hint_count",
        "action_hint_count",
        "money_hint_count",
    ]
    lines = ["context_asset_summary:"]
    lines.extend(f"  {key}={summary.get(key, 0)}" for key in ordered_keys)
    return "\n".join(lines)


def render_evidence_asset_bundle(bundle: EvidenceAssetBundle) -> str:
    lines = [
        "retrieval_policy:",
        render_retrieval_policy(bundle.retrieval_policy),
        "cards:",
    ]
    lines.extend(render_evidence_card(card) for card in bundle.evidence_cards)
    return "\n".join(lines)


def render_context_asset_bundle(bundle: EvidenceAssetBundle) -> str:
    return "\n".join(["context_asset_bundle:", render_evidence_asset_bundle(bundle)])
