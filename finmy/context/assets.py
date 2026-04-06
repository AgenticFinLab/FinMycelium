"""Passive evidence asset dataclasses and builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import List, Sequence

from finmy.generic import DataSample, UserQueryInput
from finmy.context.indexing import build_global_token_counts, count_tokens, score_token_overlap, tokenize_text


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
    query_token_counts: dict[str, int] = field(default_factory=dict)
    sample_ids: List[str] = field(default_factory=list)
    query_tokens: List[str] = field(default_factory=list)


@dataclass
class EvidenceCard:
    """Passive summary of a sample used for retrieval and rendering."""

    sample_id: str
    title: str
    excerpt: str
    tokens: List[str] = field(default_factory=list)
    score: int = 0
    source_char_count: int = 0


@dataclass
class EvidenceAssetBundle:
    """Container for all passive evidence assets attached to a build input."""

    retrieval_policy: EvidenceRetrievalPolicy
    index: EvidenceIndex
    evidence_cards: List[EvidenceCard] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "EvidenceAssetBundle":
        return cls(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[],
        )


def summarize_context_assets(bundle: EvidenceAssetBundle | None) -> dict[str, int]:
    """Return a compact, passive-only summary of attached context assets."""

    if bundle is None:
        return {
            "evidence_card_count": 0,
            "sample_id_count": 0,
            "global_token_count": 0,
            "query_token_count": 0,
        }

    return {
        "evidence_card_count": len(bundle.evidence_cards),
        "sample_id_count": len(bundle.index.sample_ids),
        "global_token_count": sum(bundle.index.token_counts.values()),
        "query_token_count": sum(bundle.index.query_token_counts.values()),
    }


def _shorten_excerpt(text: str, char_limit: int) -> str:
    if len(text) <= char_limit:
        return text
    return f"{text[:char_limit].rstrip()}..."


_NOISE_PREFIX_PHRASES = (
    "skip to main content",
    "search for careers contact about us",
    "cnn values your feedback",
    "video player was slow to load",
)

_NOISE_PREFIX_PATTERNS = tuple(
    re.compile(rf"^{re.escape(phrase)}(?:\s*->\s*|[\s\.,:;!?]+|$)", re.IGNORECASE)
    for phrase in _NOISE_PREFIX_PHRASES
)

_AD_FEEDBACK_CHAIN_PATTERN = re.compile(
    r"^ad feedback(?=(?:\s*->\s*|[\s\.,:;!?]+)+(?:cnn analysis|cnn values your feedback|video player was slow to load)\b)",
    re.IGNORECASE,
)

_AD_FEEDBACK_STRIP_PATTERN = re.compile(
    r"^ad feedback(?:\s*->\s*|[\s\.,:;!?]+)+",
    re.IGNORECASE,
)


def _strip_noise_prefix(text: str) -> str:
    working = text.lstrip()
    stripped_any = False

    while working:
        if _AD_FEEDBACK_CHAIN_PATTERN.match(working):
            strip_match = _AD_FEEDBACK_STRIP_PATTERN.match(working)
            if strip_match is None:
                break
            working = working[strip_match.end() :].lstrip()
            stripped_any = True
            continue

        for pattern in _NOISE_PREFIX_PATTERNS:
            match = pattern.match(working)
            if not match:
                continue
            working = working[match.end() :].lstrip()
            stripped_any = True
            break
        else:
            return working if stripped_any else text

    return working if stripped_any else text


def _clean_excerpt_source(text: str) -> str:
    return _strip_noise_prefix(text).strip()


def _sample_title(sample: DataSample) -> str:
    if sample.category:
        return sample.category
    return sample.sample_id or sample.raw_data_id


def build_evidence_assets(
    user_query: UserQueryInput,
    samples: Sequence[DataSample],
    retrieval_policy: EvidenceRetrievalPolicy | None = None,
) -> EvidenceAssetBundle:
    """Build passive evidence cards and a global token index from samples."""

    policy = retrieval_policy or EvidenceRetrievalPolicy()
    sample_list = list(samples)

    query_text = user_query.query_text or ""
    query_keyword_text = " ".join(user_query.key_words or [])
    query_tokens = tokenize_text(f"{query_text} {query_keyword_text}".strip())

    sample_token_counts: dict[str, dict[str, int]] = {}
    card_candidates: List[EvidenceCard] = []

    for sample in sample_list:
        content = sample.content or ""
        excerpt_source = _clean_excerpt_source(content)
        excerpt = _shorten_excerpt(excerpt_source, policy.excerpt_char_limit)
        tokens = tokenize_text(excerpt)[: policy.max_card_tokens]
        sample_token_counts[sample.sample_id] = count_tokens(content)
        card_candidates.append(
            EvidenceCard(
                sample_id=sample.sample_id,
                title=_sample_title(sample),
                excerpt=excerpt,
                tokens=tokens,
                score=score_token_overlap(tokens, query_tokens),
                source_char_count=len(content),
            )
        )

    if policy.max_cards is not None:
        card_candidates = card_candidates[: policy.max_cards]

    global_token_counts = build_global_token_counts(
        [query_text, query_keyword_text, *(sample.content for sample in sample_list)]
    )

    bundle_index = EvidenceIndex(
        token_counts=global_token_counts,
        sample_token_counts=sample_token_counts,
        query_token_counts=count_tokens(f"{query_text} {query_keyword_text}".strip()),
        sample_ids=[sample.sample_id for sample in sample_list],
        query_tokens=query_tokens,
    )

    return EvidenceAssetBundle(
        retrieval_policy=policy,
        index=bundle_index,
        evidence_cards=card_candidates,
    )
