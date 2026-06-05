"""Passive evidence asset dataclasses and builders for sparse_build."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Sequence

from finmy.generic import DataSample, UserQueryInput

from .indexing import (
    build_global_token_counts,
    count_tokens,
    score_token_overlap,
    tokenize_text,
)


@dataclass
class EvidenceRetrievalPolicy:
    """Configuration for passive evidence card extraction."""

    max_cards: int | None = None
    excerpt_char_limit: int = 240
    max_card_tokens: int = 48


@dataclass
class EvidenceIndex:
    """Simple token-based global index for passive evidence assets."""

    token_counts: dict[str, int] = field(default_factory=dict)
    sample_token_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    sample_signal_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    query_token_counts: dict[str, int] = field(default_factory=dict)
    query_signal_counts: dict[str, int] = field(default_factory=dict)
    sample_ids: list[str] = field(default_factory=list)
    query_tokens: list[str] = field(default_factory=list)


@dataclass
class EvidenceCard:
    """Passive summary of one source sample used for retrieval and rendering."""

    sample_id: str
    title: str
    excerpt: str
    tokens: list[str] = field(default_factory=list)
    score: int = 0
    source_char_count: int = 0
    time_hints: list[str] = field(default_factory=list)
    entity_hints: list[str] = field(default_factory=list)
    action_hints: list[str] = field(default_factory=list)
    money_hints: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class EvidenceAssetBundle:
    """Container for passive evidence assets derived from current build input."""

    retrieval_policy: EvidenceRetrievalPolicy
    index: EvidenceIndex
    evidence_cards: list[EvidenceCard] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "EvidenceAssetBundle":
        return cls(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[],
        )


def summarize_context_assets(bundle: EvidenceAssetBundle | None) -> dict[str, int]:
    """Return a compact, stable summary for logs and prompt inputs."""

    if bundle is None:
        return {
            "evidence_card_count": 0,
            "sample_id_count": 0,
            "global_token_count": 0,
            "query_token_count": 0,
            "signal_card_count": 0,
            "time_hint_count": 0,
            "entity_hint_count": 0,
            "action_hint_count": 0,
            "money_hint_count": 0,
        }

    return {
        "evidence_card_count": len(bundle.evidence_cards),
        "sample_id_count": len(bundle.index.sample_ids),
        "global_token_count": sum(bundle.index.token_counts.values()),
        "query_token_count": sum(bundle.index.query_token_counts.values()),
        "signal_card_count": sum(
            1 for card in bundle.evidence_cards if card.quality_flags
        ),
        "time_hint_count": sum(len(card.time_hints) for card in bundle.evidence_cards),
        "entity_hint_count": sum(
            len(card.entity_hints) for card in bundle.evidence_cards
        ),
        "action_hint_count": sum(
            len(card.action_hints) for card in bundle.evidence_cards
        ),
        "money_hint_count": sum(
            len(card.money_hints) for card in bundle.evidence_cards
        ),
    }


_MONTH_PATTERN = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)"
)
_YEAR_PATTERN = r"(?:19|20)\d{2}"
_MONTH_YEAR_RE = re.compile(rf"\b{_MONTH_PATTERN}\s+{_YEAR_PATTERN}\b", re.I)
_YEAR_RE = re.compile(rf"\b{_YEAR_PATTERN}\b")
_MONEY_RE = re.compile(
    r"(?:[£$€¥]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|thousand|m|bn))?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:million|billion|thousand|m|bn)\b)",
    re.I,
)
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,3}\b"
)
_ACTION_RULES = (
    (re.compile(r"\bbuy(?:s|ing|ed)?\b", re.I), "buy"),
    (re.compile(r"\bflee(?:s|ing|d)?\b", re.I), "flee"),
    (re.compile(r"\binvestigat(?:e|es|ed|ing)\b", re.I), "investigate"),
    (re.compile(r"\blaunder(?:s|ing|ed)?\b", re.I), "launder"),
    (re.compile(r"\bseiz(?:e|es|ed|ing)\b", re.I), "seize"),
    (re.compile(r"\btransfer(?:s|ring|red)?\b", re.I), "transfer"),
)
_MONEY_KEYWORDS = ("bitcoin", "btc", "crypto", "cryptocurrency")
_NOISE_PREFIXES = (
    "skip to main content",
    "search for careers contact about us",
    "cnn values your feedback",
    "video player was slow to load",
)


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _shorten_excerpt(text: str, char_limit: int) -> str:
    if len(text) <= char_limit:
        return text
    return f"{text[: max(char_limit - 3, 0)].rstrip()}..."


def _strip_noise_prefix(text: str) -> str:
    working = text.strip()
    lowered = working.lower()
    changed = True
    while changed:
        changed = False
        lowered = working.lower()
        for prefix in _NOISE_PREFIXES:
            if lowered.startswith(prefix):
                working = working[len(prefix) :].lstrip(" \t\r\n-:;,.!?")
                changed = True
                break
        if lowered.startswith("ad feedback") and (
            "cnn values your feedback" in lowered[:120]
            or "video player was slow to load" in lowered[:160]
            or "cnn analysis" in lowered[:80]
        ):
            working = re.sub(
                r"^ad feedback(?:\s*->\s*|[\s\.,:;!?]+)+",
                "",
                working,
                flags=re.I,
            ).lstrip()
            changed = True
    return working


def _extract_time_hints(text: str) -> list[str]:
    hints = [match.group(0).lower() for match in _MONTH_YEAR_RE.finditer(text)]
    hints.extend(match.group(0) for match in _YEAR_RE.finditer(text))
    return _dedupe(hints)


def _count_time_mentions(text: str) -> int:
    return len(_extract_time_hints(text))


def _extract_money_hints(text: str) -> list[str]:
    hints = [match.group(0).strip() for match in _MONEY_RE.finditer(text)]
    lower_text = text.lower()
    for keyword in _MONEY_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lower_text):
            hints.append(keyword)
    return _dedupe(hints)


def _extract_entity_hints(text: str) -> list[str]:
    return _dedupe(match.group(0) for match in _ENTITY_RE.finditer(text))


def _extract_action_hints(text: str) -> list[str]:
    hints: list[str] = []
    for pattern, label in _ACTION_RULES:
        if pattern.search(text):
            hints.append(label)
    return _dedupe(hints)


def _derive_quality_flags(
    time_hints: Sequence[str],
    entity_hints: Sequence[str],
    action_hints: Sequence[str],
    money_hints: Sequence[str],
) -> list[str]:
    flags: list[str] = []
    if time_hints:
        flags.append("has_time_signal")
    if entity_hints:
        flags.append("has_entity_signal")
    if action_hints:
        flags.append("has_action_signal")
    if money_hints:
        flags.append("has_money_signal")
    if len(money_hints) >= 2:
        flags.append("money_dense")
    return flags


def _sample_title(sample: DataSample) -> str:
    return sample.category or sample.sample_id or sample.raw_data_id


def build_evidence_assets(
    user_query: UserQueryInput,
    samples: Sequence[DataSample],
    retrieval_policy: EvidenceRetrievalPolicy | None = None,
) -> EvidenceAssetBundle:
    """Build passive evidence cards and a token index from build input fields."""

    policy = retrieval_policy or EvidenceRetrievalPolicy()
    sample_list = list(samples or [])
    query_text = user_query.query_text or ""
    query_keyword_text = " ".join(user_query.key_words or [])
    query_signal_text = f"{query_text} {query_keyword_text}".strip()
    query_tokens = tokenize_text(query_signal_text)

    sample_token_counts: dict[str, dict[str, int]] = {}
    sample_signal_counts: dict[str, dict[str, int]] = {}
    cards: list[EvidenceCard] = []

    for sample in sample_list:
        content = sample.content or ""
        excerpt_source = _strip_noise_prefix(content)
        excerpt = _shorten_excerpt(excerpt_source, policy.excerpt_char_limit)
        tokens = tokenize_text(excerpt)[: policy.max_card_tokens]
        time_hints = _extract_time_hints(content)
        entity_hints = _extract_entity_hints(content)
        action_hints = _extract_action_hints(content)
        money_hints = _extract_money_hints(content)
        quality_flags = _derive_quality_flags(
            time_hints, entity_hints, action_hints, money_hints
        )
        sample_token_counts[sample.sample_id] = count_tokens(content)
        sample_signal_counts[sample.sample_id] = {
            "time_hints": _count_time_mentions(content),
            "entity_hints": len(entity_hints),
            "action_hints": len(action_hints),
            "money_hints": len(money_hints),
            "quality_flags": len(quality_flags),
        }
        cards.append(
            EvidenceCard(
                sample_id=sample.sample_id,
                title=_sample_title(sample),
                excerpt=excerpt,
                tokens=tokens,
                score=score_token_overlap(tokens, query_tokens),
                source_char_count=len(content),
                time_hints=time_hints,
                entity_hints=entity_hints,
                action_hints=action_hints,
                money_hints=money_hints,
                quality_flags=quality_flags,
            )
        )

    cards = sorted(cards, key=lambda card: (-card.score, card.sample_id))
    if policy.max_cards is not None:
        cards = cards[: policy.max_cards]

    index = EvidenceIndex(
        token_counts=build_global_token_counts(
            [query_text, query_keyword_text, *(sample.content for sample in sample_list)]
        ),
        sample_token_counts=sample_token_counts,
        sample_signal_counts=sample_signal_counts,
        query_token_counts=count_tokens(query_signal_text),
        query_signal_counts={
            "time_hints": _count_time_mentions(query_signal_text),
            "entity_hints": len(_extract_entity_hints(query_signal_text)),
            "action_hints": len(_extract_action_hints(query_signal_text)),
            "money_hints": len(_extract_money_hints(query_signal_text)),
        },
        sample_ids=[sample.sample_id for sample in sample_list],
        query_tokens=query_tokens,
    )

    return EvidenceAssetBundle(
        retrieval_policy=policy,
        index=index,
        evidence_cards=cards,
    )
