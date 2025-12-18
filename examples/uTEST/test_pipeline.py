from datetime import datetime
from typing import List

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
    output_dir = f"./examples/utest/Collector/test_files/event_output_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    pipeline = FinmyPipeline({"output_dir": output_dir})
    data_sources = get_sample_data_sources()
    pipeline.lm_build_pipeline_main(
        data_sources=data_sources,
        query_text="识别与人工智能在金融风控与合规相关的内容",
        key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
    )
