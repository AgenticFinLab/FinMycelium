"""
Bocha AI Web Search API Service Integration

This module provides integration with Bocha AI's Web Search API service.
Bocha AI offers web search capabilities with optional result summarization.

Documentation Reference:
https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK

Key Features:
- Configurable result count
- Optional search result summarization
- Simple authentication via API key
- JSON-based request/response format
"""

import os
import requests
import json
from dotenv import load_dotenv


def bochasearch_api(query: str, summary: bool = False, count: int = 20):
    """
    Perform a web search using Bocha AI's Web Search API.

    Args:
        query (str): The search query string to be executed
        summary (bool, optional): Whether to include summarized results. Defaults to False.
        count (int, optional): Number of search results to return. Defaults to 20.

    Returns:
        dict: JSON response containing search results and metadata

    Raises:
        requests.exceptions.RequestException: If the API request fails
        json.JSONDecodeError: If the response cannot be parsed as JSON
    """

    # Bocha AI Web Search API endpoint
    url = "https://api.bocha.cn/v1/web-search"

    # Construct request payload with search parameters
    payload = json.dumps(
        {
            "query": query,  # The search query string
            "summary": summary,  # Boolean flag for result summarization
            "count": count,  # Number of results to return (max limit)
        }
    )

    # Load environment variables from .env file
    load_dotenv()

    # Retrieve Bocha API key from environment variables
    BOCHA_API = os.getenv("BOCHA_API_KEY")

    # Set request headers for authentication and content type
    headers = {
        "Authorization": f"Bearer {BOCHA_API}",  # Bearer token authentication
        "Content-Type": "application/json",  # JSON content type
    }

    # Execute POST request to Bocha AI API
    response = requests.request("POST", url, headers=headers, data=payload)

    # Parse and return the JSON response
    return response.json()
