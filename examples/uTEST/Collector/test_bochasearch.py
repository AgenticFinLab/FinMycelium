"""
Test Script for Bocha AI Web Search API Integration

This script provides testing functionality for the Bocha AI Web Search API module.
It verifies the integration with Bocha's search service and demonstrates
the usage with optional parameters like summarization and result count.

The test uses a sample query related to financial fraud to validate the
API connectivity and response format with enhanced features.
"""

import json

# Import the bochasearch_api function from the module
from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api

# Main execution block
if __name__ == "__main__":
    # Execute search
    search_results = bochasearch_api("蓝天格锐庞氏骗局", summary=True, count=10)

    # Save raw results
    with open(
        r"examples\Collector\test_files\bocha_raw_results_202512011350.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(search_results, f, ensure_ascii=False, indent=2)

    # Format results
    formatted_results = []
    for item in search_results["data"]["webPages"]["value"]:
        formatted_item = {
            "title": item["name"],
            "url": item["url"],
            "snippet": item["snippet"],
            "content": item["summary"],
            "sitename": item["siteName"],
            "datepublished": item["datePublished"],
        }
        formatted_results.append(formatted_item)

    # Save formatted results
    with open(
        r"examples\Collector\test_files\bocha_formatted_results_202512011350.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(formatted_results, f, ensure_ascii=False, indent=2)

    print("Results saved to raw_results.json and formatted_results.json")
