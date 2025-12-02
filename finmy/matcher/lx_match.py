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
