"""
LLM-powered semantic extraction of relevant content spans from long text.

- Focuses on semantic relevance guided by `query_text` and `key_words`.
- Prefers selecting complete and contiguous paragraphs for context preservation.
"""

from typing import List, Any, Optional, Union
import json

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
{{'paragraph_indices': paragraph indices,
'quote': related content segment,
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
      "paragraph_indices": an int, 
      "quote": "...",
      "reason": "...",
      "score": a float ranging from 0.0 to 1.0
    }},
    {{
      "paragraph_indices": an int, 
      "quote": "...",
      "reason": "...",
      "score": a float ranging from 0.0 to 1.0
    }},
    {{
      "paragraph_indices": an int, 
      "quote": "...",
      "reason": "...",
      "score": a float ranging from 0.0 to 1.0
    }},
    ...
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
        print("Output Response:")
        print(output.response)

        # Define the expected schema for validation
        EXPECTED_KEYS = {"paragraph_indices", "quote", "reason", "score"}
        SCHEMA_TEMPLATE = """[
            {
            "paragraph_indices": an int, 
            "quote": "...",
            "reason": "...",
            "score": a float ranging from 0.0 to 1.0
            }
        ]"""

        try:
            # Clean the response before parsing
            # Clean the response text by removing Markdown code block markers and whitespace.
            # Remove ```json and ``` markers
            output_text = output.response.strip()
            if output_text.startswith("```json"):
                output_text = output_text[7:]  # Remove ```json
            elif output_text.startswith("```"):
                output_text = output_text[3:]  # Remove ```
            if output_text.endswith("```"):
                output_text = output_text[:-3]  # Remove ```

            cleaned_response = output_text.strip()

            # Attempt to parse JSON
            parsed_response = safe_parse_json(cleaned_response)

            if parsed_response is None:
                # If safe_parse_json still fails, try standard json.loads
                try:
                    import json

                    parsed_response = json.loads(cleaned_response)
                except json.JSONDecodeError as json_err:
                    raise ValueError(
                        f"Failed to parse response as JSON. Error: {str(json_err)}\n"
                        f"Cleaned response text:\n{cleaned_response}\n\n"
                        f"Expected schema:\n{SCHEMA_TEMPLATE}"
                    )

            # Normalize to list
            if not isinstance(parsed_response, list):
                parsed_response = [parsed_response]

            # Validate each item in the list
            validated_items = []
            for idx, item in enumerate(parsed_response):
                if not isinstance(item, dict):
                    raise TypeError(
                        f"Item at index {idx} is not a JSON object (dict). "
                        f"Received type: {type(item)}. All items must be objects.\n"
                        f"Expected schema:\n{SCHEMA_TEMPLATE}"
                    )

                # Check for missing keys
                item_keys = set(item.keys())
                missing_keys = EXPECTED_KEYS - item_keys
                if missing_keys:
                    raise KeyError(
                        f"Item at index {idx} is missing required keys: {missing_keys}. "
                        f"Found keys: {item_keys}. Expected keys: {EXPECTED_KEYS}.\n"
                        f"Expected schema:\n{SCHEMA_TEMPLATE}"
                    )

                # Validate 'paragraph_indices' type
                if not isinstance(item["paragraph_indices"], int):
                    raise TypeError(
                        f"Item at index {idx}: 'paragraph_indices' must be an integer. "
                        f"Received type: {type(item['paragraph_indices'])} with value: {item['paragraph_indices']}."
                    )

                # Validate 'score' type and range
                score = item["score"]
                if not isinstance(score, (int, float)):
                    raise TypeError(
                        f"Item at index {idx}: 'score' must be a float. "
                        f"Received type: {type(score)} with value: {score}."
                    )

                # Convert to float for range check
                try:
                    score_float = float(score)
                except ValueError:
                    raise ValueError(
                        f"Item at index {idx}: 'score' cannot be converted to float. "
                        f"Value: {score}."
                    )

                if not (0.0 <= score_float <= 1.0):
                    raise ValueError(
                        f"Item at index {idx}: 'score' must be between 0.0 and 1.0. "
                        f"Received value: {score_float}."
                    )

                # Validate 'quote' and 'reason' are strings
                if not isinstance(item["quote"], str):
                    raise TypeError(
                        f"Item at index {idx}: 'quote' must be a string. "
                        f"Received type: {type(item['quote'])}."
                    )
                if not isinstance(item["reason"], str):
                    raise TypeError(
                        f"Item at index {idx}: 'reason' must be a string. "
                        f"Received type: {type(item['reason'])}."
                    )

                validated_items.append(item)

            output.response = validated_items
            return [item["quote"] for item in output.response]

        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            error_msg = (
                f"LLM response validation failed: {str(e)}\n\n"
                f"Raw LLM output:\n{output.response}\n\n"
                f"Cleaned output:\n{cleaned_response if 'cleaned_response' in locals() else 'N/A'}\n\n"
                f"Expected JSON schema:\n{SCHEMA_TEMPLATE}\n"
                f"Please ensure the LLM outputs strictly adhere to the specified JSON format."
            )
            raise ValueError(error_msg) from e
