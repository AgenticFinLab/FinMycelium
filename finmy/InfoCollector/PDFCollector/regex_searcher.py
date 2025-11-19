"""Basic module that supports keyword search in text parsed from PDFs.

This module provides core utilities for:
- Finding directories containing 'full.md' files
- Reading content from markdown files
- Searching for keywords using regular expressions
- Extracting surrounding context from text with complete sentences
- Saving search results to JSON format
"""

import os
import re
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional


def find_full_md_files(directory_path: str) -> List[str]:
    """Finds all 'full.md' files in subdirectories of the given directory.

    Args:
        directory_path: The root directory to search in.

    Returns:
        A list of paths to 'full.md' files found in subdirectories.
    """
    full_md_paths = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file == 'full.md':
                full_md_paths.append(os.path.join(root, file))
    return full_md_paths

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
    # Look backward from raw_start to find the start of a sentence
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
        # If no sentence end found, go to end of text
        actual_end = total_len

    # Extract and clean
    context = content[actual_start:actual_end].strip()
    return context


def search_keyword_in_file(
    file_path: str,
    keyword: str,
    context_chars: int = 2000
) -> List[Dict[str, any]]:
    """Searches for a keyword in a file and returns context around matches with complete sentences.

    Args:
        file_path: Path to the file to search in.
        keyword: The keyword to search for.
        context_chars: Number of characters to include before and after the keyword.

    Returns:
        A list of dictionaries containing match information.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Use re.finditer to find all matches with their positions
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    matches = []
    
    for match in pattern.finditer(content):
        start_pos = match.start()
        end_pos = match.end()
        
        # Extract context with complete sentences
        context = extract_context_with_sentences(
            content, start_pos, end_pos, context_chars
        )
        
        # Calculate line number (approximately)
        line_number = content[:start_pos].count('\n') + 1
        
        match_info = {
            'line_number': line_number,
            'keyword_position': (start_pos, end_pos),
            'context': context,
        }
        matches.append(match_info)
    
    return matches


def create_search_result_entry(
    file_path: str,
    keyword: str,
    matches: List[Dict[str, any]]
) -> Dict[str, any]:
    """Creates a structured entry for search results.

    Args:
        file_path: Path to full.md file.
        keyword: The keyword that was searched.
        matches: List of match information from the file.

    Returns:
        A dictionary representing a search result entry.
    """
    return {
        'file_path': os.path.abspath(file_path),
        'keyword': keyword,
        'timestamp': datetime.now().isoformat(),
        'match_count': len(matches),
        'matches': matches
    }


def save_search_results(
    results: List[Dict[str, any]],
    output_path: str
) -> None:
    """Saves search results to a JSON file.

    Args:
        results: List of search result entries.
        output_path: Path to the output JSON file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def perform_keyword_search(
    input_directory: str,
    keyword: str,
    context_chars: int = 2000,
    output_path: Optional[str] = None
) -> List[Dict[str, any]]:
    """Performs keyword search across all full.md files in subdirectories.

    This is the main function that orchestrates the search process.

    Args:
        input_directory: Directory containing subfolders with full.md files.
        keyword: The keyword to search for.
        context_chars: Number of characters to include around each match.
        output_path: Optional path for the output JSON file. If not provided,
                     defaults to 'search_information.json' in the input directory.

    Returns:
        A list of search result entries.
    """
    if output_path is None:
        output_path = os.path.join(input_directory, 'search_information.json')
    
    # Find all full.md files
    full_md_files = find_full_md_files(input_directory)
    
    all_results = []
    
    for file_path in full_md_files:
        
        # Search for keyword in the file
        matches = search_keyword_in_file(file_path, keyword, context_chars)
        
        if matches:
            # Create result entry for this file
            result_entry = create_search_result_entry(
                file_path=file_path,
                keyword=keyword,
                matches=matches
            )
            all_results.append(result_entry)
    
    # Save results to JSON file
    save_search_results(all_results, output_path)
    
    return all_results