"""
The Web Search API Service of Baidu


Baidusearch Document:
https://cloud.baidu.com/doc/AppBuilder/s/pmaxd1hvy
"""

from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api


if __name__ == "__main__":
    print(baidusearch_api("蓝天格锐庞氏骗局"))
