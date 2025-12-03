"""
Base abstractions for PDF collection and processing.

- Provides a consistent result structure (`PDFCollectorInput`, `PDFCollectorOutput`).
- Defines an abstract `BasePDFCollector` to be extended by concrete collectors.

We support different ways of PDF processing:
- API-based parser: uses external APIs (e.g., Mineru API) to extract content from PDFs.

Implementers should:
- Override `collect` to produce structured output using `PDFCollectorOutput`.
- Use the provided helper methods for file operations, logging, and directory management.
"""

import os
import csv
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class PDFCollectorInput:
    """Represents input for a PDF collection/processing task."""

    # The directory containing the files
    input_dir_path: str
    # The specific path to a PDF file (if applicable)
    input_pdf_path: str
    # The directory to store output files
    output_dir_path: str
    # List of keywords to filter by
    keywords: List[str]
    # Path to the .env file for loading environment variables
    env_file: Optional[str] = ".env"


@dataclass
class PDFCollectorOutput:
    """Represents output from a PDF collection/processing task."""

    # List of extracted text snippets
    content_list: list[str] = field(default_factory=list)
    # List of extracted image paths
    images: list[str] = field(default_factory=list)
    # The full text content of the document
    full_content: str = ""
    # Layout information (e.g., page structure)
    layout: dict = field(default_factory=dict)


class BasePDFCollector(ABC):
    """
    An abstract base class for PDF collection and processing modules.

    This class provides common functionalities and configurations
    that can be shared across different PDF processing strategies,
    such as parsing via an API or filtering based on content.
    """

    def __init__(self, pdf_collector_input: PDFCollectorInput):
        """
        Initializes the base collector.

        Args:
            pdf_collector_input (PDFCollectorInput): Input configuration for the collector.
        """
        self.input_dir = pdf_collector_input.input_dir_path
        self.output_dir = pdf_collector_input.output_dir_path
        self.keywords = pdf_collector_input.keywords
        self.logger = self._setup_logger()
        self._ensure_directories_exist()

        # Load environment variables, typically for API keys
        if pdf_collector_input.env_file:
            load_dotenv(dotenv_path=pdf_collector_input.env_file)
            self.logger.info(
                "Environment variables loaded from %s",
                pdf_collector_input.env_file,
            )

    def _ensure_directories_exist(self):
        """Creates input and output directories if they don't exist."""
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        self.logger.debug(
            "Ensured directories exist: %s, %s", self.input_dir, self.output_dir
        )

    def _setup_logger(self) -> logging.Logger:
        """Sets up a logger for the collector instance."""
        logger = logging.getLogger(self.__class__.__name__)
        # Avoid adding handlers multiple times
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    @staticmethod
    def read_csv_file(file_path: str) -> List[Dict[str, str]]:
        """
        Read a CSV file and return its content as a list of dictionaries.

        Args:
            file_path (str): Path to the CSV file to be read.

        Returns:
            List[Dict[str, str]]: List of dictionaries representing CSV rows.
        """
        records = []
        with open(file_path, "r", encoding="utf-8", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                records.append(row)
        return records

    @staticmethod
    def write_csv_file(
        file_path: str,
        records: List[Dict[str, str]],
        fieldnames: List[str],
    ) -> None:
        """
        Write records to a CSV file.

        Args:
            file_path (str): Path to the output CSV file.
            records (List[Dict[str, str]]): List of dictionaries to write.
            fieldnames (List[str]): List of field names for the CSV header.
        """
        with open(file_path, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def get_csv_fieldnames(file_path: str) -> List[str]:
        """
        Get the field names from the header of a CSV file.

        Args:
            file_path (str): Path to the CSV file.

        Returns:
            List[str]: List of field names from the CSV header.
        """
        with open(file_path, "r", encoding="utf-8", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            return reader.fieldnames or []

    @abstractmethod
    def collect(self) -> PDFCollectorOutput:
        """
        Abstract method to perform the collection or processing task.

        Subclasses must implement this method to define their specific logic
        for collecting or processing PDF data.

        Returns:
            PDFCollectorOutput: The result of the collection process.
        """
        pass

    @abstractmethod
    def filter(self, content: str) -> List[Dict[str, str]]:
        """
        Abstract method to filter records based on keywords.

        Subclasses must implement this method to define their specific logic
        for filtering records.

        Args:
            content (str): The content to filter.

        Returns:
            List[Dict[str, str]]: Filtered list of records.
        """
        pass
