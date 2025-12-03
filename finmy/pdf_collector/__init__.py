"""
PDF Collector Module

This module provides functionality for collecting and processing PDF files.
It includes base classes and utilities for PDF file handling.

Classes:
    BasePDFCollector - Abstract base class for PDF collectors
    PDFCollectorInput - Data class for collector input parameters
    PDFCollectorOutput - Data class for collector output results
    PDFParser - PDF parser implementation using Mineru API
    PDFFilter - PDF filter implementation based on keyword matching

Functions:
    Various utility functions for file operations, PDF processing, and data handling
"""

from .base import BasePDFCollector, PDFCollectorInput, PDFCollectorOutput
from .pdf_parser import PDFParser
from .pdf_filter import PDFFilter

__all__ = [
    "BasePDFCollector",
    "PDFCollectorInput",
    "PDFCollectorOutput",
    "PDFParser",
    "PDFFilter",
]
