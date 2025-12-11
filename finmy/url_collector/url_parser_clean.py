"""
Content Post-Processor Module

This module processes parsed URL results to extract clean content strings,
removing duplicate and overlapping text while preserving meaningful content.
It handles both full results lists and individual parsed_content lists.
"""

import re
from typing import List, Dict, Any, Set, Optional


class ContentPostProcessor:
    """
    A class to process parsed URL results and extract clean content strings
    with duplicate removal and content deduplication.
    """
    
    def __init__(self, min_similarity_threshold: float = 0.9, min_text_length: int = 10):
        """
        Initialize the Content Post-Processor.
        
        Args:
            min_similarity_threshold (float): Threshold for text similarity (0-1).
                                              Higher values mean stricter deduplication.
            min_text_length (int): Minimum text length to consider for deduplication.
        """
        self.min_similarity_threshold = min_similarity_threshold
        self.min_text_length = min_text_length
        
    def process_results(self, results: List[Dict[str, Any]]) -> Dict[int, str]:
        """
        Process complete results list and extract clean content for each URL.
        
        Args:
            results (List[Dict[str, Any]]): List of parsed results from URLParser.
            
        Returns:
            Dict[int, str]: Dictionary mapping URL IDs to cleaned content strings.
        """
        url_contents = {}
        
        for result in results:
            url_id = result.get('ID')
            url = result.get('url', '')
            
            # Extract content from the result
            parsed_content = result.get('parsed_content', [])
            
            if not parsed_content:
                url_contents[url_id] = ""
                continue
            
            # Process the parsed_content list
            cleaned_content = self.process_parsed_content(parsed_content)
            url_contents[url_id] = cleaned_content
            
        return url_contents
    
    def process_parsed_content(self, parsed_content: List[Dict[str, Any]]) -> str:
        """
        Process individual parsed_content list to extract clean, deduplicated content string.
        
        Args:
            parsed_content (List[Dict[str, Any]]): List of content elements from URLParser.
            
        Returns:
            str: Cleaned and deduplicated content string.
        """
        if not parsed_content:
            return ""
        
        # Step 1: Extract all text elements with their positions
        text_elements = self._extract_text_elements(parsed_content)
        
        if not text_elements:
            return ""
        
        # Step 2: Apply deduplication and hierarchy-based filtering
        filtered_elements = self._deduplicate_and_filter(text_elements)
        
        # Step 3: Sort elements by their original position
        filtered_elements.sort(key=lambda x: x['position'])
        
        # Step 4: Combine elements into final string
        final_content = self._combine_elements(filtered_elements)
        
        return final_content
    
    def _extract_text_elements(self, parsed_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract text elements from parsed_content with metadata.
        
        Args:
            parsed_content (List[Dict[str, Any]]): List of content elements.
            
        Returns:
            List[Dict[str, Any]]: List of text elements with metadata.
        """
        text_elements = []
        
        for element in parsed_content:
            if 'text' in element and element['text'].strip():
                text = element['text'].strip()
                
                # Skip very short texts that are likely navigation noise
                if len(text) < 3:
                    continue
                    
                # Skip text that's just punctuation or numbers
                if re.match(r'^[^\w\s]*$', text) or re.match(r'^\d+$', text):
                    continue
                
                text_elements.append({
                    'text': text,
                    'position': element.get('no', 0),
                    'href': element.get('href'),
                    'original_element': element
                })
        
        return text_elements
    
    def _deduplicate_and_filter(self, text_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate text elements using hierarchical containment and similarity checks.
        
        Args:
            text_elements (List[Dict[str, Any]]): List of text elements to process.
            
        Returns:
            List[Dict[str, Any]]: Deduplicated and filtered text elements.
        """
        if not text_elements:
            return []
        
        # Sort by position (original order)
        text_elements.sort(key=lambda x: x['position'])
        
        # First pass: Remove exact duplicates
        seen_texts = set()
        unique_elements = []
        
        for element in text_elements:
            text = element['text']
            if text not in seen_texts:
                seen_texts.add(text)
                unique_elements.append(element)
        
        # Second pass: Remove hierarchical duplicates (long text containing short text)
        filtered_elements = []
        
        for i, element in enumerate(unique_elements):
            text = element['text']
            keep_element = True
            
            # Check if this text is contained within any longer text
            for j, other_element in enumerate(unique_elements):
                if i == j:
                    continue
                    
                other_text = other_element['text']
                
                # If this text is substantially contained within another text
                if self._is_text_contained(text, other_text):
                    # Keep the longer text (likely the outer container)
                    if len(other_text) > len(text):
                        keep_element = False
                        break
                    # If texts are same length, keep the earlier one
                    elif len(other_text) == len(text) and other_element['position'] < element['position']:
                        keep_element = False
                        break
            
            if keep_element:
                filtered_elements.append(element)
        
        # Third pass: Remove highly similar texts
        final_elements = []
        for i, element in enumerate(filtered_elements):
            text = element['text']
            is_similar_to_existing = False
            
            for existing_element in final_elements:
                existing_text = existing_element['text']
                
                # Check if texts are highly similar
                if self._text_similarity(text, existing_text) > self.min_similarity_threshold:
                    is_similar_to_existing = True
                    # Keep the longer text
                    if len(text) > len(existing_text):
                        # Replace the existing one with current
                        final_elements.remove(existing_element)
                        final_elements.append(element)
                    break
            
            if not is_similar_to_existing:
                final_elements.append(element)
        
        return final_elements
    
    def _is_text_contained(self, short_text: str, long_text: str) -> bool:
        """
        Check if short_text is substantially contained within long_text.
        
        Args:
            short_text (str): The potentially contained text.
            long_text (str): The potentially containing text.
            
        Returns:
            bool: True if short_text is contained within long_text.
        """
        # Normalize whitespace
        short_text_norm = re.sub(r'\s+', ' ', short_text.strip())
        long_text_norm = re.sub(r'\s+', ' ', long_text.strip())
        
        # If short text is too short, be more lenient
        if len(short_text_norm) < self.min_text_length:
            return short_text_norm in long_text_norm
        
        # For longer texts, require substantial containment
        words_short = set(short_text_norm.split())
        words_long = set(long_text_norm.split())
        
        # Calculate word overlap
        if len(words_short) == 0:
            return False
            
        overlap_ratio = len(words_short.intersection(words_long)) / len(words_short)
        
        # Consider contained if most words are present in longer text
        return overlap_ratio > 0.8
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts (0-1).
        
        Args:
            text1 (str): First text.
            text2 (str): Second text.
            
        Returns:
            float: Similarity score between 0 and 1.
        """
        # Normalize texts
        text1_norm = re.sub(r'\s+', ' ', text1.strip().lower())
        text2_norm = re.sub(r'\s+', ' ', text2.strip().lower())
        
        # If texts are identical
        if text1_norm == text2_norm:
            return 1.0
        
        # Use Jaccard similarity on words
        words1 = set(text1_norm.split())
        words2 = set(text2_norm.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _combine_elements(self, elements: List[Dict[str, Any]]) -> str:
        """
        Combine filtered elements into a final content string.
        
        Args:
            elements (List[Dict[str, Any]]): List of filtered text elements.
            
        Returns:
            str: Combined content string.
        """
        if not elements:
            return ""
        
        # Sort by original position
        elements.sort(key=lambda x: x['position'])
        
        # Extract texts
        texts = [element['text'] for element in elements]
        
        # Join with appropriate spacing
        combined = " ".join(texts)
        
        # Clean up excessive whitespace
        combined = re.sub(r'\s+', ' ', combined.strip())
        
        return combined


def extract_content_from_results(results: List[Dict[str, Any]]) -> Dict[int, str]:
    """
    Convenience function to extract content from complete results.
    
    Args:
        results (List[Dict[str, Any]]): List of parsed results from URLParser.
        
    Returns:
        Dict[int, str]: Dictionary mapping URL IDs to cleaned content strings.
    """
    processor = ContentPostProcessor()
    return processor.process_results(results)


def extract_content_from_parsed_content(parsed_content: List[Dict[str, Any]]) -> str:
    """
    Convenience function to extract content from individual parsed_content list.
    
    Args:
        parsed_content (List[Dict[str, Any]]): List of content elements from URLParser.
        
    Returns:
        str: Cleaned and deduplicated content string.
    """
    processor = ContentPostProcessor()
    return processor.process_parsed_content(parsed_content)
