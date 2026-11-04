"""Bounded source discovery: publication window, full text, targeted gap repair.

Search and parse are injected adapters. No model calls and no recursive searches.
"""
import hashlib
import ipaddress
import json
import re
import math
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from finmy.runner.relevance_filter import make_document
from finmy.runner.scoped_search import plan_search, publication_allowed


def _url(value):
    try:
        p = urlsplit(value)
        host = p.hostname or ""
        if p.scheme not in ("http", "https") or not host or p.username or p.password:
            return None
        if host.lower() == "localhost" or host.lower().endswith((".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))
    except (ValueError, TypeError):
        return None


def _gap(text, title, topic, minimum):
    """Conservative quality heuristic, not a factual/semantic completeness claim."""
    if len(text.strip()) < minimum:
        return "body_too_short"
    index = re.search(r"video index|video archive|watch video|视频解析|無水印|无水印|下载资源|资源下载|档案首页", title + " " + text[:500], re.I)
    detail = re.search(r"\b(said|stated|explained|question|answer|Q:|A:)\b|表示|认为|回答|提问|问：|答：|说道|致股东|Dear.*shareholder", text, re.I)
    if index and not detail:
        return "index_without_body"
    if topic in ("meeting", "interview", "succession") and not detail:
        return "missing_speech_details"
    return None


def collect_subject_sources(query, keywords, subject, options, search, parse, save_dir, progress=None):
    options = options or {}
    plan = plan_search(query, keywords, subject, options)
    providers = options.get("providers", ["bocha", "baidu"])
    if not providers or any(p not in ("bocha", "baidu") for p in providers):
        raise ValueError("subject_search.providers must contain bocha and/or baidu")
    providers = list(dict.fromkeys(providers))
    limits = {}
    for key, default in (("results_per_query", 4), ("max_parse_calls", 40),
                         ("max_followup_queries", 3), ("max_links_per_index", 2), ("min_body_chars", 600)):
        value = options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if key in ("results_per_query", "min_body_chars") else 0):
            raise ValueError(key + " has an invalid limit")
        limits[key] = value
    report = {"plan": plan, "queries": [], "candidates": [], "gaps": [],
              "summary": {"parse_calls": 0, "followup_queries": 0}}
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    documents, content_hashes = [], set()
    cache, fetched, good, gaps = {}, set(), set(), {}
    started = time.monotonic()
    max_seconds = options.get("max_elapsed_seconds", 300)
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_elapsed_seconds must be positive and finite")
    call_ceiling = limits["max_parse_calls"]
    remaining_initial = len(plan) * len(providers)
    detail_reserve = min(limits["max_parse_calls"] // 4, limits["max_followup_queries"] * 2)
    detail_spent = 0

    def save():
        report["summary"]["accepted_documents"] = len(documents)
        report["gaps"] = [{**value, "resolved": key in good} for key, value in gaps.items()]
        (target / "subject_search_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "subject_search_sources.json").write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")

    def candidate(row, task, provider, child=False):
        nonlocal detail_spent
        key = (task["year"], task["topic"])
        record = {"url": row.get("url"), "title": row.get("title", ""), "provider": provider,
                  "published_at": row.get("published_at"), "year": task["year"], "topic": task["topic"],
                  "status": "rejected", "linked_body": child}
        report["candidates"].append(record)
        url = _url(row.get("url"))
        if not url:
            record["reason"] = "invalid_public_url"
            return
        # Search result publication metadata must pass BEFORE any expensive fetch.
        if not child:
            allowed, reason = publication_allowed(row.get("published_at"), task["start"], task["end"])
            if not allowed:
                record["reason"] = reason
                return
        if url not in fetched:
            calls = report["summary"]["parse_calls"]
            extra_detail = child and calls >= call_ceiling and detail_spent < detail_reserve
            if (calls >= limits["max_parse_calls"] or (calls >= call_ceiling and not extra_detail)
                    or time.monotonic() - started >= max_seconds):
                record["reason"] = "parse_budget_exhausted"
                return
            if extra_detail:
                detail_spent += 1
            fetched.add(url)
            report["summary"]["parse_calls"] += 1
            try:
                cache[url] = parse(url)
            except Exception as exc:
                record["reason"] = "parse_error: " + type(exc).__name__
                if task["topic"] in ("meeting", "interview", "letter", "succession"):
                    gaps.setdefault(key, {**task, "reason": "body_fetch_failed", "title": row.get("title", "")[:160]})
                return
        body = cache.get(url)
        if not isinstance(body, dict):
            record["reason"] = "parse_failed"
            return
        # A linked page never inherits its index's date. Explicit conflicting
        # body metadata also overrides search metadata and is checked again.
        published = body.get("published_at") or (None if child else row.get("published_at"))
        allowed, reason = publication_allowed(published, task["start"], task["end"])
        record["published_at"] = published
        if not allowed:
            record["reason"] = reason
            return
        text = body.get("text") or ""
        reason = _gap(text, row.get("title", ""), task["topic"], limits["min_body_chars"])
        if reason:
            record["reason"] = reason
            if task["topic"] in ("meeting", "interview", "letter", "succession"):
                gaps.setdefault(key, {**task, "reason": reason, "title": row.get("title", "")[:160]})
            if not child:
                links = [link for link in body.get("links", []) if isinstance(link, dict)
                         and re.search(r"transcript|full.text|read.more|实录|全文|文字|访谈|股东信", str(link.get("text", "")), re.I)]
                for link in links[:limits["max_links_per_index"]]:
                    candidate({"url": link.get("url"), "title": link.get("text", ""), "published_at": None}, task, provider, child=True)
            return
        good.add(key)
        digest = hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()
        if digest in content_hashes:
            record.update(status="duplicate", reason="duplicate_body")
            return
        content_hashes.add(digest)
        doc = make_document("Title:\n" + row.get("title", "") + "\n\nContent:\n" + text,
                            {"title": row.get("title", ""), "url": url, "datepublished": published}, provider)
        documents.append(doc)
        record.update(status="accepted", reason="body_available")

    def run(task, provider, phase):
        nonlocal remaining_initial, call_ceiling
        entry = {**task, "provider": provider, "phase": phase}
        report["queries"].append(entry)
        if time.monotonic() - started >= max_seconds:
            entry["error"] = "elapsed_budget_exhausted"
            return
        if phase == "initial":
            # Reserve a fair share for later years/topics and a few detail fetches.
            reserve = detail_reserve - detail_spent
            available = max(0, limits["max_parse_calls"] - report["summary"]["parse_calls"] - reserve)
            call_ceiling = report["summary"]["parse_calls"] + math.ceil(available / max(1, remaining_initial))
            remaining_initial -= 1
        else:
            call_ceiling = limits["max_parse_calls"]
        if progress:
            progress(f"Search: {task['year']} / {task['topic']} / {provider}" + (" (detail follow-up)" if phase == "followup" else ""))
        try:
            rows = search(provider, task["query"], limits["results_per_query"], task["start"], task["end"])
            entry["result_count"] = len(rows)
            for row in rows[:limits["results_per_query"]]:
                candidate(row, task, provider)
        except Exception as exc:
            entry["error"] = type(exc).__name__ + ": search failed"
        save()

    try:
        for task in plan:
            for provider in providers:
                run(task, provider, "initial")
        # Only observed thin/empty critical documents trigger ONE bounded round.
        # No empty-year filling and no follow-up of follow-up results.
        for key, gap in list(gaps.items()):
            if key in good:
                continue
            task = {k: gap[k] for k in ("query", "start", "end", "year", "topic")}
            title = gap.get("title", "").replace('"', "")
            task["query"] += f' "{title}" transcript full text questions answers 全文 实录 问答'
            for provider in providers:
                if key in good or report["summary"]["followup_queries"] >= limits["max_followup_queries"]:
                    break
                report["summary"]["followup_queries"] += 1
                run(task, provider, "followup")
    finally:
        save()
    return documents
