"""
Test file for ClassLMSimpleBuild builder.
"""

import os
import sys
from pathlib import Path
import json
import yaml

from dotenv import load_dotenv

from finmy.builder.class_build.main_build import ClassEventBuilder
from finmy.builder.base import BuildInput
from finmy.generic import UserQueryInput, DataSample


def sample_content():
    with open(r"examples\utest\Collector\test_files\All_Text_Content_20251218171844.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        data_str=print("\n\n".join(data))
        return data_str
        

def test_class_build(content: list, query: str, keywords: list, config_path: str):
    """Test the ClassEventBuild with a simple input."""
    load_dotenv()

    print("Starting ClassEventBuild test...")
    
    # Create test data samples
    test_samples = [
        DataSample(
            sample_id="test_sample_001",
            raw_data_id="raw_001",
            content=content,
            category = None,  
            knowledge_field = None,
            tag="Test",
            method="Manual Entry"
        )
    ]
    
    # Create user query input
    user_query = UserQueryInput(
        user_query_id="test_query_001",
        query_text = query,
        key_words = keywords,
        time_range=None,
        extras={"test": True}
    )
    
    # Create build input
    build_input = BuildInput(
        user_query=user_query,
        samples=test_samples
    )
    
    # Create builder configuration
    # build_config = {
    #     "lm_type": "api",
    #     "lm_name": "ARK/doubao-seed-1-6-flash-250828",  # Replace with your preferred model
    #     "generation_config": {
    #         "temperature": 0.7,
    #         "max_tokens": 2000,
    #     },
    #     "agents": {},
    #     "save_folder": "./output"
    # }

    with open(config_path, "r", encoding="utf-8") as f:
        build_config = yaml.safe_load(f)

    # Initialize builder
    builder = ClassEventBuilder(
        method_name="class_build",
        build_config=build_config
    )
    
    # Run build process
    try:
        build_output = builder.build(build_input)
        
        print("\n=== Build Output ===")
        print(f"Success: {build_output.result is not None}")
        print(f"Logs: {build_output.logs}")
        print(f"Extras: {build_output.extras}")
        
        if build_output.result:
            print(f"\nResult type: {type(build_output.result)}")
            print(f"Result keys: {list(build_output.result.keys())}")
            
            # Print first few keys of the result
            
            print("\nResult preview:")
            print(json.dumps(build_output.result, indent=2)[:500] + "...")
        
        print("\nTest completed successfully!")
        return True
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Create test output directory
    os.makedirs("./test_output", exist_ok=True)
    query = "硅谷银行是怎么回事？"
    keywords = ["scheme", "investors"]
    config_path = "configs\pipline.yml"
    # Run test
    success = test_class_build(
        content=sample_content(),
        query=query,
        keywords=keywords,
        config_path=config_path
    )
    
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)