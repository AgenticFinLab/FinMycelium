# test.py

import json
import os
import datetime
from dotenv import load_dotenv

from finmy.builder.class_build.simple_build import ClassLMSimpleBuild
from finmy.builder.class_build.prompts.ponzi_scheme import ponzi_scheme_prompt


def test_class_lm_simple_build():
    """Test the ClassLMSimpleBuild class."""
    
    # Load sample data
    load_dotenv()
    all_text_content_path = r"examples\utest\Collector\test_files\All_Text_Content_20251217025828.json"
    with open(all_text_content_path, "r", encoding="utf-8") as f:
        all_text_content = json.load(f)
    
    # Define parameters
    lm_name = "ARK/doubao-seed-1-6-flash-250828"
    
    
    prompt_template = ponzi_scheme_prompt()
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # Define output path
    output_file_path = rf"./examples/utest/Collector/test_files/event_cascade_output/EventCascade_{timestamp}.json"
    
    # Create and run the builder
    builder = ClassLMSimpleBuild(
        lm_name=lm_name,
        all_text_content=all_text_content,
        output_file_path=output_file_path,
        query="蓝天格锐是怎么骗人的？",
        keywords=["蓝天格锐"],
    )
    
    try:
        event_cascade = builder.build()
        print(f"Successfully built event cascade: {event_cascade}")
        return event_cascade
    except Exception as e:
        print(f"Error during building: {e}")
        raise


if __name__ == "__main__":
    test_class_lm_simple_build()