from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content, extract_content_from_results






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
    
    # Process individual parsed_content list
    cleaned_content = extract_content_from_parsed_content(example_parsed_content)
    
    print("Original parsed_content elements:", len(example_parsed_content))
    print("Cleaned content length:", len(cleaned_content))
    print("\nCleaned Content:")
    print("=" * 80)
    print(cleaned_content)
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
                }
            ]
        }
    ]
    
    # Process complete results
    url_contents = extract_content_from_results(example_results)
    
    print("\n\nURL Contents:")
    print("=" * 80)
    for url_id, content in url_contents.items():
        print(f"URL ID {url_id}:")
        print(content[:200] + "..." if len(content) > 200 else content)
        print("-" * 80)