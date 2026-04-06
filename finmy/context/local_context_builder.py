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
    budget_summary: dict[str, object] = field(default_factory=dict)


class LocalContextBuilder:
    """Build a local context package from passive evidence assets."""

    _SCOPE_BY_AGENT_NAME = {
        "episodereconstructor": "episode",
        "stagedescriptionreconstructor": "stage",
        "eventdescriptionreconstructor": "global",
    }
    _TARGET_CARD_BUDGET_BY_AGENT_NAME = {
        "participantreconstructor": 1,
        "transactionreconstructor": 1,
        "episodereconstructor": 1,
        "stagedescriptionreconstructor": 2,
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
    _EPISODE_ACTION_TOKENS = {
        "arrest",
        "buy",
        "charge",
        "convert",
        "flee",
        "investigate",
        "launder",
        "laundering",
        "plead",
        "reconcile",
        "seize",
        "sell",
        "trace",
        "transfer",
        "unfold",
    }
    _TRANSACTION_MONEY_TOKENS = {
        "bitcoin",
        "btc",
        "cash",
        "crypto",
        "cryptocurrency",
        "funds",
        "money",
        "payment",
        "payments",
        "proceeds",
        "settlement",
        "wire",
        "wires",
    }
    _TARGET_CARD_BUDGET_BY_SCOPE = {
        "global": 3,
        "stage": 2,
        "episode": 1,
    }

    def build(
        self,
        request: LocalContextRequest,
        bundle: EvidenceAssetBundle | None = None,
    ) -> LocalContextPackage:
        assets_provided = bundle is not None or request.context_assets is not None
        bundle = bundle or request.context_assets or EvidenceAssetBundle.empty()
        query_tokens = tokenize_text(
            f"{request.query_text or ''} {' '.join(request.key_words or [])}".strip()
        )
        scope = self._derive_scope(request)
        query_bundle = self.build_query_bundle(request)
        target_card_budget, budget_source = self._resolve_card_budget(
            bundle,
            scope,
            request.agent_name,
        )

        selected_cards, selection_rationale, candidate_card_count = self._select_cards(
            bundle,
            query_tokens,
            scope,
            query_bundle,
            request.agent_name,
            target_card_budget,
        )
        if scope == "global" and self._assess_global_status(selected_cards) != "sufficient":
            selected_cards = []
            selection_rationale = []
            candidate_card_count = 0
        selected_sample_ids = [card.sample_id for card in selected_cards]

        if not assets_provided:
            retrieval_status = "missing_context_assets"
        else:
            retrieval_status = "sufficient" if selected_sample_ids else "fallback_fulltext"
        rendered_context = "\n\n".join(render_evidence_card(card) for card in selected_cards)

        return LocalContextPackage(
            scope=scope,
            retrieval_status=retrieval_status,
            selected_sample_ids=selected_sample_ids,
            rendered_context=rendered_context,
            summary={"selected_count": len(selected_sample_ids)},
            query_bundle=query_bundle,
            memory=self._build_memory(
                selected_cards,
                bundle,
                assets_provided,
                selection_rationale,
            ),
            budget_summary=self._build_budget_summary(
                selected_cards,
                bundle,
                assets_provided,
                scope,
                selection_rationale,
                target_card_budget,
                budget_source,
                request.agent_name,
                candidate_card_count,
            ),
        )

    def build_query_bundle(self, request: LocalContextRequest) -> dict[str, object]:
        scope = self._derive_scope(request)
        agent_name = (request.agent_name or "").strip().lower()
        query_bundle: dict[str, object] = {
            "scope": scope,
            "agent_name": request.agent_name,
            "query_text": request.query_text,
            "keyword_hints": self._collect_keyword_hints(request),
        }
        if agent_name == "transactionreconstructor":
            query_bundle["money_hints"] = self._collect_transaction_money_hints(request)
            query_bundle["action_hints"] = self._collect_transaction_action_hints(request)

        if scope == "global":
            query_bundle["global_phase_hints"] = self._collect_global_phase_hints(request)
            return query_bundle

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
        query_bundle: dict[str, object],
        agent_name: str,
        target_card_budget: int,
    ) -> tuple[List[EvidenceCard], List[dict[str, object]], int]:
        if scope == "global":
            selected_cards, selection_rationale, candidate_card_count = self._select_global_cards(
                bundle,
                query_tokens,
                query_bundle,
                target_card_budget,
            )
            return selected_cards, selection_rationale, candidate_card_count

        ranked_cards = []
        for index, card in enumerate(bundle.evidence_cards):
            score, matched_fields = self._score_scope_card(
                card,
                query_tokens,
                scope,
                query_bundle,
                agent_name,
            )
            if score <= 0:
                continue
            ranked_cards.append((score, index, card, matched_fields))

        selected_entries = sorted(
            ranked_cards,
            key=lambda item: (-item[0], item[1]),
        )
        selected_entries = [
            (card, matched_fields)
            for _, _, card, matched_fields in selected_entries
        ]
        selected_entries = selected_entries[:target_card_budget]
        selected_cards = [card for card, _ in selected_entries]
        selection_rationale = [
            {
                "sample_id": card.sample_id,
                "matched_fields": matched_fields,
            }
            for card, matched_fields in selected_entries
        ]
        return selected_cards, selection_rationale, len(ranked_cards)

    def _select_global_cards(
        self,
        bundle: EvidenceAssetBundle,
        query_tokens: List[str],
        query_bundle: dict[str, object],
        target_card_budget: int,
    ) -> tuple[List[EvidenceCard], List[dict[str, object]], int]:
        query_content_tokens = [
            token for token in query_tokens if token not in self._GLOBAL_LOW_SIGNAL_TOKENS
        ]
        case_signal_tokens = self._extract_global_case_signal_tokens(query_content_tokens)
        query_information_tokens = self._extract_global_high_information_tokens(
            query_content_tokens
        )
        query_phase_hints = [
            str(value)
            for value in query_bundle.get("global_phase_hints", [])
            if isinstance(value, str)
        ]
        if not case_signal_tokens and not query_information_tokens:
            return [], [], 0

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
            card_phase_hits = self._extract_global_phase_hits(card.tokens)
            match_priority = 0 if match_kind == "strong" else 1
            phase_overlap = score_token_overlap(card_phase_hits, query_phase_hints)
            matched_fields = ["query_tokens"]
            if phase_overlap > 0:
                matched_fields.append("global_phase_hints")
            ranked_cards.append(
                (
                    match_priority,
                    -phase_overlap,
                    -overlap,
                    index,
                    card,
                    match_kind,
                    matched_fields,
                )
            )

        selected_entries = sorted(
            ranked_cards,
            key=lambda item: (item[0], item[1], item[2], item[3]),
        )
        selected_entries = selected_entries[:target_card_budget]
        selected_cards = [card for _, _, _, _, card, _, _ in selected_entries]
        selection_rationale = [
            {
                "sample_id": card.sample_id,
                "matched_fields": matched_fields,
                "match_kind": match_kind,
            }
            for _, _, _, _, card, match_kind, matched_fields in selected_entries
        ]
        return selected_cards, selection_rationale, len(ranked_cards)

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
        return phase_hints

    def _collect_transaction_money_hints(self, request: LocalContextRequest) -> List[str]:
        return self._dedupe_tokens(
            [
                token
                for token in self._collect_keyword_hints(request)
                if token in self._TRANSACTION_MONEY_TOKENS
            ]
        )

    def _collect_transaction_action_hints(self, request: LocalContextRequest) -> List[str]:
        return [
            token
            for token in self._collect_keyword_hints(request)
            if token in self._EPISODE_ACTION_TOKENS
        ]

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
        return [
            token
            for token in self._collect_keyword_hints(request)
            if token in self._EPISODE_ACTION_TOKENS
        ]

    def _collect_episode_time_hints(self, request: LocalContextRequest) -> List[str]:
        time_hints = [
            token
            for token in tokenize_text(
                " ".join(
                    [
                        request.query_text or "",
                        request.target_stage or "",
                        request.target_episode or "",
                    ]
                )
            )
            if token.isdigit() and len(token) == 4
        ]
        return self._dedupe_tokens(time_hints)

    def _build_memory(
        self,
        selected_cards: List[EvidenceCard],
        bundle: EvidenceAssetBundle,
        assets_provided: bool,
        selection_rationale: List[dict[str, object]],
    ) -> dict[str, object]:
        selected_sample_ids = [card.sample_id for card in selected_cards]
        selected_hint_counts = {
            "time_hints": sum(len(card.time_hints) for card in selected_cards),
            "entity_hints": sum(len(card.entity_hints) for card in selected_cards),
            "action_hints": sum(len(card.action_hints) for card in selected_cards),
            "money_hints": sum(len(card.money_hints) for card in selected_cards),
        }
        return {
            "asset_status": "provided" if assets_provided else "missing",
            "selected_sample_ids": selected_sample_ids,
            "selected_hint_counts": selected_hint_counts,
            "selection_rationale": selection_rationale,
            "available_card_count": len(bundle.evidence_cards),
        }

    def _build_budget_summary(
        self,
        selected_cards: List[EvidenceCard],
        bundle: EvidenceAssetBundle,
        assets_provided: bool,
        scope: str,
        selection_rationale: List[dict[str, object]],
        target_card_budget: int,
        budget_source: str,
        agent_name: str,
        candidate_card_count: int,
    ) -> dict[str, object]:
        clipped_card_count = max(candidate_card_count - len(selected_cards), 0)
        return {
            "used_card_count": len(selected_cards),
            "target_card_budget": target_card_budget,
            "available_card_count": len(bundle.evidence_cards),
            "remaining_card_budget": max(target_card_budget - len(selected_cards), 0),
            "asset_bundle_count": 1 if assets_provided else 0,
            "selection_rationale_count": len(selection_rationale),
            "candidate_card_count": candidate_card_count,
            "clipped_card_count": clipped_card_count,
            "budget_clipped": clipped_card_count > 0,
            "budget_source": budget_source,
            "budget_agent_name": agent_name,
            "budget_scope": scope,
        }

    def _resolve_card_budget(
        self,
        bundle: EvidenceAssetBundle,
        scope: str,
        agent_name: str,
    ) -> tuple[int, str]:
        normalized_agent_name = (agent_name or "").strip().lower()
        agent_budget = self._TARGET_CARD_BUDGET_BY_AGENT_NAME.get(normalized_agent_name)
        if agent_budget is not None:
            if bundle.retrieval_policy.max_cards is None:
                return agent_budget, "agent"
            return min(agent_budget, bundle.retrieval_policy.max_cards), "agent"

        scope_budget = self._TARGET_CARD_BUDGET_BY_SCOPE.get(scope, len(bundle.evidence_cards))
        if bundle.retrieval_policy.max_cards is None:
            return scope_budget, "scope"
        return min(scope_budget, bundle.retrieval_policy.max_cards), "scope"

    def _score_scope_card(
        self,
        card: EvidenceCard,
        query_tokens: List[str],
        scope: str,
        query_bundle: dict[str, object],
        agent_name: str,
    ) -> tuple[int, List[str]]:
        base_score, matched_fields = self._score_standard_scope_card(
            card,
            query_tokens,
            scope,
            query_bundle,
        )
        if base_score <= 0:
            return 0, []

        if (agent_name or "").strip().lower() != "transactionreconstructor":
            return base_score, matched_fields

        bonus_score, bonus_fields = self._score_transaction_bonus(
            card,
            query_bundle,
        )
        for field in bonus_fields:
            if field not in matched_fields:
                matched_fields.append(field)
        return base_score + bonus_score, matched_fields

    def _score_standard_scope_card(
        self,
        card: EvidenceCard,
        query_tokens: List[str],
        scope: str,
        query_bundle: dict[str, object],
    ) -> tuple[int, List[str]]:
        query_overlap = score_token_overlap(card.tokens, query_tokens)
        if query_overlap <= 0:
            return 0, []

        matched_fields = ["query_tokens"]
        score = query_overlap * 100

        if scope == "stage":
            stage_name_tokens = tokenize_text(str(query_bundle.get("stage_name", "")))
            stage_hint_tokens = [
                str(token)
                for token in query_bundle.get("stage_hints", [])
                if isinstance(token, str)
            ]
            stage_name_overlap = score_token_overlap(card.tokens, stage_name_tokens)
            stage_hint_overlap = score_token_overlap(card.tokens, stage_hint_tokens)
            if stage_name_overlap > 0:
                matched_fields.append("stage_name")
                score += stage_name_overlap * 25
            if stage_hint_overlap > 0:
                matched_fields.append("stage_hints")
                score += stage_hint_overlap * 10
            return score, matched_fields

        stage_name_tokens = tokenize_text(str(query_bundle.get("stage_name", "")))
        episode_name_tokens = tokenize_text(str(query_bundle.get("episode_name", "")))
        entity_overlap = self._score_exact_hint_overlap(
            card.entity_hints,
            query_bundle.get("entity_hints", []),
        )
        action_overlap = self._score_exact_hint_overlap(
            card.action_hints,
            query_bundle.get("action_hints", []),
        )
        time_overlap = self._score_exact_hint_overlap(
            card.time_hints,
            query_bundle.get("time_hints", []),
        )
        stage_name_overlap = score_token_overlap(card.tokens, stage_name_tokens)
        episode_name_overlap = score_token_overlap(card.tokens, episode_name_tokens)
        if stage_name_overlap > 0:
            matched_fields.append("stage_name")
            score += stage_name_overlap * 10
        if episode_name_overlap > 0:
            matched_fields.append("episode_name")
            score += episode_name_overlap * 30
        if entity_overlap > 0:
            matched_fields.append("entity_hints")
            score += entity_overlap * 40
        if action_overlap > 0:
            matched_fields.append("action_hints")
            score += action_overlap * 20
        if time_overlap > 0:
            matched_fields.append("time_hints")
            score += time_overlap * 20
        return score, matched_fields

    def _score_transaction_bonus(
        self,
        card: EvidenceCard,
        query_bundle: dict[str, object],
    ) -> tuple[int, List[str]]:
        score = 0
        matched_fields: List[str] = []
        money_hints = [
            str(token)
            for token in query_bundle.get("money_hints", [])
            if isinstance(token, str)
        ]
        action_hints = [
            str(token)
            for token in query_bundle.get("action_hints", [])
            if isinstance(token, str)
        ]
        entity_hints = [
            str(token)
            for token in query_bundle.get("entity_hints", [])
            if isinstance(token, str)
        ]
        time_hints = [
            str(token)
            for token in query_bundle.get("time_hints", [])
            if isinstance(token, str)
        ]

        money_overlap = self._score_exact_hint_overlap(card.money_hints, money_hints)
        action_overlap = self._score_exact_hint_overlap(card.action_hints, action_hints)
        if money_overlap > 0:
            matched_fields.append("money_hints")
            score += money_overlap * 200
        if action_overlap > 0:
            matched_fields.append("action_hints")
            score += action_overlap * 120

        entity_overlap = self._score_exact_hint_overlap(card.entity_hints, entity_hints)
        if entity_overlap > 0:
            matched_fields.append("entity_hints")
            score += entity_overlap * 40

        time_overlap = self._score_exact_hint_overlap(card.time_hints, time_hints)
        if time_overlap > 0:
            matched_fields.append("time_hints")
            score += time_overlap * 20

        return score, matched_fields

    def _score_exact_hint_overlap(
        self,
        left_values: List[str],
        right_values: object,
    ) -> int:
        if not isinstance(right_values, list):
            return 0
        left_normalized = {value.strip().lower() for value in left_values if value}
        right_normalized = {
            str(value).strip().lower()
            for value in right_values
            if str(value).strip()
        }
        return len(left_normalized & right_normalized)

    def _dedupe_tokens(self, values: List[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value))

    def _take_non_empty(self, values: List[str]) -> List[str]:
        return [value for value in dict.fromkeys(values) if value]
