"""
PDF Parser class for processing PDF files using the Mineru API.

This module contains the PDFParser class which provides methods to parse PDF files, collect results, and retry failed files using the Mineru API.
"""

import os
import json

from .base import (
    BasePDFCollector,
    PDFCollectorInput,
    PDFCollectorOutput,
    PDFCollectorOutputSample,
)
from .utils import parse_pdfs, retry_failed_files


class PDFParser(BasePDFCollector):
    """
    PDF parser class, inheriting from BasePDFCollector
    Uses Mineru API to parse PDF files and maps results to PDFCollectorOutput format
    """

    def __init__(self, pdf_collector_input: PDFCollectorInput):
        """
        Initialize PDFParser

        Args:
            input_dir (str): Directory containing input PDF files
            output_dir (str): Output directory for parsing results
            env_file (str): Path to .env file for loading environment variables
        """
        super().__init__(pdf_collector_input)

        # Load environment variables to get API key
        self.api_key = os.getenv("MINERU_API_KEY")
        if not self.api_key:
            raise ValueError("MINERU_API_KEY environment variable not set")

    def collect(self) -> PDFCollectorOutput:
        """
        Implement collect method, parse PDF files and return PDFCollectorOutput object

        Args:
            input_data: Optional input data (currently unused)

        Returns:
            PDFCollectorOutput: Parsing results
        """
        # Call existing parse_pdfs function for parsing
        all_failed_files_maps, original_files_list = parse_pdfs(
            input_dir=self.input_dir,
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
            retry_failed_files(
                all_failed_files_maps=all_failed_files_maps,
                original_files_list=original_files_list,
                input_dir=self.input_dir,
                output_dir=self.output_dir + "_retry",
                batch_size=self.batch_size,
                language=self.language,
                check_pdf_limits=self.check_pdf_limits,
            )
        # Read the parsing results
        output = self._read_results_from_directory(self.output_dir)
        # Save the output to JSON file
        self.save_output_to_json(output)

        return output

    def read_existing_results(self, results_dir: str = None) -> PDFCollectorOutput:
        """
        Directly read existing parsing result directory

        Args:
            results_dir (str): Parsing result directory path, if None then use self.output_dir

        Returns:
            PDFCollectorOutput: Parsing results
        """
        output_dir = results_dir if results_dir else self.output_dir

        # Check if directory exists
        if not os.path.exists(output_dir):
            self.logger.error("Results directory not found: %s", output_dir)
            return PDFCollectorOutput()

        # Read the parsing results
        output = self._read_results_from_directory(output_dir)
        # Save the output to JSON file
        self.save_output_to_json(output)

        return output

    def _read_results_from_directory(self, directory: str) -> PDFCollectorOutput:
        """
        Private method to read parsing results from a directory.
        This method contains the shared logic used by collect and read_existing_results.

        Args:
            directory (str): Directory containing parsing results

        Returns:
            PDFCollectorOutput: Parsing results, where each item is a PDFCollectorOutputSample
        """
        # Create PDFCollectorOutput object
        output = PDFCollectorOutput()

        # Process parsing results, mapping them to PDFCollectorOutput
        for root, dirs, files in os.walk(directory):
            # Check if it contains key files (full.md, layout.json, or any *_content_list.json)
            has_full_md = "full.md" in files
            has_layout = "layout.json" in files
            has_content_list = any(
                file.endswith("_content_list.json") for file in files
            )

            has_content_files = has_full_md or has_layout or has_content_list

            if has_content_files:
                # Create a new PDFCollectorOutputSample for each subfolder
                sample = PDFCollectorOutputSample()

                # Read content_list.json file (supporting files with unique identifier prefix)
                content_list_files = [
                    file for file in files if file.endswith("_content_list.json")
                ]
                if content_list_files:
                    # Use the first content_list file found
                    content_list_path = os.path.join(root, content_list_files[0])
                    try:
                        with open(content_list_path, "r", encoding="utf-8") as f:
                            sample.content_list = json.load(f)
                    except Exception as e:
                        self.logger.error("Failed to read content_list.json: %s", e)

                # Read full.md file
                if "full.md" in files:
                    full_path = os.path.join(root, "full.md")
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            sample.full_content = f.read()
                    except Exception as e:
                        self.logger.error("Failed to read full.md: %s", e)

                # Read layout.json file
                if "layout.json" in files:
                    layout_path = os.path.join(root, "layout.json")
                    try:
                        with open(layout_path, "r", encoding="utf-8") as f:
                            sample.layout = json.load(f)
                    except Exception as e:
                        self.logger.error("Failed to read layout.json: %s", e)

                # Collect image paths from images directory
                if "images" in dirs:
                    images_dir = os.path.join(root, "images")
                    try:
                        for img_file in os.listdir(images_dir):
                            sample.images.append(
                                os.path.abspath(os.path.join(images_dir, img_file))
                            )
                    except Exception as e:
                        self.logger.error("Failed to collect images: %s", e)

                # Add the sample to the results list
                output.results.append(sample)

        return output

    def save_output_to_json(self, output: PDFCollectorOutput):
        """
        Save PDFCollectorOutput object to a JSON file.

        Args:
            output: PDFCollectorOutput object to be saved
        """
        # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Define the full path for the JSON file
        json_file_path = os.path.join(self.output_dir, "parse_results.json")

        # Convert the output object to a serializable dictionary
        output_dict = {"results": []}

        for sample in output.results:
            sample_dict = {
                "content_list": sample.content_list,
                "full_content": sample.full_content,
                "layout": sample.layout,
                "images": sample.images,
            }
            output_dict["results"].append(sample_dict)

        # Write the dictionary to the JSON file
        try:
            with open(json_file_path, "w", encoding="utf-8") as f:
                json.dump(output_dict, f, ensure_ascii=False, indent=2)
            print(f"Successfully saved parsing results to {json_file_path}")
        except Exception as e:
            print(f"Failed to save results to JSON: {e}")

    def filter(self):
        pass
