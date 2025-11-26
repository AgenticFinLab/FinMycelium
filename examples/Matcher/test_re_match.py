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
from finmy.generic import UserQueryInput


def create_test_data():
    """Create test data for ReMatch testing."""
    # Sample match data with multiple paragraphs and various keywords
    match_data = """
    近年来，人工智能在资本市场与零售金融的应用显著增加。部分银行采用机器学习进行信用评分与反欺诈检测，这提升了风控效率与业务响应速度。然而，模型的稳定性与在极端市场情况下的表现仍需持续评估。

    一些机构建立了端到端的风险管理框架，包括数据治理、模型验证、监控与回溯测试。对于黑箱模型，内部与外部审计要求更高的可解释性，以满足监管对于透明度与审慎监管的原则。

    从合规角度来看，模型生命周期管理成为重点。审批、版本控制、变更记录与影响评估需要被完整记录。当模型输出被用于关键业务决策时，应建立人机协同机制与阈值告警。

    此外，数据质量直接影响模型表现。企业应建立数据目录与质量度量体系，确保训练与推断数据的一致性与合法合规使用。对于涉及个人数据的场景，必须遵守隐私保护与跨境数据流动的相关规定。

    展望未来，生成式 AI 在投研、客服与运营场景的应用将更广泛。与此同时，企业需要在创新与风险之间寻找平衡，将模型合规、透明度与韧性纳入治理框架的核心指标。
    """

    db_item = None

    # Create a summarized query with keywords
    summarized_query = SummarizedUserQuery(
        summarization="Analyze financial market and risk management",
        key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
        extras=UserQueryInput(
            query_text="识别与人工智能在金融风控与合规相关的内容",
            key_words=["人工智能", "AI", "风险管理", "模型合规", "透明度"],
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
    expected_matches = len(summarized_query.key_words)
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
