"""
Module for regex-based matching with context extraction.
"""

import re
from typing import List

from .base import BaseMatcher, MatchInput, MatchItem
from .utils import extract_context_with_paragraphs, split_paragraphs


class ReMatch(BaseMatcher):
    """Regex-based matcher implementation.

    This class implements the MatchBase interface using regular expressions
    to search for keywords in text content and extract relevant contexts.
    It finds all occurrences of keywords, extracts surrounding context with
    complete paragraphs, and maps positions for standardized output.

    Main features:
    - Case-insensitive keyword matching using regular expressions
    - Context extraction with complete paragraph boundaries preserved
    - Position mapping for paragraphs and content segments
    """

    # TODO: this function has problem about returning repetitive matched string.
    def match(self, match_input: MatchInput) -> List[str]:
        """Extract relevant text segments from match data based on keywords.

        This method searches for keywords from the summarized query in the match data, extracts context around each match with complete paragraphs, and returns a list of dictionaries containing matched text segments with 'paragraph_indices' and 'quote' keys.

        Args:
            match_input:
                - match_data: The text content to search for keywords
                - db_item: The database item containing the metadata
                - summarized_query: Including summarization, keywords, and user_query

        Return:
            List[dict]: List of dictionaries with 'paragraph_indices' and 'quote' keys containing matched text segments, each preserving sentence boundaries
        """
        # Check if match_data is empty
        if not match_input.match_data:
            return []
        # Split content into paragraphs to find paragraph indices
        content_paragraphs = split_paragraphs(match_input.match_data)
        # Get keywords from summarized_query
        keywords = []
        if match_input.summarized_query and hasattr(
            match_input.summarized_query, "key_words"
        ):
            keywords = match_input.summarized_query.key_words

        # Use keywords for matching, return empty list if no keywords
        if keywords:
            all_matches: List[MatchItem] = []

            # Process each keyword separately
            for keyword in keywords:
                # Create case-insensitive pattern for the keyword
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)

                # Find all occurrences of the keyword in the content
                for match in pattern.finditer(match_input.match_data):
                    # Ensure context boundaries are within content bounds
                    keyword_start = match.start()
                    keyword_end = match.end()
                    # Extract context around the match with full sentences and get paragraph indices
                    context, paragraph_indices = extract_context_with_paragraphs(
                        content=match_input.match_data,
                        keyword_start=keyword_start,
                        keyword_end=keyword_end,
                        context_chars=2000,  # TODO: this windows may be too long, need to be reviewed
                        content_paragraphs=content_paragraphs,
                    )
                    # Format match as dictionary with 'paragraph_indices' and 'quote' keys
                    all_matches.append(context)

            # If no matches found, return the entire content as a single quote
            if not all_matches:
                # Find all paragraph indices for the entire content
                return [match_input.match_data]

            return list(set(all_matches))
        else:
            return []
