"""
General useful utilities for the matcher module.
"""

import re
import json
from typing import List, Dict, Any


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
    Returns a default structure with an empty list when parsing fails.
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
        return [{}]


def extract_context_with_paragraphs(
    content: str,
    keyword_start: int,
    keyword_end: int,
    context_chars: int,
    content_paragraphs: list = None,
) -> tuple:
    """
    Extracts context around a keyword within a character window, expanded to full paragraphs.

    This function finds the keyword position in the content and extracts a context window around it. The extracted context is then expanded to include complete paragraphs at both the beginning and end of the window, ensuring that the returned text contains full paragraph boundaries.

    Args:
        content: The full text content to search within.
        keyword_start: The start index of the keyword in content.
        keyword_end: The end index of the keyword in content.
        context_chars: The number of characters of context to extract on each side of the keyword.
        content_paragraphs: List of paragraph dictionaries with 'start' and 'end' keys to calculate paragraph indices.

    Returns:
        tuple: A tuple containing (context_string, paragraph_indices_list) where:
            - context_string: The extracted context, expanded to include complete paragraphs at both the beginning and end. The returned string will contain full paragraphs that encompass the keyword and its surrounding context.
            - paragraph_indices_list: List of indices of paragraphs that the context spans
    """
    total_len = len(content)

    # Define the raw character window around the keyword
    # Calculate start position, ensuring it doesn't go before the beginning of content
    raw_start = max(0, keyword_start - context_chars)
    # Calculate end position, ensuring it doesn't go beyond the end of content
    raw_end = min(total_len, keyword_end + context_chars)

    # Find the paragraph that contains the keyword
    keyword_para_index = -1
    for i, para in enumerate(content_paragraphs or []):
        para_start = para["start"]
        para_end = para["end"]

        # Check if the keyword is within this paragraph
        if para_start <= keyword_start < para_end:
            keyword_para_index = i
            break

    # Find the start of the first paragraph to include in context
    # Start from the paragraph containing the keyword and work backward
    context_start = (
        content_paragraphs[keyword_para_index]["start"]
        if keyword_para_index >= 0
        else 0
    )

    # Find the paragraph that contains raw_start
    for i, para in enumerate(content_paragraphs or []):
        para_start = para["start"]
        para_end = para["end"]

        # If this paragraph overlaps with our raw_start position,
        # use this paragraph's start as context start
        if para_start <= raw_start < para_end:
            context_start = para_start
            break
        elif raw_start < para_start:
            # If raw_start is before this paragraph, use previous paragraph's start
            if i > 0:
                context_start = content_paragraphs[i - 1]["start"]
            break

    # Find the end of the last paragraph to include in context
    # Start from the paragraph containing the keyword and work forward
    context_end = (
        content_paragraphs[keyword_para_index]["end"]
        if keyword_para_index >= 0
        else total_len
    )

    # Find the paragraph that contains raw_end
    for i, para in enumerate(content_paragraphs or []):
        para_start = para["start"]
        para_end = para["end"]

        # If this paragraph overlaps with our raw_end position,
        # use this paragraph's end as context end
        if para_start <= raw_end <= para_end:
            context_end = para_end
            break
        elif para_end < raw_end:
            # Continue looking for the paragraph that contains raw_end
            continue
        else:
            # raw_end is before this paragraph starts, so use previous paragraph's end
            if i > 0:
                context_end = content_paragraphs[i - 1]["end"]
            break

    # Ensure context boundaries are within content bounds
    context_start = max(0, context_start)
    context_end = min(total_len, context_end)

    # Extract the context with full paragraph boundaries
    context = content[context_start:context_end].strip()

    # Find which paragraphs this context spans
    paragraph_indices = []
    for i, para in enumerate(content_paragraphs or []):
        para_start = para["start"]
        para_end = para["end"]

        # Check if the context overlaps with this paragraph
        context_start_pos = context_start
        context_end_pos = context_end

        # Check for overlap between context and paragraph
        if context_start_pos < para_end and context_end_pos > para_start:
            paragraph_indices.append(i)

    return context, paragraph_indices
