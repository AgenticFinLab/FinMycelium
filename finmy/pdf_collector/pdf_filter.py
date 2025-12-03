"""
Module for filtering PDF content based on keywords, extending the base PDF collector functionality.

This module provides concrete implementation for filtering PDF content based on specified keywords, leveraging the base abstractions defined in base.py.
"""

import os
import re
from typing import List, Dict

from .base import BasePDFCollector, PDFCollectorInput, PDFCollectorOutput


class PDFFilter(BasePDFCollector):
    """
    A concrete implementation of BasePDFCollector that filters PDF content based on keywords.
    """

    def __init__(self, pdf_collector_input: PDFCollectorInput):
        self.pdf_collector_input = pdf_collector_input
        """
        Initializes the PDF keyword filter.

        Args:
            pdf_collector_input (PDFCollectorInput): Input configuration for the collector.
        """
        super().__init__(pdf_collector_input)

    def collect(self) -> PDFCollectorOutput:
        """
        Perform the collection/processing task by reading the input PDF and applying keyword filtering.

        Returns:
            PDFCollectorOutput: The result of the collection process, including filtered content.
        """
        # This implementation focuses on filtering existing content
        # For a complete implementation, you would need to extract content from the PDF first
        # Here we'll return an empty output, as the actual PDF parsing would be done in a separate collector
        output = PDFCollectorOutput()

        return output

    def filter(self, content: str) -> List[Dict[str, str]]:
        """
        Filter content based on keywords.

        Args:
            content (str): The content to filter.

        Returns:
            List[Dict[str, str]]: Filtered list of records.
        """
        if not self.keywords:
            # If no keywords provided, return an empty list or the original content as a single record
            return []

        # Check if any of the keywords exist in the content
        if self.contains_keywords(content, self.keywords):
            # Return the content as a record if keywords are found
            return [{"content": content, "keywords_found": self.keywords}]
        else:
            return []

    def contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """
        Check if the text contains any of the specified keywords using regex matching.

        Args:
            text (str): Text to search in
            keywords (List[str]): List of keywords to search for

        Returns:
            bool: True if any keyword is found in the text, False otherwise
        """
        # Create a regex pattern that matches any of the keywords
        for keyword in keywords:
            # Escape special regex characters in the keyword
            escaped_keyword = re.escape(keyword)
            # Use re.IGNORECASE for case-insensitive matching
            if re.search(escaped_keyword, text, re.IGNORECASE):
                return True
        return False

    def filter_records_by_keywords(
        self, records: List[Dict[str, str]], keywords: List[str], base_folder: str
    ) -> List[Dict[str, str]]:
        """
        Filter records based on whether their corresponding files contain specified keywords.

        Args:
            records (List[Dict[str, str]]): List of records from a CSV file
            keywords (List[str]): List of keywords to search for
            base_folder (str): Base folder where files are located

        Returns:
            List[Dict[str, str]]: Filtered list of records that contain the keywords
        """
        filtered_records = []

        for record in records:
            # get the successful parsed file path from the record
            location = record["Location"]

            # Construct the full path to the file
            file_path = os.path.join(base_folder, location)

            # Check if the file exists
            if not os.path.exists(file_path):
                self.logger.warning("File does not exist: %s", file_path)
                continue

            try:
                # Read the file content
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read()

                # Check if any of the keywords exist in the content
                if self.contains_keywords(file_content, keywords):
                    filtered_records.append(record)
            except Exception as e:
                self.logger.error("Error reading file %s: %s", file_path, str(e))
                continue

        return filtered_records
