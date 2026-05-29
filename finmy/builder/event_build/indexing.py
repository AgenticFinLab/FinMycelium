"""Lightweight token indexing helpers for event_build evidence assets."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Sequence

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize_text(text: str | None) -> list[str]:
    """Return normalized alphanumeric tokens extracted from text."""

    if not text:
        return []
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def count_tokens(text: str | None) -> dict[str, int]:
    """Count normalized tokens in a single text value."""

    return dict(Counter(tokenize_text(text)))


def build_global_token_counts(texts: Iterable[str | None]) -> dict[str, int]:
    """Build a token frequency map over a collection of text values."""

    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(tokenize_text(text))
    return dict(counter)


def score_token_overlap(left_tokens: Sequence[str], right_tokens: Sequence[str]) -> int:
    """Score two token sequences using unique-token overlap."""

    return len(set(left_tokens) & set(right_tokens))
