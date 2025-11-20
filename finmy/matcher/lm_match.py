"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
- Returns verbatim excerpts (no paraphrasing) with exact character positions.
"""

import json
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from .utils import split_paragraphs, get_subset_positions, safe_parse_json


def build_messages(query_text: str, key_words: List[str], content: str):
    """Construct chat messages for the extraction request.

    - The system message enforces output as JSON and forbids paraphrasing.
    - The human message carries the query, keywords, and the original content.
    - The returned messages are consumed directly by `ChatOpenAI.invoke`.

    Expected JSON schema (illustrative):
    {
      "excerpts": [
        {
          "paragraph_indices": [0, 1],
          "quote": "verbatim excerpt covering selected paragraphs",
          "reason": "short semantic explanation",
          "score": 0.87,
          "matched_keywords": ["risk management", "ai"]
        }
      ]
    }
    """
    # The system message emphasizes semantic relevance over lexical match.
    # Keywords act as guidance signals, not hard filters. The model is instructed
    # to return complete paragraphs and to prefer contiguous ranges when expanding context.
    system = (
        "You identify ALL semantically relevant information from the provided content, "
        "using the user's query and keywords as guidance (keywords are hints, not strict filters). "
        "Relevance MUST be semantic: include synonyms, references, and logically connected sentences. "
        "Select COMPLETE PARAGRAPHS. Prefer contiguous paragraph ranges when expanding context. "
        "Return ONLY JSON with key 'excerpts': each item contains: "
        "{'paragraph_indices': contiguous indices from provided 'paragraphs', 'quote': exact substring from content covering those paragraphs, "
        " 'reason': semantic relevance explanation, 'score': number 0-1, 'matched_keywords': [subset of given keywords that apply]}. "
        "Do NOT paraphrase; copy text verbatim. Do NOT modify punctuation or spacing. "
        "Include all relevant passages; skip unrelated text."
    )
    # Split the content by blank lines to create a paragraph list with offsets.
    # This allows the model to choose paragraph indices explicitly.
    paragraphs = split_paragraphs(content)
    # Payload that the model uses to determine relevance and select complete paragraphs.
    user_payload = {
        "query_text": query_text,
        "keywords": key_words,
        "content": content,
        "paragraphs": paragraphs,
        "format": {
            "excerpts": [
                {
                    "paragraph_indices": [0],
                    "quote": "...",
                    "reason": "...",
                    "score": 0.0,
                    "matched_keywords": ["..."],
                }
            ]
        },
    }
    return [
        SystemMessage(content=system),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
    ]


def match_content_llm(
    query_text: str,
    key_words: List[str],
    content: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the LLM extraction and return verbatim excerpts with positions.

    Parameters:
    - query_text: semantic intent used to guide selection.
    - key_words: hint keywords; guidance signals, not hard filters.
    - content: full text to extract from.
    - model: optional model name for `ChatOpenAI`.

    Returns:
    - dict with `excerpts` (normalized entries with `text`, `start`, `end`, etc.) and `raw` (model raw JSON string).

    Process:
    1) Build system/human messages (with `paragraphs` offsets) and invoke the chat model.
    2) Parse JSON robustly (`safe_parse_json`).
    3) Normalize and locate excerpts (`get_subset_positions`).
    """
    messages = build_messages(query_text, key_words, content)
    llm = build_llm(model_override=model)
    resp = llm.invoke(messages)
    raw = resp.content

    data = safe_parse_json(raw)
    excerpts = data.get("excerpts", [])
    located = get_subset_positions(content, excerpts)
    return {"excerpts": located, "raw": raw}


class ExtractState(TypedDict):
    """State schema for the LangGraph single-node pipeline."""

    query_text: str
    key_words: List[str]
    content: str
    model: Optional[str]
    result: Optional[Dict[str, Any]]


def run_extract_node(state: ExtractState) -> ExtractState:
    """Execute extraction and store the result in state."""
    result = match_content_llm(
        state["query_text"], state["key_words"], state["content"], state.get("model")
    )
    state["result"] = result
    return state


def build_extract_app():
    """Build and return the compiled LangGraph app for extraction.

    The returned app can be reused across modules. It expects an `ExtractState`
    dict as input and produces a state with `result` populated by
    `match_content_with_llm`.
    """
    graph = StateGraph(ExtractState)
    graph.add_node("extract", run_extract_node)
    graph.set_entry_point("extract")
    graph.add_edge("extract", END)
    return graph.compile()
