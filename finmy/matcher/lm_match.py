"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
"""

from typing import List, Any, Optional, Union

from lmbase.inference import api_call
from lmbase.inference.base import InferInput

from .utils import safe_parse_json
from .base import MatchInput, BaseMatcher


SYSTEM_PROMPT = """
You identify ALL semantically relevant information from the provided content,
using the user's query and keywords as guidance (keywords are hints, not strict filters).
Relevance MUST be semantic: include synonyms, references, and logically connected sentences. Treat relevance broadly: surface similar or closely related content such as supporting facts, data points, figures, examples, events, news, regulations, timelines, names, places, references, and any information that materially relates to the query's intent—even when
the exact keywords do not appear. Keywords are soft signals to guide selection, never hard filters.
Select COMPLETE PARAGRAPHS. Prefer contiguous paragraph ranges when expanding context.
Return ONLY JSON: output EACH related content segment as a SEPARATE item.
A content segment is a series of consecutive paragraphs forming one coherent relevant unit.
For each item, include ONLY three keys:
{{'paragraphs': related content segment,
 'reason': semantic explanation,
 'score': number 0-1}}.
Do NOT paraphrase; copy text verbatim. Do NOT modify punctuation or spacing.
Include all relevant passages; skip unrelated text.
"""

HUMAN_PROMPT_TEMPLATE = """
Query: {query_text}
Keywords: {keywords_joined}

Please match the related paragraphs from the following content:
{content}

Output each matched item containing the content segment that are continuous paragraphs, strictly in JSON: [
    {{
      "paragraphs": "...",
      "reason": "...",
      "score": a float ranging from 0.0 to 1.0
    }}
]
"""


class LLMMatcher(BaseMatcher):
    """
    LLM-based matcher that extracts semantically relevant content.
    """

    def __init__(
        self,
        lm_name: Optional[str] = None,
        config: Optional[dict] = dict(),
    ):

        super().__init__(config=config, method_name="lm_match")
        # LLM model name to use for inference
        self.model_name = lm_name

        self.api_infer = api_call.LangChainAPIInference(
            lm_name=self.model_name,
            generation_config=self.config,
        )

    def match(self, match_input: MatchInput) -> List[Union[str, Any]]:
        """Produce selection dicts representing matched paragraph ranges.

        - Uses `summarization` as the primary intent and `keywords` as hints
        - Returns a list of dicts with `paragraph_indices` for position mapping
        """
        sq = match_input.summarized_query
        # Obtain the inference output `base.InferOutput`
        output = self.api_infer.run(
            infer_input=InferInput(
                system_msg=self.config.get("system_prompt", SYSTEM_PROMPT),
                user_msg=self.config.get("user_prompt", HUMAN_PROMPT_TEMPLATE),
            ),
            query_text=sq.summarization,
            keywords_joined=sq.key_words,
            content=match_input.match_data,
        )

        # Automatically parse and normalize response from LLM
        # TODO: It's better to use Pydantic schemas to strictly validate response structure,
        # ensuring each item has the required "paragraphs", "reason", and "score" fields with proper types.
        # For now, we only parse as list/dict.
        output.response = safe_parse_json(output.response)
        if not isinstance(output.response, list):
            output.response = [output.response]
        return output.response
