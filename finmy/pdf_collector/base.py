from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


@dataclass
class CollectInput:
    """
    Input configuration for PDF collection tasks.

    Describes parameters for a batch or single PDF processing run, consumed
    by collectors during `collect`.

    Fields:
    - source_dir: Directory path containing all PDFs to process
    - output_dir: Writable directory for outputs and intermediates
    - batch_size: Max number of documents per batch (default 50)
    - language: Primary document language (e.g., "zh", "en") to guide tokenization/OCR/layout strategies
    - check_pdf_limits: Whether to enforce size/page limits
    - split_large: Split over-limit PDFs (e.g., by pages) when limits are enabled
    - max_pages: Max pages per PDF (default 600). None disables the limit
    - max_size_mb: Max size in MB per PDF (default 200). None disables the limit
    - method: Collection/parsing method name (e.g., "PyMuPDF", "Mineru")
    - metadata: Task-level extra metadata (key-value), e.g., source tags, task ID
    """

    source_dir: str = ""
    output_dir: str = ""
    batch_size: int = 50
    language: str = "en"
    check_pdf_limits: bool = True
    split_large: bool = True
    max_pages: Optional[int] = 600
    max_size_mb: Optional[int] = 200
    method: str = "unspecified"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectOutput:
    """
    Output of a PDF collection task.

    Aggregates processing status, produced artifacts, statistics, and timing.

    Fields:
    - processed_files: Paths of successfully processed files (including split parts)
    - failed_files: Paths that failed (unreachable, format errors, parsing issues)
    - artifacts: Produced artifacts keyed by name (text, structured JSON, indexes, thumbnails, etc.)
    - report: Statistics (durations, error distribution, page counts, size distribution)
    - status: Final task status ("success", "partial", "failed", "unknown")
    - start_time: Task start timestamp
    - end_time: Task end timestamp
    """

    processed_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    report: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class PDFCollectorBase(ABC):
    """
    Base class for PDF collectors.

    Lifecycle:
    1) validate_input: validate inputs
    2) prepare: pre-work (env checks, cache/dir setup)
    3) collect: core collection/parsing (abstract; implemented by subclasses)
    4) post_process: result post-processing (stats, indexing, cleanup)

    Usage:
    - Subclass and implement `collect`; optionally override `prepare` and `post_process`
    - Call `run` to execute the full flow and obtain `CollectOutput`
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def run(self, collect_input: CollectInput) -> CollectOutput:
        """
        Execute the full collection flow.

        Steps: validate -> prepare -> collect -> post_process.

        Args:
        - collect_input: input configuration

        Returns:
        - CollectOutput: aggregated results and artifacts
        """
        self.validate_input(collect_input)
        self.prepare(collect_input)
        output = self.collect(collect_input)
        self.post_process(output)
        return output

    def validate_input(self, collect_input: CollectInput) -> None:
        """
        Basic input validation.

        Requires:
        - writable `output_dir`
        - `sources` is a directory path
        - `batch_size` > 0
        """
        if not collect_input.output_dir:
            raise ValueError("output_dir is required")
        if not isinstance(collect_input.sources, str) or not collect_input.sources:
            raise ValueError("sources must be a non-empty directory path string")
        src_path = Path(collect_input.sources)
        if not src_path.exists() or not src_path.is_dir():
            raise ValueError("sources must point to an existing directory")
        if collect_input.batch_size <= 0:
            raise ValueError("batch_size must be positive")

    def prepare(self, collect_input: CollectInput) -> None:
        """
        Pre-work stage.

        Default no-op. Subclasses may:
        - create/clean output directories
        - load parsing models or OCR resources
        - initialize caches/index builders
        """
        return None

    @abstractmethod
    def collect(self, collect_input: CollectInput) -> CollectOutput: ...

    def post_process(self, output: CollectOutput) -> None:
        """
        Post-processing stage.

        Default no-op. Subclasses may:
        - generate and persist reports
        - archive artifacts and update indexes
        - clean up intermediate files
        """
        return None
