"""
The Web Search API Service of Baidu


Baidusearch Document:
https://cloud.baidu.com/doc/AppBuilder/s/pmaxd1hvy
"""

import os
import requests
import json
from dotenv import load_dotenv


def baidusearch_api_call(query: str):

    url = "https://qianfan.baidubce.com/v2/ai_search/web_search"

    payload = json.dumps(
        {
            "messages": [{"role": "user", "content": query}],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            # "search_recency_filter": "week",
        },
        ensure_ascii=False,
    )

    load_dotenv()
    BAIDUSEARCH_API_KEY = os.getenv("BAIDUSEARCH_API_KEY")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BAIDUSEARCH_API_KEY}",
    }

    response = requests.request(
        "POST", url, headers=headers, data=payload.encode("utf-8")
    )

    response.encoding = "utf-8"

    return json.loads(response.text)
