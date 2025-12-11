"""
An interface to test the pdf parser under the finmy/collector.
"""

import logging
import argparse
import json

from dotenv import load_dotenv

from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput, PDFCollectorOutput


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Parse PDFs with configurable options."
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        type=str,
        default="input",
        help="Input directory containing PDFs",
    )
    parser.add_argument(
        "-p",
        "--input_pdf_path",
        type=str,
        default="",
        help="Path to the single input PDF file",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        default="output",
        help="Output directory for parsed results",
    )
    parser.add_argument(
        "-b",
        "--batch_size",
        type=int,
        default=200,
        help="Number of PDFs to process in one batch",
    )
    parser.add_argument(
        "-l",
        "--language",
        type=str,
        default="ch",
        help="Language code for parsing ('ch' for both Chinese and English)",
    )
    parser.add_argument(
        "--no-check-limits",
        action="store_false",
        dest="check_pdf_limits",
        help="Disable PDF size/page limits check",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="*",
        default=[],
        help="Keywords to filter the parsed content (space separated)",
    )

    args = parser.parse_args()

    config = {
        # The directory to store output files
        "output_dir": args.output_dir,
        # The batch size for processing pdfs (max: 200)
        "batch_size": args.batch_size,
        # The language code for the document (e.g., "en" for English)
        "language": args.language,
        # Whether to check PDF size and page limits
        "check_pdf_limits": args.check_pdf_limits,
        # Path to the .env file for loading environment variables
        "env_file": ".env",
    }

    test_keywords = ["finance"]
    # Create PDFCollectorInput object with keywords from command line or test keywords
    keywords = args.keywords if args.keywords else test_keywords
    pdf_collector_input = PDFCollectorInput(
        input_dir=args.input_dir,
        input_pdf_path=args.input_pdf_path,
        keywords=keywords,
    )

    # Initialize PDFCollector
    parser_instance = PDFCollector(config)

    # Run the main processing function
    logging.info("  - Starting PDF processing...")

    # Collect the parsed and filtered results
    collect_results = parser_instance.collect(pdf_collector_input)
    filter_results = parser_instance.filter(pdf_collector_input,collect_results)

    # Print final results summary
    test_row={"name":"aaa","time":"bbb"}
    test_row["parsed_content"]=collect_results.records[0].__dict__
    print("test_row: ",test_row)
    print("test_row['parsed_content']['Location']",test_row["parsed_content"]["Location"])
    
    with open(test_row["parsed_content"]["Location"],"r",encoding="utf-8") as f:
        print(f.read())
    with open("output/test_row.json","w",encoding="utf-8") as f:
        json.dump(test_row,f,ensure_ascii=False,indent=4)

    print("============")
    print("===== collect_results =====")
    print(list(collect_results.records))
    print(collect_results.records[0].Location)
    print("============")

    print("============")
    print("===== filter_results =====")
    print(filter_results)
    print("============")

