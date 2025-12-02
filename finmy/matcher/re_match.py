"""
Module for regex-based matching with context extraction.
"""

import re
import time
from typing import List

from .base import BaseMatcher, MatchInput, MatchOutput, MatchItem

from .utils import (
    get_paragraph_positions,
    extract_context_with_paragraphs,
    split_paragraphs,
    PositionWisedParagraph,
)


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

    def match(self, match_input: MatchInput) -> List[dict]:
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
            all_matches = []

            # Process each keyword separately
            for keyword in keywords:
                # Create case-insensitive pattern for the keyword
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)

                # Find all occurrences of the keyword in the content
                for match in pattern.finditer(match_input.match_data):
                    keyword_start = match.start()
                    keyword_end = match.end()

                    # Extract context around the match with full sentences and get paragraph indices
                    context, paragraph_indices = extract_context_with_paragraphs(
                        content=match_input.match_data,
                        keyword_start=keyword_start,
                        keyword_end=keyword_end,
                        context_chars=2000,
                        content_paragraphs=content_paragraphs,
                    )

                    # Format match as dictionary with 'paragraph_indices' and 'quote' keys
                    all_matches.append(
                        {"paragraph_indices": paragraph_indices, "quote": context}
                    )

            # Sort matches by their position in the match_data to maintain order
            all_matches.sort(key=lambda x: match_input.match_data.find(x["quote"]))

            # If no matches found, return the entire content as a single quote
            if not all_matches:
                # Find all paragraph indices for the entire content
                paragraph_indices = list(range(len(content_paragraphs)))
                return [
                    {
                        "paragraph_indices": paragraph_indices,
                        "quote": match_input.match_data,
                    }
                ]

            return all_matches
        else:
            return []

    def map_positions(
        self,
        match_data: str,
        matches: List[str],
    ) -> List[MatchItem]:
        """Map matched text segments to their positions in the original match data.

        This method converts the list of matched text segments into MatchItem objects
        with positional information including paragraph indices, start/end positions,
        and contiguous paragraph information.

        Args:
            match_data: The original text data to map positions against
            matches: List of matched text segments from the match method

        Returns:
            List[MatchItem]: List of MatchItem objects with positional information
        """

        mapped: List[PositionWisedParagraph] = get_paragraph_positions(
            match_data, matches
        )
        items: List[MatchItem] = []
        for m in mapped:
            idxs = m.get("paragraph_indices") or []
            idxs_sorted = idxs if isinstance(idxs, list) else []
            paragraph_index = min(idxs_sorted) if idxs_sorted else -1
            contiguous_indices = sorted(idxs_sorted) if idxs_sorted else None
            items.append(
                MatchItem(
                    paragraph=m.text,
                    paragraph_index=paragraph_index,
                    start=m.start,
                    end=m.end,
                    paragraph_contiguous=None,
                    contiguous_indices=contiguous_indices,
                )
            )
        return items

    def run(self, match_input: MatchInput) -> MatchOutput:
        """Execute the complete matching process and return a standardized MatchOutput.

        This method orchestrates the entire matching workflow:
        1. Extracts matched text segments using the match method
        2. Maps these segments to positional information using map_positions
        3. Creates a MatchOutput with timing information and matched items

        Args:
            match_input: The input containing match data and summarized query

        Returns:
            MatchOutput: Result object containing matched items, method name, and execution time
        """
        # Compute the time of the whole matching process
        start_time = time.time()
        matches = self.match(match_input)
        end_time = time.time()
        items = self.map_positions(match_input.match_data, matches)
        return MatchOutput(
            items=items,
            method=self.method_name,
            time=end_time - start_time,
        )
