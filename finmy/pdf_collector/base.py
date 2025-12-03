"""
Base abstractions for PDF parsing and filtering.

- Defines standard input/output structures (`PDFCollectorInput`, `PDFCollectorOutputSample`, `PDFCollectorOutput`)
- Provides abstract `BasePDFCollector` base class for concrete implementations
- Supports Mineru API-based parsing

Implementers should:
- Override `collect()` to return structured `PDFCollectorOutput`
- Override `filter()` to implement keyword-based filtering logic
- Use built-in helpers for file operations, logging, and directory management
"""

import os
import logging
from typing import List, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class PDFCollectorInput:
    """Represents input for a PDF collection/processing task."""

    # The directory containing the PDFs to be parsed
    input_dir: str = "input"
    # List of keywords to filter by
    keywords: List[str] = field(default_factory=list)


@dataclass
class PDFCollectorOutputSample:
    """Represents parse results from a single PDF."""

    # The unique identifier for the parsed result
    RawDataID: str = ""
    # The source path of the PDF
    Source: str = ""
    # The parsed markdown content of the PDF
    Location: str = ""
    # The parsed time of the PDF
    Time: str = ""
    # The parsed copyright information of the PDF
    Copyright: str = ""
    # The parsing method used (e.g., "Mineru API")
    Method: str = ""
    # Tags for the parsed content
    Tag: str = ""
    # The batch ID for the parsed result
    BatchID: str = ""


@dataclass
class PDFCollectorOutput:
    """Represents parse results from a PDF collection/processing task.

    A list of records, where each record corresponds to a parsed PDF result.
    """

    # List of parsed PDF results
    records: List[PDFCollectorOutputSample] = field(default_factory=list)


class BasePDFCollector(ABC):
    """
    An abstract base class for PDF parsing and filtering modules.

    This class provides common functionalities and configurations
    that can be shared across different PDF processing strategies,
    such as parsing via an API or filtering based on content.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
    ):
        """
        Initializes the base collector.

        Args:
            config (dict, optional): Configuration dictionary for the collector. Defaults to None.
        """

        self.config = config
        self.output_dir = self.config["output_dir"]
        self.batch_size = self.config["batch_size"]
        self.language = self.config["language"]
        self.check_pdf_limits = self.config["check_pdf_limits"]

        # Create output directory if it doesn't exist
        os.makedirs(self.config["output_dir"], exist_ok=True)

        # Load environment variables, typically for API keys
        if self.config["env_file"]:
            load_dotenv(dotenv_path=self.config["env_file"])

        # Initialize logger
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def collect(
        self,
        pdf_collector_input: PDFCollectorInput,
    ) -> PDFCollectorOutput:
        """
        Abstract method to perform the collection or processing task.

        Subclasses must implement this method to define their specific logic
        for parsing PDF data.

        Returns:
            PDFCollectorOutput: The result of the parsing process.
        """
        pass

    @abstractmethod
    def filter(
        self,
        pdf_collector_input: PDFCollectorInput,
        parsed_info: PDFCollectorOutput,
    ) -> PDFCollectorOutput:
        """
        Abstract method to filter records based on keywords.

        Subclasses must implement this method to define their specific logic
        for filtering records.

        Args:
            pdf_collector_input (PDFCollectorInput): Input configuration for the collector.
            parsed_info (PDFCollectorOutput): The parsed records to filter.

        Returns:
            PDFCollectorOutput: Filtered records.
        """
        pass

    def run(
        self,
        pdf_collector_input: PDFCollectorInput,
    ) -> PDFCollectorOutput:
        """
        Runs the collection and filtering process.

        Args:
            pdf_collector_input (PDFCollectorInput): Input configuration for the collector.

        Returns:
            PDFCollectorOutput: Filtered records.
        """
        # Parse PDFs and save the successful records
        parsed_info = self.collect(pdf_collector_input)
        # Filter parsed records based on keywords
        filtered_info = self.filter(pdf_collector_input, parsed_info)

        return filtered_info
