"""Passive render helpers for evidence assets."""

from __future__ import annotations

from typing import List

from finmy.context.assets import EvidenceAssetBundle, EvidenceCard, EvidenceIndex, EvidenceRetrievalPolicy


def render_retrieval_policy(policy: EvidenceRetrievalPolicy) -> str:
    return (
        f"max_cards={policy.max_cards}, "
        f"excerpt_char_limit={policy.excerpt_char_limit}, "
        f"max_card_tokens={policy.max_card_tokens}"
    )


def render_evidence_card(card: EvidenceCard) -> str:
    return "\n".join(
        [
            f"sample_id: {card.sample_id}",
            f"title: {card.title}",
            f"excerpt: {card.excerpt}",
            f"tokens: {', '.join(card.tokens)}",
        ]
    )


def render_evidence_index(index: EvidenceIndex, top_n: int = 10) -> str:
    ranked_tokens = sorted(index.token_counts.items(), key=lambda item: (-item[1], item[0]))
    lines = [f"{token}: {count}" for token, count in ranked_tokens[:top_n]]
    return "\n".join(lines)


def render_evidence_asset_bundle(bundle: EvidenceAssetBundle) -> str:
    sections: List[str] = [
        "retrieval_policy:",
        render_retrieval_policy(bundle.retrieval_policy),
        "index:",
        render_evidence_index(bundle.index),
        "cards:",
    ]
    sections.extend(render_evidence_card(card) for card in bundle.evidence_cards)
    return "\n".join(sections)


def render_evidence_bundle(bundle: EvidenceAssetBundle) -> str:
    """Alias for rendering a bundle of passive evidence assets."""

    return render_evidence_asset_bundle(bundle)
