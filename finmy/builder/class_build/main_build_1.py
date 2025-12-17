"""
Class-based financial event reconstruction builder.

This builder first classifies the financial event type using LM, then applies
class-specific prompts for detailed event reconstruction.
"""

import re
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from lmbase.inference.base import InferInput, InferOutput
from lmbase.inference import api_call

from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.converter import read_text_data_from_block
from finmy.builder.class_build.prompts import *
from finmy.builder.utils import extract_json_response


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


class ClassLMBuilder(BaseBuilder):
    """
    Build financial event cascade using classification-first approach.
    First classifies event type, then applies class-specific prompts.
    """

    def __init__(self, lm_name: str = "deepseek/deepseek-chat", config=None):
        super().__init__(method_name="class_lm_builder", config={"lm_name": lm_name})

        generation_config = (
            {} if "generation_config" not in config else config["generation_config"]
        )
        self.lm_api = api_call.LangChainAPIInference(
            lm_name=lm_name,
            generation_config=generation_config,
        )

        self.user_prompt = (
            USER_PROMPT if "user_prompt" not in config else config["user_prompt"]
        )

        self.output_dir = config.get(
            "output_dir", "./examples/utest/Collector/test_files/event_cascade_output"
        )

        # Map event types to their specific prompts
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

    def save_event_cascade(
        self, event_cascade: Dict[str, Any], output_path: str = None
    ):
        """
        Save event cascade data to JSON files in a structured directory.
        """
        if output_path is None:
            output_path = self.output_dir

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base_dir = os.path.join(output_path, f"event_cascade_{timestamp}")
        os.makedirs(base_dir, exist_ok=True)

        print(f"Saving event cascade to: {base_dir}")

        if "FinancialEventReconstruction" in event_cascade:
            event_data = event_cascade["FinancialEventReconstruction"]
        else:
            event_data = event_cascade

        main_file = os.path.join(base_dir, "EventCascade.json")
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(event_data, f, ensure_ascii=False, indent=2)
        print(f"Saved main event cascade to: {main_file}")

        if "stages" in event_data:
            stages_dir = os.path.join(base_dir, "stages")
            os.makedirs(stages_dir, exist_ok=True)

            stages = event_data["stages"]
            if isinstance(stages, list):
                for idx, stage in enumerate(stages):
                    if isinstance(stage, dict):
                        sid = stage.get("stage_id", f"S{idx+1}")
                        stage_file = os.path.join(stages_dir, f"{sid}.json")
                        with open(stage_file, "w", encoding="utf-8") as f:
                            json.dump(stage, f, ensure_ascii=False, indent=2)
                        print(f"✓ Saved stage {sid} to: {stage_file}")

        return base_dir

    def load_samples(self, build_input: BuildInput) -> Any:
        """Load the specific content of samples from the files."""
        samples_content = "\n\n".join(
            [
                read_text_data_from_block(sample.location)
                for sample in build_input.samples
            ]
        )
        print(f"Loaded {len(build_input.samples)} samples")
        return samples_content

    def build(self, build_input: BuildInput) -> BuildOutput:
        """Build the event cascades from the input samples."""
        samples_content = self.load_samples(build_input)

        # First step: Classify the event type
        print("classify.classify_prompt():\n", classify.classify_prompt())

        classification_output: InferOutput = self.lm_api.run(
            infer_input=InferInput(
                system_msg=classify.classify_prompt()
                .replace("{", "{{")
                .replace("}", "}}"),
                user_msg=self.user_prompt,
            ),
            Query=build_input.user_query.query_text,
            Keywords=build_input.user_query.key_words,
            Content=samples_content,
        )

        event_classify_json = extract_json_response(classification_output.response)
        print("Classification json:\n", event_classify_json)

        primary_type = event_classify_json["event_type"]["primary_type"]

        if primary_type in self.class_prompts:
            # Second step: Apply class-specific prompt for detailed reconstruction
            detailed_output: InferOutput = self.lm_api.run(
                infer_input=InferInput(
                    system_msg=self.class_prompts[primary_type]
                    .replace("{", "{{")
                    .replace("}", "}}"),
                    user_msg=self.user_prompt,
                ),
                Query=build_input.user_query.query_text,
                Keywords=build_input.user_query.key_words,
                Content=samples_content,
            )

            # Extract and save JSON
            try:
                print(detailed_output.response)
                output_text = detailed_output.response.strip()

                # Clean JSON response
                if output_text.startswith("```json"):
                    output_text = output_text[7:]
                elif output_text.startswith("```"):
                    output_text = output_text[3:]
                if output_text.endswith("```"):
                    output_text = output_text[:-3]

                cleaned_response = output_text.strip()
                event_cascade_json = extract_json_response(cleaned_response)
                saved_dir = self.save_event_cascade(event_cascade_json)
                print(f"Successfully saved event cascade to directory: {saved_dir}")
            except Exception as e:
                print(f"Warning: Failed to save JSON files: {e}")
                raw_output_path = os.path.join(
                    self.output_dir, "build_out_raw_response.json"
                )
                os.makedirs(self.output_dir, exist_ok=True)
                with open(raw_output_path, "w", encoding="utf-8") as f:
                    f.write(detailed_output.response)
                print(f"Raw response saved to: {raw_output_path}")

            return BuildOutput(event_cascades=[detailed_output.response])

        else:
            print(f"Warning: Unsupported event type '{primary_type}'")
            return BuildOutput(event_cascades=[classification_output.response])
