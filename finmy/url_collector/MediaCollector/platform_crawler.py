#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media Collector Module - Platform Crawler Manager
Responsible for configuring and calling MediaCrawler for multi-platform crawling
Based on the MindSpider/DeepSentimentCrawling module of the project BettaFish (https://github.com/666ghj/BettaFish)
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict


import json
from loguru import logger

from finmy.url_collector.MediaCollector.database_settings import database_url


class PlatformCrawler:
    """Platform Crawler Manager"""

    def __init__(self):
        """Initialize Platform Crawler Manager"""
        self.mediacrawler_path = Path(__file__).parent / "MediaCrawler"
        self.supported_platforms = ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]
        self.crawl_stats = {}

        # Ensure MediaCrawler directory exists
        if not self.mediacrawler_path.exists():
            raise FileNotFoundError(
                f"MediaCrawler directory does not exist: {self.mediacrawler_path}"
            )

        logger.info(
            f"Initialized Platform Crawler Manager, MediaCrawler path: {self.mediacrawler_path}"
        )

    def run_crawler(
        self,
        platform: str,
        keywords: List[str],
        login_type: str = "qrcode",
        max_notes: int = 50,
    ) -> Dict:
        """
        Run crawler

        Args:
            platform: Platform name
            keywords: Keyword list
            login_type: Login method
            max_notes: Maximum crawling count

        Returns:
            Crawling result statistics
        """
        if platform not in self.supported_platforms:
            raise ValueError(f"Unsupported platform: {platform}")

        if not keywords:
            raise ValueError("Keyword list cannot be empty")

        start_message = f"\nStarting to crawl platform: {platform}"
        start_message += f"\nKeywords: {keywords[:5]}{'...' if len(keywords) > 5 else ''} (Total {len(keywords)} keywords)"
        logger.info(start_message)

        start_time = datetime.now()

        try:
            url = database_url()
            if url.get_backend_name() != "mysql":
                raise ValueError("The bundled MediaCrawler database writer supports MySQL only")
            child_env = dict(os.environ, MYSQL_DB_USER=url.username or "",
                             MYSQL_DB_PWD=url.password or "", MYSQL_DB_HOST=url.host,
                             MYSQL_DB_PORT=str(url.port), MYSQL_DB_NAME=url.database,
                             FINMY_MEDIA_MAX_NOTES=str(max_notes))

            # Build command
            cmd = [
                sys.executable,
                "main.py",
                "--platform",
                platform,
                "--lt",
                login_type,
                "--type",
                "search",
                "--save_data_option",
                "db",
                "--keywords=" + ",".join(keywords),
                "--get_comment",
                "true",
            ]

            logger.info(f"Executing command: {' '.join(cmd)}")

            # Switch to MediaCrawler directory and execute
            result = subprocess.run(
                cmd, cwd=self.mediacrawler_path, env=child_env, timeout=3600  # 60-minute timeout
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Create statistics
            crawl_stats = {
                "platform": platform,
                "keywords_count": len(keywords),
                "duration_seconds": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "return_code": result.returncode,
                "success": result.returncode == 0,
                "notes_count": 0,
                "comments_count": 0,
                "errors_count": 0,
            }

            # Save statistics
            self.crawl_stats[platform] = crawl_stats

            if result.returncode == 0:
                logger.info(
                    f"✅ {platform} crawling completed, time taken: {duration:.1f} seconds"
                )
            else:
                logger.error(
                    f"❌ {platform} crawling failed, return code: {result.returncode}"
                )

            return crawl_stats

        except subprocess.TimeoutExpired:
            logger.error(f"❌ {platform} crawling timeout")
            return {"success": False, "error": "Crawling timeout", "platform": platform}
        except Exception as e:
            logger.error(f"❌ {platform} crawling exception: {e}")
            return {"success": False, "error": str(e), "platform": platform}

    def _parse_crawl_output(
        self, output_lines: List[str], error_lines: List[str]
    ) -> Dict:
        """Parse crawling output, extract statistics"""
        stats = {
            "notes_count": 0,
            "comments_count": 0,
            "errors_count": 0,
            "login_required": False,
        }

        # Parse output lines
        for line in output_lines:
            if "条笔记" in line or "条内容" in line:
                try:
                    # Extract numbers
                    import re

                    numbers = re.findall(r"\d+", line)
                    if numbers:
                        stats["notes_count"] = int(numbers[0])
                except:
                    pass
            elif "条评论" in line:
                try:
                    import re

                    numbers = re.findall(r"\d+", line)
                    if numbers:
                        stats["comments_count"] = int(numbers[0])
                except:
                    pass
            elif "登录" in line or "扫码" in line:
                stats["login_required"] = True

        # Parse error lines
        for line in error_lines:
            if "error" in line.lower() or "异常" in line:
                stats["errors_count"] += 1

        return stats

    def run_multi_platform_crawl_by_keywords(
        self,
        keywords: List[str],
        platforms: List[str],
        login_type: str = "qrcode",
        max_notes_per_keyword: int = 50,
    ) -> Dict:
        """
        Multi-platform crawling based on keywords - Each keyword is crawled on all platforms

        Args:
            keywords: Keyword list
            platforms: Platform list
            login_type: Login method
            max_notes_per_keyword: Maximum crawling count per keyword per platform

        Returns:
            Overall crawling statistics
        """

        start_message = f"\n🚀 Starting all-platform keyword crawling"
        start_message += f"\n   Keyword count: {len(keywords)}"
        start_message += f"\n   Platform count: {len(platforms)}"
        start_message += f"\n   Login method: {login_type}"
        start_message += f"\n   Maximum crawling count per keyword per platform: {max_notes_per_keyword}"
        start_message += f"\n   Total crawling tasks: {len(keywords)} × {len(platforms)} = {len(keywords) * len(platforms)}"
        logger.info(start_message)

        total_stats = {
            "total_keywords": len(keywords),
            "total_platforms": len(platforms),
            "total_tasks": len(keywords) * len(platforms),
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_notes": 0,
            "total_comments": 0,
            "keyword_results": {},
            "platform_summary": {},
        }

        # Initialize platform statistics
        for platform in platforms:
            total_stats["platform_summary"][platform] = {
                "successful_keywords": 0,
                "failed_keywords": 0,
                "total_notes": 0,
                "total_comments": 0,
            }

        # Crawl all keywords on each platform at once
        for platform in platforms:
            logger.info(f"\n📝 Crawling all keywords on {platform} platform")
            logger.info(
                f"   Keywords: {', '.join(keywords[:5])}{'...' if len(keywords) > 5 else ''}"
            )

            try:
                # Pass all keywords to the platform at once
                result = self.run_crawler(
                    platform, keywords, login_type, max_notes_per_keyword
                )

                if result.get("success"):
                    total_stats["successful_tasks"] += len(keywords)
                    total_stats["platform_summary"][platform]["successful_keywords"] = (
                        len(keywords)
                    )

                    notes_count = result.get("notes_count", 0)
                    comments_count = result.get("comments_count", 0)

                    total_stats["total_notes"] += notes_count
                    total_stats["total_comments"] += comments_count
                    total_stats["platform_summary"][platform][
                        "total_notes"
                    ] = notes_count
                    total_stats["platform_summary"][platform][
                        "total_comments"
                    ] = comments_count

                    # Record results for each keyword
                    for keyword in keywords:
                        if keyword not in total_stats["keyword_results"]:
                            total_stats["keyword_results"][keyword] = {}
                        total_stats["keyword_results"][keyword][platform] = result

                    logger.info(
                        f"   ✅ Success: {notes_count} contents, {comments_count} comments"
                    )
                else:
                    total_stats["failed_tasks"] += len(keywords)
                    total_stats["platform_summary"][platform]["failed_keywords"] = len(
                        keywords
                    )

                    # Record failure results for each keyword
                    for keyword in keywords:
                        if keyword not in total_stats["keyword_results"]:
                            total_stats["keyword_results"][keyword] = {}
                        total_stats["keyword_results"][keyword][platform] = result

                    logger.error(
                        f"   ❌ Failed: {result.get('error', 'Unknown error')}"
                    )

            except Exception as e:
                total_stats["failed_tasks"] += len(keywords)
                total_stats["platform_summary"][platform]["failed_keywords"] = len(
                    keywords
                )
                error_result = {"success": False, "error": str(e)}

                # Record exception results for each keyword
                for keyword in keywords:
                    if keyword not in total_stats["keyword_results"]:
                        total_stats["keyword_results"][keyword] = {}
                    total_stats["keyword_results"][keyword][platform] = error_result

                logger.error(f"   ❌ Exception: {e}")

        # Print detailed statistics
        finish_message = f"\n📊 All-platform keyword crawling completed!"
        finish_message += f"\n   Total tasks: {total_stats['total_tasks']}"
        finish_message += f"\n   Successful: {total_stats['successful_tasks']}"
        finish_message += f"\n   Failed: {total_stats['failed_tasks']}"
        finish_message += f"\n   Success rate: {total_stats['successful_tasks']/total_stats['total_tasks']*100:.1f}%"
        finish_message += f"\n   Total contents: {total_stats['total_notes']} items"
        finish_message += f"\n   Total comments: {total_stats['total_comments']} items"
        logger.info(finish_message)

        platform_summary_message = f"\n� Platform statistics:"
        for platform, stats in total_stats["platform_summary"].items():
            success_rate = (
                stats["successful_keywords"] / len(keywords) * 100 if keywords else 0
            )
            platform_summary_message += f"\n   {platform}: {stats['successful_keywords']}/{len(keywords)} keywords successful ({success_rate:.1f}%), "
            platform_summary_message += f"{stats['total_notes']} contents"
        logger.info(platform_summary_message)

        return total_stats

    def get_crawl_statistics(self) -> Dict:
        """Get crawling statistics"""
        return {
            "platforms_crawled": list(self.crawl_stats.keys()),
            "total_platforms": len(self.crawl_stats),
            "detailed_stats": self.crawl_stats,
        }

    def save_crawl_log(self, log_path: str = None):
        """Save crawling log"""
        if not log_path:
            log_path = f"crawl_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(self.crawl_stats, f, ensure_ascii=False, indent=2)
            logger.info(f"Crawling log saved to: {log_path}")
        except Exception as e:
            logger.exception(f"Failed to save crawling log: {e}")
