"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
- Returns verbatim excerpts (no paraphrasing) with exact character positions.
"""

from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate

from .utils import split_paragraphs, get_paragraph_positions, safe_parse_json
from .base import MatchInput

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
{'paragraphs': contiguous indices from the list below,
 'reason': semantic explanation,
 'score': number 0-1}.
Do NOT paraphrase; copy text verbatim. Do NOT modify punctuation or spacing.
Include all relevant passages; skip unrelated text.
"""

HUMAN_PROMPT_TEMPLATE = (
    "Query: {query_text}\n"
    "Keywords: {keywords_joined}\n\n"
    "Targets (optional, each item is an intent to match):\n"
    "{targets_text}\n\n"
    "Paragraphs (use indices for 'paragraphs'):\n"
    "{paragraphs_text}\n\n"
    "Output strictly in JSON: {\n"
    '  "excerpts": [\n'
    "    {\n"
    '      "paragraphs": [0],\n'
    '      "reason": "...",\n'
    '      "score": 0.0\n'
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
    targets: Optional[List[str]] = None,
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
    targets_list = targets or []
    targets_text = (
        "\n".join([f"- {t}" for t in targets_list]) if targets_list else "- (none)"
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", sys_txt),
            ("human", human_txt),
        ]
    )
    return prompt.format_messages(
        query_text=query_text,
        keywords_joined=keywords_joined,
        targets_text=targets_text,
        paragraphs_text=paragraphs_text,
    )


def match_content_llm(
    query_text: str,
    key_words: List[str],
    content: str,
    model: Optional[str] = None,
    targets: Optional[List[str]] = None,
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
    messages = build_messages(query_text, key_words, content, targets=targets)
    llm = api_call.build_llm(model_override=model)
    resp = llm.invoke(messages)
    raw = resp.content

    data = safe_parse_json(raw)
    excerpts = data.get("excerpts", [])
    located = get_paragraph_positions(content, excerpts)
    return {"excerpts": located, "raw": raw}


def match_from_input(
    match_input: MatchInput, model: Optional[str] = None
) -> Dict[str, Any]:
    """Run matching based on `MatchInput.summarized_query`.

    - Uses `summarization` as main intent and `keywords` as guidance.
    - Searches in `match_data` and returns verbatim excerpts with positions.
    """
    sq = match_input.summarized_query
    query_text = sq.summarization if sq and sq.summarization else ""
    key_words = sq.keywords if sq and sq.keywords else []
    content = match_input.match_data or ""
    targets = [query_text] if query_text else None
    return match_content_llm(
        query_text=query_text,
        key_words=key_words,
        content=content,
        model=model,
        targets=targets,
    )


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
