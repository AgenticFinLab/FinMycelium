"""
Test Script for Baidu Web Search API Integration

This script provides testing functionality for the Baidu Web Search API module.
It verifies the integration with Baidu's search service and demonstrates
basic usage of the baidusearch_api function.

The test uses a sample query related to financial fraud to validate the
API connectivity and response format.
"""

import json

from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api


def save_json(data, filename):
    """Save data to JSON file"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    # Execute search
    search_results = baidusearch_api("蓝天格锐庞氏骗局")

    # Save raw results
    with open(
        r"examples\Collector\test_files\baidu_raw_results_202512011350.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(search_results, f, ensure_ascii=False, indent=2)
    print("Raw results saved to baidu_raw_results.json")

    # Format results
    formatted_results = []
    if "references" in search_results:
        for ref in search_results["references"]:
            formatted_item = {
                "title": ref.get("title", ""),
                "url": ref.get("url", ""),
                "snippet": ref.get("snippet", ""),
                "content": ref.get("content", ""),
                "sitename": ref.get("website", ""),
                "datepublished": ref.get("date", ""),
            }
            formatted_results.append(formatted_item)

    # Save formatted results
    with open(
        r"examples\Collector\test_files\baidu_formatted_results_202512011350.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(formatted_results, f, ensure_ascii=False, indent=2)
    print("Formatted results saved to baidu_formatted_results.json")

    # Print summary
    print(f"Found {len(formatted_results)} results")


if __name__ == "__main__":
    main()
