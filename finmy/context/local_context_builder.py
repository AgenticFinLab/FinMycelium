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
    target_stage: str = ""
    target_episode: str = ""


@dataclass
class LocalContextPackage:
    """Minimal retrieval result for a local agent context."""

    scope: str
    retrieval_status: str
    selected_sample_ids: List[str] = field(default_factory=list)
    rendered_context: str = ""
    summary: dict[str, int] = field(default_factory=dict)


class LocalContextBuilder:
    """Build a local context package from passive evidence assets."""

    _SCOPE_BY_AGENT_NAME = {
        "episodereconstructor": "episode",
        "stagedescriptionreconstructor": "stage",
        "eventdescriptionreconstructor": "global",
    }
    _GLOBAL_LOW_SIGNAL_TOKENS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "not",
        "of",
        "on",
        "or",
        "our",
        "should",
        "that",
        "the",
        "their",
        "them",
        "these",
        "this",
        "those",
        "to",
        "us",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
    _GLOBAL_TEMPLATE_TOKENS = {
        "about",
        "article",
        "back",
        "careers",
        "contact",
        "content",
        "edition",
        "headlines",
        "home",
        "international",
        "latest",
        "main",
        "menu",
        "newsletters",
        "page",
        "related",
        "search",
        "site",
        "stories",
        "skip",
        "sign",
        "up",
        "us",
    }
    _GLOBAL_CASE_SIGNAL_TOKENS = {
        "blue",
        "fraud",
        "evidence",
        "launder",
        "laundering",
        "money",
        "ponzi",
        "proceeds",
        "qian",
        "reconciliation",
        "scheme",
        "sky",
        "zhimin",
        "bitcoin",
    }
    _GLOBAL_NOISE_PHRASES = (
        "skip to main content",
        "ad feedback",
        "search for careers contact about us",
        "cnn values your feedback",
        "video player was slow to load",
    )

    def build(
        self,
        request: LocalContextRequest,
        bundle: EvidenceAssetBundle,
    ) -> LocalContextPackage:
        query_tokens = tokenize_text(
            f"{request.query_text or ''} {' '.join(request.key_words or [])}".strip()
        )
        scope = self._derive_scope(request)

        selected_cards = self._select_cards(bundle, query_tokens, scope)
        selected_sample_ids = [card.sample_id for card in selected_cards]

        retrieval_status = "sufficient" if selected_sample_ids else "fallback_fulltext"
        rendered_context = "\n\n".join(render_evidence_card(card) for card in selected_cards)

        return LocalContextPackage(
            scope=scope,
            retrieval_status=retrieval_status,
            selected_sample_ids=selected_sample_ids,
            rendered_context=rendered_context,
            summary={"selected_count": len(selected_sample_ids)},
        )

    def _select_cards(
        self,
        bundle: EvidenceAssetBundle,
        query_tokens: List[str],
        scope: str,
    ) -> List[EvidenceCard]:
        if scope == "global":
            return self._select_global_cards(bundle, query_tokens)

        ranked_cards = []
        for index, card in enumerate(bundle.evidence_cards):
            overlap = score_token_overlap(card.tokens, query_tokens)
            if overlap <= 0:
                continue
            ranked_cards.append((overlap, index, card))

        selected_cards = [
            card
            for _, _, card in sorted(ranked_cards, key=lambda item: (-item[0], item[1]))
        ]
        if bundle.retrieval_policy.max_cards is not None:
            selected_cards = selected_cards[: bundle.retrieval_policy.max_cards]
        return selected_cards

    def _select_global_cards(
        self,
        bundle: EvidenceAssetBundle,
        query_tokens: List[str],
    ) -> List[EvidenceCard]:
        query_content_tokens = [
            token for token in query_tokens if token not in self._GLOBAL_LOW_SIGNAL_TOKENS
        ]
        case_signal_tokens = self._extract_global_case_signal_tokens(query_content_tokens)
        query_information_tokens = self._extract_global_high_information_tokens(
            query_content_tokens
        )
        if not case_signal_tokens and not query_information_tokens:
            return []

        ranked_cards = []
        for index, card in enumerate(bundle.evidence_cards):
            if self._is_global_noise_card(card):
                continue

            overlap, match_kind = self._classify_global_card_match(
                card.tokens,
                case_signal_tokens,
                query_information_tokens,
            )
            if overlap <= 0:
                continue
            match_priority = 0 if match_kind == "strong" else 1
            ranked_cards.append((match_priority, -overlap, index, card))

        selected_cards = [
            card
            for _, _, _, card in sorted(ranked_cards, key=lambda item: (item[0], item[1], item[2]))
        ]
        if bundle.retrieval_policy.max_cards is not None:
            selected_cards = selected_cards[: bundle.retrieval_policy.max_cards]
        return selected_cards

    def _extract_global_case_signal_tokens(self, tokens: List[str]) -> List[str]:
        return [token for token in tokens if token in self._GLOBAL_CASE_SIGNAL_TOKENS]

    def _extract_global_high_information_tokens(self, tokens: List[str]) -> List[str]:
        return [
            token
            for token in tokens
            if token not in self._GLOBAL_CASE_SIGNAL_TOKENS
            and token not in self._GLOBAL_LOW_SIGNAL_TOKENS
            and token not in self._GLOBAL_TEMPLATE_TOKENS
            and len(token) >= 7
        ]

    def _classify_global_card_match(
        self,
        card_tokens: List[str],
        case_signal_tokens: List[str],
        query_information_tokens: List[str],
    ) -> tuple[int, str]:
        card_case_tokens = self._extract_global_case_signal_tokens(card_tokens)
        strong_overlap = score_token_overlap(card_case_tokens, case_signal_tokens)
        if strong_overlap > 0:
            return strong_overlap, "strong"

        card_information_tokens = self._extract_global_high_information_tokens(card_tokens)
        backstop_overlap_tokens = set(card_information_tokens) & set(query_information_tokens)
        backstop_overlap = len(backstop_overlap_tokens)
        if backstop_overlap >= 2 and sum(
            1 for token in backstop_overlap_tokens if len(token) >= 8
        ) >= 2:
            return backstop_overlap, "backstop"
        return 0, ""

    def _is_global_noise_card(self, card: EvidenceCard) -> bool:
        haystack = f"{card.title} {card.excerpt}".strip().lower()
        return any(phrase in haystack for phrase in self._GLOBAL_NOISE_PHRASES)

    def _derive_scope(self, request: LocalContextRequest) -> str:
        agent_name = (request.agent_name or "").strip().lower()
        mapped_scope = self._SCOPE_BY_AGENT_NAME.get(agent_name)
        if mapped_scope is not None:
            return mapped_scope
        if request.target_episode:
            return "episode"
        if request.target_stage:
            return "stage"
        return "global"
