from finmy.url_collector.HrefCollector.bocha_get import bocha_api_call


if __name__ == "__main__":
    print(bocha_api_call("蓝天格锐庞氏骗局", summary=True, count=10))
