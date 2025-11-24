"""
The Web Search API Service of Bocha


Bocha:
https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
"""

from finmy.url_collector.LinkCollector.link_bocha_get import bocha_api_call

if __name__ == "__main__":
    print(bocha_api_call("蓝天格锐庞氏骗局", summary=True, count=10))
