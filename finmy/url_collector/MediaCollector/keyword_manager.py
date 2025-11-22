#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSentimentCrawling Module - Keyword Manager
Get keywords from BroadTopicExtraction module and assign them to different platforms for crawling
"""

import sys
import json
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import List, Dict, Optional
import random
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    import config
except ImportError:
    raise ImportError("Cannot import config.py configuration file")

from config import settings
from loguru import logger


class KeywordManager:
    """Keyword Manager"""

    def __init__(self):
        """Initialize Keyword Manager"""
        self.engine: Engine = None
        self.connect()

    def connect(self):
        """Connect to database"""
        try:
            dialect = (settings.DB_DIALECT or "mysql").lower()
            if dialect in ("postgresql", "postgres"):
                url = f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            else:
                url = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            self.engine = create_engine(url, future=True)
            logger.info(
                f"Keyword Manager successfully connected to database: {settings.DB_NAME}"
            )
        except ModuleNotFoundError as e:
            missing: str = str(e)
            if "psycopg" in missing:
                logger.error(
                    "Database connection failed: PostgreSQL driver psycopg not installed. Please install: psycopg[binary]. Reference command: uv pip install psycopg[binary]"
                )
            elif "pymysql" in missing:
                logger.error(
                    "Database connection failed: MySQL driver pymysql not installed. Please install: pymysql. Reference command: uv pip install pymysql"
                )
            else:
                logger.error(f"Database connection failed (missing driver): {e}")
            raise
        except Exception as e:
            logger.exception(f"Keyword Manager database connection failed: {e}")
            raise

    def get_latest_keywords(
        self, target_date: date = None, max_keywords: int = 100
    ) -> List[str]:
        """
        Get latest keyword list

        Args:
            target_date: Target date, defaults to today
            max_keywords: Maximum number of keywords

        Returns:
            Keyword list
        """
        if not target_date:
            target_date = date.today()

        logger.info(f"Getting keywords for {target_date}...")

        # First try to get keywords for the specified date
        topics_data = self.get_daily_topics(target_date)

        if topics_data and topics_data.get("keywords"):
            keywords = topics_data["keywords"]
            logger.info(
                f"Successfully obtained {len(keywords)} keywords for {target_date}"
            )

            # If there are too many keywords, randomly select the specified number
            if len(keywords) > max_keywords:
                keywords = random.sample(keywords, max_keywords)
                logger.info(f"Randomly selected {max_keywords} keywords")

            return keywords

        # If no keywords for today, try to get recent days' keywords
        logger.info(
            f"No keyword data for {target_date}, trying to get recent keywords..."
        )
        recent_topics = self.get_recent_topics(days=7)

        if recent_topics:
            # Merge keywords from recent days
            all_keywords = []
            for topic in recent_topics:
                if topic.get("keywords"):
                    all_keywords.extend(topic["keywords"])

            # Deduplicate and limit quantity
            unique_keywords = list(set(all_keywords))
            if len(unique_keywords) > max_keywords:
                unique_keywords = random.sample(unique_keywords, max_keywords)

            logger.info(
                f"Obtained {len(unique_keywords)} keywords from recent 7 days data"
            )
            return unique_keywords

        # If nothing found, return default keywords
        logger.info("No keyword data found, using default keywords")
        return self._get_default_keywords()

    def get_daily_topics(self, extract_date: date = None) -> Optional[Dict]:
        """
        Get daily topic analysis

        Args:
            extract_date: Extraction date, defaults to today

        Returns:
            Topic analysis data, returns None if not exists
        """
        if not extract_date:
            extract_date = date.today()

        try:
            with self.engine.connect() as conn:
                result = (
                    conn.execute(
                        text("SELECT * FROM daily_topics WHERE extract_date = :d"),
                        {"d": extract_date},
                    )
                    .mappings()
                    .first()
                )

            if result:
                # Convert to mutable dict then assign
                result = dict(result)
                result["keywords"] = (
                    json.loads(result["keywords"]) if result.get("keywords") else []
                )
                return result
            else:
                return None

        except Exception as e:
            logger.exception(f"Failed to get topic analysis: {e}")
            return None

    def get_recent_topics(self, days: int = 7) -> List[Dict]:
        """
        Get topic analysis for recent days

        Args:
            days: Number of days

        Returns:
            Topic analysis list
        """
        try:
            start_date = date.today() - timedelta(days=days)
            with self.engine.connect() as conn:
                results = (
                    conn.execute(
                        text(
                            """
                        SELECT * FROM daily_topics 
                        WHERE extract_date >= :start_date
                        ORDER BY extract_date DESC
                        """
                        ),
                        {"start_date": start_date},
                    )
                    .mappings()
                    .all()
                )

            # Convert to mutable dict list then process
            results = [dict(r) for r in results]
            for result in results:
                result["keywords"] = (
                    json.loads(result["keywords"]) if result.get("keywords") else []
                )

            return results

        except Exception as e:
            logger.exception(f"Failed to get recent topic analysis: {e}")
            return []

    def _get_default_keywords(self) -> List[str]:
        """Get default keyword list"""
        return [
            "科技",
            "人工智能",
            "AI",
            "编程",
            "互联网",
            "创业",
            "投资",
            "理财",
            "股市",
            "经济",
            "教育",
            "学习",
            "考试",
            "大学",
            "就业",
            "健康",
            "养生",
            "运动",
            "美食",
            "旅游",
            "时尚",
            "美妆",
            "购物",
            "生活",
            "家居",
            "电影",
            "音乐",
            "游戏",
            "娱乐",
            "明星",
            "新闻",
            "热点",
            "社会",
            "政策",
            "环保",
        ]

    def get_all_keywords_for_platforms(
        self, platforms: List[str], target_date: date = None, max_keywords: int = 100
    ) -> List[str]:
        """
        Get same keyword list for all platforms

        Args:
            platforms: Platform list
            target_date: Target date
            max_keywords: Maximum number of keywords

        Returns:
            Keyword list (shared by all platforms)
        """
        keywords = self.get_latest_keywords(target_date, max_keywords)

        if keywords:
            logger.info(
                f"Prepared same {len(keywords)} keywords for {len(platforms)} platforms"
            )
            logger.info(f"Each keyword will be crawled on all platforms")

        return keywords

    def get_keywords_for_platform(
        self, platform: str, target_date: date = None, max_keywords: int = 50
    ) -> List[str]:
        """
        Get keywords for specific platform (now all platforms use same keywords)

        Args:
            platform: Platform name
            target_date: Target date
            max_keywords: Maximum number of keywords

        Returns:
            Keyword list (same as other platforms)
        """
        keywords = self.get_latest_keywords(target_date, max_keywords)

        logger.info(
            f"Prepared {len(keywords)} keywords for platform {platform} (same as other platforms)"
        )
        return keywords

    def _filter_keywords_by_platform(
        self, keywords: List[str], platform: str
    ) -> List[str]:
        """
        Filter keywords based on platform characteristics

        Args:
            keywords: Original keyword list
            platform: Platform name

        Returns:
            Filtered keyword list
        """
        # Platform preference keyword mapping (can be adjusted as needed)
        platform_preferences = {
            "xhs": ["美妆", "时尚", "生活", "美食", "旅游", "购物", "健康", "养生"],
            "dy": ["娱乐", "音乐", "舞蹈", "搞笑", "美食", "生活", "科技", "教育"],
            "ks": ["生活", "搞笑", "农村", "美食", "手工", "音乐", "娱乐"],
            "bili": ["科技", "游戏", "动漫", "学习", "编程", "数码", "科普"],
            "wb": ["热点", "新闻", "娱乐", "明星", "社会", "时事", "科技"],
            "tieba": ["游戏", "动漫", "学习", "生活", "兴趣", "讨论"],
            "zhihu": ["知识", "学习", "科技", "职场", "投资", "教育", "思考"],
        }

        # If platform has specific preferences, prioritize related keywords
        preferred_keywords = platform_preferences.get(platform, [])

        if preferred_keywords:
            # First select platform preferred keywords
            filtered = []
            remaining = []

            for keyword in keywords:
                if any(pref in keyword for pref in preferred_keywords):
                    filtered.append(keyword)
                else:
                    remaining.append(keyword)

            # If preferred keywords are insufficient, supplement with other keywords
            if len(filtered) < len(keywords) // 2:
                filtered.extend(remaining[: len(keywords) - len(filtered)])

            return filtered

        # If no specific preference, return original keywords
        return keywords

    def get_crawling_summary(self, target_date: date = None) -> Dict:
        """
        Get crawling task summary

        Args:
            target_date: Target date

        Returns:
            Crawling summary information
        """
        if not target_date:
            target_date = date.today()

        topics_data = self.get_daily_topics(target_date)

        if topics_data:
            return {
                "date": target_date,
                "keywords_count": len(topics_data.get("keywords", [])),
                "summary": topics_data.get("summary", ""),
                "has_data": True,
            }
        else:
            return {
                "date": target_date,
                "keywords_count": 0,
                "summary": "No data available",
                "has_data": False,
            }

    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Keyword Manager database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


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
