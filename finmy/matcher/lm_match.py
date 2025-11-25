"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
- Returns verbatim excerpts (no paraphrasing) with exact character positions.
"""

from typing import List, Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate

from .utils import safe_parse_json
from .base import MatchInput, MatchBase

from lmbase.inference import api_call

SYSTEM_PROMPT = """
You identify ALL semantically relevant information from the provided content,
using the user's query and keywords as guidance (keywords are hints, not strict filters).
Relevance MUST be semantic: include synonyms, references, and logically connected sentences. Treat relevance broadly: surface similar or closely related content such as supporting facts, data points, figures, examples, events, news, regulations, timelines, names, places, references, and any information that materially relates to the query's intent—even when
the exact keywords do not appear. Keywords are soft signals to guide selection, never hard filters.
Select COMPLETE PARAGRAPHS. Prefer contiguous paragraph ranges when expanding context.
Return ONLY JSON: output EACH related content segment as a SEPARATE item.
A content segment is a series of consecutive paragraphs forming one coherent relevant unit.
For each item, include ONLY three keys:
{'paragraphs': related content segment,
 'reason': semantic explanation,
 'score': number 0-1}.
Do NOT paraphrase; copy text verbatim. Do NOT modify punctuation or spacing.
Include all relevant passages; skip unrelated text.
"""

HUMAN_PROMPT_TEMPLATE = """
Query: {query_text}
Keywords: {keywords_joined}

Please match the related paragraphs from the following content:
{content}

Output each matched item containing the content segment that are continuous paragraphs, strictly in JSON: [
    {
      "paragraphs": "...",
      "reason": "...",
      "score": a float ranging from 0.0 to 0.1
    }
]
"""


class LLMMatcher(MatchBase):
    """
    LLM-based matcher that extracts semantically relevant content.
    """

    def __init__(
        self,
        lm_name: Optional[str] = None,
        config: Optional[dict] = None,
    ):

        super().__init__(config=config, method_name="lm_match")
        # LLM model name to use for inference
        self.model_name = lm_name

    def _build_messages(
        self,
        query_text: str,
        key_words: List[str],
        target_content: str,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ):
        """Construct system/human messages for the chat model.

        - Splits content into paragraphs with indices
        - Injects query, keywords, and full target_content into the template
        """
        keywords_joined = ", ".join(key_words)
        sys_txt = system_prompt or SYSTEM_PROMPT
        human_txt = user_prompt or HUMAN_PROMPT_TEMPLATE

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", sys_txt),
                ("human", human_txt),
            ]
        )
        return prompt.format_messages(
            query_text=query_text,
            keywords_joined=keywords_joined,
            targets_content=target_content,
        )

    def _invoke_llm(self, messages) -> str:
        """Invoke the LLM with prepared messages and return raw content."""
        llm = api_call.build_llm(model_override=self.model_name)
        resp = llm.invoke(messages)
        return resp.content

    def _parse_items(self, raw: str) -> List[Dict[str, Any]]:
        """Parse model JSON into position-ready selection items.

        Accepts either a list of items or an object with `excerpts`.
        Converts each to `{"paragraph_indices": [...]}` for downstream mapping.
        """
        data = safe_parse_json(raw)
        items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict):
                    idxs = it.get("paragraphs") or []
                    if isinstance(idxs, list) and all(isinstance(i, int) for i in idxs):
                        items.append({"paragraph_indices": idxs})
        elif isinstance(data, dict):
            for it in data.get("excerpts", []):
                if isinstance(it, dict):
                    idxs = it.get("paragraphs") or it.get("paragraph_indices") or []
                    if isinstance(idxs, list) and all(isinstance(i, int) for i in idxs):
                        items.append({"paragraph_indices": idxs})
        return items

    def match(self, match_input: MatchInput) -> List[Dict[str, Any]]:
        """Produce selection dicts representing matched paragraph ranges.

        - Uses `summarization` as the primary intent and `keywords` as hints
        - Returns a list of dicts with `paragraph_indices` for position mapping
        """
        sq = match_input.summarized_query
        messages = self._build_messages(
            query_text=sq.summarization,
            key_words=sq.keywords,
            target_content=match_input.match_data,
        )
        raw = self._invoke_llm(messages)
        return self._parse_items(raw)
