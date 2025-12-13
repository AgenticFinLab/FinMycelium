"""
Test script for URLParserClean functionality.
"""

from finmy.url_collector.base import URLCollectorInput
from finmy.url_collector.url_parser_clean import ContentPostProcessor, extract_content_from_parsed_content, extract_content_from_results


# Example usage
if __name__ == "__main__":
    # Example parsed_content list (from your example)
    example_parsed_content = [
        {
            "text": "首页 新闻 军事 财经 娱乐 汽车 游戏 文化 援藏 插画 健康 公益 优选 法制 守艺中华 应急中国 更多 佛学 文史 古诗词 人物 解梦 生活 商业 数智 地方频道 湖北 山东 山西 丝路 注册 登录",
            "no": 1,
            "href": None
        },
        {
            "text": "首页 新闻 军事 财经 娱乐 汽车 游戏 文化 援藏 插画 健康 公益 优选 法制 守艺中华 应急中国 更多 佛学 文史 古诗词 人物 解梦 生活 商业 数智 地方频道 湖北 山东 山西 丝路 注册 登录",
            "no": 2,
            "href": None
        },
        {
            "text": "首页",
            "no": 3,
            "href": "https://www.china.com/"
        },
        {
            "text": "This is a unique article title about important news",
            "no": 4,
            "href": None
        },
        {
            "text": "This is a unique article title about important news with additional details",
            "no": 5,
            "href": None
        },
        {
            "text": "Article content goes here with meaningful information",
            "no": 6,
            "href": None
        }
    ]
    
    print("Test 1: Process individual parsed_content list")
    print("=" * 80)
    
    # Process individual parsed_content list using convenience function
    cleaned_content = extract_content_from_parsed_content(example_parsed_content)
    
    print("Original parsed_content elements:", len(example_parsed_content))
    print("Cleaned content length:", len(cleaned_content))
    print("Characters removed:", len(' '.join([e['text'] for e in example_parsed_content])) - len(cleaned_content))
    print("\nCleaned Content:")
    print("=" * 80)
    print(cleaned_content)
    print("=" * 80)
    
    print("\n\nTest 2: Process using ContentPostProcessor class directly")
    print("=" * 80)
    
    # Test using ContentPostProcessor class
    processor = ContentPostProcessor(
        method_name="test_content_processor",
        config={"min_similarity_threshold": 0.9, "min_text_length": 10},
        min_similarity_threshold=0.9,
        min_text_length=10
    )
    
    cleaned_content2 = processor.process_parsed_content(example_parsed_content)
    print("Using ContentPostProcessor class:")
    print(cleaned_content2[:500] + "..." if len(cleaned_content2) > 500 else cleaned_content2)
    
    print("\n\nTest 3: Process complete results")
    print("=" * 80)
    
    # Example with full results
    example_results = [
        {
            "ID": 1,
            "url": "https://example.com/page1",
            "parsertime": "2024-01-01T12:00:00",
            "content": example_parsed_content
        },
        {
            "ID": 2,
            "url": "https://example.com/page2",
            "parsertime": "2024-01-01T12:05:00",
            "content": [
                {
                    "text": "Different page content here",
                    "no": 1,
                    "href": None
                },
                {
                    "text": "Different page content here",  # Duplicate
                    "no": 2,
                    "href": None
                },
                {
                    "text": "More unique content for page 2",
                    "no": 3,
                    "href": None
                }
            ]
        }
    ]
    
    # Process complete results using convenience function
    url_contents = extract_content_from_results(example_results)
    
    print("URL Contents:")
    print("=" * 80)
    for url_id, content in url_contents.items():
        print(f"URL ID {url_id}:")
        print(f"Content length: {len(content)} characters")
        print(content[:200] + "..." if len(content) > 200 else content)
        print("-" * 80)
    
    print("\n\nTest 4: Process using ContentPostProcessor.run() method")
    print("=" * 80)
    
    # Test using the run() method with URLCollectorInput
    processor2 = ContentPostProcessor(method_name="test_processor_run")
    
    # Create input with parsing results in extras
    clean_input = URLCollectorInput(
        urls=[],  # URLs not needed for cleaning
        extras={
            "parsing_results": example_results,
            "source": "test_cleaning"
        }
    )
    
    # Run the processor
    clean_output = processor2.run(clean_input)
    
    print(f"Processing completed with {len(clean_output.logs)} logs")
    print(f"Processed {len(clean_output.results)} results")
    print(f"Extracted {len(clean_output.parsed_contents)} cleaned contents")
    
    # Show logs
    if clean_output.logs:
        print("\nProcessing logs:")
        for log in clean_output.logs:
            print(f"  - {log}")
    
    # Show cleaned contents
    print("\nCleaned contents from processor.run():")
    for url_id, content in clean_output.parsed_contents.items():
        print(f"  URL {url_id}: {content[:100]}...")
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 80)