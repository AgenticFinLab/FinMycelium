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

import os
from typing import List, Dict, Any, Optional, Tuple

from llama_index.core import (
    Document,
    SimpleKeywordTableIndex,
    SummaryIndex,
    VectorStoreIndex,
    Settings,
)
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.openai import OpenAIEmbedding

from .base import MatchInput, BaseMatcher
from .utils import split_paragraphs, SplitParagraph


class LXMatcherBase(BaseMatcher):
    def __init__(
        self, config: Optional[dict] = None, method_name: Optional[str] = None
    ):
        super().__init__(config=config, method_name="lx_match")
        self.context_chars: int = (config or {}).get("context_chars", 96)
        self.top_k: int = int((config or {}).get("top_k", 8))
        self.llm = self._build_llm()
        self.embed_model = self._build_embed_model()
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model

    def _build_llm(self):
        return OpenAILike(
            model=os.getenv("LLAMA_INDEX_LLM_MODEL_NAME"),
            api_key=os.getenv("LLAMA_INDEX_LLM_MODEL_API_KEY"),
            api_base=os.getenv("LLAMA_INDEX_LLM_MODEL_BASE_URL"),
            is_chat_model=True,
        )

    def _build_embed_model(self):
        return OpenAIEmbedding(
            model_name="text-embedding-v4",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=os.getenv("LLAMA_INDEX_EMBEDDING_API_KEY"),
            use_api=True,
        )

    def _get_matches_from_lx_response(self, resp) -> List[str]:
        """
        Extracts matched text segments from the LlamaIndex response.

        Hint:
            The LlamaIndex query response object typically contains a 'source_nodes' attribute,
            which holds the retrieved nodes (such as paragraph segments) relevant to the query.
            This method collects the text content from these nodes for further processing or output.

        Args:
            resp: LlamaIndex query response, expected to include 'source_nodes'.

        Returns:
            List of matched text strings extracted from the response.
        """
        src = getattr(
            resp, "source_nodes", []
        )  # nodes with scoring/metadata, may be empty if no matches
        matched: List[str] = []
        for sn in src:
            # Each 'sn' is a node object; retrieve its text content.
            matched.append(sn.get_text())

        return matched


class LXMatcher(LXMatcherBase):
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
        super().__init__(config=config, method_name="lx_kw_match")
        self.context_chars: int = (config or {}).get("context_chars", 96)
        self.top_k: int = int((config or {}).get("top_k", 8))

    def _match_with_llamaindex(
        self,
        content: str,
        query_text: str,
        keywords: List[str],
    ) -> List[str]:
        """Retrieve relevant paragraphs via SimpleKeywordTableIndex.

        - Converts each paragraph to a `Document` with `paragraph_index` metadata.
        - Builds a keyword-table index and queries with query_text + keywords.
        - Maps `source_nodes` back to paragraph indices.
        """
        paragraphs: List[SplitParagraph] = split_paragraphs(content)  # [{index, text}]
        docs: List[Document] = [Document(text=p.text) for p in paragraphs]
        index = SimpleKeywordTableIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            # Attach keyword hints to guide retrieval
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        return self._get_matches_from_lx_response(resp)

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

    def match(self, match_input: MatchInput) -> List[str]:
        """Return selections of contiguous paragraph indices.

        Current strategy:
        - Use SimpleKeywordTableIndex-based retrieval with `summarization` and
          `keywords` hints; no content modification.
        """
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        summarization = sq.summarization if sq and sq.summarization else ""
        keywords = sq.key_words if sq and sq.key_words else []

        # Use LlamaIndex for matching
        li_selections = self._match_with_llamaindex(
            content=content, query_text=summarization, keywords=keywords
        )
        return li_selections


class KWMatcher(LXMatcherBase):
    """Direct keyword-based matching via SimpleKeywordTableIndex.

    - Builds a keyword index over paragraphs and retrieves relevant nodes.
    - Returns selections as contiguous `paragraph_indices` ranges.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="lx_keyword_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections for keyword matches."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.key_words if sq and sq.key_words else []
        paragraphs = split_paragraphs(content)
        docs: List[Document] = [Document(text=p.text) for p in paragraphs]
        index = SimpleKeywordTableIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        return self._get_matches_from_lx_response(resp)


class LMMatcher(LXMatcherBase):
    """LLM-aware matching via LlamaIndex SummaryIndex.

    - Uses index summaries/LLM guidance to select relevant paragraphs.
    - Maps results back to contiguous `paragraph_indices`.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="lx_llm_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections guided by LLM summaries."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.key_words if sq and sq.key_words else []
        paragraphs = split_paragraphs(content)
        docs: List[Document] = [Document(text=p.text) for p in paragraphs]
        index = SummaryIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        return self._get_matches_from_lx_response(resp)


class VectorMatcher(LXMatcherBase):
    """RAG-style matching via embedding search with VectorStoreIndex.

    - Encodes paragraphs into vectors and retrieves nearest matches.
    - Outputs contiguous `paragraph_indices` ranges for downstream mapping.
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config=config, method_name="lx_vector_match")
        self.top_k: int = int((config or {}).get("similarity_top_k", 8))

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Return contiguous paragraph index selections via vector/RAG retrieval."""
        content = match_input.match_data or ""
        sq = match_input.summarized_query
        query_text = sq.summarization if sq and sq.summarization else ""
        keywords = sq.key_words if sq and sq.key_words else []
        paragraphs = split_paragraphs(content)
        docs: List[Document] = [Document(text=p.text) for p in paragraphs]
        index = VectorStoreIndex.from_documents(docs)
        q = query_text.strip()
        if keywords:
            q = f"{q} \nKeywords: " + ", ".join(k.strip() for k in keywords if k)
        qe = index.as_query_engine(similarity_top_k=self.top_k)
        resp = qe.query(q)
        return self._get_matches_from_lx_response(resp)
