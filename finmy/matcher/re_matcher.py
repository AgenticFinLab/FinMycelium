"""Basic module that supports keyword search in text parsed from PDFs.

This module provides core utilities for:
- Reading 'parser_information.csv' to locate 'full.md' files
- Reading content from markdown files
- Searching for keywords using regular expressions
- Extracting surrounding context from text with complete sentences
- Saving search results to JSON format
"""

import os
import re
import csv
import json
from datetime import datetime
from typing import List, Dict, Optional, Union


def extract_context_with_sentences(
    content: str,
    keyword_start: int,
    keyword_end: int,
    context_chars: int,
) -> str:
    """Extracts context around a keyword within a character window, expanded to full sentences."""
    total_len = len(content)

    # Define the raw character window
    raw_start = max(0, keyword_start - context_chars)
    raw_end = min(total_len, keyword_end + context_chars)

    # Expand backward to the beginning of the first complete sentence in the window
    actual_start = raw_start
    for i in range(raw_start, -1, -1):
        if i == 0:
            actual_start = 0
            break
        # Check if previous character is a sentence ending punctuation
        if re.match(r"[.!?。！？]", content[i - 1]):
            actual_start = i
            break

    # Expand forward to the end of the last complete sentence in the window
    actual_end = raw_end
    for i in range(raw_end, total_len):
        # Check if current character is a sentence ending punctuation
        if re.match(r"[.!?。！？]", content[i]):
            actual_end = i + 1
            break
    else:
        # If no sentence ending found, extend to end of content
        actual_end = total_len

    context = content[actual_start:actual_end].strip()
    return context


def search_keywords_in_file(
    file_path: str,
    keywords: List[str],
    context_chars: int = 2000,
) -> List[Dict[str, any]]:
    """Searches for multiple keywords in a file and returns context around matches with complete sentences."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read file {file_path}: {e}")
        return []

    all_matches = []

    # Process each keyword separately
    for keyword in keywords:
        # Create case-insensitive pattern for the keyword
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)

        # Find all occurrences of the keyword in the content
        for match in pattern.finditer(content):
            start_pos = match.start()
            end_pos = match.end()

            # Extract context around the match with full sentences
            context = extract_context_with_sentences(
                content, start_pos, end_pos, context_chars
            )

            # Calculate line number where the match occurs
            line_number = content[:start_pos].count("\n") + 1

            match_info = {
                "line_number": line_number,
                # Character positions of the match
                "keyword_position": (start_pos, end_pos),
                # Context text with complete sentences
                "context": context,
                # The keyword that was matched
                "matched_keyword": keyword,
            }
            all_matches.append(match_info)

    # Sort matches by their position in the content to maintain order
    all_matches.sort(key=lambda x: x["keyword_position"][0])

    return all_matches


def get_next_sample_id(output_path: str) -> int:
    """Gets the next SampleID based on existing results in the JSON file."""
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
            if isinstance(existing_results, list):
                # Return the next ID after the last existing result
                return len(existing_results) + 1
            else:
                # If not a list, start with ID 1
                return 1
        except (json.JSONDecodeError, KeyError):
            # If JSON is invalid, start with ID 1
            return 1
    else:
        # If output file doesn't exist, start with ID 1
        return 1


def create_search_result_entry(
    file_path: str,
    output_path: str,
    keywords: List[str],
    matches: List[Dict[str, any]],
    raw_data_id: str,
    sample_id: int,
) -> Dict[str, any]:
    """Creates a structured entry for search results."""
    return {
        # Sequential ID for this search result
        "SampleID": str(sample_id),
        # ID from the source CSV file
        "RawDataID": raw_data_id,
        # Absolute path to the output JSON file
        "Location": os.path.abspath(output_path),
        # Timestamp of the search
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # Placeholder for category classification
        "Category": "",
        # Placeholder for field classification
        "Field": "",
        # Tag identifying the project/organization
        "Tag": "AgenticFin, HKUST(GZ)",
        # Search method used
        "Method": "Regular Expression",
        # Placeholder for review comments
        "Reviews": "",
        # Path to the source markdown file
        "Source": file_path,
        # The keywords that were searched for
        "keywords": keywords,
        # Number of matches found in this file
        "match_count": len(matches),
        # List of individual match details
        "matches": matches,
    }


def save_search_results(results: List[Dict[str, any]], output_path: str) -> None:
    """Saves search results to a JSON file."""
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def perform_keyword_search(
    input_directory: str,
    keyword: Union[str, List[str]],  # Accept both string and list of strings
    context_chars: int = 2000,
    output_path: Optional[str] = None,
) -> List[Dict[str, any]]:
    """Performs keyword search using parser_information.csv to locate full.md files.

    Args:
        input_directory: Directory containing 'parser_information.csv'.
        keyword: The keyword or list of keywords to search for.
        context_chars: Number of characters to include around each match.
        output_path: Optional path for the output JSON file. If not provided, defaults to 'search_information.json' in the input directory.

    Returns:
        A list of search result entries.
    """
    # Convert single keyword to list for consistent processing
    if isinstance(keyword, str):
        keywords = [keyword]
    else:
        keywords = keyword

    # Set default output path if not provided
    if output_path is None:
        output_path = os.path.join(input_directory, "search_information.json")

    # Path to the CSV file that maps RawDataID to markdown files
    csv_path = os.path.join(input_directory, "parser_information.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Expected parser_information.csv at {csv_path} but it does not exist."
        )

    # Get the starting SampleID based on existing results
    current_sample_id = get_next_sample_id(output_path)

    all_results = []

    # Read the CSV file to get file locations
    with open(csv_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Get the markdown file path from the CSV row
            md_file_path = row.get("Location")
            # Get the RawDataID from the CSV row
            raw_data_id = row.get("RawDataID", "")

            # Skip if file path is missing or file doesn't exist
            if not md_file_path or not os.path.exists(md_file_path):
                print(
                    f"Warning: Markdown file not found or missing Location: {md_file_path}"
                )
                continue

            # Search for all keywords in the markdown file
            matches = search_keywords_in_file(md_file_path, keywords, context_chars)
            if matches:
                # Create a result entry for this file if matches are found
                result_entry = create_search_result_entry(
                    file_path=md_file_path,
                    output_path=output_path,
                    keywords=keywords,
                    matches=matches,
                    raw_data_id=raw_data_id,
                    sample_id=current_sample_id,
                )
                all_results.append(result_entry)
                # Increment SampleID for next result if any
                current_sample_id += 1

    # Save all results to the output JSON file
    save_search_results(all_results, output_path)
    return all_results


def parse_keywords(keyword_input: str) -> List[str]:
    """Parse the keyword input, which can be a single keyword or a comma-separated list.

    Supports hyphen-to-space conversion for multi-word phrases (e.g., 'reinforcement-learning' -> 'reinforcement learning').
    """
    # Split by comma first
    keywords = [kw.strip() for kw in keyword_input.split(",")]
    # Replace hyphens with spaces in each keyword, then remove empty strings
    keywords = [kw.replace("-", " ") for kw in keywords if kw]
    return keywords
