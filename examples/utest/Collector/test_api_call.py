from lmbase.inference.api_call import LangChainAPIInference, InferInput
from finmy.builder.class_build.prompts.ponzi_scheme import ponzi_scheme_prompt
import os
from dotenv import load_dotenv
import datetime
import json
import re


def clean_json_response(response_text):
    """Clean AI JSON response, remove possible Markdown tags"""
    # Remove leading/trailing whitespace
    response_text = response_text.strip()
    
    # Remove Markdown code block tags
    if response_text.startswith("```json"):
        response_text = response_text[7:]  # Remove ```json
    elif response_text.startswith("```"):
        response_text = response_text[3:]  # Remove ```
    
    if response_text.endswith("```"):
        response_text = response_text[:-3]  # Remove trailing ```
    
    # Remove any other non-JSON text (like explanations before/after JSON)
    # Find the first { and last } to extract pure JSON
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        response_text = response_text[start_idx:end_idx+1]
    
    return response_text.strip()


def parse_json_safely(json_string):
    """Safely parse JSON string with detailed error reporting"""
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        print(f"Error position: line {e.lineno}, column {e.colno}")
        
        # Show context around error
        start = max(0, e.pos - 50)
        end = min(len(json_string), e.pos + 50)
        print(f"Context around error: {json_string[start:end]}")
        
        # Try to fix common JSON issues
        fixed_json = fix_common_json_issues(json_string)
        try:
            return json.loads(fixed_json)
        except:
            raise ValueError(f"Cannot parse JSON even after fixing attempts")


def fix_common_json_issues(json_string):
    """Fix common JSON formatting issues"""
    # Fix unescaped quotes
    json_string = re.sub(r'(?<!\\)"(?!(,|:|}|]|\s))', r'\"', json_string)
    
    # Fix missing quotes around property names
    json_string = re.sub(r'(\{|,)\s*(\w+)\s*:', r'\1 "\2":', json_string)
    
    # Fix trailing commas
    json_string = re.sub(r',\s*([}\]])', r'\1', json_string)
    
    # Fix single quotes to double quotes
    json_string = json_string.replace("'", '"')
    
    return json_string


def save_json_to_file(data, directory, filename):
    """Save JSON data to file with proper encoding"""
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"JSON file saved to: {filepath}")
    return filepath


def test_class_build():
    load_dotenv()
    save_dir = r"examples/utest/Collector/test_files"
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    
    # 1. First test basic API functionality
    print("=" * 50)
    print("Step 1: Testing basic API functionality...")
    print("=" * 50)
    
    test_api_call = LangChainAPIInference(lm_name="ARK/doubao-seed-1-6-flash-250828")
    chatbot = InferInput(
        system_msg = "You are a JSON generator. Always return valid JSON format only.",
        user_msg = "Return a simple test JSON with fields: test (string), status (string), message (string)",
    )
    result = test_api_call.run(chatbot)
    print("Test API response:", result.response)
    
    try:
        test_json = json.loads(result.response)
        print("✓ Basic test successful - API returns valid JSON")
    except json.JSONDecodeError:
        print("✗ Basic test failed - API does not return pure JSON")
        # Save raw response for debugging
        debug_path = os.path.join(save_dir, f"api_test_raw_{timestamp}.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(result.response)
        print(f"Raw response saved to: {debug_path}")
    
    # 2. Load text content
    print("\n" + "=" * 50)
    print("Step 2: Loading text content...")
    print("=" * 50)
    
    all_text_content_path = r"examples\utest\Collector\test_files\All_Text_Content_20251217025828.json"
    
    # Try to load as JSON first, if not, read as text
    try:
        with open(all_text_content_path, "r", encoding="utf-8") as f:
            All_Text_Content = json.load(f)
        print("✓ Successfully loaded text content as JSON")
        # Convert to string for the prompt
        text_for_prompt = json.dumps(All_Text_Content, ensure_ascii=False)
    except json.JSONDecodeError:
        print("File is not valid JSON, reading as plain text...")
        with open(all_text_content_path, "r", encoding="utf-8") as f:
            All_Text_Content = f.read()
        text_for_prompt = All_Text_Content
    
    print(f"Text content length: {len(text_for_prompt)} characters")
    
    # 3. Run ponzi scheme analysis
    print("\n" + "=" * 50)
    print("Step 3: Running ponzi scheme analysis...")
    print("=" * 50)
    
    # Get the prompt
    prompt_content = ponzi_scheme_prompt()
    print(f"Prompt length: {len(prompt_content)} characters")
    
    # Create API call
    aihubmix_api_call = LangChainAPIInference(lm_name="ARK/doubao-seed-1-6-flash-250828")
    
    # Create chatbot input
    # IMPORTANT: If the prompt contains { and } that are NOT for format strings,
    # we should NOT escape them
    chatbot = InferInput(
        system_msg = prompt_content,
        user_msg = f"Please analyze the following text content and identify Ponzi scheme characteristics:\n\n{text_for_prompt}\n\nPlease return the analysis in valid JSON format only, without any additional text, explanations, or Markdown formatting.",
    )
    
    # Run inference
    print("Sending request to API...")
    result = aihubmix_api_call.run(chatbot)
    print("API call completed.")
    
    # 4. Process and save the response
    print("\n" + "=" * 50)
    print("Step 4: Processing response...")
    print("=" * 50)
    
    # Clean the response
    print("Cleaning response...")
    cleaned_response = clean_json_response(result.response)
    
    # Save raw response for debugging
    raw_response_path = os.path.join(
        save_dir, 
        f"ponzi_scheme_raw_response_{timestamp}.txt"
    )
    with open(raw_response_path, "w", encoding="utf-8") as f:
        f.write(result.response)
    print(f"Raw response saved to: {raw_response_path}")
    
    # Save cleaned response for debugging
    cleaned_response_path = os.path.join(
        save_dir,
        f"ponzi_scheme_cleaned_{timestamp}.txt"
    )
    with open(cleaned_response_path, "w", encoding="utf-8") as f:
        f.write(cleaned_response)
    print(f"Cleaned response saved to: {cleaned_response_path}")
    
    # Parse JSON
    print("Parsing JSON...")
    try:
        response_data = parse_json_safely(cleaned_response)
        print("✓ Successfully parsed JSON")
        
        # Save as proper JSON file
        json_filepath = save_json_to_file(
            response_data,
            save_dir,
            f"ponzi_scheme_response_{timestamp}.json"
        )
        
        # Print summary
        print("\n" + "=" * 50)
        print("ANALYSIS COMPLETE")
        print("=" * 50)
        print(f"Results saved to: {json_filepath}")
        print(f"Response type: {type(response_data)}")
        
        # Show structure if it's a dict
        if isinstance(response_data, dict):
            print(f"Top-level keys: {list(response_data.keys())}")
            if "ponzi_scheme_reconstruction" in response_data:
                recon = response_data["ponzi_scheme_reconstruction"]
                if "metadata" in recon:
                    meta = recon["metadata"]
                    print(f"Scheme name: {meta.get('scheme_common_name', 'N/A')}")
                    print(f"Estimated scale: {meta.get('estimated_global_scale', {}).get('principal_invested_estimate', 'N/A')}")
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"✗ Failed to parse JSON: {e}")
        
        # Try one more approach - find and extract JSON object
        print("Attempting to extract JSON using regex...")
        json_match = re.search(r'(\{.*\})', cleaned_response, re.DOTALL)
        if json_match:
            extracted_json = json_match.group(1)
            print(f"Extracted JSON length: {len(extracted_json)}")
            
            try:
                response_data = json.loads(extracted_json)
                print("✓ Successfully parsed extracted JSON")
                
                # Save the extracted JSON
                json_filepath = save_json_to_file(
                    response_data,
                    save_dir,
                    f"ponzi_scheme_response_extracted_{timestamp}.json"
                )
            except json.JSONDecodeError as e2:
                print(f"✗ Even extracted JSON is invalid: {e2}")
                print("Please check the raw response file and fix manually.")
        else:
            print("✗ No JSON object found in response")
            print("The AI may not be returning JSON format. Check the prompt and system message.")


if __name__ == "__main__":
    test_class_build()