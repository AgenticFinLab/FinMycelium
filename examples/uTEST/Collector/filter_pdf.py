"""
Example script to filter markdown files based on keywords.

This script reads parser_information.csv from a specified folder,
searches for keywords in corresponding markdown files,
and creates a filtered output file with matching records.

Example Usage:

python examples/Collector/filter_pdf.py -i output -k reinforcement-learning,LLM

The script will:
1. Read parser_information.csv from the specified folder
2. Create filter_information.csv in the same folder
3. For each record in parser_information.csv:
   - Find the corresponding markdown file using the 'Location' field
   - Search for the specified keywords in the markdown file content
   - If any keyword is found, add the record to filter_information.csv
4. Output the number of matching records found
"""

import os
import sys
import argparse
from typing import List

from finmy.pdf_collector import pdf_filter

from finmy.matcher import re_match


def main(input_path: str, keywords: List[str]) -> None:
    """
    Main function to process CSV file and filter records based on keywords.

    Args:
        input_path (str): Path to the folder containing parser_information.csv
        keywords (List[str]): List of keywords to search for in markdown files
    """
    # Construct the path to parser_information.csv
    parser_csv_path = os.path.join(input_path, "parser_information.csv")

    # Check if the parser_information.csv file exists
    if not os.path.exists(parser_csv_path):
        print(f"Error: parser_information.csv not found at {parser_csv_path}")
        sys.exit(1)

    print(f"Reading parser information from: {parser_csv_path}")

    # Read the CSV file
    records = pdf_filter.read_csv_file(parser_csv_path)
    print(f"Loaded {len(records)} records from parser_information.csv")

    # Get the field names from the original CSV
    fieldnames = pdf_filter.get_csv_fieldnames(parser_csv_path)

    # Filter records based on keywords
    print(f"Filtering records with keywords: {keywords}")
    filtered_records = pdf_filter.filter_records_by_keywords(
        records, keywords, input_path
    )

    print(f"Found {len(filtered_records)} records matching the keywords")

    # Define the output file path
    filter_csv_path = os.path.join(input_path, "filter_information.csv")

    # Write the filtered records to the output CSV file
    pdf_filter.write_csv_file(filter_csv_path, filtered_records, fieldnames)

    print(f"Filtered records saved to: {filter_csv_path}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Filter markdown files based on keywords in a CSV file."
    )
    parser.add_argument(
        "--input_path",
        "-i",
        type=str,
        help="Path to the folder containing parser_information.csv",
    )
    parser.add_argument(
        "--keywords",
        "-k",
        type=str,
        required=True,
        help="""Keyword or list of keywords to search for in the markdown files. Can be a single keyword, comma-separated keywords (e.g., 'keyword1,keyword2,keyword3')""",
    )

    args = parser.parse_args()

    # Validate folder path
    if not os.path.isdir(args.input_path):
        print(f"Error: Folder does not exist: {args.input_path}")
        sys.exit(1)

    # Parse keywords from input
    keywords = re_match.parse_keywords(args.keywords)
    print(f"Parsed keywords: {keywords}")

    # Run the main function
    main(input_path=args.input_path, keywords=keywords)
