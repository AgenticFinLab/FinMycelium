"""
Test script for ReMatch class.

This script tests the functionality of the ReMatch class by creating mock
MatchInput objects with keywords and verifying the matching results.
"""

import sys
import os

# Add the parent directory to the path so we can import from finmy
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from finmy.matcher.re_match import ReMatch
from finmy.matcher.base import MatchInput, MatchOutput
from finmy.matcher.summarizer import SummarizedUserQuery
from finmy.query import UserQueryInput


def create_test_data():
    """Create test data for ReMatch testing."""
    # Sample match data with multiple paragraphs and various keywords
    match_data = """
    Artificial intelligence is transforming the financial industry. AI algorithms can analyze market trends and predict potential risks with high accuracy.
    
    Supply chain disruptions continue to impact global markets. Companies are working to establish more resilient supply chains.

    Financial markets experienced significant volatility today. The stock index fell by 2.3% in early trading.
    
    Risk management strategies are becoming increasingly important for investors. Experts recommend diversifying portfolios across different asset classes.
    
    Market volatility is expected to continue in the coming months. Investors should remain cautious and consider long-term investment strategies.
    """

    db_item = None

    # Create a summarized query with keywords
    summarized_query = SummarizedUserQuery(
        summarization="Analyze financial market and risk management",
        keywords=[
            "financial markets",
            "risk management",
        ],
        user_query=QueryInput(
            content=match_data,
            query_text="I want to know about financial markets and risk management",
            key_words=[
                "financial markets",
                "risk management",
            ],
        ),
    )

    return match_data, db_item, summarized_query


def test_re_match_match_method():
    """Test the match method of ReMatch class."""
    print("Testing match method...")

    match_data, db_item, summarized_query = create_test_data()

    # Create MatchInput
    match_input = MatchInput(
        match_data=match_data,
        db_item=db_item,
        summarized_query=summarized_query,
    )

    # Create ReMatch instance
    re_matcher = ReMatch(method_name="test_re_match")

    # Test match method
    matches = re_matcher.match(match_input)

    print(f"Found {len(matches)} matches")
    for i, match in enumerate(matches, 1):
        print(f"Match {i}:\n{match}\n")

    # Verify that we got matches for all keywords
    expected_matches = len(summarized_query.keywords)
    assert (
        len(matches) >= expected_matches
    ), f"Expected at least {expected_matches} matches, got {len(matches)}"

    print("Match method test passed!\n")
    return matches, match_data


def test_re_match_map_positions():
    """Test the map_positions method of ReMatch class."""
    print("Testing map_positions method...")

    match_data, db_item, summarized_query = create_test_data()

    # Create MatchInput
    match_input = MatchInput(
        match_data=match_data,
        db_item=db_item,
        summarized_query=summarized_query,
    )

    # Create ReMatch instance
    re_matcher = ReMatch(method_name="test_re_match")

    # Get matches first
    matches = re_matcher.match(match_input)

    # Test map_positions method
    match_items = re_matcher.map_positions(match_data, matches)

    print(f"Mapped {len(match_items)} items")
    for i, item in enumerate(match_items, 1):
        print(f"MatchItem {i}:")
        print(f"  Paragraph: {item.paragraph}...")
        print(f"  Paragraph Index: {item.paragraph_index}")
        print(f"  Start: {item.start}")
        print(f"  End: {item.end}")
        print(f"  Contiguous Indices: {item.contiguous_indices}")
        print()

    # Verify that positions are correctly mapped
    assert len(match_items) == len(
        matches
    ), f"Expected {len(matches)} items, got {len(match_items)}"
    for item in match_items:
        assert item.start is not None, "Start position should not be None"
        assert item.end is not None, "End position should not be None"

    print("map_positions method test passed!\n")
    return match_items


def test_re_match_run_method():
    """Test the run method of ReMatch class."""
    print("Testing run method...")

    match_data, db_item, summarized_query = create_test_data()

    # Create MatchInput
    match_input = MatchInput(
        match_data=match_data,
        db_item=db_item,
        summarized_query=summarized_query,
    )

    # Create ReMatch instance
    re_matcher = ReMatch(method_name="test_re_match")

    # Test run method
    result = re_matcher.run(match_input)

    print(f"Run result:")
    print(f"  Method: {result.method}")
    print(f"  Execution Time: {result.time:.6f} seconds")
    print(f"  Number of Items: {len(result.items)}")
    print()

    # Verify result structure
    assert isinstance(result, MatchOutput), "Result should be a MatchOutput object"
    assert len(result.items) > 0, "Result should contain items"
    assert result.method == "test_re_match", "Method name should match"
    assert result.time >= 0, "Execution time should be non-negative"

    print("run method test passed!\n")
    return result


def main():
    """Run all tests for ReMatch class."""
    print("Starting ReMatch tests...\n")

    try:
        # Run individual tests
        test_re_match_match_method()
        test_re_match_map_positions()
        test_re_match_run_method()

        print("All tests passed successfully!")
        return 0
    except AssertionError as e:
        print(f"Test failed: {e}")
        return 1
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
