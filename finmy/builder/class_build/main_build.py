"""
Class builder implementation for event cascade reconstruction using LLM.
"""

import json
import os
import re
from typing import Dict, Any, List, Optional

import logging

from lmbase.inference.api_call import LangChainAPIInference, InferInput
from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput, AgentState

# Import all prompt modules
from finmy.builder.class_build.prompts import (
    classify,
    ponzi_scheme,
    pyramid_scheme,
    pump_and_dump,
    market_manipulation,
    accounting_fraud,
    cryptocurrency_ico_scam,
    forex_binary_options_fraud,
    advance_fee_fraud,
    affinity_fraud,
    embezzlement_misappropriation_of_funds,
    bank_run,
    short_squeeze,
    sovereign_default,
    liquidity_spiral,
    regulatory_arbitrage,
    credit_event,
    systemic_shock,
    leverage_cycle_collapse,
    stablecoin_depeg,
    other_financial_event,
)


def format_user_prompt(query: str, keywords: List[str], content: str) -> str:
    """Format the user prompt with query, keywords, and content.

    Args:
        query: User query text
        keywords: List of keyword hints
        content: Text content for analysis

    Returns:
        Formatted user prompt string
    """
    return USER_PROMPT.format(
        Query=query,
        Keywords=", ".join(keywords),
        Content=content,
    )


USER_PROMPT = """
Task: Using the schema and rules defined in the system prompt, reconstruct the specific financial event strictly from the input Content below. Base all details on Content and follow the requirement in the Description and Keywords; do not invent, alter, or extend beyond what it explicitly supports. Produce a clear, layered, professional JSON output.

=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===

Generate content in JSON format according to the SYSTEM_PROMPT schema.
"""


class ClassEventBuilder(BaseBuilder):
    """Class builder for generating event cascades from text content using LLM.

    This builder implements a two-stage process:
    1. Classify the financial event type
    2. Generate detailed event cascade for the classified type
    """

    def __init__(
        self,
        method_name: Optional[str] = None,
        build_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the class builder.

        Args:
            method_name: Name of the builder method
            build_config: Configuration dictionary for the builder
        """
        super().__init__(method_name=method_name, build_config=build_config)

        # Initialize class prompts dictionary
        self.class_prompts = {
            "Ponzi Scheme": ponzi_scheme.ponzi_scheme_prompt(),
            "Pyramid Scheme": pyramid_scheme.pyramid_scheme_prompt(),
            "Pump and Dump": pump_and_dump.pump_and_dump_prompt(),
            "Market Manipulation": market_manipulation.market_manipulation_prompt(),
            "Accounting Fraud": accounting_fraud.accounting_fraud_prompt(),
            "Cryptocurrency / ICO Scam": cryptocurrency_ico_scam.cryptocurrency_ico_scam_prompt(),
            "Forex / Binary Options Fraud": forex_binary_options_fraud.forex_binary_options_fraud_prompt(),
            "Advance-Fee Fraud": advance_fee_fraud.advance_fee_fraud_prompt(),
            "Affinity Fraud": affinity_fraud.affinity_fraud_prompt(),
            "Embezzlement / Misappropriation of Funds": embezzlement_misappropriation_of_funds.embezzlement_misappropriation_of_funds_prompt(),
            "Bank Run": bank_run.bank_run_prompt(),
            "Short Squeeze": short_squeeze.short_squeeze_prompt(),
            "Sovereign Default": sovereign_default.sovereign_default_prompt(),
            "Liquidity Spiral": liquidity_spiral.liquidity_spiral_prompt(),
            "Regulatory Arbitrage": regulatory_arbitrage.regulatory_arbitrage_prompt(),
            "Credit Event": credit_event.credit_event_prompt(),
            "Systemic Shock": systemic_shock.systemic_shock_prompt(),
            "Leverage Cycle Collapse": leverage_cycle_collapse.leverage_cycle_collapse_prompt(),
            "Stablecoin Depeg": stablecoin_depeg.stablecoin_depeg_prompt(),
            "Other Financial Event": other_financial_event.other_financial_event_prompt(),
        }

        self.user_prompt = USER_PROMPT

    @staticmethod
    def extract_json_response(response_text: str) -> Dict[str, Any]:
        """Extract a JSON object/array from an LLM response text.

        Args:
            response_text: Raw response text from LLM

        Returns:
            Parsed JSON as dictionary

        Raises:
            ValueError: If no valid JSON can be found
        """
        clean_text = response_text.strip()

        # Remove code block markers if present
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL)
        if m:
            clean_text = m.group(1)

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            # Try to find JSON objects or arrays in the text
            matches = re.findall(r"(\{.*\}|\[.*\])", clean_text, re.DOTALL)
            if matches:
                longest = max(matches, key=len)
                return json.loads(longest)
            raise ValueError(f"Failed to parse JSON from response: {e}") from e

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """Execute exactly one stage using prompts from the provided state.

        Args:
            state: Current agent state
            agent_name: Name of the agent to execute

        Returns:
            Updated agent state after execution
        """
        # This builder uses a different pattern (not using LangGraph nodes)
        # So we implement a simplified version
        return state

    def graph(self):
        """Construct and compile the LangGraph for this agent or pipeline.

        Returns:
            A CompiledStateGraph with entry point and edges defined
        """
        # This builder doesn't use LangGraph, so return None
        return None

    def save_event_cascade(
        self, event_cascade: Dict[str, Any], output_path: str
    ) -> str:
        """Save event cascade data to JSON file.

        Args:
            event_cascade: Dictionary containing event cascade data
            output_path: Path to save the JSON file

        Returns:
            Path to the saved file
        """
        # Create directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        logging.info(f"Saving event cascade to: {output_path}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(event_cascade, f, ensure_ascii=False, indent=2)

        logging.info(f"Successfully saved event cascade to: {output_path}")
        return output_path

    def test_api_connection(self) -> str:
        """Test the API connection with a simple message.

        Returns:
            Response from the test call
        """
        test_api_call = LangChainAPIInference(lm_name=self.build_config["lm_name"])
        chatbot = InferInput(
            system_msg="Hello",
            user_msg="Test message",
        )
        result = test_api_call.run(chatbot)
        logging.info(f"Test response: {result.response}")
        return result.response

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Build and process event cascade from input data.

        Args:
            build_input: Input data container

        Returns:
            BuildOutput containing event cascades and results

        Raises:
            ValueError: If JSON parsing fails
            Exception: For other errors during processing
        """
        logging.info("Starting event cascade building process...")

        # Test API connection first
        self.test_api_connection()

        # Extract query information
        user_query = build_input.user_query
        query_text = user_query.query_text or ""
        keywords = user_query.key_words or []

        # Combine all sample content
        all_content = []
        for sample in build_input.samples:
            all_content.append(
                {
                    "sample_id": sample.sample_id,
                    "content": sample.content,
                    "category": sample.category,
                    "knowledge_field": sample.knowledge_field,
                }
            )

        # Create API call instance
        api_call = LangChainAPIInference(lm_name=self.build_config["lm_name"])

        # Stage 1: Classify event type
        logging.info("Classifying event type...")
        classify_chatbot = InferInput(
            system_msg=classify.classify_prompt().replace("{", "{{").replace("}", "}}"),
            user_msg=self.user_prompt.format(
                Query=query_text,
                Keywords=", ".join(keywords),
                Content=str(all_content[:200]),
            )
            + "\n\nSYSTEM PROMPT:\n\n"
            + classify.classify_prompt().replace("{", "{{").replace("}", "}}"),
        )

        classify_output = api_call.run(classify_chatbot)
        classify_output_text = classify_output.response.strip()
        logging.info(f"Classify output text: {classify_output_text}")

        classify_result = self.extract_json_response(classify_output_text)
        classify_event_type = classify_result["event_type"]["primary_type"]
        logging.info(f"Classified event type: {classify_event_type}")

        # Stage 2: Generate detailed event cascade
        logging.info(f"Generating detailed event cascade for: {classify_event_type}")
        event_prompt = self.class_prompts.get(
            classify_event_type, self.class_prompts["Other Financial Event"]
        )
        escaped_prompt = event_prompt.replace("{", "{{").replace("}", "}}")

        detailed_chatbot = InferInput(
            system_msg=escaped_prompt,
            user_msg=str(all_content) + "\n\n\n" + escaped_prompt,
        )

        detailed_output = api_call.run(detailed_chatbot)
        output_text = detailed_output.response.strip()
        logging.info("Received detailed output from LLM")

        # Try to parse JSON directly
        try:
            event_cascade_json = self.extract_json_response(output_text)
        except json.JSONDecodeError:
            # If direct parsing fails, try to format it
            logging.info("Direct JSON parsing failed, attempting to format response...")

            for i in range(3):
                try:
                    logging.info(f"Format attempt {i+1}")
                    format_chatbot = InferInput(
                        system_msg="You are a professional JSON format expert.",
                        user_msg=output_text.replace("{", "{{").replace("}", "}}")
                        + "\n\nPlease format the above text as a proper JSON object strictly. "
                        + "If there is any error in the format, please fix it. "
                        + "Don't add any extra text or change the content of the text. "
                        + "Only return the JSON object. "
                        + "You should ignore directly: "
                        + "(1) javascript:void((function(){{}})()); "
                        + "(2) document.open();document.domain='sogou.com';document.close();",
                    )

                    format_output = api_call.run(format_chatbot)
                    format_output_text = format_output.response.strip()
                    event_cascade_json = self.extract_json_response(format_output_text)
                    break

                except Exception as e:
                    logging.error(f"Format attempt {i+1} failed: {e}")
                    if i == 2:
                        raise ValueError(
                            f"Failed to parse JSON from LLM response after 3 attempts: {e}"
                        )

        # Save the event cascade
        output_path = os.path.join(
            self.save_dir,
            f"Class_Build_Event_Cascade_{classify_event_type.replace(' ', '_').replace('/', '_')}.json",
        )
        self.save_event_cascade(event_cascade_json, output_path)

        # Create BuildOutput
        build_output = BuildOutput(
            event_cascades=event_cascade_json,
            logs=[
                f"Classified event type: {classify_event_type}",
                f"Output saved to: {output_path}",
                f"Processing completed successfully",
            ],
            extras={
                "classified_event_type": classify_event_type,
                "output_file_path": output_path,
                "num_samples_processed": len(build_input.samples),
            },
        )

        return build_output
