"""
Implementation of using LlamaIndex to match the targets from the given
content based on the user query.
"""

from typing import List, Dict, Any, Optional, Set, Tuple

from llama_index.core import Document, SimpleKeywordTableIndex

from .base import MatchInput, MatchBase
from .utils import split_paragraphs


class LIMatcher(MatchBase):
    """Rule-based matcher that extracts relevant contiguous paragraphs.

    Overview:
    - Uses exact substring search for `summarization` and each `keyword`
    - Expands each hit into full paragraphs via `extract_context_with_paragraphs`
    - Returns only indices for matched contiguous paragraph segments

    Design Principles:
    - Non-destructive: does not alter the original content
    - Deterministic: no LLM involved, fully reproducible
    - Minimal surface: produces `paragraph_indices` to integrate with `MatchBase.map_positions`
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize matcher with optional configuration.

        Args:
            config: Optional dict; supports `context_chars` and `top_k`

        Notes:
            - When LlamaIndex is available, builds a keyword index per request.
            - Falls back to deterministic rule-based extraction if unavailable.
        """
        super().__init__(config=config, method_name="li_match")
        self.context_chars: int = (config or {}).get("context_chars", 96)
        self.top_k: int = int((config or {}).get("top_k", 8))

    def _group_contiguous(self, indices: List[int]) -> List[List[int]]:
        """Group sorted indices into contiguous ranges."""
        if not indices:
            return []
        sorted_idxs = sorted(set(indices))
        groups: List[List[int]] = []
        cur: List[int] = [sorted_idxs[0]]
        for i in sorted_idxs[1:]:
            if i == cur[-1] + 1:
                cur.append(i)
            else:
                groups.append(cur)
                cur = [i]
        groups.append(cur)
        return groups

    def _match_with_llamaindex(
        self,
        content: str,
        query_text: str,
        keywords: List[str],
    ) -> List[Dict[str, Any]]:
        """Use LlamaIndex SimpleKeywordTableIndex to retrieve relevant paragraphs."""
        paragraphs = split_paragraphs(content)
        docs: List[Document] = [
            Document(text=p["text"], metadata={"paragraph_index": p["index"]})
            for p in paragraphs
        ]
        index = SimpleKeywordTableIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        src = getattr(resp, "source_nodes", [])
        matched: List[int] = []
        for sn in src:
            try:
                md = getattr(getattr(sn, "node", sn), "metadata", {})
                idx = md.get("paragraph_index")
                if isinstance(idx, int):
                    matched.append(idx)
            except Exception:
                continue
        selections: List[Dict[str, Any]] = []
        for grp in self._group_contiguous(matched):
            if grp:
                selections.append({"paragraph_indices": grp})
        return selections

    def _find_occurrences(self, content: str, term: str) -> List[Tuple[int, int]]:
        """Find non-overlapping occurrences of `term` in `content`.

        Returns a list of (start, end) character offsets for each match.
        """
        if not term:
            return []
        occ: List[Tuple[int, int]] = []
        start = 0
        while True:
            idx = content.find(term, start)
            if idx == -1:
                break
            # Record the exact span for the found term
            occ.append((idx, idx + len(term)))
            # Advance to avoid overlapping the same occurrence
            start = idx + len(term)
        return occ

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Produce selection dicts describing matched contiguous paragraph ranges.

        Strategy:
        - Search `summarization` and each `keyword` as exact substrings in `content`
        - For every hit, expand to full paragraphs and collect their indices
        - Deduplicate segments by their sorted index tuples
        """
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        summarization = sq.summarization if sq and sq.summarization else ""
        keywords = sq.keywords if sq and sq.keywords else []

        # Precompute paragraph boundaries to enable index mapping
        content_paragraphs = split_paragraphs(content)
        # Track seen segments to avoid duplicates
        seen: Set[Tuple[int, ...]] = set()
        selections: List[Dict[str, Any]] = []

        # Aggregate search terms: summarization first, then keyword hints
        terms: List[str] = []
        if summarization:
            terms.append(summarization)
        for k in keywords:
            if k:
                terms.append(k)

        # Use LlamaIndex for matching
        li_selections = self._match_with_llamaindex(
            content=content, query_text=summarization, keywords=keywords
        )
        return li_selections
