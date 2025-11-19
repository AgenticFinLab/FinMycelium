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
        type=bool,
        default=True,
        help="Enable PDF size/page limits check",
    )
    parser.add_argument(
        "-r",
        "--retry_failed",
        type=bool,
        default=True,
        help="Retry failed files after initial processing",
    )

    args = parser.parse_args()

    # Run the main processing function with default parameters
    # Return the failed files map and original files list
    failed_maps, orig_list = pdf_parser.parse_pdfs(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        language=args.language,
        check_pdf_limits=args.check_pdf_limits,
    )

    # Run the retry function if there are failed files map and retry_failed is True
    if failed_maps and args.retry_failed:
        pdf_parser.retry_failed_files(
            all_failed_files_maps=failed_maps,
            original_files_list=orig_list,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            language=args.language,
            check_pdf_limits=args.check_pdf_limits,
        )
    else:
        print("\nNo failed files found from initial processing. Skipping retry.")
