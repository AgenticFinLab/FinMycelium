"""
A session to test the url_parser module.
"""

from finmy.url_collector.url_parser import URLParser

# Example usage and testing
if __name__ == "__main__":
    # Example URL list including problematic URLs
    sample_urls = [
        "http://www.jyb.cn/rmtzcg/xwy/wzxw/202511/t20251119_2111415715.html",
        "http://v.people.cn/n1/2025/1121/c431305-40608834.html",
        "https://baijiahao.baidu.com/s?id=1850027474872762323&wfr=spider&for=pc",
        # Add more URLs here for testing
    ]

    # Initialize parser with Selenium fallback enabled
    parser = URLParser(delay=2.0, use_selenium_fallback=True, selenium_wait_time=5)

    # Parse URLs
    results = parser.parse_urls(sample_urls)

    # Save results to JSON (default)
    json_file = parser.save_to_json(
        results,
        filename=r"examples\Collector\test_files\parsed_results_202511291838.json",
    )

    # Example of saving to other formats
    # csv_file = parser.save_to_csv(results)
    # mysql_success = parser.save_to_mysql(results, 'localhost', 'user', 'password', 'database_name')

    print("Parsing completed. Results:")
    for result in results:
        print(f"URL {result['ID']}: {result['url']}")
        print(f"Elements found: {len(result['content'])}")
        print(f"First few elements: {result['content'][:3]}")  # Show first 3 elements
        print("-" * 50)
