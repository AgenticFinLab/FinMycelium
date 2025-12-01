#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media Collector Module - Keyword Manager
Get keywords and assign them to different platforms for crawling
"""


from finmy.url_collector.MediaCollector.keyword_manager import KeywordManager

if __name__ == "__main__":
    # Test Keyword Manager
    with KeywordManager() as km:
        # Test getting keywords
        keywords = km.get_latest_keywords(max_keywords=20)
        logger.info(f"Keywords obtained: {keywords}")

        # Test platform distribution
        platforms = ["xhs", "dy", "bili"]
        distribution = km.distribute_keywords_by_platform(keywords, platforms)
        for platform, kws in distribution.items():
            logger.info(f"{platform}: {kws}")

        # Test crawling summary
        summary = km.get_crawling_summary()
        logger.info(f"Crawling summary: {summary}")

        logger.info("Keyword Manager test completed!")
