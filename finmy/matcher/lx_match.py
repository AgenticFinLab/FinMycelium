"""
LlamaIndex-based matchers for extracting relevant content segments.

This module provides three matcher implementations that do not modify
the original content and instead identify relevant contiguous paragraph
indices for downstream position mapping:

- KWMatcher: keyword/term-driven retrieval via SimpleKeywordTableIndex
- LMMatcher: LLM-driven retrieval via SummaryIndex
- VectorMatcher: embedding/RAG retrieval via VectorStoreIndex

Each matcher converts content paragraphs into LlamaIndex `Document`s with
`paragraph_index` metadata, queries using the appropriate index type, and
returns selections as `{"paragraph_indices": [...]}`.
"""

from typing import List, Dict, Any, Optional, Tuple

from llama_index.core import (
    Document,
    SimpleKeywordTableIndex,
    SummaryIndex,
    VectorStoreIndex,
)

from .base import MatchInput, BaseMatcher
from .utils import split_paragraphs


class LXMatcher(BaseMatcher):
    """Legacy LlamaIndex matcher invoking SimpleKeywordTableIndex.

    Notes:
    - Uses keyword-table retrieval to identify relevant paragraphs.
    - Returns only `paragraph_indices` for contiguous segments.
    - `context_chars` in config is reserved for potential future fallback
      strategies and may be unused in this implementation.
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize with optional configuration.

        Args:
            config: may include `context_chars` (reserved) and `top_k` for
                    keyword table retrieval.
        """
        super().__init__(config=config, method_name="li_match")
        self.context_chars: int = (config or {}).get("context_chars", 96)
        self.top_k: int = int((config or {}).get("top_k", 8))

    def _match_with_llamaindex(
        self,
        content: str,
        query_text: str,
        keywords: List[str],
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant paragraphs via SimpleKeywordTableIndex.

        - Converts each paragraph to a `Document` with `paragraph_index` metadata.
        - Builds a keyword-table index and queries with query_text + keywords.
        - Maps `source_nodes` back to paragraph indices.
        """
        paragraphs = split_paragraphs(content)  # [{index, text}]
        docs: List[Document] = [
            Document(text=p["text"], metadata={"paragraph_index": p["index"]})
            for p in paragraphs
        ]
        index = SimpleKeywordTableIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            # Attach keyword hints to guide retrieval
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        src = getattr(resp, "source_nodes", [])  # nodes with scoring/metadata
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

    def _find_occurrences(
        self,
        content: str,
        term: str,
    ) -> List[Tuple[int, int]]:
        """Find non-overlapping occurrences of `term` in `content`.

        Returns:
            List of (start, end) offsets covering each exact match span.
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
        """Return selections of contiguous paragraph indices.

        Current strategy:
        - Use SimpleKeywordTableIndex-based retrieval with `summarization` and
          `keywords` hints; no content modification.
        """
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        summarization = sq.summarization if sq and sq.summarization else ""
        keywords = sq.keywords if sq and sq.keywords else []

        # Use LlamaIndex for matching
        li_selections = self._match_with_llamaindex(
            content=content, query_text=summarization, keywords=keywords
        )
        return li_selections


def _group_contiguous(indices: List[int]) -> List[List[int]]:
    """Group indices into contiguous ranges (module-level helper).

    Example:
        [0, 1, 3] -> [[0, 1], [3]]
    """
    if not indices:
        return []
    s = sorted(set(indices))
    groups: List[List[int]] = []
    cur: List[int] = [s[0]]
    for i in s[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    return groups


class KWMatcher(BaseMatcher):
    """Direct keyword-based matching via SimpleKeywordTableIndex.

    - Builds a keyword index over paragraphs and retrieves relevant nodes.
    - Returns selections as contiguous `paragraph_indices` ranges.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="li_keyword_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections for keyword matches."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.keywords if sq and sq.keywords else []
        paragraphs = split_paragraphs(content)
        docs = [
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
            md = getattr(getattr(sn, "node", sn), "metadata", {})
            idx = md.get("paragraph_index")
            if isinstance(idx, int):
                matched.append(idx)
        selections: List[Dict[str, Any]] = []
        for grp in _group_contiguous(matched):
            selections.append({"paragraph_indices": grp})
        return selections


class LMMatcher(BaseMatcher):
    """LLM-aware matching via LlamaIndex SummaryIndex.

    - Uses index summaries/LLM guidance to select relevant paragraphs.
    - Maps results back to contiguous `paragraph_indices`.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="li_llm_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections guided by LLM summaries."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.keywords if sq and sq.keywords else []
        paragraphs = split_paragraphs(content)
        docs = [
            Document(text=p["text"], metadata={"paragraph_index": p["index"]})
            for p in paragraphs
        ]
        index = SummaryIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        src = getattr(resp, "source_nodes", [])
        matched: List[int] = []
        for sn in src:
            md = getattr(getattr(sn, "node", sn), "metadata", {})
            idx = md.get("paragraph_index")
            if isinstance(idx, int):
                matched.append(idx)
        selections: List[Dict[str, Any]] = []
        for grp in _group_contiguous(matched):
            selections.append({"paragraph_indices": grp})
        return selections


class VectorMatcher(BaseMatcher):
    """RAG-style matching via embedding search with VectorStoreIndex.

    - Encodes paragraphs into vectors and retrieves nearest matches.
    - Outputs contiguous `paragraph_indices` ranges for downstream mapping.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="li_rag_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections via vector/RAG retrieval."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.keywords if sq and sq.keywords else []
        paragraphs = split_paragraphs(content)
        docs = [
            Document(text=p["text"], metadata={"paragraph_index": p["index"]})
            for p in paragraphs
        ]
        index = VectorStoreIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        src = getattr(resp, "source_nodes", [])
        matched: List[int] = []
        for sn in src:
            md = getattr(getattr(sn, "node", sn), "metadata", {})
            idx = md.get("paragraph_index")
            if isinstance(idx, int):
                matched.append(idx)
        selections: List[Dict[str, Any]] = []
        for grp in _group_contiguous(matched):
            selections.append({"paragraph_indices": grp})
        return selections
