from datetime import datetime
from typing import List
import argparse
import yaml
from pathlib import Path

from finmy.pipeline import FinmyPipeline


def get_sample_data_sources() -> List[str]:
    """
    Get sample data sources (URLs or PDF paths) for testing purposes.

    Returns:
        List of URLs or PDF file paths. Examples:
        - URLs: ["https://example.com/article1", "https://example.com/article2"]
        - PDF paths: ["/path/to/document.pdf", "/path/to/another.pdf"]
        - PDF directories: ["/path/to/pdf_directory"]
    """
    # Example: Using URLs
    # Uncomment and modify the URLs below to use actual URLs
    return [
        # "https://example.com/article1",
        # "https://example.com/article2",
        "https://www.bbc.com/news/articles/cvg4w1g9ezko"
    ]

    # Example: Using PDF file paths
    # Uncomment and modify the paths below to use actual PDF files
    # return [
    #     "/path/to/document1.pdf",
    #     "/path/to/document2.pdf",
    # ]

    # Example: Using PDF directory
    # Uncomment and modify the path below to use a directory containing PDFs
    # return [
    #     "/path/to/pdf_directory",
    # ]


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run FinMycelium pipeline with YAML config."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="configs/pipline.yml",
        help="Path to YAML config file for pipeline",
    )
    args = parser.parse_args()
    config_path = args.config

    # Load configuration from YAML file
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            f"Please provide a valid path to the YAML config file."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Override output_dir with timestamp if not specified in config
    if "output_dir" not in config or not config["output_dir"]:
        config["output_dir"] = (
            f"./examples/utest/Collector/test_files/"
            f"event_output_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

    # Initialize pipeline with configuration
    pipeline = FinmyPipeline(config)

    # Get data sources
    data_sources = get_sample_data_sources()

    # Run pipeline
    pipeline.lm_build_pipeline_main(
        data_sources=data_sources,
        query_text="识别与人工智能在金融风控与合规相关的内容",
        key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
    )
