"""
Simple Test Script for UserSearchProcessor

Basic examples showing how to use the UserSearchProcessor class
for processing different types of URL inputs.
"""

import os
import sys
import pandas as pd
import json

from finmy.url_collector.SearchCollector.user_search import UserSearchProcessor


def create_test_files():
    """Create simple test files for demonstration."""

    # Create test directory
    test_dir = "examples/Collector/test_files"
    os.makedirs(test_dir, exist_ok=True)

    # Sample data
    sample_data = [
        {"title": "Google", "url": "https://www.google.com"},
        {"title": "Python", "url": "https://www.python.org"},
        {"title": None, "url": "https://www.example.com"},
        {"title": "GitHub", "url": None},
    ]

    # Create XLSX file
    df = pd.DataFrame(sample_data)
    xlsx_path = os.path.join(test_dir, "usls_usersearch.xlsx")
    df.to_excel(xlsx_path, index=False)

    # Create CSV file
    csv_path = os.path.join(test_dir, "usls_usersearch.csv")
    df.to_csv(csv_path, index=False)

    # Create JSON file
    json_path = os.path.join(test_dir, "usls_usersearch.json")
    with open(json_path, "w") as f:
        json.dump(sample_data, f, indent=2)

    print("Created test files:")
    print(f"- {xlsx_path}")
    print(f"- {csv_path}")
    print(f"- {json_path}")

    return xlsx_path, csv_path, json_path


def test_processor():
    """Test the UserSearchProcessor with different inputs."""

    processor = UserSearchProcessor()
    xlsx_path, csv_path, json_path = create_test_files()

    print("\n" + "=" * 50)
    print("TESTING UserSearchProcessor")
    print("=" * 50)

    # Test XLSX file
    print("\n1. Testing XLSX file:")
    results = processor.process_xlsx_file(xlsx_path)
    for i, item in enumerate(results, 1):
        print(f"  {i}. Title: {item['title']}, URL: {item['url']}")

    # Test CSV file
    print("\n2. Testing CSV file:")
    results = processor.process_csv_file(csv_path)
    for i, item in enumerate(results, 1):
        print(f"  {i}. Title: {item['title']}, URL: {item['url']}")

    # Test JSON file
    print("\n3. Testing JSON file:")
    results = processor.process_json_file(json_path)
    for i, item in enumerate(results, 1):
        print(f"  {i}. Title: {item['title']}, URL: {item['url']}")

    # Test single URL
    print("\n4. Testing single URL:")
    results = processor.process_single_url("https://www.test.com")
    for item in results:
        print(f"  Title: {item['title']}, URL: {item['url']}")

    # Test URL list
    print("\n5. Testing URL list:")
    urls = ["https://www.site1.com", "https://www.site2.com"]
    results = processor.process_url_list(urls)
    for i, item in enumerate(results, 1):
        print(f"  {i}. Title: {item['title']}, URL: {item['url']}")

    # Test auto-detect
    print("\n6. Testing auto-detect:")
    results = processor.process(xlsx_path)  # Auto-detects file type
    print(f"  Auto-detected {len(results)} items from {xlsx_path}")


if __name__ == "__main__":
    test_processor()
