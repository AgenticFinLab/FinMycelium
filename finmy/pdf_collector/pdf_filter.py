"""
Base module for parsing and filtering markdown files based on keywords.

This module provides core functionality to read parsing information from a CSV file,
search for keywords in markdown files, and filter records based on keyword matches.
"""

import os
import re
import csv
from typing import List, Dict


def read_csv_file(file_path: str) -> List[Dict[str, str]]:
    """
    Read a CSV file and return its content as a list of dictionaries.

    Args:
        file_path (str): Path to the CSV file to be read

    Returns:
        List[Dict[str, str]]: List of dictionaries representing CSV rows
    """
    records = []
    with open(file_path, "r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            records.append(row)
    return records


def write_csv_file(
    file_path: str, records: List[Dict[str, str]], fieldnames: List[str]
) -> None:
    """
    Write records to a CSV file.

    Args:
        file_path (str): Path to the output CSV file
        records (List[Dict[str, str]]): List of dictionaries to write
        fieldnames (List[str]): List of field names for the CSV header
    """
    with open(file_path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def read_markdown_file(file_path: str) -> str:
    """
    Read the content of a markdown file.

    Args:
        file_path (str): Path to the markdown file

    Returns:
        str: Content of the markdown file
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def contains_keywords(text: str, keywords: List[str]) -> bool:
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
    records: List[Dict[str, str]], keywords: List[str], base_folder: str
) -> List[Dict[str, str]]:
    """
    Filter records based on whether their corresponding markdown files contain specified keywords.

    Args:
        records (List[Dict[str, str]]): List of records from parser_information.csv
        keywords (List[str]): List of keywords to search for
        base_folder (str): Base folder where markdown files are located

    Returns:
        List[Dict[str, str]]: Filtered list of records that contain the keywords
    """
    filtered_records = []

    for record in records:
        location = record.get("Location", "")
        if not location:
            continue

        # Construct the full path to the markdown file
        markdown_path = os.path.join(base_folder, location)

        # Check if the file exists
        if not os.path.exists(markdown_path):
            print(f"Warning: File does not exist: {markdown_path}")
            continue

        try:
            # Read the markdown file content
            markdown_content = read_markdown_file(markdown_path)

            # Check if any of the keywords exist in the content
            if contains_keywords(markdown_content, keywords):
                filtered_records.append(record)
        except Exception as e:
            print(f"Error reading file {markdown_path}: {str(e)}")
            continue

    return filtered_records


def get_csv_fieldnames(file_path: str) -> List[str]:
    """
    Get the field names from the header of a CSV file.

    Args:
        file_path (str): Path to the CSV file

    Returns:
        List[str]: List of field names from the CSV header
    """
    with open(file_path, "r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        return reader.fieldnames or []
