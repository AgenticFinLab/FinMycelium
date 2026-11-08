"""Deterministic source-text budgeting after P0; no model calls or new dependencies."""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from itertools import groupby
from pathlib import Path
from typing import Any

from finmy.runner.relevance_filter import render_document

PRIORITY = {"CORE": 0, "CONTEXT": 1, "REVIEW": 2, "UNCLASSIFIED": 2}
SEARCH_PHASE = {"initial": 0, "followup": 1, "decision_followup": 2}
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


def _fit(document: dict[str, Any], candidates, allowance: int, metadata: bool, *, allow_whole=True):
    """Fit whole text or source slices, counting headers and omission markers too."""
    text = document["raw_text"]
    prefix = render_document({**document, "raw_text": ""}) if metadata else ""
    whole = prefix + text
    if allow_whole and text and len(whole) <= allowance:
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
    # Adjacent slices are one original passage. Keep wrappers only at real gaps.
    merged = []
    for start, end in selected:
        if merged and merged[-1][1] == start:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    selected = merged
    rendered = prefix + "".join(_block(text, start, end) for start, end in selected)
    if len(rendered) > allowance:
        raise AssertionError("Internal context budget overflow")
    return rendered, selected


def _strings(value):
    return list(dict.fromkeys(item.strip() for item in value
                             if isinstance(item, str) and item.strip())) if isinstance(value, list) else []


def _event_ranges(document, chunks):
    """Select original passages; event terms are retrieval hints, never evidence.

    A document retrieved for an event is not necessarily about that event. Exact
    lexical hits prioritize passages, while P0 determines which chunks may enter.
    No claim of semantic coverage is made from term matching.
    """
    text = document["raw_text"]
    valid = [chunk for chunk in chunks if isinstance(chunk, dict)
             and type(chunk.get("start_char")) is int and type(chunk.get("end_char")) is int
             and 0 <= chunk["start_char"] < chunk["end_char"] <= len(text)]
    allowed = sorted((chunk["start_char"], chunk["end_char"]) for chunk in valid
                     if chunk.get("relevance", "REVIEW") in PRIORITY)
    if not valid:
        allowed = [(0, len(text))] if text else []
    merged = []
    for left, right in allowed:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    marker = re.search(r"\n\ncontent:\n", text, re.I)
    body_start = marker.end() if marker else 0
    matches, nearby, term_hits = [], [], {}
    route_terms = [term for route in document.get("event_routes", []) if isinstance(route, dict)
                   for term in _strings(route.get("event_terms"))]
    for term in list(dict.fromkeys(_strings(document.get("event_terms")) + route_terms)):
        if len(term) > 160:
            continue
        pattern = re.compile(r"(?<![A-Za-z0-9])" + r"\s+".join(map(re.escape, term.split()))
                             + r"(?![A-Za-z0-9])", re.I)
        rows = []
        for left, right in merged:
            for match in pattern.finditer(text, max(left, body_start), right):
                rows.append((match.start(), match.end(), left, right))
        if rows:
            term_hits[term] = [(a, b) for a, b, _, _ in rows]
            matches.append([(max(left, a - 120), min(right, b + 120), True)
                            for a, b, left, right in rows])
            nearby.append([(max(left, a - 600), min(right, b + 600), False)
                           for a, b, left, right in rows])
    def interleave(queues):
        for index in range(max(map(len, queues), default=0)):
            for queue in queues:
                if index < len(queue):
                    yield queue[index]
    # Prioritize one passage per term before repeated mentions of the same term.
    # P0 quotes keep their original locations and remain protected from clipping.
    p0 = _ranges(text, valid) if merged else []
    permitted_p0 = [(max(a, left), min(b, right), atomic)
                    for a, b, atomic in p0 for left, right in merged
                    if max(a, left) < min(b, right)]
    candidates = list(interleave(matches))
    candidates += [row for row in permitted_p0 if row[2]]
    candidates += list(interleave(nearby))
    candidates += [row for row in permitted_p0 if not row[2]]
    return list(dict.fromkeys(candidates)), term_hits, merged


def _event_schedule(items):
    """Round-robin sources by event and phase, emitting shared sources once."""
    event_ids = list(dict.fromkeys(event for item in items for event in item["event_ids"]))
    queues = []
    for event_id in event_ids:
        phases = {}
        for item in sorted(items, key=lambda row: (PRIORITY[row["label"]], row["index"])):
            if event_id in item["event_ids"]:
                phases.setdefault(item["document"].get("search_phase", "initial"), []).append(item)
        queue = []
        for index in range(max(map(len, phases.values()), default=0)):
            queue.extend(rows[index] for rows in phases.values() if index < len(rows))
        queues.append(queue)
    ordered, seen = [], set()
    while any(queues):
        for queue in queues:
            while queue and queue[0]["document"]["document_id"] in seen:
                queue.pop(0)
            if queue:
                item = queue.pop(0)
                seen.add(item["document"]["document_id"])
                ordered.append(item)
    return ordered, event_ids


def _allocate_events(documents, decisions, options, include_metadata):
    """Spend one finite input budget on event passages before general background."""
    if options.get("preserve_all", False):
        raise ValueError("Event allocation does not support preserve_all")
    limit = _integer(options.get("max_content_length", 60000), "max_content_length", 0)
    cap = _integer(options.get("max_document_chars", 12000), "max_document_chars")
    seed = min(cap, _integer(options.get("min_document_chars", 2000), "min_document_chars"))
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
        decision = decision_by_id.get(doc_id, {})
        label = doc.get("relevance", decision.get("relevance", "UNCLASSIFIED"))
        if decision.get("relevance") == "IRRELEVANT":
            label = "IRRELEVANT"
        if label not in PRIORITY and label != "IRRELEVANT":
            label = "REVIEW"
        routes = doc.get("event_routes", [])
        routes = routes if isinstance(routes, list) else []
        doc["event_routes"] = routes
        route_terms = {}
        for route in routes:
            if not isinstance(route, dict) or not isinstance(route.get("event_id"), str):
                continue
            event_id = route["event_id"].strip()
            if event_id:
                route_terms[event_id] = list(dict.fromkeys(route_terms.get(event_id, [])
                                            + _strings(route.get("event_terms"))))
        event_ids = list(dict.fromkeys(_strings(doc.get("event_ids")) + list(route_terms)))
        if len(event_ids) == 1 and event_ids[0] not in route_terms:
            route_terms[event_ids[0]] = _strings(doc.get("event_terms"))
        candidates, hits, permitted = _event_ranges(doc, decision.get("chunks") or [])
        prepared.append({"document": doc, "index": index, "label": label,
                         "event_ids": event_ids, "candidates": candidates,
                         "route_terms": route_terms, "hits": hits, "permitted": permitted})
    useful = [item for item in prepared if item["label"] in PRIORITY]
    event_items, _ = _event_schedule([item for item in useful if item["event_ids"] and item["hits"]])
    unmatched, _ = _event_schedule([item for item in useful if item["event_ids"] and not item["hits"]])
    events = list(dict.fromkeys(event for item in prepared for event in item["event_ids"]))
    background = sorted([item for item in useful if not item["event_ids"]],
                        key=lambda item: (PRIORITY[item["label"]], item["index"]))
    selected, remaining = {}, limit
    step = max(seed, 512)
    targets = [seed] + list(range(seed + step, cap, step)) + ([cap] if cap > seed else [])
    for group in (event_items, unmatched, background):
        # Breadth across events and retrieval phases comes before expansion.
        # Expansion also proceeds in bounded increments so one long event cannot
        # immediately consume every character left after initial coverage.
        for target in targets:
            for item in group:
                doc = item["document"]
                doc_id = doc["document_id"]
                old, _ = selected.get(doc_id, ("", []))
                allowance = min(target, remaining + len(old))
                if allowance <= len(old):
                    continue
                full_allowed = item["permitted"] == [(0, len(doc["raw_text"]))]
                value, ranges = _fit(doc, item["candidates"], allowance, include_metadata,
                                     allow_whole=full_allowed)
                if value and len(value) > len(old):
                    selected[doc_id] = value, ranges
                    remaining -= len(value) - len(old)
    # Keep each event's sources together in the emitted list, after scheduling
    # allocations fairly. A shared document is emitted only under its first group.
    event_rank = {event: index for index, event in enumerate(events)}
    ordered = sorted(prepared, key=lambda item: (
        min((event_rank.get(event, len(events)) for event in item["event_ids"]), default=len(events)),
        PRIORITY.get(item["label"], 3), item["index"]))
    contents, records = [], []
    for item in ordered:
        doc = item["document"]
        value, ranges = selected.get(doc["document_id"], ("", []))
        if value:
            contents.append(value)
        chars = sum(end - start for start, end in ranges)
        included_terms = [term for term, hits in item["hits"].items()
                          if any(left <= a and b <= right for a, b in hits for left, right in ranges)]
        records.append({"document_id": doc["document_id"], "title": doc.get("title", ""),
            "url": doc.get("url", ""), "relevance": item["label"],
            "search_phase": doc.get("search_phase", "initial"), "event_ids": item["event_ids"],
            "event_terms_matched": list(item["hits"]), "event_terms_included": included_terms,
            "event_routes": [{"event_id": event, "matched_terms": [term for term in terms if term in item["hits"]],
                              "included_terms": [term for term in terms if term in included_terms]}
                             for event, terms in item["route_terms"].items()],
            "routing_without_body_term_match": bool(item["event_ids"]) and not item["hits"],
            "original_chars": len(doc["raw_text"]), "included_source_chars": chars,
            "builder_chars": len(value), "included": bool(value),
            "truncated": bool(value) and chars < len(doc["raw_text"]),
            "source_ranges": [{"start_char": a, "end_char": b} for a, b in ranges],
            "omission_reason": (None if value else "filtered_irrelevant" if item["label"] == "IRRELEVANT"
                else "empty_source" if not doc["raw_text"] else "no_permitted_source_range"
                if not item["permitted"] else "insufficient_budget_or_document_cap")})
    used = sum(map(len, contents))
    if used > limit or remaining != limit - used:
        raise AssertionError("Internal total context budget overflow")
    summary = {"candidate_documents": len(documents), "included_documents": len(contents),
        "included_by_label": dict(Counter(row["relevance"] for row in records if row["included"])),
        "omitted_documents": sum(not row["included"] for row in records),
        "truncated_documents": sum(row["truncated"] for row in records),
        "max_content_length": limit, "used_chars": used, "unused_chars": remaining,
        "max_document_chars": cap, "min_document_chars": seed}
    warnings = []
    missed = [row["document_id"] for row in records
              if row["relevance"] in {"CORE", "CONTEXT"} and not row["included"]]
    if missed:
        warnings.append("Budget could not admit CORE/CONTEXT sources: " + ", ".join(missed))
    coverage = [{"event_id": event,
        "routed_document_ids": [row["document_id"] for row in records if event in row["event_ids"]],
        "included_document_ids": [row["document_id"] for row in records
                                  if event in row["event_ids"] and row["included"]],
        "lexically_matched_document_ids": [row["document_id"] for row in records
            if any(route["event_id"] == event and route["matched_terms"] for route in row["event_routes"])],
        "lexically_admitted_document_ids": [row["document_id"] for row in records
            if any(route["event_id"] == event and route["included_terms"] for route in row["event_routes"])],
        "coverage_basis": "routing_and_verbatim_term_matches_only",
        "semantic_support_checked": False} for event in events]
    return {"contents": contents, "report": {"version": "context-event-budget-v1", "unit": "characters",
        "allocation_strategy": "event", "routing_is_evidence": False,
        "event_coverage": coverage, "summary": summary, "warnings": warnings, "documents": records}}


def allocate_context(
    documents: list[dict[str, Any]], decisions: list[dict[str, Any]],
    config: dict[str, Any], *, include_metadata: bool = True,
) -> dict[str, Any]:
    """Reserve a small share for CORE/CONTEXT before expanding any long source.

    Allocate each search phase before the next, so follow-ups use only remaining
    space and never shrink earlier excerpts. Within each phase, fill CORE/CONTEXT
    before REVIEW. P0 labels are reused as-is; source quality is not rescored.
    The limit is a CHARACTER budget for source content, not a model token limit.
    """
    options = config.get("all_content_config", {}) or {}
    if not isinstance(options, dict):
        raise ValueError("all_content_config must be a mapping")
    if options.get("allocation_strategy") == "event":
        return _allocate_events(documents, decisions, options, include_metadata)
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
                         "phase": SEARCH_PHASE.get(doc.get("search_phase"), 0),
                         "candidates": _ranges(doc["raw_text"], chunks or [])})
    if unlimited:
        limit = sum(len(render_document(p["document"]) if include_metadata else
                        p["document"]["raw_text"]) for p in prepared)
    ordered = sorted(prepared, key=lambda p: (p["phase"], PRIORITY.get(p["label"], 3), p["index"]))
    groups = []
    for _, phase in groupby(ordered, key=lambda p: p["phase"]):
        phase = list(phase)
        groups.extend([p for p in phase if p["label"] in labels]
                      for labels in ({"CORE", "CONTEXT"}, {"REVIEW", "UNCLASSIFIED"}))
    selected: dict[str, tuple[str, list[tuple[int, int]]]] = {}
    remaining = limit
    for group in groups:
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
            "search_phase": doc.get("search_phase", "initial"),
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
    parser.add_argument("--allocation-strategy", choices=("phase_order", "event"), default="phase_order")
    args = parser.parse_args()
    source = Path(args.input_dir)
    target = Path(args.output_dir) if args.output_dir else source / "budget_review"
    if source.resolve() == target.resolve():
        parser.error("Use a separate output directory to preserve the original run")
    docs = json.loads((source / "filtered_documents.json").read_text(encoding="utf-8"))
    path = source / "relevance_decisions.json"
    decisions = json.loads(path.read_text(encoding="utf-8"))["documents"] if path.exists() else []
    result = allocate_context(docs, decisions, {"all_content_config": {
        "max_content_length": args.max_chars, "max_document_chars": args.max_document_chars,
        "allocation_strategy": args.allocation_strategy}})
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
