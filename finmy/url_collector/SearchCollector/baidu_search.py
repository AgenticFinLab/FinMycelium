"""
Baidu Web Search API Service Integration

This module provides integration with Baidu's Web Search API through Baidu Qianfan platform.
It allows performing web searches programmatically and retrieving structured search results.

Documentation Reference:
https://cloud.baidu.com/doc/AppBuilder/s/pmaxd1hvy

Key Features:
- Standard edition web search
- Baidu search engine integration
- UTF-8 encoding support
- JSON request/response handling
"""

import os
import json

import requests
from dotenv import load_dotenv


def baidusearch_api(query: str):
    """
    Perform a web search using Baidu's Web Search API.

    Args:
        query (str): The search query string to be executed

    Returns:
        dict: JSON response containing search results and metadata

    Raises:
        requests.exceptions.RequestException: If the API request fails
        json.JSONDecodeError: If the response cannot be parsed as JSON
    """

    # Baidu Qianfan Web Search API endpoint
    url = "https://qianfan.baidubce.com/v2/ai_search/web_search"

    # Construct the request payload with search parameters
    payload = json.dumps(
        {
            "messages": [
                {"role": "user", "content": query}
            ],  # User query in chat format
            "edition": "standard",  # API edition - standard version
            "search_source": "baidu_search_v2",  # Use Baidu search engine as source
            # "search_recency_filter": "week",  # Optional: Filter results by recency
        },
        ensure_ascii=False,  # Preserve non-ASCII characters in the query
    )

    # Load environment variables from .env file
    load_dotenv()

    # Retrieve API key from environment variables
    BAIDUSEARCH_API_KEY = os.getenv("BAIDUSEARCH_API_KEY")

    # Set request headers for API authentication and content type
    headers = {
        "Content-Type": "application/json",  # Specify JSON content type
        "Authorization": f"Bearer {BAIDUSEARCH_API_KEY}",  # Bearer token authentication
    }

    # Execute POST request to Baidu API with proper encoding
    response = requests.request(
        "POST",
        url,
        headers=headers,
        data=payload.encode("utf-8"),  # Encode payload as UTF-8 bytes
    )

    # Set response encoding to UTF-8 to handle Chinese characters properly
    response.encoding = "utf-8"

    # Parse and return the JSON response
    return json.loads(response.text)
