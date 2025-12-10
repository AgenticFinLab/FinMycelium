"""
User-Provided URL and File Processing Module

This module handles processing of URLs and files provided directly by users.
It provides a comprehensive class to handle various input formats including
XLSX files, CSV files, JSON files, single URLs, and URL lists.

The module is designed to support multiple input sources for URL collection
and processing in web search and data analysis workflows.
"""

import os
import json
from typing import List, Dict, Union, Any

import pandas as pd



class UserSearchProcessor:
    """
    A class to process user-provided URLs and files containing URL data.

    This class handles multiple input formats and ensures consistent output
    structure regardless of the input source.
    """

    def __init__(self):
        """Initialize the URL processor."""
        self.required_fields = ["title", "url"]

    def _validate_file_exists(self, file_path: str) -> None:
        """
        Validate that the file exists and is accessible.

        Args:
            file_path (str): Path to the file to validate

        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If the file path is empty or invalid
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError("File path must be a non-empty string")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

    def _process_dataframe(self, df: pd.DataFrame) -> List[Dict[str, str]]:
        """
        Process DataFrame to extract title and URL fields.

        Args:
            df (pd.DataFrame): DataFrame containing URL data

        Returns:
            List[Dict[str, str]]: List of dictionaries with title and URL
        """
        result = []

        # Check if required columns exist
        for _, row in df.iterrows():
            item = {}
            for field in self.required_fields:
                if field in df.columns and pd.notna(row[field]):
                    item[field] = str(row[field])
                else:
                    item[field] = None
            result.append(item)

        return result

    def process_xlsx_file(self, xlsx_path: str) -> List[Dict[str, str]]:
        """
        Process URLs from an XLSX file.

        This function reads URLs from an XLSX file and processes them for
        subsequent analysis or search operations. The file must contain
        'title' and 'url' columns.

        Args:
            xlsx_path (str): File path to the XLSX file containing URLs

        Returns:
            List[Dict[str, str]]: List of dictionaries with title and URL
            Example: [{"title":"xxxx", "url":"https://xxxx"}, ...]

        Raises:
            FileNotFoundError: If the XLSX file does not exist
            ValueError: If the file cannot be parsed as XLSX
            Exception: For other processing errors
        """
        try:
            self._validate_file_exists(xlsx_path)

            # Read Excel file
            df = pd.read_excel(xlsx_path)

            # Process data and return
            return self._process_dataframe(df)

        except FileNotFoundError:
            raise
        except Exception as e:
            raise ValueError(f"Error processing XLSX file {xlsx_path}: {str(e)}")

    def process_csv_file(self, csv_path: str) -> List[Dict[str, str]]:
        """
        Process URLs from a CSV file.

        This function reads URLs from a CSV file and processes them for
        subsequent analysis or search operations. The file must contain
        'title' and 'url' columns.

        Args:
            csv_path (str): File path to the CSV file containing URLs

        Returns:
            List[Dict[str, str]]: List of dictionaries with title and URL
            Example: [{"title":"xxxx", "url":"https://xxxx"}, ...]

        Raises:
            FileNotFoundError: If the CSV file does not exist
            ValueError: If the file cannot be parsed as CSV
            Exception: For other processing errors
        """
        try:
            self._validate_file_exists(csv_path)

            # Read CSV file
            df = pd.read_csv(csv_path)

            # Process data and return
            return self._process_dataframe(df)

        except FileNotFoundError:
            raise
        except Exception as e:
            raise ValueError(f"Error processing CSV file {csv_path}: {str(e)}")

    def process_json_file(self, json_path: str) -> List[Dict[str, str]]:
        """
        Process URLs from a JSON file.

        This function reads URLs from a JSON file and processes them for
        subsequent analysis or search operations. The file must contain
        objects with 'title' and 'url' fields.

        Args:
            json_path (str): File path to the JSON file containing URLs

        Returns:
            List[Dict[str, str]]: List of dictionaries with title and URL
            Example: [{"title":"xxxx", "url":"https://xxxx"}, ...]

        Raises:
            FileNotFoundError: If the JSON file does not exist
            ValueError: If the file cannot be parsed as JSON or has invalid structure
            Exception: For other processing errors
        """
        try:
            self._validate_file_exists(json_path)

            # Read and parse JSON file
            with open(json_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            # Handle different JSON structures
            if isinstance(data, list):
                # JSON is a list of objects
                json_data = data
            elif isinstance(data, dict):
                # JSON is a single object or has nested structure
                # Look for a key that contains a list of items
                json_data = []
                for key, value in data.items():
                    if isinstance(value, list):
                        json_data.extend(value)
                    else:
                        json_data.append(value)
            else:
                raise ValueError("Invalid JSON structure: expected list or object")

            # Process each item
            result = []
            for item in json_data:
                if isinstance(item, dict):
                    processed_item = {}
                    for field in self.required_fields:
                        processed_item[field] = (
                            item.get(field) if field in item else None
                        )
                    result.append(processed_item)
                else:
                    # If item is not a dict, create entry with None title
                    result.append({"title": None, "url": str(item) if item else None})

            return result

        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON format in file {json_path}: {str(e)}"
            ) from e
        except Exception as e:
            raise ValueError(f"Error processing JSON file {json_path}: {str(e)}")

    def process_single_url(self, url: str) -> List[Dict[str, str]]:
        """
        Process a single URL provided by the user.

        This function handles processing of individual URLs for analysis
        or inclusion in search operations.

        Args:
            url (str): Single URL string to be processed

        Returns:
            List[Dict[str, str]]: List containing one dictionary with title and URL
            Example: [{"title": None, "url":"https://xxxx"}]

        Raises:
            ValueError: If the URL is empty or not a string
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")

        # Return single URL with None title
        return [{"title": None, "url": url}]

    def process_url_list(self, urls: List[str]) -> List[Dict[str, str]]:
        """
        Process a list of URLs provided by the user.

        This function handles batch processing of multiple URLs for analysis
        or inclusion in search operations.

        Args:
            urls (List[str]): List of URL strings to be processed

        Returns:
            List[Dict[str, str]]: List of dictionaries with title and URL
            Example: [{"title": None, "url":"https://xxxx"}, ...]

        Raises:
            ValueError: If urls is not a list or contains invalid items
        """
        if not isinstance(urls, list):
            raise ValueError("Input must be a list of URLs")

        result = []
        for url in urls:
            if url and isinstance(url, str):
                result.append({"title": None, "url": url})
            else:
                # Include invalid URLs with None values
                result.append({"title": None, "url": None})

        return result

    def process(self, input_data: Union[str, List[str]]) -> List[Dict[str, str]]:
        """
        Main processing method that automatically detects input type and processes accordingly.

        Args:
            input_data (Union[str, List[str]]): Input data which can be:
                - File path (XLSX, CSV, JSON)
                - Single URL string
                - List of URL strings

        Returns:
            List[Dict[str, str]]: Processed URL data in consistent format

        Raises:
            ValueError: If input type is not supported or data is invalid
        """
        if isinstance(input_data, list):
            return self.process_url_list(input_data)

        elif isinstance(input_data, str):
            # Check if it's a file path
            if os.path.exists(input_data):
                file_extension = input_data.lower()

                if file_extension.endswith(".xlsx"):
                    return self.process_xlsx_file(input_data)
                elif file_extension.endswith(".csv"):
                    return self.process_csv_file(input_data)
                elif file_extension.endswith(".json"):
                    return self.process_json_file(input_data)
                else:
                    raise ValueError(f"Unsupported file format: {input_data}")
            else:
                # Treat as single URL
                return self.process_single_url(input_data)

        else:
            raise ValueError(f"Unsupported input type: {type(input_data)}")


def url_xlsx_file(xlsx_path: str) -> List[Dict[str, str]]:
    """
    Process URLs from an XLSX file.

    This function reads URLs from an XLSX file and processes them for
    subsequent analysis or search operations.

    Args:
        xlsx_path (str): File path to the XLSX file containing URLs

    Returns:
        List[Dict[str, str]]: Processed URLs from the XLSX file
    """
    processor = UserSearchProcessor()
    return processor.process_xlsx_file(xlsx_path)


def url_csv_file(csv_path: str) -> List[Dict[str, str]]:
    """
    Process URLs from a CSV file.

    This function reads URLs from a CSV file and processes them for
    subsequent analysis or search operations.

    Args:
        csv_path (str): File path to the CSV file containing URLs

    Returns:
        List[Dict[str, str]]: Processed URLs from the CSV file
    """
    processor = UserSearchProcessor()
    return processor.process_csv_file(csv_path)


def url_json_file(json_path: str) -> List[Dict[str, str]]:
    """
    Process URLs from a JSON file.

    This function reads URLs from a JSON file and processes them for
    subsequent analysis or search operations.

    Args:
        json_path (str): File path to the JSON file containing URLs

    Returns:
        List[Dict[str, str]]: Processed URLs from the JSON file
    """
    processor = UserSearchProcessor()
    return processor.process_json_file(json_path)


def url_single(url: str) -> List[Dict[str, str]]:
    """
    Process a single URL provided by the user.

    This function handles processing of individual URLs for analysis
    or inclusion in search operations.

    Args:
        url (str): Single URL string to be processed

    Returns:
        List[Dict[str, str]]: Processed URL data with metadata
    """
    processor = UserSearchProcessor()
    return processor.process_single_url(url)


def url_list(urls: list) -> List[Dict[str, str]]:
    """
    Process a list of URLs provided by the user.

    This function handles batch processing of multiple URLs for analysis
    or inclusion in search operations.

    Args:
        urls (list): List of URL strings to be processed

    Returns:
        List[Dict[str, str]]: Processed URL data with metadata for each URL
    """
    processor = UserSearchProcessor()
    return processor.process_url_list(urls)
