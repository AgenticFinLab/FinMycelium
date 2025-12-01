#!/usr/bin/env python
"""
Run every LX matcher implementation against the curated example set and optionally
persist the aggregated findings as Markdown for manual inspection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import gc
from typing import Dict, List, Any, Tuple

import dotenv

from finmy.matcher.base import MatchInput
from finmy.matcher.lx_match import (
    KWMatcher as LXKWMatcher,
    LXMatcher,
    VectorMatcher as LXVectorMatcher,
    LMMatcher as LXLMMatcher,
)

from finmy.matcher.lm_match import LLMMatcher
from finmy.matcher.re_match import ReMatch
from finmy.matcher.summarizer import SummarizedUserQuery


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EXAMPLES_PATH = SCRIPT_DIR / "match_examples.json"

dotenv.load_dotenv()


def load_examples(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Examples file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Examples file must contain a JSON list")
    return data


MATCHERS = {
    "LXKWMatcher": LXKWMatcher,
    "LXLMMatcher": LXLMMatcher,
    "LXMatcher": LXMatcher,
    "LXVectorMatcher": LXVectorMatcher,
    "ReMatch": ReMatch,
    "LMMatcher": LLMMatcher,
}


def run_all_matchers_on_examples(
    examples: List[Dict[str, Any]],
    matcher_names: List[str] = None,
) -> Dict[str, List[List[Dict[str, Any]]]]:
    """
    Run each matcher in matcher_names on all examples.
    Returns a dict {matcher_name: [results_per_example]}
    """
    matcher_names = matcher_names or list(MATCHERS.keys())
    all_results = {}
    for mname in matcher_names:
        print(f"{mname} running...")
        cls = MATCHERS[mname]
        if mname == "LMMatcher":
            matcher = cls(lm_name="deepseek-chat")
        else:
            matcher = cls()
        matcher_results = []
        for ex in examples:
            sq = SummarizedUserQuery(
                summarization=ex.get("query_text") or "",
                key_words=ex.get("key_words", []),
            )
            match_input = MatchInput(
                match_data=ex.get("content") or "",
                summarized_query=sq,
            )
            # For ReMatch and legacy matchers, support both .match and .run API signatures
            if hasattr(matcher, "run"):
                res = matcher.run(match_input)
                # Try to standardize the output to [{paragraph_indices: ...}]
                items = getattr(res, "items", [])
                output = []
                for item in items:
                    indices = getattr(item, "contiguous_indices", None)
                    if (
                        indices is None
                        and hasattr(item, "start")
                        and hasattr(item, "end")
                    ):
                        indices = list(range(item.start, item.end + 1))
                    output.append({"paragraph_indices": indices})
                matcher_results.append(output)
            elif hasattr(matcher, "match"):
                # LX matchers and ReMatch
                output = matcher.match(match_input)
                matcher_results.append(output)
            else:
                matcher_results.append([])
        all_results[mname] = matcher_results
        gc.collect()
    return all_results


def render_markdown_aggregated(
    examples: List[Dict[str, Any]],
    all_results: Dict[str, List[List[Dict[str, Any]]]],
) -> str:
    """Produce a Markdown summary for manual inspection."""
    lines = []
    matcher_names = list(all_results.keys())
    for idx, ex in enumerate(examples):
        lines.append(f"### Example {idx + 1}: {ex.get('query_text', '')}\n")
        lines.append("<details>\n<summary>Content</summary>\n\n")
        lines.append(ex.get("content", ""))
        lines.append("\n</details>\n")
        lines.append(f"\n**Key Words:** {', '.join(ex.get('key_words', []))}\n")
        for mname in matcher_names:
            res = all_results[mname][idx]
            lines.append(f"\n- **{mname}:** {res}")
        lines.append("\n---\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=str, default=str(DEFAULT_EXAMPLES_PATH))
    parser.add_argument(
        "--matchers", type=str, nargs="*", help="Optional names of matchers to run."
    )
    args = parser.parse_args()

    examples = load_examples(Path(args.examples))
    all_results = run_all_matchers_on_examples(examples, matcher_names=args.matchers)

    md = render_markdown_aggregated(examples, all_results)
    with open("docs/example-results.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Wrote matcher results to example-results.md")


if __name__ == "__main__":
    main()
