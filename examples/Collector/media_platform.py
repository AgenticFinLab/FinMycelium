"""
Media Collector Module - Platform Crawler Manager
Responsible for configuring and calling MediaCrawler for multi-platform crawling
"""

from loguru import logger

from finmy.url_collector.MediaCollector.platform_crawler import PlatformCrawler


if __name__ == "__main__":
    # Test Platform Crawler Manager
    crawler = PlatformCrawler()

    # Test configuration
    test_keywords = ["蓝天格锐庞氏骗局"]
    result = crawler.run_crawler("wb", test_keywords, max_notes=5)

    logger.info(f"Test result: {result}")
    logger.info("Platform Crawler Manager test completed!")
