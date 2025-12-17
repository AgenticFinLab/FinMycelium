from lmbase.inference.api_call import LangChainAPIInference, InferInput
from finmy.builder.class_build.prompts.ponzi_scheme import ponzi_scheme_prompt
import os
from dotenv import load_dotenv
import datetime
import json
from typing import Dict, Any
import re


def extract_json_response(response_text: str) -> Dict[str, Any]:
    """Extract a JSON object/array from an LLM response text.

    Behavior:
    - Strips markdown code fences if present (``` or ```json).
    - Attempts to parse the cleaned text directly as JSON.
    - If that fails, searches for the longest JSON object/array substring and parses it.
    - Raises ValueError if no valid JSON can be found.

    Examples:
    >>> t = "Response: OK. {\"b\": [1,2,3]}"
    >>> extract_json_response(t)
    {'b': [1, 2, 3]}
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


def save_event_cascade(event_cascade: Dict[str, Any], output_path: str = None) -> str:
    """
    Save event cascade data to JSON files in a structured directory.
    
    Args:
        event_cascade: Dictionary containing event cascade data
        output_path: Base directory for saving output (optional)
    
    Returns:
        Path to the created directory containing the saved JSON file
    """
    if output_path is None:
        output_path = "./examples/utest/Collector/test_files/event_cascade_output"

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    base_dir = os.path.join(output_path, f"event_cascade_{timestamp}")
    os.makedirs(base_dir, exist_ok=True)

    print(f"Saving event cascade to: {base_dir}")

    main_file = os.path.join(base_dir, "EventCascade.json")
    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(event_cascade, f, ensure_ascii=False, indent=2)
    print(f"Saved main event cascade to: {main_file}")

    return base_dir


def test_class_build():
    """Test function for building and processing event cascade from ponzi scheme analysis."""
    load_dotenv()
    
    # Load input text content
    all_text_content_path = r"examples\utest\Collector\test_files\All_Text_Content_20251217025828.json"
    with open(all_text_content_path, "r", encoding="utf-8") as f:
        all_text_content = json.load(f)
    
    print("Loaded text content:", all_text_content)

    # Test API connection with a simple message
    test_api_call = LangChainAPIInference(lm_name="ARK/doubao-seed-1-6-flash-250828")
    chatbot = InferInput(
        system_msg="Hello",
        user_msg="Test message",
    )
    result = test_api_call.run(chatbot)
    print("Test response:", result.response)

    # Prepare ponzi scheme prompt
    prompt_template = ponzi_scheme_prompt()
    # Escape curly braces for f-string safety
    escaped_prompt = prompt_template.replace("{", "{{").replace("}", "}}")
    
    # Make API call for detailed ponzi scheme analysis
    aihubmix_api_call = LangChainAPIInference(lm_name="ARK/doubao-seed-1-6-flash-250828")
    chatbot = InferInput(
        system_msg=escaped_prompt,
        user_msg=str(all_text_content) + escaped_prompt,
    )
    detailed_output = aihubmix_api_call.run(chatbot)

    print("Detailed output:", detailed_output.response)
    output_text = detailed_output.response.strip()

    # Extract and parse JSON response
    try:
        event_cascade_json = extract_json_response(output_text)
        saved_dir = save_event_cascade(
            event_cascade=event_cascade_json,
            output_path="./examples/utest/Collector/test_files/event_cascade_output"
        )
        print(f"Successfully saved event cascade to: {saved_dir}")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error processing JSON response: {e}")
        # Save raw response for debugging
        debug_dir = "./examples/utest/Collector/test_files/debug_output"
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = os.path.join(debug_dir, f"raw_response_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.txt")
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"Raw response saved to: {debug_file}")


if __name__ == "__main__":
    test_class_build()