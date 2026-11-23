"""Search parsed full.md files and save literal matches and their context."""
import argparse
import json
from pathlib import Path
import re

from finmy.matcher.utils import extract_context_with_paragraphs, split_paragraphs


def search_files(root, keywords, context_chars):
    results = []
    patterns = [(kw, re.compile(re.escape(kw), re.IGNORECASE)) for kw in keywords]
    for path in sorted(root.rglob("full.md")):
        content = path.read_text(encoding="utf-8")
        paragraphs = split_paragraphs(content)
        matches = []
        for keyword, pattern in patterns:
            for match in pattern.finditer(content):
                start, end = match.span()
                context, _ = extract_context_with_paragraphs(
                    content, start, end, context_chars, paragraphs)
                matches.append(dict(matched_keyword=keyword, keyword_position=[start, end],
                                    line_number=1 + content.count("\n", 0, start), context=context))
        if matches:
            results.append(dict(Source=str(path.relative_to(root)), keyword=keywords,
                                match_count=len(matches), matches=matches))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input-path", type=Path, default=Path("pdf_parse_results"))
    parser.add_argument("-k", "--keyword", required=True, help="Comma-separated words or phrases")
    parser.add_argument("-o", "--output-path", type=Path, help="Default: search_information.json in the input directory")
    parser.add_argument("-c", "--context-chars", type=int, default=2000,
                        help="Characters per side before expansion to paragraph boundaries")
    args = parser.parse_args()
    keywords = list(dict.fromkeys(k.strip().replace("-", " ") for k in args.keyword.split(",") if k.strip()))
    if not args.input_path.is_dir() or not keywords or args.context_chars < 0:
        parser.error("Supply an existing input directory, at least one keyword and a nonnegative context size")
    results = search_files(args.input_path, keywords, args.context_chars)
    output = args.output_path or args.input_path / "search_information.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(results)} matching files. Saved {output}")


if __name__ == "__main__":
    main()
