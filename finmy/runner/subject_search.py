"""Bounded source discovery: publication window, full text, targeted gap repair.

Search and parse are injected adapters. No model calls and no recursive searches.
"""
import hashlib
import ipaddress
import json
import logging
import re
import math
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from finmy.runner.relevance_filter import make_document
from finmy.runner.scoped_search import plan_search, publication_allowed


def _content_hash(text):
    # Search archives include a title wrapper; deduplicate the actual body.
    body = text.split("\n\nContent:\n", 1)[-1]
    return hashlib.sha256(re.sub(r"\s+", " ", body).strip().encode()).hexdigest()


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


def _critical_topic(title, text=""):
    # Classify retrieved evidence only; never use categories to split discovery.
    value = title + " " + text[:500]
    for topic, pattern in (
        ("meeting", r"annual\s+meeting|shareholder\w*\s+meeting|股东大会|股東大會"),
        ("letter", r"shareholder\w*\s+letter|annual\s+letter|股东信|股東信|致股东|致股東"),
        ("interview", r"interview|访谈|訪談|采访|採訪"),
        ("succession", r"success(?:ion|or)|接班|继任|繼任"),
    ):
        if re.search(pattern, value, re.I):
            return topic
    return None


def collect_subject_sources(query, keywords, subject, options, search, parse, save_dir, progress=None,
                            *, followup_tasks=None, known_urls=(), known_documents=()):
    options = options or {}
    known_urls = {_url(url) for url in known_urls}
    plan = plan_search(query, keywords, subject, options)
    providers = options.get("providers", ["bocha", "baidu"])
    if not providers or any(p not in ("bocha", "baidu") for p in providers):
        raise ValueError("subject_search.providers must contain bocha and/or baidu")
    providers = list(dict.fromkeys(providers))
    limits = {}
    for key, default in (("max_parse_calls", 40),
                         ("max_followup_queries", 3), ("max_links_per_index", 2), ("min_body_chars", 600)):
        value = options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if key == "min_body_chars" else 0):
            raise ValueError(key + " has an invalid limit")
        limits[key] = value
    report = {"plan": plan, "queries": [], "candidates": [], "gaps": [],
              "summary": {"parse_calls": 0, "followup_queries": 0}}
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    documents = []
    content_hashes = {_content_hash(doc["raw_text"]) for doc in known_documents}
    cache, fetched, good, gaps = {}, set(), set(), {}
    started = time.monotonic()
    max_seconds = options.get("max_elapsed_seconds", 300)
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_elapsed_seconds must be positive and finite")
    call_ceiling = limits["max_parse_calls"]
    remaining_initial = len(plan) * len(providers)
    detail_reserve = min(limits["max_parse_calls"] // 4, limits["max_followup_queries"] * 2)
    detail_spent = 0

    def log_progress(message):
        logging.info("%s", message)
        if progress:
            progress(message)

    def save():
        report["summary"]["accepted_documents"] = len(documents)
        report["gaps"] = [{**value, "resolved": key in good} for key, value in gaps.items()]
        (target / "subject_search_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "subject_search_sources.json").write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")

    def candidate(row, task, provider, phase, child=False):
        nonlocal detail_spent
        record = {"url": row.get("url"), "title": row.get("title", ""), "provider": provider,
                  "published_at": row.get("published_at"), "start": task["start"], "end": task["end"],
                  "status": "rejected", "linked_body": child, "phase": phase}
        report["candidates"].append(record)
        url = _url(row.get("url"))
        if not url:
            record["reason"] = "invalid_public_url"
            return
        if url in known_urls:
            record["reason"] = "already_collected"
            return
        key = task.get("gap_id") or url
        topic = task.get("topic") or _critical_topic(row.get("title", ""))
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
            log_progress(f"{provider.title()} Search: Parsing {url}")
            try:
                cache[url] = parse(url)
            except Exception as exc:
                record["reason"] = "parse_error: " + type(exc).__name__
                if topic:
                    gaps.setdefault(key, {**task, "gap_id": key, "topic": topic, "reason": "body_fetch_failed", "title": row.get("title", "")[:160]})
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
        topic = topic or _critical_topic(row.get("title", ""), text)
        reason = _gap(text, row.get("title", ""), topic, limits["min_body_chars"])
        if reason:
            record["reason"] = reason
            if topic:
                gaps.setdefault(key, {**task, "gap_id": key, "topic": topic, "reason": reason, "title": row.get("title", "")[:160]})
            if not child:
                links = [link for link in body.get("links", []) if isinstance(link, dict)
                         and re.search(r"transcript|full.text|read.more|实录|全文|文字|访谈|股东信", str(link.get("text", "")), re.I)]
                for link in links[:limits["max_links_per_index"]]:
                    candidate({"url": link.get("url"), "title": link.get("text", ""), "published_at": None}, {**task, "gap_id": key, "topic": topic}, provider, phase, child=True)
            return
        good.add(key)
        digest = _content_hash(text)
        if digest in content_hashes:
            record.update(status="duplicate", reason="duplicate_body")
            return
        content_hashes.add(digest)
        doc = make_document("Title:\n" + row.get("title", "") + "\n\nContent:\n" + text,
                            {"title": row.get("title", ""), "url": url, "datepublished": published}, provider)
        doc["search_phase"] = phase
        documents.append(doc)
        record.update(status="accepted", reason="body_available")

    def run(task, provider, phase):
        nonlocal remaining_initial, call_ceiling
        entry = {**task, "provider": provider, "phase": phase}
        report["queries"].append(entry)
        if time.monotonic() - started >= max_seconds:
            entry["error"] = "elapsed_budget_exhausted"
            log_progress(f"{provider.title()} Search: Skipped {phase} search: elapsed time limit reached.")
            return
        if phase == "initial":
            # Reserve a fair share for later providers and a few detail fetches.
            reserve = detail_reserve - detail_spent
            available = max(0, limits["max_parse_calls"] - report["summary"]["parse_calls"] - reserve)
            call_ceiling = report["summary"]["parse_calls"] + math.ceil(available / max(1, remaining_initial))
            remaining_initial -= 1
        else:
            call_ceiling = limits["max_parse_calls"]
        label = f"{provider.title()} Search"
        suffix = {"followup": " (detail follow-up)", "decision_followup": " (decision follow-up)"}.get(phase, "")
        log_progress(f"Start: {label}{suffix}")
        if phase != "initial":
            reasons = {
                "body_too_short": "Retrieved body is too short.",
                "index_without_body": "Index page found; full text is missing.",
                "missing_speech_details": "Meeting or interview coverage lacks speech details.",
                "body_fetch_failed": "Failed to retrieve the source body.",
            }
            log_progress(f"{label}: Reason: {reasons.get(task.get('reason'), task.get('reason', 'Missing source details.'))}")
        log_progress(f"{label}: Query: {task['query']}")
        log_progress(f"{label}: Publication date range: {task['start']} to {task['end']}.")
        try:
            count = {"bocha": 10, "baidu": 20}[provider]
            if phase != "initial":
                count //= 4
            entry["requested_count"] = count
            rows = search(provider, task["query"], count, task["start"], task["end"])
            entry["result_count"] = len(rows)
            log_progress(f"{label}: Get {len(rows)} search results.")
            for row in rows[:count]:
                candidate(row, task, provider, phase)
        except Exception as exc:
            entry["error"] = type(exc).__name__ + ": search failed"
            log_progress(f"{label}: Search failed ({type(exc).__name__}).")
        save()

    try:
        if followup_tasks is not None:
            # One fixed decision-search round. Do not recursively fill gaps found here.
            for task in followup_tasks:
                task = {**task, "start": plan[0]["start"], "end": plan[0]["end"]}
                for provider in providers:
                    if report["summary"]["followup_queries"] >= limits["max_followup_queries"]:
                        break
                    report["summary"]["followup_queries"] += 1
                    run(task, provider, "decision_followup")
            log_progress(f"Decision follow-up: Retrieved {len(documents)} new source(s); "
                         "no further search rounds. Missing details remain undocumented.")
            return documents
        for task in plan:
            for provider in providers:
                run(task, provider, "initial")
        # Only observed thin/empty critical documents trigger ONE bounded round.
        # No empty-year filling and no follow-up of follow-up results.
        for key, gap in list(gaps.items()):
            if key in good:
                continue
            task = {k: gap[k] for k in ("query", "start", "end", "gap_id", "topic", "reason")}
            title = gap.get("title", "").replace('"', "")
            task["query"] += f' "{title}" transcript full text questions answers 全文 实录 问答'
            for provider in providers:
                if key in good or report["summary"]["followup_queries"] >= limits["max_followup_queries"]:
                    break
                report["summary"]["followup_queries"] += 1
                run(task, provider, "followup")
        unresolved = sum(key not in good for key in gaps)
        if any("error" in entry for entry in report["queries"]):
            log_progress("Detail follow-up: Search incomplete; see search errors above.")
        elif not gaps or not unresolved:
            log_progress("Detail follow-up: No additional search needed."
                         if not report["summary"]["followup_queries"]
                         else "Detail follow-up: Completed; observed source gaps resolved.")
        else:
            log_progress(f"Detail follow-up: Stopped with {unresolved} unresolved source gap(s); "
                         "follow-up round or configured limit reached.")
    finally:
        save()
    return documents
