"""Non-UI search-driven runner for FinMycelium experiments."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING
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


def _limit_content_length(content_list: List[str], max_length: int | float) -> List[str]:
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
