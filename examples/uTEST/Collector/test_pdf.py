"""
An interface to test the pdf parser under the finmy/collector.
"""

import argparse

from dotenv import load_dotenv

from finmy.pdf_collector.base import PDFCollectorInput
from finmy.pdf_collector.pdf_parser import PDFParser

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
        default="en",
        help="Language code for parsing (e.g., 'en', 'es')",
    )
    parser.add_argument(
        "--no-check-limits",
        action="store_false",
        dest="check_pdf_limits",
        help="Disable PDF size/page limits check",
    )

    args = parser.parse_args()

    # Create PDFCollectorInput object
    pdf_input = PDFCollectorInput(
        input_dir_path=args.input_dir,
        output_dir_path=args.output_dir,
        batch_size=args.batch_size,
        language=args.language,
        check_pdf_limits=args.check_pdf_limits,
    )
    # Initialize PDFParser
    parser_instance = PDFParser(pdf_input)

    # Run the main processing function
    print("\nStarting PDF processing...")

    # Collect the parsed results
    results = parser_instance.collect()

    # Print results summary
    print(f"\nTotal PDFs parsed results saved: {len(results.results)}")
