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


def find_sentence_boundaries(text: str, start_pos: int, end_pos: int) -> Tuple[int, int]:
    """Finds the sentence boundaries around a keyword position.

    Args:
        text: The full text content.
        start_pos: Start position of the keyword.
        end_pos: End position of the keyword.

    Returns:
        A tuple containing the start and end positions of the sentence boundaries.
    """
    # Define sentence ending patterns (common sentence terminators)
    sentence_endings = r'[.!?。！？]'
    
    # Find the start of the sentence (look for sentence ending or beginning of text)
    # Start from the keyword position and go backwards
    sentence_start = 0
    for i in range(start_pos - 1, -1, -1):
        if re.match(sentence_endings, text[i]) or i == 0:
            # If we found a sentence ending, start from the next character
            if i == 0 and re.match(sentence_endings, text[i]):
                sentence_start = 0
            else:
                sentence_start = i + 1
            break
    else:
        # If no sentence ending found before keyword, start from the beginning
        sentence_start = 0

    # Find the end of the sentence (look for sentence ending or end of text)
    # Start from the keyword position and go forwards
    sentence_end = len(text)
    for i in range(end_pos, len(text)):
        if re.match(sentence_endings, text[i]):
            # Include the sentence ending character
            sentence_end = i + 1
            break

    return sentence_start, sentence_end


def extract_context_with_sentences(
    content: str,
    keyword_start: int,
    keyword_end: int,
    context_chars: int
) -> str:
    """Extracts context around a keyword ensuring sentence boundaries.

    Args:
        content: The full content text.
        keyword_start: Start position of the keyword.
        keyword_end: End position of the keyword.
        context_chars: Number of characters to include before and after the keyword.

    Returns:
        Context string with complete sentences.
    """
    # Calculate initial boundaries based on the specified character count
    initial_start = max(0, keyword_start - context_chars)
    initial_end = min(len(content), keyword_end + context_chars)

    # Find the sentence boundaries for the keyword
    sentence_start, sentence_end = find_sentence_boundaries(
        content, keyword_start, keyword_end
    )

    # Expand the boundaries to include complete sentences while respecting the character limit
    # Start by finding the actual sentence boundaries within the initial context window
    actual_start = initial_start
    actual_end = initial_end

    # Expand backwards to find the start of the sentence that contains or is before the initial_start
    for i in range(initial_start, -1, -1):
        if i == 0:
            actual_start = 0
            break
        if re.match(r'[.!?。！？]', content[i-1]):
            actual_start = i
            break

    # Expand forwards to find the end of the sentence that contains or is after the initial_end
    for i in range(initial_end, len(content)):
        if re.match(r'[.!?。！？]', content[i]):
            actual_end = i + 1
            break

    # Ensure we don't go beyond the original sentence boundaries if they are within the expanded range
    actual_start = max(actual_start, sentence_start)
    actual_end = min(actual_end, sentence_end)

    # Extract the context with sentence boundaries
    context = content[actual_start:actual_end]
    
    # Strip leading/trailing whitespace but preserve meaningful content
    context = context.strip()
    
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