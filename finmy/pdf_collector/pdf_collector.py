"""
PDF Collector class for parsing PDF files using the Mineru API and filtering records based on keywords.

This module contains the PDFCollector class which provides methods to parse PDF files, collect results, and retry failed files using the Mineru API. After parsing, the class filters records based on keywords.
"""

import os
import json

from .base import (
    BasePDFCollector,
    PDFCollectorInput,
    PDFCollectorOutput,
)
from .utils import parse_pdfs, retry_failed_files, contains_keywords


class PDFCollector(BasePDFCollector):
    """
    PDF collector class, inheriting from BasePDFCollector
    Uses Mineru API to parse PDF files and maps results to PDFCollectorOutput format. After parsing, filters records based on keywords.
    """

    def __init__(self, config):
        """
        Initialize PDFCollector

        Args:
            config (Dict): Configuration dictionary containing parser settings.
        """
        super().__init__(config)

        # Load environment variables to get API key
        self.api_key = os.getenv("MINERU_API_KEY")
        if not self.api_key:
            raise ValueError("MINERU_API_KEY environment variable not set")

    def collect(
        self,
        pdf_collector_input: PDFCollectorInput,
    ) -> PDFCollectorOutput:
        """
        Implement collect method, parse PDF files and return PDFCollectorOutput object

        Args:
            input_data: Optional input data (currently unused)

        Returns:
            PDFCollectorOutput: Parsing results
        """
        parsed_info = PDFCollectorOutput()
        # Parse PDFs and collect results
        all_failed_files_maps, original_files_list, parsed_info = parse_pdfs(
            # from pdf_collector_input
            input_dir=pdf_collector_input.input_dir,
            # from self.config
            output_dir=self.output_dir,
            batch_size=self.batch_size,
            language=self.language,
            check_pdf_limits=self.check_pdf_limits,
        )
        # Retry failed files if any
        if any(len(files) > 0 for files in all_failed_files_maps.values()):
            self.logger.info(
                "Retrying %d failed files",
                sum(len(files) for files in all_failed_files_maps.values()),
            )
            retry_parsed_info = retry_failed_files(
                all_failed_files_maps=all_failed_files_maps,
                original_files_list=original_files_list,
                input_dir=pdf_collector_input.input_dir,
                output_dir=self.output_dir + "_retry",
                batch_size=self.batch_size,
                language=self.language,
                check_pdf_limits=self.check_pdf_limits,
            )
            parsed_info.records.extend(retry_parsed_info.records)

        return parsed_info

    def filter(
        self,
        pdf_collector_input: PDFCollectorInput,
        parsed_info: PDFCollectorOutput,
    ) -> PDFCollectorOutput:
        """
        Implement filter method, filter parsed content based on keywords

        Args:
            pdf_collector_input (PDFCollectorInput): Input configuration for the collector.
            parsed_info (PDFCollectorOutput): Parsing results to filter.

        Returns:
            PDFCollectorOutput: Filtered results
        """
        # Create a new PDFCollectorOutput for filtered results
        filtered_info = PDFCollectorOutput()

        # construct the save path to the filter information json file
        filtered_info_path = os.path.join(
            self.output_dir,
            "filter_information.json",
        )

        # If no keywords provided, return all results
        if not pdf_collector_input.keywords:
            self.logger.info("No keywords provided, returning all results")
            return parsed_info

        self.logger.info(
            "Filtering %d records with keywords: %s",
            len(parsed_info.records),
            pdf_collector_input.keywords,
        )

        # Iterate through each parsed sample
        for sample in parsed_info.records:
            # Get the location of the markdown file
            markdown_location = sample.Location

            # Construct the full path to the markdown file
            markdown_path = os.path.join(self.output_dir, markdown_location)

            # Check if the file exists
            if not os.path.exists(markdown_path):
                self.logger.warning("Markdown file does not exist: %s", markdown_path)
                continue

            try:
                # Read the markdown file content
                with open(markdown_path, "r", encoding="utf-8") as file:
                    file_content = file.read()

                # Check if the content contains any of the keywords
                if contains_keywords(file_content, pdf_collector_input.keywords):
                    # Add the sample to filtered results
                    filtered_info.records.append(sample)
                    self.logger.info(
                        "Sample %s matched keywords, added to filtered results",
                        sample.RawDataID,
                    )
                else:
                    self.logger.debug(
                        "Sample %s did not match keywords, skipped", sample.RawDataID
                    )
            except Exception as e:
                self.logger.error("Error reading file %s: %s", markdown_path, str(e))
                continue

        self.logger.info(
            "Filtering completed, %d records matched keywords",
            len(filtered_info.records),
        )

        # After processing all files, save the filtered results to JSON file
        with open(filtered_info_path, mode="w", encoding="utf-8") as jsonfile:
            # Convert the dataclass to dictionary and then save as JSON
            json.dump(
                filtered_info,
                jsonfile,
                default=lambda obj: obj.__dict__,
                ensure_ascii=False,
                indent=2,
            )

            print(f"Filtered information saved to: {filtered_info_path}")

        return filtered_info
