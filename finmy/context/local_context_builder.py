"""Minimal local context retrieval scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
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
    context_assets: EvidenceAssetBundle | None = None


@dataclass
class LocalContextPackage:
    """Minimal retrieval result for a local agent context."""

    scope: str
    retrieval_status: str
    selected_sample_ids: List[str] = field(default_factory=list)
    rendered_context: str = ""
    summary: dict[str, int] = field(default_factory=dict)
    query_bundle: dict[str, object] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)
    budget_summary: dict[str, int] = field(default_factory=dict)


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
    _GLOBAL_PHASE_BUCKET_TERMS = {
        "early": {
            "blue",
            "fraud",
            "ponzi",
            "scheme",
            "sky",
            "2014",
            "2015",
        },
        "middle": {
            "bitcoin",
            "launder",
            "laundering",
            "myanmar",
            "2018",
            "2019",
        },
        "late": {
            "court",
            "trial",
            "sentenced",
            "jailed",
            "2024",
            "2025",
        },
    }
    _GLOBAL_NOISE_PREFIXES = (
        "skip to main content",
        "search for careers contact about us",
        "cnn values your feedback",
        "video player was slow to load",
    )
    _GLOBAL_AD_FEEDBACK_NOISE_PATTERN = re.compile(
        r"^ad feedback(?:\s*->\s*|[\s\.,:;!?]+)+"
        r"(?:cnn values your feedback|video player was slow to load|cnn analysis)\b"
    )
    _GLOBAL_MIN_INFORMATION_BODY_TOKENS = 4

    def build(
        self,
        request: LocalContextRequest,
        bundle: EvidenceAssetBundle | None = None,
    ) -> LocalContextPackage:
        bundle = bundle or request.context_assets or EvidenceAssetBundle.empty()
        query_tokens = tokenize_text(
            f"{request.query_text or ''} {' '.join(request.key_words or [])}".strip()
        )
        scope = self._derive_scope(request)
        query_bundle = self.build_query_bundle(request)

        selected_cards = self._select_cards(bundle, query_tokens, scope)
        if scope == "global" and self._assess_global_status(selected_cards) != "sufficient":
            selected_cards = []
        selected_sample_ids = [card.sample_id for card in selected_cards]

        retrieval_status = "sufficient" if selected_sample_ids else "fallback_fulltext"
        rendered_context = "\n\n".join(render_evidence_card(card) for card in selected_cards)

        return LocalContextPackage(
            scope=scope,
            retrieval_status=retrieval_status,
            selected_sample_ids=selected_sample_ids,
            rendered_context=rendered_context,
            summary={"selected_count": len(selected_sample_ids)},
            query_bundle=query_bundle,
            memory=self._build_memory(selected_cards, bundle),
            budget_summary=self._build_budget_summary(selected_cards, bundle),
        )

    def build_query_bundle(self, request: LocalContextRequest) -> dict[str, object]:
        scope = self._derive_scope(request)
        query_bundle: dict[str, object] = {
            "scope": scope,
            "agent_name": request.agent_name,
            "query_text": request.query_text,
            "keyword_hints": self._collect_keyword_hints(request),
        }

        if scope == "global":
            query_bundle["global_phase_hints"] = self._collect_global_phase_hints(request)
            return query_bundle

        if request.target_stage:
            query_bundle["stage_name"] = request.target_stage

        if scope == "stage":
            query_bundle["stage_hints"] = self._collect_stage_hints(request)
            return query_bundle

        query_bundle["episode_name"] = request.target_episode
        query_bundle["entity_hints"] = self._collect_episode_entity_hints(request)
        query_bundle["action_hints"] = self._collect_episode_action_hints(request)
        query_bundle["time_hints"] = self._collect_episode_time_hints(request)
        return query_bundle

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

    def _assess_global_status(self, selected_cards: List[EvidenceCard]) -> str:
        if not selected_cards:
            return "fallback_fulltext"

        phase_hits = set()
        for card in selected_cards:
            phase_hits.update(self._extract_global_phase_hits(card.tokens))

        if phase_hits == {"late"}:
            return "fallback_fulltext"
        return "sufficient"

    def _extract_global_case_signal_tokens(self, tokens: List[str]) -> List[str]:
        return [token for token in tokens if token in self._GLOBAL_CASE_SIGNAL_TOKENS]

    def _extract_global_phase_hits(self, tokens: List[str]) -> List[str]:
        token_set = {token for token in tokens if token}
        hits = []
        for phase_name, phase_terms in self._GLOBAL_PHASE_BUCKET_TERMS.items():
            if token_set.intersection(phase_terms):
                hits.append(phase_name)
        return hits

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
        excerpt = (card.excerpt or "").strip().lower()
        if not excerpt:
            return True

        body_excerpt = self._strip_global_noise_prefix(excerpt)
        if body_excerpt == excerpt:
            return False

        body_tokens = tokenize_text(body_excerpt)
        if not body_tokens:
            return True

        body_content_tokens = [
            token
            for token in body_tokens
            if token not in self._GLOBAL_LOW_SIGNAL_TOKENS
            and token not in self._GLOBAL_TEMPLATE_TOKENS
        ]
        has_case_signal = bool(self._extract_global_case_signal_tokens(body_content_tokens))
        if has_case_signal:
            return False

        has_information_signal = (
            len(self._extract_global_high_information_tokens(body_content_tokens))
            >= self._GLOBAL_MIN_INFORMATION_BODY_TOKENS
        )
        return not has_information_signal

    def _strip_global_noise_prefix(self, excerpt: str) -> str:
        for prefix in sorted(self._GLOBAL_NOISE_PREFIXES, key=len, reverse=True):
            if excerpt.startswith(prefix):
                return excerpt[len(prefix) :].lstrip(" \t\r\n-:;,.!?")
        ad_feedback_match = self._GLOBAL_AD_FEEDBACK_NOISE_PATTERN.match(excerpt)
        if ad_feedback_match:
            return excerpt[ad_feedback_match.end() :].lstrip(" \t\r\n-:;,.!?")
        return excerpt

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

    def _collect_keyword_hints(self, request: LocalContextRequest) -> List[str]:
        return self._dedupe_tokens(
            [
                *tokenize_text(" ".join(request.key_words or [])),
                *tokenize_text(request.query_text),
            ]
        )

    def _collect_global_phase_hints(self, request: LocalContextRequest) -> List[str]:
        query_tokens = self._collect_keyword_hints(request)
        phase_hints = []
        for phase_name, phase_terms in self._GLOBAL_PHASE_BUCKET_TERMS.items():
            if set(query_tokens) & phase_terms:
                phase_hints.append(phase_name)
        return phase_hints or ["early", "middle"]

    def _collect_stage_hints(self, request: LocalContextRequest) -> List[str]:
        return self._dedupe_tokens(
            [
                *tokenize_text(request.target_stage),
                *self._collect_keyword_hints(request),
            ]
        )

    def _collect_episode_entity_hints(self, request: LocalContextRequest) -> List[str]:
        return self._take_non_empty(
            [
                request.target_episode,
                request.target_stage,
                *request.key_words,
            ]
        )

    def _collect_episode_action_hints(self, request: LocalContextRequest) -> List[str]:
        action_hints = [
            token
            for token in self._collect_keyword_hints(request)
            if token not in self._GLOBAL_LOW_SIGNAL_TOKENS and len(token) >= 4
        ]
        return action_hints[:4] or ["reconstruct"]

    def _collect_episode_time_hints(self, request: LocalContextRequest) -> List[str]:
        time_hints = [
            token for token in tokenize_text(request.query_text) if token.isdigit() and len(token) == 4
        ]
        return self._dedupe_tokens(time_hints) or ["timeline"]

    def _build_memory(
        self,
        selected_cards: List[EvidenceCard],
        bundle: EvidenceAssetBundle,
    ) -> dict[str, object]:
        selected_sample_ids = [card.sample_id for card in selected_cards]
        selected_signal_counts = {
            "time_hints": sum(len(card.time_hints) for card in selected_cards),
            "entity_hints": sum(len(card.entity_hints) for card in selected_cards),
            "action_hints": sum(len(card.action_hints) for card in selected_cards),
            "money_hints": sum(len(card.money_hints) for card in selected_cards),
            "quality_flags": sum(len(card.quality_flags) for card in selected_cards),
        }
        return {
            "selected_sample_ids": selected_sample_ids,
            "selected_signal_counts": selected_signal_counts,
            "available_card_count": len(bundle.evidence_cards),
        }

    def _build_budget_summary(
        self,
        selected_cards: List[EvidenceCard],
        bundle: EvidenceAssetBundle,
    ) -> dict[str, int]:
        max_cards = bundle.retrieval_policy.max_cards
        return {
            "used_card_count": len(selected_cards),
            "available_card_count": len(bundle.evidence_cards),
            "remaining_card_budget": max((max_cards or len(bundle.evidence_cards)) - len(selected_cards), 0),
        }

    def _dedupe_tokens(self, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value))

    def _take_non_empty(self, values: List[str]) -> List[str]:
        return [value for value in dict.fromkeys(values) if value]
