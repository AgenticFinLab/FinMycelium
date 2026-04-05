"""Minimal local context retrieval scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from finmy.context.assets import EvidenceAssetBundle, EvidenceCard
from finmy.context.indexing import score_token_overlap, tokenize_text
from finmy.context.renderers import render_evidence_card


@dataclass
class LocalContextRequest:
    """Inputs needed to build a local context package."""

    agent_name: str
    query_text: str = ""
    key_words: List[str] = field(default_factory=list)
    context_assets: EvidenceAssetBundle | None = None


@dataclass
class LocalContextPackage:
    """Minimal retrieval result for a local agent context."""

    scope: str
    retrieval_status: str
    selected_cards: List[EvidenceCard] = field(default_factory=list)
    rendered_context: str = ""
    summary: dict[str, int] = field(default_factory=dict)


class LocalContextBuilder:
    """Build a local context package from passive evidence assets."""

    def build(self, request: LocalContextRequest) -> LocalContextPackage:
        bundle = request.context_assets or EvidenceAssetBundle.empty()
        query_tokens = tokenize_text(
            f"{request.query_text or ''} {' '.join(request.key_words or [])}".strip()
        )

        selected_cards = [
            card
            for card in bundle.evidence_cards
            if score_token_overlap(card.tokens, query_tokens) > 0
        ]

        if bundle.retrieval_policy.max_cards is not None:
            selected_cards = selected_cards[: bundle.retrieval_policy.max_cards]

        retrieval_status = "sufficient" if selected_cards else "fallback_fulltext"
        rendered_context = "\n\n".join(render_evidence_card(card) for card in selected_cards)

        return LocalContextPackage(
            scope=self._derive_scope(request.agent_name),
            retrieval_status=retrieval_status,
            selected_cards=selected_cards,
            rendered_context=rendered_context,
            summary={"selected_count": len(selected_cards)},
        )

    def _derive_scope(self, agent_name: str) -> str:
        scope = (agent_name or "").strip()
        return scope or "default"
