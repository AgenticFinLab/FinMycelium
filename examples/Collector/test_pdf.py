"""
An interface to test the pdf parser under the finmy/collector.
"""

import argparse


from finmy.collector import pdf_parser


if __name__ == "__main__":

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
        "-c",
        "--check_pdf_limits",
        action="store_true",
        help="Enable PDF size/page limits check",
    )

    args = parser.parse_args()

    # Run the main processing function with default parameters
    pdf_parser.parse_pdfs(
        input_dir="input",
        output_dir="output",
        batch_size=200,
        language="en",
        check_pdf_limits=True,
    )
