"""
Test Flow Script for FinMycelium Data Processing Pipeline

This script demonstrates the complete workflow of processing raw text data through
the FinMycelium system:

1. Raw Data Ingestion: Convert raw text content into RawData objects and store them
2. User Query Processing: Create and store user query inputs
3. Query Summarization: Generate summarized queries using keyword-based LLM summarizer
4. Data Matching: Match raw data against summarized queries using LLM matcher
5. Meta Sample Generation: Convert match outputs into meta samples
6. Build Input Preparation: Prepare build inputs for downstream processing

The script serves as both a test case and an example of how to use the FinMycelium
framework for financial data processing and knowledge extraction.
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import pytz

from finmy.generic import RawData, UserQueryInput
from finmy.converter import (
    write_text_data_to_block,
    raw_data_and_summarized_query_to_match_input,
    convert_to_build_input,
    match_output_to_meta_samples,
)
from finmy.db_manager import DataManager
from finmy.builder.base import BuildInput, BaseBuilder
from finmy.builder.registry import get as get_builder
from finmy.summarizer.summarizer import BaseSummarizer
from finmy.summarizer.registry import get as get_summarizer
from finmy.matcher.base import MatchInput, SummarizedUserQuery, BaseMatcher
from finmy.matcher.registry import get as get_matcher
from finmy.pdf_collector import PDFCollectorOutput
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput
from finmy.url_collector.base import URLCollectorOutput, URLCollectorInput
from finmy.url_collector.url_parser import URLParser
from finmy.matcher.base import MatchOutput, MatchItem
from finmy.converter import read_text_data_from_block
from finmy.builder.agent_build.prompts import *


# ============================================================================
# Pipeline Class
# ============================================================================


class FinmyPipeline:
    """A pipeline class for FinMycelium data processing workflow.

    This class uses **Registry Factory Pattern** to enable dynamic component
    selection without code changes.
    Different summarizers, matchers, and builders can be selected via configuration.

    """

    def __init__(self, finmy_config: dict):
        """
        Initialize the pipeline with configuration.

        Args:
            finmy_config: A dict containing all configuration parameters for the pipeline.
        """
        self.config = dict(finmy_config) if finmy_config is not None else {}

        # Core configuration fields
        self.output_dir = self.config["output_dir"]

        # Component configurations
        self.url_collector_config = self.config["url_collector_config"]
        self.pdf_collector_config = self.config["pdf_collector_config"]
        self.summarizer_config = self.config["summarizer_config"]
        self.matcher_config = self.config["matcher_config"]
        self.builder_config = self.config["builder_config"]
        self.db_config = self.config["db_config"]

        # stateful modules
        self.logger: Optional[logging.Logger] = None
        self.data_manager: Optional[DataManager] = None

        # Work modules
        self.pdf_collector: Optional[PDFCollector] = None
        self.url_collector: Optional[URLParser] = None
        self.summarizer: Optional[BaseSummarizer] = None
        self.matcher: Optional[BaseMatcher] = None
        self.builder: Optional[BaseBuilder] = None
        self.initialize()

    def initialize(self):
        """
        Initialize the pipeline components.

        This method sets up logging, data manager, and component factories.
        """
        # Initialize the Stateful modules
        self.logger = self.setup_logging()
        self.data_manager = DataManager(self.db_config)

        # Initialize the Work modules
        self.pdf_collector = PDFCollector(self.pdf_collector_config)
        self.url_collector = URLParser(self.url_collector_config)
        self.summarizer = self._create_summarizer()
        if self.matcher_config["use_matcher"]:
            self.matcher = self._create_matcher()
        else:
            self.logger.info("not using matcher")
            self.matcher = None
        self.builder = self._create_builder()

    # ------------------------------------------------------------------
    # Internal helpers for configurable component selection (Registry-based)
    # ------------------------------------------------------------------

    def _create_summarizer(self) -> BaseSummarizer:
        """
        Factory for the summarizer component using registry pattern.

        Returns:
            A summarizer instance based on ``summarizer_type`` configuration.
        """
        config = self.summarizer_config
        if "summarizer_type" not in config:
            # Fallback to "type" if "summarizer_type" is not present
            if "type" in config:
                config["summarizer_type"] = config.pop("type")
            else:
                raise ValueError(
                    "summarizer_config must contain 'summarizer_type' or 'type'"
                )
        return get_summarizer(config)

    def _create_matcher(self) -> BaseMatcher:
        """
        Factory for the matcher component using registry pattern.

        Returns:
            A matcher instance based on ``matcher_type`` configuration.
        """
        config = self.matcher_config.copy()
        if "matcher_type" not in config:
            raise ValueError("matcher_config must contain 'matcher_type'")
        matcher_type = config["matcher_type"]
        self.logger.info("Creating matcher: %s", matcher_type)
        return get_matcher(config)

    def _create_builder(self) -> BaseBuilder:
        """
        Factory for the builder component using registry pattern.

        Returns:
            A builder instance based on ``builder_type`` configuration.
        """
        config = self.builder_config
        if "builder_type" not in config:
            # Fallback to "type" if "builder_type" is not present
            if "type" in config:
                config["builder_type"] = config.pop("type")
            else:
                raise ValueError("builder_config must contain 'builder_type' or 'type'")
        if "output_dir" not in config:
            config["output_dir"] = self.output_dir
        return get_builder(config)

    def setup_logging(self) -> logging.Logger:
        """
        Setup logging configuration to output to both console and file.
        Each run creates a new log file with timestamp.


        Returns:
            Logger instance configured for this script
        """
        # Create logs directory if it doesn't exist
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)

        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"test_flow_{timestamp}.log"

        # Create logger
        logger = logging.getLogger("test_flow")
        logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Create formatters
        detailed_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(detailed_formatter)

        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(detailed_formatter)

        # Add handlers to logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        logger.info("Logging initialized. Log file: %s", log_file)
        return logger

    def create_raw_data_records(self, texts: List[str]) -> List[RawData]:
        """
        Convert raw text content into RawData objects and store them in block storage.

        Args:
            texts: List of raw text strings to be processed

        Returns:
            List of RawData objects created from the input texts
        """
        raw_data_records = []
        for text in texts:
            # Write content to block storage
            filename = write_text_data_to_block(text)
            # Create RawData object
            utc_time = datetime.now(pytz.UTC)
            formatted_time = utc_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            raw_data = RawData(
                raw_data_id=str(uuid.uuid4()),
                source="mock_text",
                location=filename,
                time=formatted_time,
                data_copyright="AgenticFin Lab, All rights reserved.",
                tag="",
                method="mock_input",
            )
            raw_data_records.append(raw_data)
        return raw_data_records

    def create_raw_data_from_pdf_output(
        self, pdf_output: PDFCollectorOutput
    ) -> List[RawData]:
        """
        Convert PDFCollectorOutput into RawData objects.

        Each parsed PDF record is mapped directly to a RawData entry by
        reusing its metadata and parsed markdown location.
        """
        raw_data_records: List[RawData] = []
        for sample in pdf_output.records:
            # sample.Location is already a markdown file path produced by PDFCollector
            # We treat it as the storage location for the raw content.
            time_str = sample.Time or datetime.now(pytz.UTC).strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
            raw_data = RawData(
                raw_data_id=sample.RawDataID or str(uuid.uuid4()),
                source=sample.Source,
                location=sample.Location,
                time=time_str,
                data_copyright=sample.Copyright
                or "AgenticFin Lab, All rights reserved.",
                method=sample.Method or "PDFCollector",
                tag=sample.Tag or "",
            )
            raw_data_records.append(raw_data)
        return raw_data_records

    def create_raw_data_from_url_output(
        self, url_output: URLCollectorOutput
    ) -> List[RawData]:
        """
        Convert URLCollectorOutput into RawData objects.

        For each parsed URL, the cleaned text content is written to block storage
        and referenced by the resulting RawData entry.
        """
        raw_data_records: List[RawData] = []

        # url_output.parsed_contents: Dict[int, str] maps URL ID -> cleaned text
        contents = url_output.parsed_contents
        results = {item["ID"]: item for item in url_output.results}

        for url_id, content in contents.items():
            result = results[url_id]
            url = result["url"]

            # Skip entries without meaningful content
            if not content:
                continue

            # Persist the cleaned content into block storage
            filename = write_text_data_to_block(content)

            utc_time = datetime.now(pytz.UTC)
            formatted_time = utc_time.strftime("%Y-%m-%d %H:%M:%S %Z")

            raw_data = RawData(
                raw_data_id=str(uuid.uuid4()),
                source=url,
                location=filename,
                time=formatted_time,
                data_copyright="AgenticFin Lab, All rights reserved.",
                method="URLParser",
                tag="url",
            )
            raw_data_records.append(raw_data)

        return raw_data_records

    def store_raw_data(self, raw_data_records: List[RawData]) -> None:
        """
        Store RawData objects in the database.

        Args:
            raw_data_records: List of RawData objects to be stored
        """
        self.logger.info("Writing and saving RawData objects...")
        self.data_manager.insert_raw_data_batch(raw_data_records)
        self.logger.info("RawData objects saved successfully")
        self.logger.info("=" * 25)

    def create_and_store_user_query(
        self,
        query_text: str,
        key_words: List[str],
    ) -> UserQueryInput:
        """
        Create a user query input object and store it in the database.

        Args:
            query_text: The query text
            key_words: List of keywords for the query

        Returns:
            UserQueryInput object that was created and stored
        """
        self.logger.info("Creating user query input object...")
        user_query_input = UserQueryInput(
            query_text=query_text,
            key_words=key_words,
        )
        self.logger.info("User query input object created: %s", user_query_input)
        self.logger.info("Inserting user query input object into database...")
        self.data_manager.insert_user_query(user_query_input)
        self.logger.info("User query input object inserted successfully")
        self.logger.info("=" * 25)
        return user_query_input

    def summarize_user_query(
        self, user_query_input: UserQueryInput
    ) -> SummarizedUserQuery:
        """
        Generate a summarized query from user query input using keyword-based LLM summarizer.

        Args:
            user_query_input: UserQueryInput object to be summarized

        Returns:
            SummarizedUserQuery object containing the summarized query
        """
        self.logger.info("Generating summarized query using Summarizer...")
        summarized_query = self.summarizer.summarize(user_query_input)
        self.logger.info("Summarized query created: %s", summarized_query)
        self.logger.info("=" * 25)
        return summarized_query

    def match_raw_data_with_query(
        self, raw_data: RawData, summarized_query: SummarizedUserQuery
    ) -> MatchInput:
        """
        Create a MatchInput object from raw data and summarized query.

        Args:
            raw_data: RawData object to be matched
            summarized_query: SummarizedUserQuery object for matching

        Returns:
            MatchInput object ready for matching operations
        """
        self.logger.info(
            "Creating MatchInput object from raw_data and summarized_query..."
        )
        match_input = raw_data_and_summarized_query_to_match_input(
            raw_data=raw_data,
            summarized_query=summarized_query,
        )
        self.logger.info("MatchInput object created: %s", match_input)
        self.logger.info("=" * 25)
        return match_input

    def perform_llm_matching(self, match_input: MatchInput):
        """
        Perform matching using LLM matcher.

        Args:
            match_input: MatchInput object containing data to be matched

        Returns:
            Match output from the LLM matcher
        """
        match_output = self.matcher.run(match_input)
        self.logger.info("Matching result: %s", match_output)
        self.logger.info("=" * 25)
        return match_output

    def create_meta_samples(self, match_output, raw_data: RawData):
        """
        Convert match output into meta samples.

        Args:
            match_output: Output from the matcher
            raw_data: RawData object associated with the match output

        Returns:
            List of MetaSample objects created from the match output
        """
        self.logger.info("Creating meta_samples from match_output...")
        meta_samples = match_output_to_meta_samples(
            match_output=match_output,
            raw_data=raw_data,
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
        )
        self.logger.info("Meta samples created: %s", meta_samples)
        self.logger.info("=" * 25)
        return meta_samples

    def store_meta_samples(self, meta_samples) -> None:
        """
        Store meta samples in the database.

        Args:
            meta_samples: List of MetaSample objects to be stored
        """
        self.logger.info("Saving meta_samples to database...")
        self.data_manager.insert_meta_samples(meta_samples)
        self.logger.info("Meta samples saved successfully")
        self.logger.info("=" * 25)

    def create_build_input(
        self, user_query_input: UserQueryInput, meta_samples
    ) -> BuildInput:
        """
        Create BuildInput object from user query and meta samples.

        Args:
            user_query_input: UserQueryInput object
            meta_samples: List of MetaSample objects

        Returns:
            BuildInput object ready for builder processing
        """
        self.logger.info(
            "Creating BuildInput object from user_query and meta_samples..."
        )
        build_input = convert_to_build_input(
            user_query=user_query_input,
            meta_samples=meta_samples,
            extras={},
        )
        self.logger.info("BuildInput object created: %s", build_input)
        self.logger.info("=" * 25)
        return build_input

    def _is_url(self, source: str) -> bool:
        """
        Check if a source string is a URL.

        Args:
            source: String to check

        Returns:
            True if the string is a URL, False otherwise
        """
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc]) and result.scheme in [
                "http",
                "https",
            ]
        except Exception:
            return False

    def _is_pdf_path(self, source: str) -> bool:
        """
        Check if a source string is a PDF file path.

        Args:
            source: String to check

        Returns:
            True if the string is a PDF file path, False otherwise
        """
        return source.lower().endswith(".pdf")

    def _collect_data_from_sources(
        self,
        data_sources: List[str],
        pdf_collector_config: Optional[dict] = None,
        url_collector_config: Optional[dict] = None,
    ) -> List[RawData]:
        """
        Collect data from URLs or PDF paths using collectors.

        Args:
            data_sources: List of URLs or PDF file paths
            pdf_collector_config: Optional configuration for PDF collector
            url_collector_config: Optional configuration for URL collector

        Returns:
            List of RawData objects created from collected data
        """
        urls = []
        pdf_paths = []

        # Separate URLs and PDF paths
        for source in data_sources:
            if self._is_url(source):
                urls.append(source)
            elif self._is_pdf_path(source):
                pdf_paths.append(source)
            else:
                # Try to check if it's a directory containing PDFs
                if os.path.isdir(source):
                    # If it's a directory, treat it as PDF input directory
                    pdf_paths.append(source)
                else:
                    # Log warning if logger is available
                    if self.logger:
                        self.logger.warning(
                            "Unknown source type: %s, skipping...", source
                        )
                    else:
                        self.logger.warning(
                            "Warning: Unknown source type: %s, skipping...", source
                        )

        raw_data_records: List[RawData] = []

        # Process PDFs
        if pdf_paths:
            # Default PDF collector config
            # Use collector_config from self.config as base
            default_pdf_config = self.pdf_collector_config

            # Ensure output_dir is set if not present
            if "output_dir" not in default_pdf_config:
                default_pdf_config["output_dir"] = os.path.join(
                    self.config["save_folder"], "pdf_collector_output"
                )

            # Set other defaults if not present
            if "batch_size" not in default_pdf_config:
                default_pdf_config["batch_size"] = 200
            if "language" not in default_pdf_config:
                default_pdf_config["language"] = "ch"
            if "check_pdf_limits" not in default_pdf_config:
                default_pdf_config["check_pdf_limits"] = True
            if "env_file" not in default_pdf_config:
                default_pdf_config["env_file"] = ".env"

            if pdf_collector_config:
                default_pdf_config.update(pdf_collector_config)

            pdf_collector = PDFCollector(default_pdf_config)

            # Group PDF paths: if it's a directory, use input_dir;
            # if it's a file, use input_pdf_path
            pdf_dirs = [p for p in pdf_paths if os.path.isdir(p)]
            pdf_files = [p for p in pdf_paths if os.path.isfile(p)]

            # Process directories
            for pdf_dir in pdf_dirs:
                pdf_input = PDFCollectorInput(
                    input_dir=pdf_dir,
                    input_pdf_path="",
                    keywords=[],
                )
                pdf_output = pdf_collector.run(pdf_input)
                raw_data_records.extend(
                    self.create_raw_data_from_pdf_output(pdf_output)
                )

            # Process individual PDF files
            for pdf_file in pdf_files:
                pdf_input = PDFCollectorInput(
                    input_dir="",
                    input_pdf_path=os.path.abspath(pdf_file),
                    keywords=[],
                )
                pdf_output = pdf_collector.run(pdf_input)
                raw_data_records.extend(
                    self.create_raw_data_from_pdf_output(pdf_output)
                )

        # Process URLs
        if urls:
            # Default URL collector config
            # Use collector_config from self.config as base
            default_url_config = self.url_collector_config

            # Set defaults if not present
            if "delay" not in default_url_config:
                default_url_config["delay"] = 1.0
            if "use_selenium_fallback" not in default_url_config:
                default_url_config["use_selenium_fallback"] = True
            if "selenium_wait_time" not in default_url_config:
                default_url_config["selenium_wait_time"] = 5

            if url_collector_config:
                default_url_config.update(url_collector_config)

            url_input = URLCollectorInput(
                urls=urls,
                extras={},
            )
            url_output = self.url_collector.run(url_input)
            raw_data_records.extend(self.create_raw_data_from_url_output(url_output))

        if not raw_data_records:
            raise ValueError(
                "No raw data records created from collectors. "
                "Please ensure data_sources contains valid URLs or PDF paths."
            )

        return raw_data_records

    def lm_build_pipeline_main(
        self,
        data_sources: List[str],
        query_text: str,
        key_words: List[str],
        pdf_collector_config: Optional[dict] = None,
        url_collector_config: Optional[dict] = None,
    ):
        """
        Main function that orchestrates the complete data processing workflow.

        This function executes the following steps:
        1. Initialize data manager
        2. Collect data from URLs or PDF paths using collectors
        3. Create and store raw data records
        4. Create and store user query input
        5. Summarize user query
        6. Match raw data with summarized query
        7. Generate meta samples from match results
        8. Store meta samples
        9. Create build input for downstream processing
        10. Run the configured builder to get the final build output.

        Args:
            data_sources: List of URLs or PDF file paths to collect data from
            query_text: Natural language query text
            key_words: List of keywords for the query
            pdf_collector_config: Optional configuration dict for PDF collector
            url_collector_config: Optional configuration dict for URL collector

        Returns:
            The build output object produced by the selected builder.
        """
        # Initialize logging
        self.setup_logging()

        # Initialize data manager
        self.data_manager = DataManager(engine_config=self.db_config)

        # Step 1: Collect data from URLs or PDF paths using collectors
        raw_data_records = self._collect_data_from_sources(
            data_sources=data_sources,
            pdf_collector_config=pdf_collector_config,
            url_collector_config=url_collector_config,
        )

        # Step 2: Store raw data records in database
        self.store_raw_data(raw_data_records)

        # Step 3: Create and store user query input
        user_query_input = self.create_and_store_user_query(
            query_text=query_text,
            key_words=key_words,
        )

        # Step 4: Summarize user query
        summarized_query = self.summarize_user_query(user_query_input)

        meta_samples = []

        if self.matcher_config.use_matcher:
            for raw_data in raw_data_records:
                # Step 5: Create match input from raw data and summarized query
                match_input = self.match_raw_data_with_query(raw_data, summarized_query)
                # Step 6: Perform LLM matching
                match_output = self.perform_llm_matching(match_input)

                # Step 7: Convert match output to meta samples
                meta_sample = self.create_meta_samples(match_output, raw_data)
                meta_samples += meta_sample
        else:
            self.logger.info("not using matcher")
            for raw_data in raw_data_records:
                content = read_text_data_from_block(raw_data.location)
                mock_match_output = MatchOutput(
                    items=[
                        MatchItem(
                            paragraph=content,
                            start=0,
                            end=len(content),
                        )
                    ],
                )
                meta_sample = self.create_meta_samples(mock_match_output, raw_data)
                meta_samples += meta_sample

        # Step 8: Store meta samples in database
        self.store_meta_samples(meta_samples)

        # Step 9: Create build input for downstream processing
        build_input = self.create_build_input(user_query_input, meta_samples)
        # Note: build_input is created for demonstration purposes and can be used
        # by downstream builders in a production workflow

        # 4. Create the system and user prompts
        agent_names = list(self.builder_config["agents"].keys())
        agent_system_msgs = {}
        agent_user_msgs = {}

        for name in agent_names:
            if "skeleton" in name.lower():
                agent_system_msgs[name] = EventLayoutReconstructorSys
                agent_user_msgs[name] = EventLayoutReconstructorUser
            if "participant" in name.lower():
                agent_system_msgs[name] = ParticipantReconstructorSys
                agent_user_msgs[name] = ParticipantReconstructorUser
            if "transaction" in name.lower():
                agent_system_msgs[name] = TransactionReconstructorSys
                agent_user_msgs[name] = TransactionReconstructorUser
            if "episode" in name.lower():
                agent_system_msgs[name] = EpisodeReconstructorSys
                agent_user_msgs[name] = EpisodeReconstructorUser
            if "stagedescription" in name.lower():
                agent_system_msgs[name] = StageDescriptionReconstructorSys
                agent_user_msgs[name] = StageDescriptionReconstructorUser
            if "eventdescription" in name.lower():
                agent_system_msgs[name] = EventDescriptionReconstructorSys
                agent_user_msgs[name] = EventDescriptionReconstructorUser

        # Build the state
        state = {
            "build_input": build_input,
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": agent_system_msgs,
            "agent_user_msgs": agent_user_msgs,
        }

        # Run build
        self.logger.info("Starting AgentEventBuilder...")
        graph = self.builder.graph()

        # Retrieve graph config from the loaded configuration
        graph_config = self.builder_config["graph_config"]

        final_state = graph.invoke(state, graph_config)
        self.logger.info("Build completed.")

        # Integrate final result
        final_cascade = self.builder.integrate_results(final_state)

        build_input = final_state.pop("build_input")

        # Save the final state to the json
        self.builder.save_traces(
            build_input.to_dict(),
            save_name="BuildInput",
            file_format="json",
        )
        self.builder.save_traces(
            final_state,
            save_name="FinalState",
            file_format="json",
        )
        self.builder.save_traces(
            final_cascade,
            save_name="FinalEventCascade",
            file_format="json",
        )
        self.logger.info("Traces saved.")

        # Test integrate_from_files
        self.logger.info("\nTesting integrate_from_files...")
        restored_cascade = self.builder.integrate_from_files()
        self.builder.save_traces(
            restored_cascade,
            save_name="IntegratedEventCascade",
            file_format="json",
        )
        self.logger.info("integrate_from_files test completed.")

        return restored_cascade

    def lm_build_pipeline_with_contents(
        self,
        contents: list,
        query_text: str,
        key_words: list,
    ):
        """
        Build the pipeline with the provided contents (list of text),
        query_text (query string), and key_words (list of keywords).
        Returns the build result.
        """
        # Initialize logging
        self.setup_logging()

        # Initialize data manager
        self.data_manager = DataManager(engine_config=self.db_config)

        # 初始化原始数据
        raw_data_records = self.create_raw_data_records(contents)
        # 存储原始数据
        self.store_raw_data(raw_data_records)

        # Step 3: Create and store user query input
        user_query_input = self.create_and_store_user_query(
            query_text=query_text,
            key_words=key_words,
        )

        # Step 4: Summarize user query
        summarized_query = self.summarize_user_query(user_query_input)

        meta_samples = []

        if self.matcher_config["use_matcher"]:
            for raw_data in raw_data_records:
                # Step 5: Create match input from raw data and summarized query
                match_input = self.match_raw_data_with_query(raw_data, summarized_query)
                # Step 6: Perform LLM matching
                match_output = self.perform_llm_matching(match_input)

                # Step 7: Convert match output to meta samples
                meta_sample = self.create_meta_samples(match_output, raw_data)
                meta_samples += meta_sample
        else:
            self.logger.info("not using matcher")
            for raw_data in raw_data_records:
                content = read_text_data_from_block(raw_data.location)
                mock_match_output = MatchOutput(
                    items=[
                        MatchItem(
                            paragraph=content,
                            start=0,
                            end=len(content),
                        ),
                    ],
                )
                meta_sample = self.create_meta_samples(mock_match_output, raw_data)
                meta_samples += meta_sample

        # Step 8: Store meta samples in database
        self.store_meta_samples(meta_samples)

        build_input = self.create_build_input(user_query_input, meta_samples)

        if self.builder_config["builder_type"] == "AgentEventBuilder":
            agent_names = list(self.builder_config["agents"].keys())
            agent_system_msgs = {}
            agent_user_msgs = {}

            for name in agent_names:
                if "skeleton" in name.lower():
                    agent_system_msgs[name] = EventLayoutReconstructorSys
                    agent_user_msgs[name] = EventLayoutReconstructorUser
                if "participant" in name.lower():
                    agent_system_msgs[name] = ParticipantReconstructorSys
                    agent_user_msgs[name] = ParticipantReconstructorUser
                if "transaction" in name.lower():
                    agent_system_msgs[name] = TransactionReconstructorSys
                    agent_user_msgs[name] = TransactionReconstructorUser
                if "episode" in name.lower():
                    agent_system_msgs[name] = EpisodeReconstructorSys
                    agent_user_msgs[name] = EpisodeReconstructorUser
                if "stagedescription" in name.lower():
                    agent_system_msgs[name] = StageDescriptionReconstructorSys
                    agent_user_msgs[name] = StageDescriptionReconstructorUser
                if "eventdescription" in name.lower():
                    agent_system_msgs[name] = EventDescriptionReconstructorSys
                    agent_user_msgs[name] = EventDescriptionReconstructorUser

            # Build the state
            state = {
                "build_input": build_input,
                "agent_results": [],
                "agent_executed": [],
                "cost": [],
                "agent_system_msgs": agent_system_msgs,
                "agent_user_msgs": agent_user_msgs,
            }

            # Run build
            self.logger.info("Starting AgentEventBuilder...")
            graph = self.builder.graph()

            # Retrieve graph config from the loaded configuration
            graph_config = self.builder_config["graph_config"]

            final_state = graph.invoke(state, graph_config)
            self.logger.info("Build completed.")

            # Integrate final result
            final_cascade = self.builder.integrate_results(final_state)

            build_input = final_state.pop("build_input")

            # Save the final state to the json
            self.builder.save_traces(
                build_input.to_dict(),
                save_name="BuildInput",
                file_format="json",
            )
            self.builder.save_traces(
                final_state,
                save_name="FinalState",
                file_format="json",
            )
            self.builder.save_traces(
                final_cascade,
                save_name="FinalEventCascade",
                file_format="json",
            )
            self.logger.info("Traces saved.")

            # Test integrate_from_files
            self.logger.info("\nTesting integrate_from_files...")
            restored_cascade = self.builder.integrate_from_files()
            self.builder.save_traces(
                restored_cascade,
                save_name="IntegratedEventCascade",
                file_format="json",
            )
            self.logger.info("integrate_from_files test completed.")

            return restored_cascade

        elif self.builder_config["builder_type"] == "ClassEventBuilder":
            return self.builder.build(build_input)

        else:
            raise ValueError(
                f"Invalid builder type: {self.builder_config['builder_type']}"
            )
