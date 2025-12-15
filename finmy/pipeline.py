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

import uuid
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import List
import pytz

from finmy.generic import RawData, UserQueryInput
from finmy.converter import (
    write_text_data_to_block,
    raw_data_and_summarized_query_to_match_input,
    convert_to_build_input,
    match_output_to_meta_samples,
)
from finmy.db_manager import DataManager
from finmy.builder.base import BuildInput
from finmy.builder.lm_build import LMBuilder
from finmy.builder.class_build.main_build import ClassLMBuilder
from finmy.matcher.base import MatchInput, SummarizedUserQuery
from finmy.matcher.lm_match import LLMMatcher
from finmy.matcher.summarizer import KWLMSummarizer


class FinmyPipeline:
    """A pipeline class for FinMycelium data processing workflow."""

    def __init__(self, finmy_config: dict):
    # def __init__(self, output_dir: str):
        """
        Initialize the pipeline with output directory.

        Args:
            output_dir: Directory where output files will be saved
        """
        self.output_dir = finmy_config["output_dir"]
        self.logger = None
        self.data_manager = None

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

        logger.info(f"Logging initialized. Log file: {log_file}")
        self.logger = logger
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
                source="",
                location=filename,
                time=formatted_time,
                data_copyright="AgenticFin Lab, All rights reserved.",
                tag=[""],
                method="",
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
        self.logger.info(f"User query input object created: {user_query_input}")
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
        summarizer = KWLMSummarizer({"llm_name": "ARK/doubao-seed-1-6-flash-250828"})
        summarized_query = summarizer.summarize(user_query_input)
        self.logger.info(f"Summarized query created: {summarized_query}")
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
        self.logger.info(f"MatchInput object created: {match_input}")
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
        self.logger.info("Performing matching using lm_matcher...")
        lm_matcher = LLMMatcher(lm_name="ARK/doubao-seed-1-6-flash-250828")
        match_output = lm_matcher.run(match_input)
        self.logger.info(f"Matching result: {match_output}")
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
        self.logger.info(f"Meta samples created: {meta_samples}")
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
        self.logger.info(f"BuildInput object created: {build_input}")
        self.logger.info("=" * 25)
        return build_input

    def lm_build_pipeline_main(
        self, raw_texts: List[str], query_text: str, key_words: List[str]
    ):
        """
        Main function that orchestrates the complete data processing workflow.

        This function executes the following steps:
        1. Initialize data manager
        2. Create and store raw data records
        3. Create and store user query input
        4. Summarize user query
        5. Match raw data with summarized query
        6. Generate meta samples from match results
        7. Store meta samples
        8. Create build input for downstream processing
        """
        # Initialize logging
        self.setup_logging()

        # Initialize data manager
        self.data_manager = DataManager()

        # Step 1: Create raw data records from sample texts
        raw_texts = raw_texts
        raw_data_records = self.create_raw_data_records(raw_texts)

        # Step 2: Store raw data records in database
        self.store_raw_data(raw_data_records)

        # Step 3: Create and store user query input
        user_query_input = self.create_and_store_user_query(
            query_text=query_text,
            key_words=key_words,
        )

        # Step 4: Summarize user query
        summarized_query = self.summarize_user_query(user_query_input)

            
        meta_samples=[]
        for i in range(len(raw_data_records)):
            # Step 5: Create match input from raw data and summarized query
            match_input = self.match_raw_data_with_query(
                raw_data_records[i], summarized_query
            )
            # Step 6: Perform LLM matching
            match_output = self.perform_llm_matching(match_input)

            # Step 7: Convert match output to meta samples
            meta_sample = self.create_meta_samples(match_output, raw_data_records[i])

            meta_samples += meta_sample

        # Step 8: Store meta samples in database
        self.store_meta_samples(meta_samples)

        # Step 9: Create build input for downstream processing
        build_input = self.create_build_input(user_query_input, meta_samples)
        # Note: build_input is created for demonstration purposes and can be used
        # by downstream builders in a production workflow
        assert build_input is not None, "BuildInput should be created successfully"

        print("Start building ...")

        # Uncomment for standard LMBuilder
        # lmbuilder = LMBuilder(
        #     config={"output_dir": self.output_dir}  # Specify output directory
        # )
        # build_output = lmbuilder.build(build_input)

        # Using ClassLMBuilder
        lmbuilder = ClassLMBuilder(
            config={"output_dir": self.output_dir}  # Specify output directory
        )
        build_output = lmbuilder.build(build_input)

        # print("build_output:", build_output)

        assert build_output is not None, "BuildOutput should be created successfully"

        self.logger.info("Test flow completed successfully!")
