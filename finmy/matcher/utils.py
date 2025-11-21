"""
General useful utilities for the matcher module.
"""

import re
import json
from typing import TypedDict, List, Dict, Any, Optional


def split_paragraphs(content: str) -> List[Dict[str, Any]]:
    """Split content into paragraphs separated by blank lines and record offsets.

    Returns a list of dicts with keys: 'index', 'text', 'start', 'end'.
    """
    # Paragraphs are split on ≥1 blank line sequences to preserve natural sections.
    # We track the absolute character offsets for each paragraph to enable
    # reconstructing verbatim spans later without altering the original text.
    parts = re.split(r"(?:\r?\n\s*){2,}", content)
    paragraphs: List[Dict[str, Any]] = []
    pos = 0
    for i, part in enumerate(parts):
        start = content.find(part, pos)
        if start == -1:
            # Fallback: search from beginning; may cause non-sequential mapping for duplicate text.
            start = content.find(part)
        end = start + len(part) if start != -1 else None
        if end is not None:
            pos = end
        paragraphs.append(
            {
                "index": i,
                "text": part,
                "start": start,
                "end": end,
            }
        )
    return paragraphs


def get_paragraph_positions(
    content: str,
    paragraphs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute positions of selected paragraphs within `content`.

    Accepts generic selection items (not tied to any specific model schema). Each item may include:
    - `paragraph_indices`: list[int] indicating which paragraphs to span
    - `quote`: exact substring to locate

    Returns mapping-only dicts: `text`, `start`, `end`, optionally
    `paragraph_indices` and `contiguous`. Unmatched quotes yield `start/end=None`.
    """
    content_paragraphs = split_paragraphs(content)
    used_ranges: List[range] = []
    results: List[Dict[str, Any]] = []
    for item in paragraphs:
        idxs = item.get("paragraph_indices") or []
        if (
            isinstance(idxs, list)
            and len(idxs) > 0
            and all(isinstance(i, int) for i in idxs)
        ):
            idxs_sorted = sorted(idxs)
            contiguous = all(
                (idxs_sorted[i] + 1 == idxs_sorted[i + 1])
                for i in range(len(idxs_sorted) - 1)
            )
            first = max(0, min(idxs_sorted))
            last = min(len(content_paragraphs) - 1, max(idxs_sorted))
            start = content_paragraphs[first]["start"]
            end = content_paragraphs[last]["end"]
            text = content[start:end]
            r = range(start, end)
            conflict = any(
                (max(r.start, ur.start) < min(r.stop, ur.stop)) for ur in used_ranges
            )
            if not conflict:
                used_ranges.append(r)
            results.append(
                {
                    "text": text,
                    "start": start,
                    "end": end,
                    "paragraph_indices": idxs_sorted,
                    "contiguous": contiguous,
                }
            )
            continue

        q = item.get("quote", "")
        if q:
            start = content.find(q)
            if start == -1:
                results.append({"text": q, "start": None, "end": None})
                continue
            end = start + len(q)
            r = range(start, end)
            conflict = any(
                (max(r.start, ur.start) < min(r.stop, ur.stop)) for ur in used_ranges
            )
            if not conflict:
                used_ranges.append(r)
            results.append({"text": q, "start": start, "end": end})

    return results


def safe_parse_json(text: str) -> Dict[str, Any]:
    """Robustly parse JSON from model output.

    Some models may wrap JSON with additional prose. This routine first attempts
    a direct parse; if that fails, it extracts the first JSON-looking block via regex.
    Returns a default structure with an empty 'excerpts' list when parsing fails.
    """
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"excerpts": []}
