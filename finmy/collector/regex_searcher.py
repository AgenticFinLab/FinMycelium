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
import json
import csv
from datetime import datetime
from typing import List, Dict, Tuple, Optional


def extract_context_with_sentences(
    content: str,
    keyword_start: int,
    keyword_end: int,
    context_chars: int
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
        if re.match(r'[.!?。！？]', content[i - 1]):
            actual_start = i
            break

    # Expand forward to the end of the last complete sentence in the window
    actual_end = raw_end
    for i in range(raw_end, total_len):
        if re.match(r'[.!?。！？]', content[i]):
            actual_end = i + 1
            break
    else:
        actual_end = total_len

    context = content[actual_start:actual_end].strip()
    return context


def search_keyword_in_file(
    file_path: str,
    keyword: str,
    context_chars: int = 2000
) -> List[Dict[str, any]]:
    """Searches for a keyword in a file and returns context around matches with complete sentences."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read file {file_path}: {e}")
        return []

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    matches = []
    
    for match in pattern.finditer(content):
        start_pos = match.start()
        end_pos = match.end()
        
        context = extract_context_with_sentences(
            content, start_pos, end_pos, context_chars
        )
        
        line_number = content[:start_pos].count('\n') + 1
        
        match_info = {
            'line_number': line_number,
            'keyword_position': (start_pos, end_pos),
            'context': context,
        }
        matches.append(match_info)
    
    return matches


def get_next_sample_id(output_path: str) -> int:
    """Gets the next SampleID based on existing results in the JSON file."""
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
            if isinstance(existing_results, list):
                return len(existing_results) + 1
            else:
                return 1
        except (json.JSONDecodeError, KeyError):
            return 1
    else:
        return 1


def create_search_result_entry(
    file_path: str,
    output_path: str,
    keyword: str,
    matches: List[Dict[str, any]],
    raw_data_id: str,
    sample_id: int
) -> Dict[str, any]:
    """Creates a structured entry for search results."""
    return {
        'SampleID': str(sample_id),
        'RawDataID': raw_data_id,
        'Location': os.path.abspath(output_path),
        'Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'Category': '',
        'Field': '',
        'Tag': 'AgenticFin, HKUST(GZ)',
        'Method': 'Regular Expression',
        'Reviews': '',
        'Source': file_path,
        'keyword': keyword,
        'match_count': len(matches),
        'matches': matches
    }


def save_search_results(
    results: List[Dict[str, any]],
    output_path: str
) -> None:
    """Saves search results to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def perform_keyword_search(
    input_directory: str,
    keyword: str,
    context_chars: int = 2000,
    output_path: Optional[str] = None
) -> List[Dict[str, any]]:
    """Performs keyword search using parser_information.csv to locate full.md files.

    Args:
        input_directory: Directory containing 'parser_information.csv'.
        keyword: The keyword to search for.
        context_chars: Number of characters to include around each match.
        output_path: Optional path for the output JSON file. If not provided,
                     defaults to 'search_information.json' in the input directory.

    Returns:
        A list of search result entries.
    """
    if output_path is None:
        output_path = os.path.join(input_directory, 'search_information.json')
    
    csv_path = os.path.join(input_directory, 'parser_information.csv')
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Expected parser_information.csv at {csv_path} but it does not exist.")
    
    # Get the starting SampleID based on existing results
    current_sample_id = get_next_sample_id(output_path)
    
    all_results = []
    
    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            md_file_path = row.get('Location')
            raw_data_id = row.get('RawDataID', '')
            
            if not md_file_path or not os.path.exists(md_file_path):
                print(f"Warning: Markdown file not found or missing Location: {md_file_path}")
                continue
            
            matches = search_keyword_in_file(md_file_path, keyword, context_chars)
            if matches:
                result_entry = create_search_result_entry(
                    file_path=md_file_path,
                    output_path=output_path,
                    keyword=keyword,
                    matches=matches,
                    raw_data_id=raw_data_id,
                    sample_id=current_sample_id
                )
                all_results.append(result_entry)
                current_sample_id += 1  # Increment for next result if any
    
    save_search_results(all_results, output_path)
    return all_results