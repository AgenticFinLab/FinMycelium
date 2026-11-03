"""Deterministic source-text budgeting after P0; no model calls or new dependencies."""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from finmy.runner.relevance_filter import render_document

PRIORITY = {"CORE": 0, "CONTEXT": 1, "REVIEW": 2, "UNCLASSIFIED": 2}
EXCERPT_NOTE = (
    "Verbatim source excerpts follow; gaps are omitted. Offsets refer to raw_text "
    "(Python character offsets, end exclusive), not event times.\n"
)


def _integer(value: Any, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"all_content_config.{name} must be an integer >= {minimum}")
    return value


def _uncovered(start: int, end: int, selected: list[tuple[int, int]]):
    """Subtract already selected text; overlapping P0 chunks must not duplicate it."""
    cursor = start
    for left, right in sorted(selected):
        if right <= cursor:
            continue
        if left >= end:
            break
        if cursor < left:
            yield cursor, min(left, end)
        cursor = max(cursor, right)
    if cursor < end:
        yield cursor, end


def _ranges(text: str, chunks: list[dict[str, Any]]):
    """Verbatim quotes first, nearby context second, relevant chunks third.

    P0 decisions are selection hints, never appended to source evidence. For long
    mixed documents, known IRRELEVANT chunks are not used as budget padding.
    """
    usable = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        start, end = chunk.get("start_char"), chunk.get("end_char")
        label = chunk.get("relevance", "REVIEW")
        if (type(start) is int and type(end) is int and 0 <= start < end <= len(text)
                and label in PRIORITY):
            usable.append((PRIORITY[label], start, end, chunk))
    usable.sort(key=lambda item: (item[0], item[1], item[2]))
    quotes, surroundings = [], []
    for rank, start, end, chunk in usable:
        evidence = chunk.get("evidence", "")
        if rank > 1 or not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 1200:
            continue
        segment = text[start:end]
        offset = segment.find(evidence)
        if offset >= 0:
            left, right = start + offset, start + offset + len(evidence)
        else:
            # P0 accepts whitespace-normalised excerpts. Recover ORIGINAL offsets.
            match = re.search(r"\s+".join(re.escape(t) for t in evidence.split()), segment)
            if match is None:
                continue
            left, right = start + match.start(), start + match.end()
        quotes.append((left, right, True))
        surroundings.append((max(start, left - 400), min(end, right + 400), False))
    candidates = quotes + surroundings + [(start, end, False) for _, start, end, _ in usable]
    # Missing/unusable decisions must not drop a retained document.
    return candidates or [(0, len(text), False)]


def _block(text: str, start: int, end: int) -> str:
    return f"\n[Source chars {start}:{end}]\n{text[start:end]}\n"


def _fit(document: dict[str, Any], candidates, allowance: int, metadata: bool):
    """Fit whole text or source slices, counting headers and omission markers too."""
    text = document["raw_text"]
    prefix = render_document({**document, "raw_text": ""}) if metadata else ""
    whole = prefix + text
    if text and len(whole) <= allowance:
        return whole, [(0, len(text))]
    prefix += EXCERPT_NOTE
    remaining = allowance - len(prefix)
    selected: list[tuple[int, int]] = []
    for start, end, atomic in candidates:
        fragments = list(_uncovered(start, end, selected))
        if atomic and sum(len(_block(text, a, b)) for a, b in fragments) > remaining:
            # Never output a chopped quote as the evidence selected by P0.
            continue
        for left, right in fragments:
            cost = len(_block(text, left, right))
            if cost > remaining:
                if atomic:
                    continue
                # This overhead is an upper bound when shortening the right edge.
                overhead = cost - (right - left)
                take = min(right - left, max(0, remaining - overhead))
                if take < min(64, right - left):
                    continue
                right = left + take
                # Prefer a nearby sentence/line ending; preserve source characters.
                tail = text[max(left, right - 160):right]
                boundaries = list(re.finditer(r"\n|[.!?。！？](?:\s|$)", tail))
                if boundaries:
                    boundary = max(left, right - 160) + boundaries[-1].end()
                    if boundary - left >= min(64, right - left):
                        right = boundary
                cost = len(_block(text, left, right))
            if right > left and cost <= remaining:
                selected.append((left, right))
                remaining -= cost
    # A header alone, or a few meaningless characters, is not an admitted source.
    if sum(end - start for start, end in selected) < min(128, len(text)) or not text:
        return "", []
    selected.sort()
    rendered = prefix + "".join(_block(text, start, end) for start, end in selected)
    if len(rendered) > allowance:
        raise AssertionError("Internal context budget overflow")
    return rendered, selected


def allocate_context(
    documents: list[dict[str, Any]], decisions: list[dict[str, Any]],
    config: dict[str, Any], *, include_metadata: bool = True,
) -> dict[str, Any]:
    """Reserve a small share for CORE/CONTEXT before expanding any long source.

    Fill higher-priority documents up to their per-document cap, then consider
    REVIEW documents. P0 labels are reused as-is; source quality is not rescored.
    The limit is a CHARACTER budget for source content, not a model token limit.
    """
    options = config.get("all_content_config", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("all_content_config must be a mapping")
    cap = _integer(options.get("max_document_chars", 12000), "max_document_chars")
    seed = min(cap, _integer(options.get("min_document_chars", 2000), "min_document_chars"))
    limit = options.get("max_content_length")
    unlimited = limit is None or (type(limit) is float and math.isinf(limit) and limit > 0)
    if not unlimited:
        limit = _integer(limit, "max_content_length", 0)
    decision_by_id = {item["document_id"]: item for item in decisions}
    prepared, ids = [], set()
    for index, source in enumerate(documents):
        if not isinstance(source, dict) or not isinstance(source.get("raw_text"), str):
            raise ValueError("Each budget document must have string raw_text")
        doc = dict(source)
        doc_id = doc.setdefault("document_id", f"DOC_{index + 1:04d}")
        if not isinstance(doc_id, str) or not doc_id or doc_id in ids:
            raise ValueError("Budget document IDs must be non-empty and unique")
        ids.add(doc_id)
        label = doc.get("relevance", "UNCLASSIFIED")
        if label not in PRIORITY and label != "IRRELEVANT":
            label = "REVIEW"
        chunks = decision_by_id.get(doc_id, {}).get("chunks", [])
        prepared.append({"document": doc, "label": label, "index": index,
                         "candidates": _ranges(doc["raw_text"], chunks or [])})
    if unlimited:
        limit = sum(len(render_document(p["document"]) if include_metadata else
                        p["document"]["raw_text"]) for p in prepared)
    ordered = sorted(prepared, key=lambda p: (PRIORITY.get(p["label"], 3), p["index"]))
    high = [p for p in ordered if p["label"] in {"CORE", "CONTEXT"}]
    review = [p for p in ordered if p["label"] in {"REVIEW", "UNCLASSIFIED"}]
    selected: dict[str, tuple[str, list[tuple[int, int]]]] = {}
    remaining = limit
    for group in (high, review):
        # First secure breadth within the group, then expand. CONTEXT gets a seed
        # before long CORE documents can consume the entire remaining budget.
        for target in (seed, cap):
            for item in group:
                doc = item["document"]
                doc_id = doc["document_id"]
                old, _ = selected.get(doc_id, ("", []))
                allowance = min(target, remaining + len(old))
                if allowance <= len(old):
                    continue
                value, ranges = _fit(doc, item["candidates"], allowance, include_metadata)
                if value and len(value) > len(old):
                    selected[doc_id] = (value, ranges)
                    remaining -= len(value) - len(old)
                # Do not break on a long document: later sources still get a turn.
    contents = [selected[p["document"]["document_id"]][0] for p in ordered
                if p["document"]["document_id"] in selected]
    records = []
    for item in ordered:
        doc = item["document"]
        value, ranges = selected.get(doc["document_id"], ("", []))
        chars = sum(end - start for start, end in ranges)
        records.append({
            "document_id": doc["document_id"], "title": doc.get("title", ""),
            "url": doc.get("url", ""), "relevance": item["label"],
            "original_chars": len(doc["raw_text"]), "included_source_chars": chars,
            "builder_chars": len(value), "included": bool(value),
            "truncated": bool(value) and chars < len(doc["raw_text"]),
            "source_ranges": [{"start_char": a, "end_char": b} for a, b in ranges],
            "omission_reason": (None if value else "filtered_irrelevant" if
                                item["label"] == "IRRELEVANT" else "empty_source" if
                                not doc["raw_text"] else "insufficient_budget_or_document_cap"),
        })
    summary = {
        "candidate_documents": len(documents), "included_documents": len(contents),
        "included_by_label": dict(Counter(r["relevance"] for r in records if r["included"])),
        "omitted_documents": sum(not r["included"] for r in records),
        "truncated_documents": sum(r["truncated"] for r in records),
        "max_content_length": limit, "used_chars": sum(map(len, contents)),
        "unused_chars": remaining, "max_document_chars": cap, "min_document_chars": seed,
    }
    if summary["used_chars"] > limit:
        raise AssertionError("Internal total context budget overflow")
    warnings = []
    missed = [r["document_id"] for r in records if r["relevance"] in {"CORE", "CONTEXT"}
              and not r["included"]]
    if missed:
        warnings.append("Budget could not admit CORE/CONTEXT sources: " + ", ".join(missed))
    return {"contents": contents, "report": {"version": "context-budget-v1",
            "unit": "characters", "summary": summary, "warnings": warnings, "documents": records}}


def main() -> None:
    """Repack an existing P0 run without searching, classifying, or building."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", help="Default: INPUT_DIR/budget_review")
    parser.add_argument("--max-chars", type=int, default=60000)
    parser.add_argument("--max-document-chars", type=int, default=12000)
    args = parser.parse_args()
    source = Path(args.input_dir)
    target = Path(args.output_dir) if args.output_dir else source / "budget_review"
    if source.resolve() == target.resolve():
        parser.error("Use a separate output directory to preserve the original run")
    docs = json.loads((source / "filtered_documents.json").read_text(encoding="utf-8"))
    path = source / "relevance_decisions.json"
    decisions = json.loads(path.read_text(encoding="utf-8"))["documents"] if path.exists() else []
    result = allocate_context(docs, decisions, {"all_content_config": {
        "max_content_length": args.max_chars, "max_document_chars": args.max_document_chars}})
    target.mkdir(parents=True, exist_ok=True)
    for filename, value in (("builder_input_contents.json", result["contents"]),
                            ("context_budget_report.json", result["report"])):
        (target / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["report"]["summary"], ensure_ascii=False, indent=2))
    for warning in result["report"]["warnings"]:
        print("WARNING:", warning)
    print("Saved:", target)


if __name__ == "__main__":
    main()
