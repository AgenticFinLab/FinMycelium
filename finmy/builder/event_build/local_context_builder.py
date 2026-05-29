"""Local context selection for ContextEventBuilder prompts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .context_assets import EvidenceAssetBundle, EvidenceCard
from .indexing import score_token_overlap, tokenize_text
from .renderers import render_evidence_card


@dataclass
class LocalContextRequest:
    """Inputs needed to build a local context package."""

    agent_name: str
    query_text: str = ""
    key_words: list[str] = field(default_factory=list)
    target_stage: str = ""
    target_episode: str = ""
    context_assets: EvidenceAssetBundle | None = None
    max_context_chars: int = 6000


@dataclass
class LocalContextPackage:
    """Selected local context and audit metadata for one agent call."""

    scope: str
    retrieval_status: str
    selected_sample_ids: list[str] = field(default_factory=list)
    rendered_context: str = ""
    summary: dict[str, int] = field(default_factory=dict)
    query_bundle: dict[str, object] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)
    budget_summary: dict[str, object] = field(default_factory=dict)


class LocalContextBuilder:
    """Build deterministic local context packages from passive evidence cards."""

    _SCOPE_BY_AGENT_NAME = {
        "episodereconstructor": "episode",
        "participantreconstructor": "episode",
        "transactionreconstructor": "episode",
        "stagedescriptionreconstructor": "stage",
        "eventdescriptionreconstructor": "global",
    }
    _CARD_BUDGET_BY_AGENT_NAME = {
        "participantreconstructor": 1,
        "transactionreconstructor": 1,
        "episodereconstructor": 1,
        "stagedescriptionreconstructor": 2,
        "eventdescriptionreconstructor": 3,
    }
    _CARD_BUDGET_BY_SCOPE = {
        "episode": 1,
        "stage": 2,
        "global": 3,
    }

    def build(
        self,
        request: LocalContextRequest,
        bundle: EvidenceAssetBundle | None = None,
    ) -> LocalContextPackage:
        assets_provided = bundle is not None or request.context_assets is not None
        bundle = bundle or request.context_assets or EvidenceAssetBundle.empty()
        scope = self._derive_scope(request)
        query_bundle = self.build_query_bundle(request)
        card_budget = self._resolve_card_budget(request, bundle, scope)
        selected_cards, candidate_count = self._select_cards(
            bundle=bundle,
            request=request,
            query_bundle=query_bundle,
            card_budget=card_budget,
        )
        selected_sample_ids = [card.sample_id for card in selected_cards]
        rendered_context = self._clip_context(
            "\n\n".join(render_evidence_card(card) for card in selected_cards),
            request.max_context_chars,
        )
        retrieval_status = "sufficient" if selected_sample_ids else "fallback_fulltext"
        if not assets_provided:
            retrieval_status = "missing_context_assets"

        return LocalContextPackage(
            scope=scope,
            retrieval_status=retrieval_status,
            selected_sample_ids=selected_sample_ids,
            rendered_context=rendered_context,
            summary={"selected_count": len(selected_sample_ids)},
            query_bundle=query_bundle,
            memory={
                "asset_status": "provided" if assets_provided else "missing",
                "selected_sample_ids": selected_sample_ids,
                "available_card_count": len(bundle.evidence_cards),
            },
            budget_summary={
                "used_card_count": len(selected_sample_ids),
                "target_card_budget": card_budget,
                "available_card_count": len(bundle.evidence_cards),
                "candidate_card_count": candidate_count,
                "remaining_card_budget": max(card_budget - len(selected_cards), 0),
                "budget_scope": scope,
                "budget_agent_name": request.agent_name,
            },
        )

    def build_query_bundle(self, request: LocalContextRequest) -> dict[str, object]:
        scope = self._derive_scope(request)
        query_bundle: dict[str, object] = {
            "scope": scope,
            "agent_name": request.agent_name,
            "query_text": request.query_text,
            "keyword_hints": self._dedupe(
                [
                    *tokenize_text(" ".join(request.key_words or [])),
                    *tokenize_text(request.query_text),
                ]
            ),
        }
        if scope in {"stage", "episode"}:
            query_bundle["stage_name"] = request.target_stage
            query_bundle["stage_hints"] = tokenize_text(request.target_stage)
        if scope == "episode":
            query_bundle["episode_name"] = request.target_episode
            query_bundle["episode_hints"] = tokenize_text(request.target_episode)
            query_bundle["entity_hints"] = self._dedupe(
                [request.target_stage, request.target_episode, *request.key_words]
            )
            query_bundle["action_hints"] = [
                token
                for token in query_bundle["keyword_hints"]
                if token in {"buy", "flee", "investigate", "launder", "seize", "transfer"}
            ]
            query_bundle["time_hints"] = [
                token
                for token in tokenize_text(
                    f"{request.query_text} {request.target_stage} {request.target_episode}"
                )
                if token.isdigit() and len(token) == 4
            ]
        return query_bundle

    def _select_cards(
        self,
        bundle: EvidenceAssetBundle,
        request: LocalContextRequest,
        query_bundle: dict[str, object],
        card_budget: int,
    ) -> tuple[list[EvidenceCard], int]:
        query_tokens = self._query_tokens(request, query_bundle)
        ranked_cards: list[tuple[int, int, EvidenceCard]] = []
        for index, card in enumerate(bundle.evidence_cards):
            score = score_token_overlap(card.tokens, query_tokens)
            score += self._hint_overlap(card.entity_hints, query_bundle.get("entity_hints"))
            score += self._hint_overlap(card.action_hints, query_bundle.get("action_hints"))
            score += self._hint_overlap(card.time_hints, query_bundle.get("time_hints"))
            if score > 0:
                ranked_cards.append((score, index, card))

        ranked_cards.sort(key=lambda item: (-item[0], item[1]))
        selected = [card for _, _, card in ranked_cards[:card_budget]]
        return selected, len(ranked_cards)

    def _query_tokens(
        self,
        request: LocalContextRequest,
        query_bundle: dict[str, object],
    ) -> list[str]:
        values = [
            request.query_text,
            " ".join(request.key_words or []),
            str(query_bundle.get("stage_name", "")),
            str(query_bundle.get("episode_name", "")),
        ]
        return self._dedupe(tokenize_text(" ".join(values)))

    def _resolve_card_budget(
        self,
        request: LocalContextRequest,
        bundle: EvidenceAssetBundle,
        scope: str,
    ) -> int:
        agent_budget = self._CARD_BUDGET_BY_AGENT_NAME.get(
            (request.agent_name or "").lower()
        )
        budget = agent_budget or self._CARD_BUDGET_BY_SCOPE.get(scope, 1)
        if bundle.retrieval_policy.max_cards is not None:
            budget = min(budget, bundle.retrieval_policy.max_cards)
        return max(budget, 0)

    def _derive_scope(self, request: LocalContextRequest) -> str:
        mapped_scope = self._SCOPE_BY_AGENT_NAME.get((request.agent_name or "").lower())
        if mapped_scope:
            return mapped_scope
        if request.target_episode:
            return "episode"
        if request.target_stage:
            return "stage"
        return "global"

    def _clip_context(self, context: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        if len(context) <= max_chars:
            return context
        if max_chars <= 3:
            return context[:max_chars]
        return f"{context[: max_chars - 3].rstrip()}..."

    def _hint_overlap(self, left_values: list[str], right_values: object) -> int:
        if not isinstance(right_values, list):
            return 0
        left = {value.strip().lower() for value in left_values if value}
        right = {str(value).strip().lower() for value in right_values if str(value)}
        return len(left & right)

    def _dedupe(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
