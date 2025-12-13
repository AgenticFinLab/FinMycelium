"""
Test script for URLParser class.
"""

from finmy.url_collector.base import URLCollectorInput
from finmy.url_collector.url_parser import URLParser


# Example usage
if __name__ == "__main__":
    # Example URL list including problematic URLs
    sample_urls = [
        "http://www.jyb.cn/rmtzcg/xwy/wzxw/202511/t20251119_2111415715.html",
        "http://v.people.cn/n1/2025/1121/c431305-40608834.html",
        "https://baijiahao.baidu.com/s?id=1850027474872762323&wfr=spider&for=pc",
    ]

    # Create collector input
    collector_input = URLCollectorInput(
        urls=sample_urls,
        extras={"source": "example_test", "test_mode": True}
    )

    # Initialize parser with configuration
    parser = URLParser(
        method_name="test_url_parser",
        config={
            "delay": 2.0,
            "use_selenium_fallback": True,
            "selenium_wait_time": 5,
        }
    )

    # Run the collector
    output = parser.run(collector_input)

    print(f"Parsing completed. Parsed {len(output.results)} URLs")
    print(f"Logs: {len(output.logs)} log entries")
    
    for result in output.results:
        print(f"\nURL {result['ID']}: {result['url']}")
        print(f"Parse time: {result['parsertime']}")
        print(f"Elements found: {len(result['content'])}")
        
        # Show content preview
        content_id = result['ID']
        if content_id in output.parsed_contents:
            content = output.parsed_contents[content_id]
            if content:
                print(f"Content preview: {content[:200]}...")
            else:
                print(f"Content: Empty or failed to extract")
        else:
            print(f"Content: Not available in parsed_contents")
        
        print("-" * 50)

    # Show summary statistics
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    total_elements = sum(len(r['content']) for r in output.results if isinstance(r.get('content'), list))
    successful_parses = sum(1 for r in output.results if 'error' not in str(r.get('content', {})))
    
    print(f"Total URLs processed: {len(output.results)}")
    print(f"Successfully parsed: {successful_parses}")
    print(f"Total content elements: {total_elements}")
    print(f"Unique parsed contents: {len(output.parsed_contents)}")
    
    # Show first few logs
    if output.logs:
        print(f"\nFirst 5 logs:")
        for i, log in enumerate(output.logs[:5]):
            print(f"  {i+1}. {log}")
    
    # Save results to JSON
    if output.results:
        json_file = parser.save_to_json(output.results, r"examples\utest\Collector\test_files\test_url_parser_results.json")
        print(f"\nResults saved to: {json_file}")