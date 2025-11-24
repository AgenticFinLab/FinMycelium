#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media Collector Module - Main Workflow
Full-platform keyword crawling based on topics
Based on the DeepSentimentCrawling module of the project BettaFish (https://github.com/666ghj/BettaFish)
"""

import sys
import argparse
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from keyword_manager import KeywordManager
from platform_crawler import PlatformCrawler


class DeepSentimentCrawling:
    """Deep Sentiment Crawling Main Workflow"""

    def __init__(self):
        """Initialize Deep Sentiment Crawling"""
        self.keyword_manager = KeywordManager()
        self.platform_crawler = PlatformCrawler()
        self.supported_platforms = ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]

    def run_daily_crawling(
        self,
        target_date: date = None,
        platforms: List[str] = None,
        max_keywords_per_platform: int = 50,
        max_notes_per_platform: int = 50,
        login_type: str = "qrcode",
    ) -> Dict:
        """
        Execute daily crawling task

        Args:
            target_date: Target date, defaults to today
            platforms: List of platforms to crawl, defaults to all supported platforms
            max_keywords_per_platform: Maximum number of keywords per platform
            max_notes_per_platform: Maximum number of content to crawl per platform
            login_type: Login method

        Returns:
            Crawling result statistics
        """
        if not target_date:
            target_date = date.today()

        if not platforms:
            platforms = self.supported_platforms

        print(f"🚀 Starting deep sentiment crawling task for {target_date}")
        print(f"Target platforms: {platforms}")

        # 1. Get keyword summary
        summary = self.keyword_manager.get_crawling_summary(target_date)
        print(f"📊 Keyword summary: {summary}")

        if not summary["has_data"]:
            print("⚠️ No topic data found, cannot proceed with crawling")
            return {"success": False, "error": "No topic data"}

        # 2. Get keywords (no assignment, all platforms use the same keywords)
        print(f"\n📝 Getting keywords...")
        keywords = self.keyword_manager.get_latest_keywords(
            target_date, max_keywords_per_platform
        )

        if not keywords:
            print("⚠️ No keywords found, cannot proceed with crawling")
            return {"success": False, "error": "No keywords"}

        print(f"   Retrieved {len(keywords)} keywords")
        print(f"   Will crawl each keyword on {len(platforms)} platforms")
        print(
            f"   Total crawling tasks: {len(keywords)} × {len(platforms)} = {len(keywords) * len(platforms)}"
        )

        # 3. Execute full-platform keyword crawling
        print(f"\n🔄 Starting full-platform keyword crawling...")
        crawl_results = self.platform_crawler.run_multi_platform_crawl_by_keywords(
            keywords, platforms, login_type, max_notes_per_platform
        )

        # 4. Generate final report
        final_report = {
            "date": target_date.isoformat(),
            "summary": summary,
            "crawl_results": crawl_results,
            "success": crawl_results["successful_tasks"] > 0,
        }

        print(f"\n✅ Deep sentiment crawling task completed!")
        print(f"   Date: {target_date}")
        print(
            f"   Successful tasks: {crawl_results['successful_tasks']}/{crawl_results['total_tasks']}"
        )
        print(f"   Total keywords: {crawl_results['total_keywords']}")
        print(f"   Total platforms: {crawl_results['total_platforms']}")
        print(f"   Total content: {crawl_results['total_notes']} items")

        return final_report

    def run_platform_crawling(
        self,
        platform: str,
        target_date: date = None,
        max_keywords: int = 50,
        max_notes: int = 50,
        login_type: str = "qrcode",
    ) -> Dict:
        """
        Execute crawling task for a single platform

        Args:
            platform: Platform name
            target_date: Target date
            max_keywords: Maximum number of keywords
            max_notes: Maximum number of content to crawl
            login_type: Login method

        Returns:
            Crawling result
        """
        if platform not in self.supported_platforms:
            raise ValueError(f"Unsupported platform: {platform}")

        if not target_date:
            target_date = date.today()

        print(f"🎯 Starting crawling task for {platform} platform ({target_date})")

        # Get keywords
        keywords = self.keyword_manager.get_keywords_for_platform(
            platform, target_date, max_keywords
        )

        if not keywords:
            print(f"⚠️ No keywords found for {platform} platform")
            return {"success": False, "error": "No keywords"}

        print(f"📝 Preparing to crawl {len(keywords)} keywords")

        # Execute crawling
        result = self.platform_crawler.run_crawler(
            platform, keywords, login_type, max_notes
        )

        return result

    def list_available_topics(self, days: int = 7):
        """List recent available topics"""
        print(f"📋 Topic data from the last {days} days:")

        recent_topics = self.keyword_manager.db_manager.get_recent_topics(days)

        if not recent_topics:
            print("   No topic data available")
            return

        for topic in recent_topics:
            extract_date = topic["extract_date"]
            keywords_count = len(topic.get("keywords", []))
            summary_preview = (
                topic.get("summary", "")[:100] + "..."
                if len(topic.get("summary", "")) > 100
                else topic.get("summary", "")
            )

            print(f"   📅 {extract_date}: {keywords_count} keywords")
            print(f"      Summary: {summary_preview}")
            print()

    def show_platform_guide(self):
        """Display platform usage guide"""
        print("🔧 Platform Crawling Guide:")
        print()

        platform_info = {
            "xhs": "小红书 - Mainly beauty, lifestyle, fashion content",
            "dy": "抖音 - Short videos, entertainment, lifestyle content",
            "ks": "快手 - Lifestyle, entertainment, rural content",
            "bili": "B站 - Technology, learning, gaming, anime content",
            "wb": "微博 - Hot news, celebrities, social topics",
            "tieba": "百度贴吧 - Interest discussions, gaming, learning",
            "zhihu": "知乎 - Knowledge Q&A, in-depth discussions",
        }

        for platform, desc in platform_info.items():
            print(f"   {platform}: {desc}")

        print()
        print("💡 Usage Suggestions:")
        print("   1. First-time use requires QR code login for each platform")
        print("   2. Recommend testing a single platform first to confirm login works")
        print("   3. Avoid excessive crawling volume to prevent restrictions")
        print("   4. Use --test mode for small-scale testing")

    def close(self):
        """Close resources"""
        if self.keyword_manager:
            self.keyword_manager.close()


def main():
    """Command line entry point"""
    parser = argparse.ArgumentParser(
        description="DeepSentimentCrawling - Topic-based Deep Sentiment Crawling"
    )

    # Basic parameters
    parser.add_argument(
        "--date", type=str, help="Target date (YYYY-MM-DD), defaults to today"
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"],
        help="Specify a single platform for crawling",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        nargs="+",
        choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"],
        help="Specify multiple platforms for crawling",
    )

    # Crawling parameters
    parser.add_argument(
        "--max-keywords",
        type=int,
        default=50,
        help="Maximum keywords per platform (default: 50)",
    )
    parser.add_argument(
        "--max-notes",
        type=int,
        default=50,
        help="Maximum content to crawl per platform (default: 50)",
    )
    parser.add_argument(
        "--login-type",
        type=str,
        choices=["qrcode", "phone", "cookie"],
        default="qrcode",
        help="Login method (default: qrcode)",
    )

    # Function parameters
    parser.add_argument(
        "--list-topics", action="store_true", help="List recent topic data"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="View topics from recent days (default: 7)"
    )
    parser.add_argument(
        "--guide", action="store_true", help="Display platform usage guide"
    )
    parser.add_argument(
        "--test", action="store_true", help="Test mode (small amount of data)"
    )

    args = parser.parse_args()

    # Parse date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("❌ Date format error, please use YYYY-MM-DD format")
            return

    # Create crawling instance
    crawler = DeepSentimentCrawling()

    try:
        # Display guide
        if args.guide:
            crawler.show_platform_guide()
            return

        # List topics
        if args.list_topics:
            crawler.list_available_topics(args.days)
            return

        # Test mode parameter adjustment
        if args.test:
            args.max_keywords = min(args.max_keywords, 10)
            args.max_notes = min(args.max_notes, 10)
            print("Test mode: Limiting keyword and content quantities")

        # Single platform crawling
        if args.platform:
            result = crawler.run_platform_crawling(
                args.platform,
                target_date,
                args.max_keywords,
                args.max_notes,
                args.login_type,
            )

            if result["success"]:
                print(f"\n{args.platform} crawling successful!")
            else:
                print(
                    f"\n{args.platform} crawling failed: {result.get('error', 'Unknown error')}"
                )

            return

        # Multi-platform crawling
        platforms = args.platforms if args.platforms else None
        result = crawler.run_daily_crawling(
            target_date, platforms, args.max_keywords, args.max_notes, args.login_type
        )

        if result["success"]:
            print(f"\nMulti-platform crawling task completed!")
        else:
            print(
                f"\nMulti-platform crawling failed: {result.get('error', 'Unknown error')}"
            )

    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
    except Exception as e:
        print(f"\nExecution error: {e}")
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
