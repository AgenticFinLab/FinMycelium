"""
Base abstractions for content matching.

- Provides a consistent result structure (`MatchOutput`, `MatchItem`).
- Defines an abstract `MatchBase` to be extended by concrete matchers
  (e.g., LLM-based, rule-based, hybrid).

We support different ways of matchers:
- LLM-based matcher: uses large models to extract semantically relevant content.
- Rule-based matcher: applies manually crafted or predefined rules to match content.
- Hybrid matcher: combines multiple methods for improved accuracy.

Based on the following platforms:
- Haystack: a flexible framework for building search and question-answering pipelines.
- Langchain: a library for building applications that use language models.
- LlamaIndex: a library for building applications that use language models to index and query data.


Implementers should:
- Override `match` to produce raw output and a list of selection dicts.
- Use `run` for end-to-end execution and standardized results.
"""

import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union
from abc import ABC, abstractmethod

from .utils import get_paragraph_positions
from .summarizer import SummarizedUserQuery


@dataclass
class MatchInput:
    """Standardized input to a matcher.

    - `match_data`: upstream data to be matched (e.g., full article text or model output)
    - `db_item`: associated DB record from storage providing metadata/context for matching
    - `summarized_query`: summarized user query (optional) that guides selection
    """

    match_data: Optional[str] = None
    db_item: Optional[Dict[str, Any]] = None
    summarized_query: Optional[SummarizedUserQuery] = None


@dataclass
class MatchItem:
    """A single matched subset from the source content.

    - `paragraph`: paragraph of the source content (no paraphrasing)
    - `start`/`end`: for the paragraph, character offsets into the original content; `None` when
      the selection could not be matched (e.g., quote not found)
    """

    paragraph: str
    paragraph_index: int
    start: Optional[int]
    end: Optional[int]
    paragraph_contiguous: Optional[List[str]] = None
    contiguous_indices: Optional[List[int]] = None


@dataclass
class MatchOutput:
    """Standardized container for match outputs.

    - `items`: MatchItem
    - `raw`: raw string produced by upstream matcher (e.g., model JSON)
    - `method`: identifier of the method used by the matcher (if any)
    """

    items: List[MatchItem]
    method: Optional[str] = None
    time: Optional[float] = None


class BaseMatcher(ABC):
    """Abstract base class for all matchers.

    Responsibilities:
    - Expose a `match` method returning `(raw, selections)` where:
      * `raw`: optional raw string from upstream (e.g., model response)
      * `selections`: list of dicts accepted by `get_subset_positions`, each
        item may include `paragraph_indices: List[int]` and/or `quote: str`.
    - Provide `run` and `map_positions` helpers to standardize outputs.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        method_name: Optional[str] = None,
    ):
        self.config = config
        self.method_name = method_name

    @abstractmethod
    def match(self, match_input: MatchInput) -> List[Union[str, Any]]:
        """Produce raw output and selection items for positional mapping.

        Return:
        - List[str]: list of strings, each string is a matched sub-content that may containing one target paragraph or multiple paragraphs.
        """

    def map_positions(
        self,
        content: str,
        matches: List[Union[str, Any]],
    ) -> List[MatchItem]:
        """Translate generic matches from the `match` into positional `MatchItem`s.

        Uses `get_subset_positions` to compute `start`/`end` based on either
        paragraph indices or the first occurrence of an exact quote.
        """

        mapped = get_paragraph_positions(content, matches)
        items: List[MatchItem] = []
        for m in mapped:
            text = m.get("text", "")
            start = m.get("start")
            end = m.get("end")
            idxs = m.get("paragraph_indices") or []
            idxs_sorted = idxs if isinstance(idxs, list) else []
            paragraph_index = min(idxs_sorted) if idxs_sorted else -1
            contiguous_indices = sorted(idxs_sorted) if idxs_sorted else None
            items.append(
                MatchItem(
                    paragraph=text,
                    paragraph_index=paragraph_index,
                    start=start,
                    end=end,
                    paragraph_contiguous=None,
                    contiguous_indices=contiguous_indices,
                )
            )
        return items

    def run(self, match_input: MatchInput) -> MatchOutput:
        """End-to-end execution returning a standardized `MatchOutput`.

        - Delegates extraction to `match`
        - Normalizes positions via `map_positions`
        - Echoes inputs and the matcher's `model` into the result
        """
        # Compute the time of the whole matching process
        start_time = time.time()
        matches = self.match(match_input)
        end_time = time.time()
        items = self.map_positions(match_input.match_data, matches)
        return MatchOutput(
            items=items,
            method=self.method_name,
            time=end_time - start_time,
        )
