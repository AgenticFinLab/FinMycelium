"""
Test Script for Bocha AI Web Search API Integration

This script provides testing functionality for the Bocha AI Web Search API module.
It verifies the integration with Bocha's search service and demonstrates
the usage with optional parameters like summarization and result count.

The test uses a sample query related to financial fraud to validate the
API connectivity and response format with enhanced features.
"""

# Import the bochasearch_api function from the module
from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api


# Main execution block - runs when script is executed directly
if __name__ == "__main__":
    # Execute test search with enhanced parameters:
    # - Sample query about financial fraud
    # - summary=True enables result summarization
    # - count=10 limits results to 10 items
    search_results = bochasearch_api("蓝天格锐庞氏骗局", summary=True, count=10)

    # Print the search results to console for verification
    print(search_results)
