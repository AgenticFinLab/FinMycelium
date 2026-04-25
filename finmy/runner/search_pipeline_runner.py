"""Non-UI search-driven runner for FinMycelium experiments."""

from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from finmy.url_collector.base import URLCollectorInput

if TYPE_CHECKING:
    from finmy.url_collector.url_parser import URLParser


logger = logging.getLogger(__name__)
DEFAULT_BOCHA_COUNT = 10
DEFAULT_BAIDU_COUNT = 20
DEFAULT_MERGE_STRATEGY = "append"


def build_search_query(main_input: str, keywords: List[str]) -> str:
    return f"{main_input} \n\nkeywords: {' '.join(keywords)}"


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def _default_parser(config: Dict[str, Any]):
    from finmy.url_collector.url_parser import URLParser

    parser_config = dict(config.get("url_collector_config", {}) or {})
    return URLParser(
        config=parser_config,
        delay=parser_config.get("delay", 2.0),
        use_selenium_fallback=parser_config.get("use_selenium_fallback", True),
        selenium_wait_time=parser_config.get("selenium_wait_time", 5),
    )


def _create_pipeline(config: Dict[str, Any]):
    from finmy.pipeline import FinmyPipeline

    return FinmyPipeline(config)


def _bocha_search(query: str, *, summary: bool, count: int):
    from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api

    return bochasearch_api(query, summary=summary, count=count)


def _baidu_search(query: str):
    from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api

    return baidusearch_api(query)


def _render_parsed_content(parsed_content: List[Dict[str, Any]]) -> str:
    from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content

    return extract_content_from_parsed_content(parsed_content)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _configured_bocha_count(config: Dict[str, Any]) -> int:
    search_config = config.get("search_config", {}) or {}
    bocha_count = int(search_config.get("bocha_count", DEFAULT_BOCHA_COUNT))
    if bocha_count <= 0:
        raise ValueError("search_config.bocha_count must be a positive integer")
    return bocha_count


def _configured_search_options(config: Dict[str, Any]) -> Dict[str, Any]:
    search_config = config.get("search_config", {}) or {}
    bocha_count = int(search_config.get("bocha_count", DEFAULT_BOCHA_COUNT))
    baidu_count = int(search_config.get("baidu_count", DEFAULT_BAIDU_COUNT))
    if bocha_count <= 0:
        raise ValueError("search_config.bocha_count must be a positive integer")
    if baidu_count <= 0:
        raise ValueError("search_config.baidu_count must be a positive integer")

    merge_strategy = search_config.get("merge_strategy", DEFAULT_MERGE_STRATEGY)
    if merge_strategy not in {"append", "interleave"}:
        raise ValueError("search_config.merge_strategy must be 'append' or 'interleave'")

    quality_filter = dict(search_config.get("quality_filter", {}) or {})
    return {
        "bocha_count": bocha_count,
        "baidu_count": baidu_count,
        "merge_strategy": merge_strategy,
        "quality_filter": quality_filter,
    }


def _safe_search_call(fn, *args, source_name: str, **kwargs) -> Dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("%s search failed: %s", source_name, exc)
        return {
            "_error": {
                "source": source_name,
                "type": type(exc).__name__,
                "message": str(exc),
            }
        }


def _format_bocha_results(
    response: Dict[str, Any],
    search_query: str,
    keywords: List[str],
    parser,
    result_limit: int | None = None,
) -> List[Dict[str, Any]]:
    formatted_results: List[Dict[str, Any]] = []
    items = response.get("data", {}).get("webPages", {}).get("value", [])
    for item in items[:result_limit]:
        formatted_item = {
            "title": item["name"],
            "url": item["url"],
            "search_query_content": search_query,
            "keywords": ",".join(keywords),
            "snippet": item.get("snippet", ""),
            "content": item.get("summary", ""),
            "sitename": item.get("siteName", ""),
            "datepublished": item.get("datePublished", ""),
        }
        output = parser.run(URLCollectorInput(urls=[item["url"]]))
        formatted_item["parsed_content"] = (
            output.results[0]["content"] if output.results else []
        )
        formatted_results.append(formatted_item)
    return formatted_results


def _format_baidu_results(
    response: Dict[str, Any],
    search_query: str,
    keywords: List[str],
    parser,
    result_limit: int | None = None,
) -> List[Dict[str, Any]]:
    formatted_results: List[Dict[str, Any]] = []
    for item in response.get("references", [])[:result_limit]:
        formatted_item = {
            "title": item["title"],
            "url": item["url"],
            "search_query_content": search_query,
            "keywords": ",".join(keywords),
            "snippet": item.get("snippet", ""),
            "content": item.get("content", ""),
            "sitename": item.get("website", ""),
            "datepublished": item.get("date", ""),
        }
        output = parser.run(URLCollectorInput(urls=[item["url"]]))
        formatted_item["parsed_content"] = (
            output.results[0]["content"] if output.results else []
        )
        formatted_results.append(formatted_item)
    return formatted_results


def _canonical_url(url: str) -> str:
    parsed = urlsplit((url or "").strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    ignored_query_keys = {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "spm",
    }
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in ignored_query_keys
    ]
    query = urlencode(query_items, doseq=True)
    return urlunsplit(("", host, path, query, ""))


def _looks_like_search_page(url: str) -> bool:
    parsed = urlsplit((url or "").strip())
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host.endswith("google.com") and path.startswith("/search"):
        return True
    if host.endswith("bing.com") and path.startswith("/search"):
        return True
    if host.endswith("baidu.com") and path.startswith("/s"):
        return True
    if host.endswith("duckduckgo.com") and path in {"", "/", "/html"}:
        return True
    return False


def _looks_like_auth_or_error_page(item: Dict[str, Any]) -> bool:
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    path = urlsplit(url).path.lower()
    auth_fragments = ("/login", "/signin", "/sign-in", "/register", "/account/login")
    bad_title_fragments = (
        "access denied",
        "are you a robot",
        "403 forbidden",
        "404 not found",
        "just a moment",
        "login",
        "page not found",
        "sign in",
    )
    return any(fragment in path for fragment in auth_fragments) or any(
        fragment in title for fragment in bad_title_fragments
    )


def _quality_text(item: Dict[str, Any]) -> str:
    parts = [
        item.get("title", ""),
        item.get("snippet", ""),
        item.get("content", ""),
        _render_parsed_content(item.get("parsed_content", [])),
    ]
    return "\n".join(part for part in parts if part)


def _filter_search_results(
    formatted_results: List[Dict[str, Any]],
    quality_filter: Dict[str, Any],
    seen_urls: set[str],
) -> List[Dict[str, Any]]:
    if not quality_filter.get("enabled", False):
        return list(formatted_results)

    min_text_chars = int(quality_filter.get("min_text_chars", 0) or 0)
    dedupe_url = bool(quality_filter.get("dedupe_url", False))
    reject_search_pages = quality_filter.get("reject_search_pages", True)
    reject_auth_pages = quality_filter.get("reject_auth_pages", True)
    filtered: List[Dict[str, Any]] = []

    for item in formatted_results:
        title = item.get("title", "")
        url = item.get("url", "")
        if not title or not url:
            continue
        canonical = _canonical_url(url)
        if dedupe_url and canonical in seen_urls:
            continue
        if reject_search_pages and _looks_like_search_page(url):
            continue
        if reject_auth_pages and _looks_like_auth_or_error_page(item):
            continue
        if min_text_chars > 0 and len(_quality_text(item).strip()) < min_text_chars:
            continue

        filtered.append(item)
        if dedupe_url:
            seen_urls.add(canonical)

    return filtered


def _merge_formatted_results(
    bocha_results: List[Dict[str, Any]],
    baidu_results: List[Dict[str, Any]],
    merge_strategy: str,
) -> List[Dict[str, Any]]:
    if merge_strategy != "interleave":
        return list(bocha_results) + list(baidu_results)

    merged: List[Dict[str, Any]] = []
    max_len = max(len(bocha_results), len(baidu_results))
    for index in range(max_len):
        if index < len(bocha_results):
            merged.append(bocha_results[index])
        if index < len(baidu_results):
            merged.append(baidu_results[index])
    return merged


def _render_content_blocks(formatted_results: List[Dict[str, Any]]) -> List[str]:
    rendered: List[str] = []
    for item in formatted_results:
        rendered.append(
            f"Title:\n{item['title']}\n\n"
            f"Sitename:\n{item['sitename']}\n\n"
            f"Content:\n{item['content']}\n\n\n"
            f"Parsed Content:\n"
            f"{_render_parsed_content(item['parsed_content'])}\n\n\n"
        )
    return rendered


def collect_search_contents(
    search_query: str,
    keywords: List[str],
    save_dir: str | Path,
    parser=None,
    bocha_count: int = DEFAULT_BOCHA_COUNT,
    baidu_count: int = DEFAULT_BAIDU_COUNT,
    merge_strategy: str = DEFAULT_MERGE_STRATEGY,
    quality_filter: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    parser = parser or _default_parser({})
    quality_filter = dict(quality_filter or {})
    if merge_strategy not in {"append", "interleave"}:
        raise ValueError("merge_strategy must be 'append' or 'interleave'")

    bocha_response = _safe_search_call(
        _bocha_search,
        search_query,
        summary=True,
        count=bocha_count,
        source_name="bocha",
    )
    baidu_response = _safe_search_call(
        _baidu_search,
        search_query,
        source_name="baidu",
    )

    bocha_formatted = _format_bocha_results(
        bocha_response,
        search_query,
        keywords,
        parser,
        result_limit=bocha_count,
    )
    baidu_formatted = _format_baidu_results(
        baidu_response,
        search_query,
        keywords,
        parser,
        result_limit=baidu_count,
    )

    seen_urls: set[str] = set()
    bocha_filtered = _filter_search_results(bocha_formatted, quality_filter, seen_urls)
    baidu_filtered = _filter_search_results(baidu_formatted, quality_filter, seen_urls)

    bocha_path = save_dir / f"formatted_bocha_search_results_{stamp}.json"
    baidu_path = save_dir / f"formatted_baidu_search_results_{stamp}.json"
    filtered_bocha_path = save_dir / f"filtered_bocha_search_results_{stamp}.json"
    filtered_baidu_path = save_dir / f"filtered_baidu_search_results_{stamp}.json"
    _write_json(bocha_path, bocha_formatted)
    _write_json(baidu_path, baidu_formatted)
    _write_json(filtered_bocha_path, bocha_filtered)
    _write_json(filtered_baidu_path, baidu_filtered)

    merged_results = _merge_formatted_results(
        bocha_filtered,
        baidu_filtered,
        merge_strategy=merge_strategy,
    )
    all_text_content = _render_content_blocks(merged_results)
    all_text_path = save_dir / f"All_Text_Content_{stamp}.json"
    _write_json(all_text_path, all_text_content)

    return {
        "bocha_result_count": len(bocha_formatted),
        "baidu_result_count": len(baidu_formatted),
        "filtered_bocha_result_count": len(bocha_filtered),
        "filtered_baidu_result_count": len(baidu_filtered),
        "bocha_results_path": str(bocha_path),
        "baidu_results_path": str(baidu_path),
        "filtered_bocha_results_path": str(filtered_bocha_path),
        "filtered_baidu_results_path": str(filtered_baidu_path),
        "all_text_content_path": str(all_text_path),
        "all_text_content": all_text_content,
    }


_NOISE_LINE_PATTERNS = (
    "skip to main content",
    "cookie",
    "privacy policy",
    "terms of use",
    "all rights reserved",
    "advertisement",
    "subscribe",
    "sign in",
    "log in",
    "navigation",
    "newsletter",
    "accept all",
    "share this",
)

_SIGNAL_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}\b|"
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2}\b|"
    r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?|"
    r"\b\d[\d,]*(?:\.\d+)?\s?(?:million|billion|trillion|mn|bn|usd|eur|gbp|rmb|yuan)\b",
    re.IGNORECASE,
)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _light_denoise_content(content: str) -> str:
    """Remove obvious web boilerplate without summarizing or reordering content."""
    seen_short_lines: set[str] = set()
    cleaned_lines: List[str] = []
    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lowered = line.lower()
        if len(line) < 140 and any(pattern in lowered for pattern in _NOISE_LINE_PATTERNS):
            continue
        if len(line) < 90:
            if lowered in seen_short_lines:
                continue
            seen_short_lines.add(lowered)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _signal_terms(query_text: str | None, keywords: Iterable[str] | None) -> List[str]:
    raw_terms: List[str] = []
    if query_text:
        raw_terms.append(query_text)
        raw_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9&.'-]{3,}", query_text))
        raw_terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", query_text))
    for keyword in keywords or []:
        for part in re.split(r"[;,|]", str(keyword)):
            part = part.strip()
            if part:
                raw_terms.append(part)
                raw_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9&.'-]{3,}", part))
                raw_terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", part))

    terms: List[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        normalized = re.sub(r"\s+", " ", term).strip()
        key = normalized.lower()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        terms.append(normalized)
        if len(terms) >= 40:
            break
    return terms


def _merge_ranges(ranges: List[tuple[int, int]], content_length: int) -> List[tuple[int, int]]:
    normalized = [
        (max(0, start), min(content_length, end))
        for start, end in ranges
        if end > start
    ]
    if not normalized:
        return []
    normalized.sort()
    merged = [normalized[0]]
    for start, end in normalized[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _render_ranges(content: str, ranges: List[tuple[int, int]]) -> str:
    parts: List[str] = []
    previous_end = 0
    for start, end in ranges:
        if parts and start > previous_end:
            parts.append("\n...\n")
        parts.append(content[start:end].strip())
        previous_end = end
    return "\n".join(part for part in parts if part).strip()


def _clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rstrip()
    last_break = max(clipped.rfind("\n"), clipped.rfind(". "), clipped.rfind("。"))
    if last_break >= max_chars * 0.65:
        clipped = clipped[: last_break + 1].rstrip()
    return clipped


def _trim_evidence_aware_item(
    content: str,
    *,
    query_text: str | None,
    keywords: Iterable[str] | None,
    trim_config: Dict[str, Any],
    item_cap: int | None = None,
) -> str:
    soft_cap = _positive_int(trim_config.get("per_item_soft_cap"), 8000)
    hard_cap = _positive_int(trim_config.get("per_item_hard_cap"), 16000)
    head_chars = _positive_int(trim_config.get("head_chars"), 2500)
    window_chars = _positive_int(trim_config.get("keyword_window_chars"), 1800)
    if item_cap is not None:
        hard_cap = min(hard_cap, item_cap)
        soft_cap = min(soft_cap, hard_cap)
    if hard_cap <= 0:
        return ""

    cleaned = _light_denoise_content(content)
    if len(cleaned) <= soft_cap:
        return cleaned

    ranges: List[tuple[int, int]] = [(0, min(head_chars, len(cleaned)))]
    lowered = cleaned.lower()
    half_window = max(1, window_chars // 2)
    signal_range_count = 0

    for term in _signal_terms(query_text, keywords):
        pattern = re.escape(term.lower())
        for match in re.finditer(pattern, lowered):
            ranges.append((match.start() - half_window, match.end() + half_window))
            signal_range_count += 1
            if signal_range_count >= 10:
                break
        if signal_range_count >= 10:
            break

    for match in _SIGNAL_PATTERN.finditer(cleaned):
        ranges.append((match.start() - half_window, match.end() + half_window))
        signal_range_count += 1
        if signal_range_count >= 14:
            break

    if signal_range_count == 0 and len(cleaned) > head_chars:
        tail_chars = min(max(600, head_chars // 2), len(cleaned) - head_chars)
        ranges.append((len(cleaned) - tail_chars, len(cleaned)))

    rendered = _render_ranges(cleaned, _merge_ranges(ranges, len(cleaned)))
    cap = hard_cap if signal_range_count else soft_cap
    return _clip_text(rendered, cap)


def _limit_content_length(
    content_list: List[str],
    max_length: int | float,
    query_text: str | None = None,
    keywords: Iterable[str] | None = None,
    trim_config: Dict[str, Any] | None = None,
) -> List[str]:
    trim_config = trim_config or {}
    trim_mode = str(
        trim_config.get("content_trim_mode")
        or trim_config.get("trim_mode")
        or "greedy"
    )
    if trim_mode != "evidence_aware":
        limited: List[str] = []
        total = 0
        for item in content_list:
            item_length = len(item)
            if total + item_length <= max_length:
                limited.append(item)
                total += item_length
            else:
                break
        return limited

    limited: List[str] = []
    total = 0
    min_item_chars = _positive_int(trim_config.get("min_item_chars"), 1200)
    for item in content_list:
        remaining = max_length - total
        if remaining < min_item_chars:
            break
        item_cap = int(remaining) if remaining != float("inf") else None
        trimmed = _trim_evidence_aware_item(
            item,
            query_text=query_text,
            keywords=keywords,
            trim_config=trim_config,
            item_cap=item_cap,
        )
        if not trimmed:
            continue
        if total + len(trimmed) <= max_length:
            limited.append(trimmed)
            total += len(trimmed)
        else:
            break
    return limited


def run_search_pipeline(
    config: Dict[str, Any],
    main_input: str,
    keywords: List[str],
    save_dir: str | Path,
    parser=None,
) -> Dict[str, Any]:
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    search_query = build_search_query(main_input, keywords)
    search_payload = collect_search_contents(
        search_query=search_query,
        keywords=keywords,
        save_dir=save_dir,
        parser=parser or _default_parser(config),
        **_configured_search_options(config),
    )
    max_length = (
        config.get("all_content_config", {}).get("max_content_length", float("inf"))
    )
    limited_contents = _limit_content_length(
        search_payload["all_text_content"],
        max_length=max_length,
        query_text=main_input,
        keywords=keywords,
        trim_config=config.get("all_content_config", {}),
    )

    pipeline = _create_pipeline(config)
    pipeline_result = pipeline.lm_build_pipeline_with_contents(
        contents=limited_contents,
        query_text=main_input,
        key_words=keywords,
    )
    return {
        **search_payload,
        "search_query": search_query,
        "limited_content_count": len(limited_contents),
        "pipeline_result": pipeline_result,
        "save_dir": str(save_dir),
    }
