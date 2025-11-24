"""

The Web Search API Service of Bocha


Bocha:
https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK


"""

import requests
import json
from dotenv import load_dotenv


def bocha_api_call(query: str, summary: bool = False, count: int = 20):

    url = "https://api.bocha.cn/v1/web-search"

    payload = json.dumps({"query": query, "summary": summary, "count": count})

    load_dotenv()
    BOCHA_API = os.getenv("DB_HOST")

    headers = {
        "Authorization": f"Bearer {BoCHA_API}",
        "Content-Type": "application/json",
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    return response.json()


if __name__ == "__main__":
    print(bocha_api_call("蓝天格锐庞氏骗局", summary=True, count=10))
