"""Example script for searching keywords in PDF full text files.

This script demonstrates how to use the base module to search for keywords
in multiple 'full.md' files within different directories and save the results
to a JSON file.
"""

import os
import sys
import argparse

from finmy.matcher import re_matcher


def main():
    """Main function to parse arguments and execute the search."""
    parser = argparse.ArgumentParser(
        description="Search for keywords in PDF extracted markdown files."
    )

    parser.add_argument(
        "--input-path",
        "-i",
        type=str,
        default="pdf_parse_results",
        help="Directory containing subfolders with full.md files",
    )

    parser.add_argument(
        "--keyword",
        "-k",
        type=str,
        required=True,
        help="""Keyword or list of keywords to search for in the markdown files. Can be a single keyword, comma-separated keywords (e.g., 'keyword1,keyword2,keyword3')""",
    )

    parser.add_argument(
        "--output-path",
        "-o",
        type=str,
        help="Path for the output JSON file (default: search_information.json in input directory)",
    )

    parser.add_argument(
        "--context-chars",
        "-c",
        type=int,
        default=2000,
        help="Number of characters to include before and after each keyword match (default: 2000)",
    )

    args = parser.parse_args()

    # Validate input directory
    if not os.path.isdir(args.input_path):
        print(f"Error: Input path '{args.input_path}' is not a valid directory.")
        return 1

    # Parse keywords from input
    keywords = re_matcher.parse_keywords(args.keyword)
    print(f"Parsed keywords: {keywords}")

    # Perform the keyword search
    try:
        print(f"Searching for keywords: {keywords}")
        results = re_matcher.perform_keyword_search(
            input_directory=args.input_path,
            # Pass the list of keywords
            keyword=keywords,
            context_chars=args.context_chars,
            output_path=args.output_path,
        )

        print(f"Search completed. Found matches in {len(results)} files.")
        if args.output_path:
            print(f"Results saved to: {args.output_path}")
        else:
            default_output = os.path.join(args.input_path, "search_information.json")
            print(f"Results saved to: {default_output}")

        return 0

    except Exception as e:
        print(f"An error occurred during the search: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
