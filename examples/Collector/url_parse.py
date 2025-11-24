"""
A session to test the url_parser module.
"""

from finmy.url_collector.url_parser import URLParser

# Example usage and testing
if __name__ == "__main__":
    # Example URL list
    # Add more URLs here for testing
    sample_urls = [
        # "http://www.jyb.cn/rmtzcg/xwy/wzxw/202511/t20251119_2111415715.html",
        "http://v.people.cn/n1/2025/1121/c431305-40608834.html"
    ]

    # Initialize parser
    parser = URLParser(delay=2.0)

    # Parse URLs
    results = parser.parse_urls(sample_urls)

    # Save results to JSON (default)
    parser.save_to_json(results)

    # Example of saving to other formats
    # parser.save_to_csv(results)
    # parser.save_to_mysql(results, 'localhost', 'user', 'password', 'database_name')

    print("Parsing completed. Results:")
    for result in results:
        print(f"URL {result['ID']}: {result['url']}")
        print(f"Elements found: {len(result['content'])}")
