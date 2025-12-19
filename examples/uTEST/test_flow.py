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
from finmy.matcher.base import MatchInput, SummarizedUserQuery
from finmy.matcher.lm_match import LLMMatcher
from finmy.summarizer.summarizer import KWLMSummarizer


def setup_logging() -> logging.Logger:
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
    return logger


def get_sample_raw_texts() -> List[str]:
    """
    Get sample raw text content for testing purposes.

    Returns:
        List of raw text strings containing financial and AI-related content
        in both Chinese and English.
    """
    return [
        """
        近年来，人工智能在资本市场与零售金融的应用显著增加。部分银行采用机器学习进行信用评分与反欺诈检测，这提升了风控效率与业务响应速度。然而，模型的稳定性与在极端市场情况下的表现仍需持续评估。

        一些机构建立了端到端的风险管理框架，包括数据治理、模型验证、监控与回溯测试。对于黑箱模型，内部与外部审计要求更高的可解释性，以满足监管对于透明度与审慎监管的原则。

        从合规角度来看，模型生命周期管理成为重点。审批、版本控制、变更记录与影响评估需要被完整记录。当模型输出被用于关键业务决策时，应建立人机协同机制与阈值告警。

        此外，数据质量直接影响模型表现。企业应建立数据目录与质量度量体系，确保训练与推断数据的一致性与合法合规使用。对于涉及个人数据的场景，必须遵守隐私保护与跨境数据流动的相关规定。

        展望未来，生成式 AI 在投研、客服与运营场景的应用将更广泛。与此同时，企业需要在创新与风险之间寻找平衡，将模型合规、透明度与韧性纳入治理框架的核心指标。
        """,
        """
        In recent years, artificial intelligence has seen significant growth in capital markets and retail finance applications. Some banks have adopted machine learning for credit scoring and fraud detection, boosting risk control efficiency and operational responsiveness. However, the stability of models and their performance under extreme market conditions still require continuous assessment.Several institutions have established end-to-end risk management frameworks, incorporating data governance, model validation, monitoring, and back-testing. For black-box models, both internal and external audits demand higher levels of explainability to meet regulatory expectations regarding transparency and sound supervision.
        
        From a compliance perspective, model lifecycle management is a key priority. Approval, version control, change tracking, and impact assessments must be fully documented. When model outputs are used for critical business decisions, firms should establish human-in-the-loop mechanisms and threshold alerts.
        
        Moreover, data quality directly affects model performance. Organizations should implement data catalogs and quality metrics systems to ensure consistency and lawful, compliant usage of data for training and inference. For scenarios involving personal data, privacy protection and cross-border data flow regulations must be strictly observed.
        
        Looking ahead, generative AI will be more widely used in investment research, customer service, and operations. At the same time, organizations need to balance innovation and risk by making model compliance, transparency, and resilience central metrics in their governance frameworks.
        """,
    ]


def create_raw_data_records(texts: List[str]) -> List[RawData]:
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
        raw_data = RawData(
            raw_data_id=str(uuid.uuid4()),
            source="https://example.com",
            location=filename,
            time="2024-06-01T12:00:00Z",
            data_copyright="AgenticFin Lab, All rights reserved.",
            tag=["测试"],
            method="人工导入",
        )
        raw_data_records.append(raw_data)
    return raw_data_records


def store_raw_data(
    data_manager: DataManager, raw_data_records: List[RawData], logger: logging.Logger
) -> None:
    """
    Store RawData objects in the database.

    Args:
        data_manager: DataManager instance for database operations
        raw_data_records: List of RawData objects to be stored
        logger: Logger instance for logging
    """
    logger.info("Writing and saving RawData objects...")
    data_manager.insert_raw_data_batch(raw_data_records)
    logger.info("RawData objects saved successfully")
    logger.info("=" * 25)


def create_and_store_user_query(
    data_manager: DataManager, logger: logging.Logger
) -> UserQueryInput:
    """
    Create a user query input object and store it in the database.

    Args:
        data_manager: DataManager instance for database operations
        logger: Logger instance for logging

    Returns:
        UserQueryInput object that was created and stored
    """
    logger.info("Creating user query input object...")
    user_query_input = UserQueryInput(
        query_text="识别与人工智能在金融风控与合规相关的内容",
        key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
    )
    logger.info(f"User query input object created: {user_query_input}")
    logger.info("Inserting user query input object into database...")
    data_manager.insert_user_query(user_query_input)
    logger.info("User query input object inserted successfully")
    logger.info("=" * 25)
    return user_query_input


def summarize_user_query(
    user_query_input: UserQueryInput, logger: logging.Logger
) -> SummarizedUserQuery:
    """
    Generate a summarized query from user query input using keyword-based LLM summarizer.

    Args:
        user_query_input: UserQueryInput object to be summarized
        logger: Logger instance for logging

    Returns:
        SummarizedUserQuery object containing the summarized query
    """
    logger.info("Generating summarized query using Summarizer...")
    summarizer = KWLMSummarizer({"llm_name": "ARK/doubao-seed-1-6-flash-250828"})
    summarized_query = summarizer.summarize(user_query_input)
    logger.info(f"Summarized query created: {summarized_query}")
    logger.info("=" * 25)
    return summarized_query


def match_raw_data_with_query(
    raw_data: RawData, summarized_query: SummarizedUserQuery, logger: logging.Logger
) -> MatchInput:
    """
    Create a MatchInput object from raw data and summarized query.

    Args:
        raw_data: RawData object to be matched
        summarized_query: SummarizedUserQuery object for matching
        logger: Logger instance for logging

    Returns:
        MatchInput object ready for matching operations
    """
    logger.info("Creating MatchInput object from raw_data and summarized_query...")
    match_input = raw_data_and_summarized_query_to_match_input(
        raw_data=raw_data,
        summarized_query=summarized_query,
    )
    logger.info(f"MatchInput object created: {match_input}")
    logger.info("=" * 25)
    return match_input


def perform_llm_matching(match_input: MatchInput, logger: logging.Logger):
    """
    Perform matching using LLM matcher.

    Args:
        match_input: MatchInput object containing data to be matched
        logger: Logger instance for logging

    Returns:
        Match output from the LLM matcher
    """
    logger.info("Performing matching using lm_matcher...")
    lm_matcher = LLMMatcher(lm_name="ARK/doubao-seed-1-6-flash-250828")
    match_output = lm_matcher.run(match_input)
    logger.info(f"Matching result: {match_output}")
    logger.info("=" * 25)
    return match_output


def create_meta_samples(match_output, raw_data: RawData, logger: logging.Logger):
    """
    Convert match output into meta samples.

    Args:
        match_output: Output from the matcher
        raw_data: RawData object associated with the match output
        logger: Logger instance for logging

    Returns:
        List of MetaSample objects created from the match output
    """
    logger.info("Creating meta_samples from match_output...")
    meta_samples = match_output_to_meta_samples(
        match_output=match_output,
        raw_data=raw_data,
        category="金融风控",
        knowledge_field="人工智能",
    )
    logger.info(f"Meta samples created: {meta_samples}")
    logger.info("=" * 25)
    return meta_samples


def store_meta_samples(
    data_manager: DataManager, meta_samples, logger: logging.Logger
) -> None:
    """
    Store meta samples in the database.

    Args:
        data_manager: DataManager instance for database operations
        meta_samples: List of MetaSample objects to be stored
        logger: Logger instance for logging
    """
    logger.info("Saving meta_samples to database...")
    data_manager.insert_meta_samples(meta_samples)
    logger.info("Meta samples saved successfully")
    logger.info("=" * 25)


def create_build_input(
    user_query_input: UserQueryInput, meta_samples, logger: logging.Logger
) -> BuildInput:
    """
    Create BuildInput object from user query and meta samples.

    Args:
        user_query_input: UserQueryInput object
        meta_samples: List of MetaSample objects
        logger: Logger instance for logging

    Returns:
        BuildInput object ready for builder processing
    """
    logger.info("Creating BuildInput object from user_query and meta_samples...")
    build_input = convert_to_build_input(
        user_query=user_query_input,
        meta_samples=meta_samples,
        extras={},
    )
    logger.info(f"BuildInput object created: {build_input}")
    logger.info("=" * 25)
    return build_input


def main():
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
    logger = setup_logging()

    # Initialize data manager
    data_manager = DataManager()

    # Step 1: Create raw data records from sample texts
    raw_texts = get_sample_raw_texts()
    raw_data_records = create_raw_data_records(raw_texts)

    # Step 2: Store raw data records in database
    store_raw_data(data_manager, raw_data_records, logger)

    # Step 3: Create and store user query input
    user_query_input = create_and_store_user_query(data_manager, logger)

    # Step 4: Summarize user query
    summarized_query = summarize_user_query(user_query_input, logger)

    # Step 5: Create match input from raw data and summarized query
    match_input = match_raw_data_with_query(
        raw_data_records[0], summarized_query, logger
    )

    # Step 6: Perform LLM matching
    match_output = perform_llm_matching(match_input, logger)

    # Step 7: Convert match output to meta samples
    meta_samples = create_meta_samples(match_output, raw_data_records[0], logger)

    # Step 8: Store meta samples in database
    store_meta_samples(data_manager, meta_samples, logger)

    # Step 9: Create build input for downstream processing
    build_input = create_build_input(user_query_input, meta_samples, logger)
    # Note: build_input is created for demonstration purposes and can be used
    # by downstream builders in a production workflow
    assert build_input is not None, "BuildInput should be created successfully"

    print("Start building ...")
    lmbuilder = LMBuilder(
        config={
            "output_dir": "./examples/utest/Collector/test_files/event_cascade_output"
        }  # Specify output directory
    )
    # build_output = lmbuilder.build(build_input)
    build_output = lmbuilder.build_class(build_input)
    print("build_output:", build_output)

    assert build_output is not None, "BuildOutput should be created successfully"

    # Optionally, you can also save the BuildOutput itself
    output_file = "./data/build_output.pkl"
    with open(output_file, "wb") as f:
        pickle.dump(build_output, f)
    print(f"BuildOutput also saved to: {output_file}")

    logger.info("Test flow completed successfully!")


if __name__ == "__main__":
    main()
