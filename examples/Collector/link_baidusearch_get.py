"""
The Web Search API Service of Baidu


Baidusearch Document:
https://cloud.baidu.com/doc/AppBuilder/s/pmaxd1hvy
"""

from finmy.url_collector.LinkCollector.link_baidusearch_get import baidusearch_api_call


if __name__ == "__main__":
    print(baidusearch_api_call("蓝天格锐庞氏骗局"))
