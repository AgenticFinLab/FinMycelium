"""Non-UI search-driven runner for FinMycelium experiments."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

from finmy.url_collector.base import URLCollectorInput

if TYPE_CHECKING:
    from finmy.url_collector.url_parser import URLParser


logger = logging.getLogger(__name__)


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
) -> List[Dict[str, Any]]:
    formatted_results: List[Dict[str, Any]] = []
    items = response.get("data", {}).get("webPages", {}).get("value", [])
    for item in items:
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
) -> List[Dict[str, Any]]:
    formatted_results: List[Dict[str, Any]] = []
    for item in response.get("references", []):
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
) -> Dict[str, Any]:
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    parser = parser or _default_parser({})

    bocha_response = _safe_search_call(
        _bocha_search,
        search_query,
        summary=True,
        count=10,
        source_name="bocha",
    )
    baidu_response = _safe_search_call(
        _baidu_search,
        search_query,
        source_name="baidu",
    )

    bocha_formatted = _format_bocha_results(bocha_response, search_query, keywords, parser)
    baidu_formatted = _format_baidu_results(baidu_response, search_query, keywords, parser)

    bocha_path = save_dir / f"formatted_bocha_search_results_{stamp}.json"
    baidu_path = save_dir / f"formatted_baidu_search_results_{stamp}.json"
    _write_json(bocha_path, bocha_formatted)
    _write_json(baidu_path, baidu_formatted)

    all_text_content = _render_content_blocks(bocha_formatted) + _render_content_blocks(
        baidu_formatted
    )
    all_text_path = save_dir / f"All_Text_Content_{stamp}.json"
    _write_json(all_text_path, all_text_content)

    return {
        "bocha_result_count": len(bocha_formatted),
        "baidu_result_count": len(baidu_formatted),
        "bocha_results_path": str(bocha_path),
        "baidu_results_path": str(baidu_path),
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
