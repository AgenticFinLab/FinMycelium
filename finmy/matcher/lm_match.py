"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
- Returns verbatim excerpts (no paraphrasing) with exact character positions.
"""

from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate

from .utils import split_paragraphs, get_subset_positions, safe_parse_json

from lmbase.inference import api_call

SYSTEM_PROMPT = (
    "You identify ALL semantically relevant information from the provided content, "
    "using the user's query and keywords as guidance (keywords are hints, not strict filters). "
    "Relevance MUST be semantic: include synonyms, references, and logically connected sentences. "
    "Select COMPLETE PARAGRAPHS. Prefer contiguous paragraph ranges when expanding context. "
    "Return ONLY JSON with key 'excerpts': each item contains: "
    "{'paragraph_indices': indices from the list below, 'quote': exact verbatim text, "
    " 'reason': semantic explanation, 'score': number 0-1, 'matched_keywords': subset of given keywords}. "
    "Do NOT paraphrase; copy text verbatim. Do NOT modify punctuation or spacing. "
    "Include all relevant passages; skip unrelated text."
)

HUMAN_PROMPT_TEMPLATE = (
    "Query: {query_text}\n"
    "Keywords: {keywords_joined}\n\n"
    "Paragraphs (use indices for 'paragraph_indices'):\n"
    "{paragraphs_text}\n\n"
    "Output strictly in JSON: {\n"
    '  "excerpts": [\n'
    "    {\n"
    '      "paragraph_indices": [0],\n'
    '      "quote": "...",\n'
    '      "reason": "...",\n'
    '      "score": 0.0,\n'
    '      "matched_keywords": ["..."]\n'
    "    }\n"
    "  ]\n"
    "}"
)

PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT_TEMPLATE),
    ]
)


def build_messages(
    query_text: str,
    key_words: List[str],
    content: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
):
    """Construct chat messages using a template with string content.

    Accepts optional `system_prompt` and `user_prompt`. When omitted,
    defaults to `SYSTEM_PROMPT` and `HUMAN_PROMPT_TEMPLATE`.
    """
    paragraphs = split_paragraphs(content)
    keywords_joined = ", ".join(key_words)
    parts = []
    for p in paragraphs:
        idx = p.get("index")
        txt = p.get("text")
        parts.append(f"[{idx}] >>> {txt}")
    paragraphs_text = "\n\n".join(parts)

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
        paragraphs_text=paragraphs_text,
    )


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
    llm = api_call.build_llm(model_override=model)
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
