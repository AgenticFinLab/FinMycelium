
# finmy/builder/class_build/simple_build.py

import json
import datetime
import re
import os
from typing import Dict, Any, Optional, List
from lmbase.inference.api_call import LangChainAPIInference, InferInput
from finmy.builder.class_build.prompts import *


def format_user_prompt(
    query: str,
    keywords: List[str],
    content: str,
) -> str:
    """Format the user prompt with query, keywords, and content."""
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
class ClassLMSimpleBuild:
    """Simple builder class for generating event cascades from text content using LLM."""
    
    def __init__(
        self,
        lm_name: str,
        all_text_content: List[Dict[str, Any]],
        output_file_path: str,
        query: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ):
        """
        Initialize the simple builder.
        
        Args:
            lm_name: Name of the language model to use
            prompt_template: Template for the prompt
            all_text_content: List of text content dictionaries
            output_file_path: Full path to the output JSON file
            system_msg: Optional custom system message (uses prompt_template if not provided)
        """
        self.lm_name = lm_name
        self.all_text_content = all_text_content
        self.output_file_path = output_file_path
        self.query = query or ""
        self.keywords = keywords or []

        self.user_prompt = USER_PROMPT

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
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL)
        if m:
            clean_text = m.group(1)
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            matches = re.findall(r"(\{.*\}|\[.*\])", clean_text, re.DOTALL)
            if matches:
                longest = max(matches, key=len)
                return json.loads(longest)
            raise ValueError(f"Failed to parse JSON from response: {e}") from e
    
    def save_event_cascade(self, event_cascade: Dict[str, Any]) -> str:
        """
        Save event cascade data to JSON file.
        
        Args:
            event_cascade: Dictionary containing event cascade data
            
        Returns:
            Path to the saved file
        """
        # Create directory if it doesn't exist
        output_dir = os.path.dirname(self.output_file_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        print(f"Saving event cascade to: {self.output_file_path}")
        
        with open(self.output_file_path, "w", encoding="utf-8") as f:
            json.dump(event_cascade, f, ensure_ascii=False, indent=2)
        
        print(f"Successfully saved event cascade to: {self.output_file_path}")
        return self.output_file_path
    
    def test_api_connection(self) -> str:
        """
        Test the API connection with a simple message.
        
        Returns:
            Response from the test call
        """
        test_api_call = LangChainAPIInference(lm_name=self.lm_name)
        chatbot = InferInput(
            system_msg="Hello",
            user_msg="Test message",
        )
        result = test_api_call.run(chatbot)
        print("Test response:", result.response)
        return result.response
    
    def build(self) -> Dict[str, Any]:
        """
        Build and process event cascade from text content.
        
        Returns:
            Parsed event cascade as dictionary
            
        Raises:
            ValueError: If JSON parsing fails
            Exception: For other errors during processing
        """
        print("Starting event cascade building process...")
        
        # Test API connection first
        self.test_api_connection()
        
    
        api_call = LangChainAPIInference(lm_name=self.lm_name)

        print("system_msg:", classify.classify_prompt().replace("{", "{{").replace("}", "}}"))
        classify_chatbot = InferInput(
            system_msg= classify.classify_prompt().replace("{", "{{").replace("}", "}}"),
            user_msg=  self.user_prompt.format(Query=self.query, Keywords=self.keywords, Content=str(self.all_text_content[:200])) + "\n\nSYSTEM PROMPT:\n\n"+ classify.classify_prompt().replace("{", "{{").replace("}", "}}"),
        )
        classify_output = api_call.run(classify_chatbot)
        classify_output_text = classify_output.response.strip()
        print("Classify output text:", classify_output_text)
        classify_event_type = self.extract_json_response(classify_output_text)["event_type"]["primary_type"]
        print(f"Classified event type: {classify_event_type}")

        # Get the prompt for the event type
        event_prompt = self.class_prompts.get(classify_event_type, self.class_prompts["Other Financial Event"])
        escaped_prompt = event_prompt.replace("{", "{{").replace("}", "}}")

        chatbot = InferInput(
            system_msg=escaped_prompt,
            user_msg=str(self.all_text_content) + "\n\n\n" + escaped_prompt,
        )
        detailed_output = api_call.run(chatbot)
        
        print("Received detailed output from LLM")
        output_text = detailed_output.response.strip()
        
    # Extract and parse JSON response
        try:
            format_chatbot = InferInput(
                system_msg="You are a professional JSON format expert.",
                user_msg=output_text.replace("{", "{{").replace("}", "}}") + "\n\nPlease format the above text as a proper JSON object strictly. If there is any error in the format, please fix it. Don't add any extra text or change the content of the text. Only return the JSON object. You should ignore directly: (1) javascript:void((function(){{}})()); (2) document.open();document.domain='sogou.com';document.close(); ",
            )
            format_output = api_call.run(format_chatbot)
            format_output_text = format_output.response.strip()
            print("Format output text:", format_output_text)

            event_cascade_json = self.extract_json_response(format_output_text)
            
            # Save the event cascade
            self.save_event_cascade(event_cascade_json)
            
            return event_cascade_json
            
        except:
            try: 
                print("Try to format the output text again...")
                format_chatbot = InferInput(
                    system_msg="You are a professional JSON format expert.",
                    user_msg=output_text.replace("{", "{{").replace("}", "}}") + "\n\nPlease format the above text as a proper JSON object strictly. If there is any error in the format, please fix it. Don't add any extra text or change the content of the text. Only return the JSON object. You should ignore directly: (1) javascript:void((function(){{}})()); (2) document.open();document.domain='sogou.com';document.close(); ",
                )
                format_output = api_call.run(format_chatbot)
                format_output_text = format_output.response.strip()
                print("Format output text:", format_output_text)
                event_cascade_json = self.extract_json_response(format_output_text)
                # Save the event cascade
                self.save_event_cascade(event_cascade_json)
                return event_cascade_json
            except Exception as e:
                print(f"Error processing JSON response: {e}")
                # Save raw response for debugging
                debug_dir = "./debug_output"
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(
                    debug_dir, 
                    f"raw_response_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
                )
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(output_text)
                print(f"Raw response saved to: {debug_file}")
                
                raise ValueError(f"Failed to parse JSON from LLM response: {e}") from e