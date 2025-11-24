"""
Media Collector Module - Main Workflow
Full-platform keyword crawling based on topics
"""

import argparse

from finmy.url_collector.MediaCollector.media_get import DeepSentimentCrawling


def main():
    """Command line entry point"""
    parser = argparse.ArgumentParser(
        description="MediaCrawling - Topic-based Media Crawling"
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
