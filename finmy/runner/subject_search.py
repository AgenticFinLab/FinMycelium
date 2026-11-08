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


def validate_subject_search_options(options):
    """Validate finite application limits before any provider or parser call."""
    if not isinstance(options, dict):
        raise ValueError("subject_search must be a mapping")
    result = dict(options)
    providers = result.get("providers", ["bocha", "baidu"])
    if (not isinstance(providers, list) or not providers
            or any(p not in ("bocha", "baidu") for p in providers)):
        raise ValueError("subject_search.providers must contain bocha and/or baidu")
    result["providers"] = list(dict.fromkeys(providers))
    for key, default in (("max_parse_calls", 40), ("max_search_calls", 12),
                         ("max_followup_queries", 3), ("max_links_per_index", 2),
                         ("min_body_chars", 600)):
        value = result.get(key, default)
        if type(value) is not int or value < (1 if key == "min_body_chars" else 0):
            raise ValueError(key + " must be a finite nonnegative integer")
        result[key] = value
    seconds = result.get("max_elapsed_seconds", 300)
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds <= 0):
        raise ValueError("max_elapsed_seconds must be positive and finite")
    result["max_elapsed_seconds"] = seconds
    for provider, default in (("bocha", 10), ("baidu", 20)):
        key = provider + "_count"
        value = result.get(key, default)
        if type(value) is not int or not 1 <= value <= 50:
            raise ValueError(key + " must be an integer from 1 to 50")
        result[key] = value
        key = "followup_" + key
        value = result.get(key, max(1, value // 4))
        if type(value) is not int or not 1 <= value <= 50:
            raise ValueError(key + " must be an integer from 1 to 50")
        result[key] = value
    return result


def _event_metadata(task):
    result = {}
    for plural, singular in (("event_ids", "event_id"),
                             ("event_labels", "event_label"), ("event_terms", None)):
        values = task.get(plural, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        extra = task.get(singular) if singular else None
        if plural == "event_labels":
            extra = extra or task.get("event_title")
        values = values + ([extra] if extra else [])
        result[plural] = list(dict.fromkeys(x.strip() for x in values
                                          if isinstance(x, str) and x.strip()))
    return result


def _associate(document, task):
    # Query membership is routing metadata, never a factual association claim.
    metadata = _event_metadata(task)
    for key, values in metadata.items():
        if values:
            document[key] = list(dict.fromkeys(document.get(key, []) + values))
    routes = document.setdefault("event_routes", []) if metadata["event_ids"] else []
    for index, event_id in enumerate(metadata["event_ids"]):
        labels = metadata["event_labels"]
        route = {"event_id": event_id,
                 "event_label": labels[index] if index < len(labels) else "",
                 "event_terms": list(metadata["event_terms"])}
        previous = next((item for item in routes if item.get("event_id") == event_id), None)
        if previous is None:
            routes.append(route)
        else:
            previous["event_terms"] = list(dict.fromkeys(previous.get("event_terms", []) + route["event_terms"]))
            if not previous.get("event_label"):
                previous["event_label"] = route["event_label"]


def _round_robin(tasks):
    groups = {}
    for index, task in enumerate(tasks):
        ids = _event_metadata(task)["event_ids"]
        key = ids[0] if ids else "task:" + str(index)
        groups.setdefault(key, []).append(task)
    result = []
    while any(groups.values()):
        for group in groups.values():
            if group:
                result.append(group.pop(0))
    return result


def collect_subject_sources(query, keywords, subject, options, search, parse, save_dir, progress=None,
                            *, followup_tasks=None, known_urls=(), known_documents=(), usage=None,
                            initial_tasks=None, phase="initial", auto_followup=True,
                            followup_phase="decision_followup"):
    """Collect bounded raw sources, optionally sharing one run's cost ledger.

    Every limit is a cumulative ceiling against ``usage``. A caller may use a
    lower ceiling for discovery and restore the configured ceiling for events,
    without resetting costs or elapsed time. Source associations are hints only.
    """
    options = validate_subject_search_options(options or {})
    if initial_tasks is not None and followup_tasks is not None:
        raise ValueError("Use initial_tasks or followup_tasks, not both")
    if type(auto_followup) is not bool:
        raise ValueError("auto_followup must be a boolean")
    root_plan = plan_search(query, keywords, subject, options)
    providers = options["providers"]
    limits = options
    usage = {} if usage is None else usage
    if not isinstance(usage, dict):
        raise ValueError("usage must be a mutable mapping")
    usage.setdefault("started_at", time.monotonic())
    for key in ("search_calls", "parse_calls", "followup_queries"):
        usage.setdefault(key, 0)
        if type(usage[key]) is not int or usage[key] < 0:
            raise ValueError("Invalid shared usage counter: " + key)
    started = usage["started_at"]
    if isinstance(started, bool) or not isinstance(started, (int, float)) or not math.isfinite(started):
        raise ValueError("Invalid shared usage started_at")
    usage.setdefault("attempted_urls", [])
    if not isinstance(usage["attempted_urls"], list):
        raise ValueError("usage.attempted_urls must be a list")
    attempted = set(usage["attempted_urls"])
    known_urls = {_url(url) for url in known_urls}
    known_documents = list(known_documents)
    by_url = {_url(doc.get("url")): doc for doc in known_documents if _url(doc.get("url"))}
    by_hash = {_content_hash(doc["raw_text"]): doc for doc in known_documents}
    known_urls.update(by_url)

    def normalize_task(task):
        if not isinstance(task, dict) or not isinstance(task.get("query"), str) or not task["query"].strip():
            raise ValueError("Search tasks require a nonempty query")
        task = dict(task)
        task.setdefault("start", root_plan[0]["start"])
        task.setdefault("end", root_plan[0]["end"])
        from datetime import date
        try:
            start, end = date.fromisoformat(task["start"]), date.fromisoformat(task["end"])
            low, high = date.fromisoformat(root_plan[0]["start"]), date.fromisoformat(root_plan[0]["end"])
        except (TypeError, ValueError):
            raise ValueError("Search task dates must be ISO calendar dates") from None
        if not low <= start <= end <= high:
            raise ValueError("Search task dates must remain inside the configured publication window")
        if "provider" in task and task["provider"] not in providers:
            raise ValueError("Task provider is not enabled")
        return task

    supplied = followup_tasks if followup_tasks is not None else initial_tasks
    plan = [normalize_task(task) for task in (root_plan if supplied is None else supplied)]
    plan = _round_robin(plan)
    # Explicit provider assignments already express a bounded event-major plan.
    # Preserve that order so the supplementary phase can rotate providers without
    # provider 1 consuming all available time. Legacy unassigned plans keep their
    # existing provider-round behavior.
    if supplied is not None and all("provider" in task for task in plan):
        scheduled = [(task, task["provider"]) for task in plan]
    else:
        scheduled = [(task, provider) for provider in providers for task in plan
                     if task.get("provider", provider) == provider]
    report = {"plan": plan, "queries": [], "candidates": [], "gaps": [],
              "summary": {"parse_calls": 0, "search_calls": 0, "followup_queries": 0}}
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    documents = []
    cache, fetched, good, gaps = {}, set(), set(), {}
    max_seconds = limits["max_elapsed_seconds"]
    call_ceiling = limits["max_parse_calls"]
    # Reserve parse shares only for provider calls that can actually run under
    # the remaining cumulative search cap, not every task in a larger plan.
    remaining_initial = min(len(scheduled), max(0, limits["max_search_calls"] - usage["search_calls"]))
    remaining_followup = min(remaining_initial,
                             max(0, limits["max_followup_queries"] - usage["followup_queries"]))
    remaining_parses = max(0, limits["max_parse_calls"] - usage["parse_calls"])
    detail_reserve = (min(remaining_parses // 4, limits["max_followup_queries"] * 2)
                      if auto_followup else 0)
    detail_spent = 0

    def log_progress(message):
        logging.info("%s", message)
        if progress:
            progress(message)

    def save():
        report["summary"].update(accepted_documents=len(documents),
                                 cumulative_search_calls=usage["search_calls"],
                                 cumulative_parse_calls=usage["parse_calls"],
                                 cumulative_followup_queries=usage["followup_queries"])
        report["gaps"] = [{**value, "resolved": key in good} for key, value in gaps.items()]
        report["limits"] = {key: limits[key] for key in
                            ("max_search_calls", "max_parse_calls", "max_followup_queries", "max_elapsed_seconds")}
        (target / "subject_search_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "subject_search_sources.json").write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")

    def candidate(row, task, provider, current_phase, child=False):
        nonlocal detail_spent
        if not isinstance(row, dict):
            return
        record = {"url": row.get("url"), "title": row.get("title", ""), "provider": provider,
                  "published_at": row.get("published_at"), "start": task["start"], "end": task["end"],
                  "status": "rejected", "linked_body": child, "phase": current_phase,
                  **_event_metadata(task)}
        report["candidates"].append(record)
        url = _url(row.get("url"))
        if not url:
            record["reason"] = "invalid_public_url"
            return
        key = task.get("gap_id") or url
        topic = (task.get("topic") or _critical_topic(row.get("title", ""))
                 or ("event" if _event_metadata(task)["event_ids"] else None))
        # Even duplicate membership must pass this task's narrower date window.
        if not child:
            allowed, reason = publication_allowed(row.get("published_at"), task["start"], task["end"])
            if not allowed:
                record["reason"] = reason
                return
        if url in by_url:
            doc = by_url[url]
            allowed, reason = publication_allowed(doc.get("published_at"), task["start"], task["end"])
            if allowed:
                _associate(doc, task)
                good.add(key)
                record.update(status="duplicate", reason="already_collected")
            else:
                record["reason"] = reason
            return
        if url in known_urls:
            record["reason"] = "already_collected"
            return
        if url in attempted and url not in fetched:
            record["reason"] = "already_attempted"
            return
        if url not in fetched:
            calls = usage["parse_calls"]
            extra_detail = child and calls >= call_ceiling and detail_spent < detail_reserve
            if (calls >= limits["max_parse_calls"] or (calls >= call_ceiling and not extra_detail)
                    or time.monotonic() - started >= max_seconds):
                record["reason"] = "parse_budget_exhausted"
                return
            if extra_detail:
                detail_spent += 1
            fetched.add(url)
            attempted.add(url)
            usage["attempted_urls"].append(url)
            usage["parse_calls"] += 1
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
        published = body.get("published_at") or (None if child else row.get("published_at"))
        allowed, reason = publication_allowed(published, task["start"], task["end"])
        record["published_at"] = published
        if not allowed:
            record["reason"] = reason
            return
        text = body.get("text") or ""
        if not isinstance(text, str):
            record["reason"] = "invalid_body"
            return
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
                    candidate({"url": link.get("url"), "title": link.get("text", ""), "published_at": None}, {**task, "gap_id": key, "topic": topic}, provider, current_phase, child=True)
            return
        good.add(key)
        digest = _content_hash(text)
        if digest in by_hash:
            doc = by_hash[digest]
            # Keep a separately dated source when the retained representative
            # cannot be used inside this task's narrower publication window.
            if (not _event_metadata(task)["event_ids"]
                    or publication_allowed(doc.get("published_at"), task["start"], task["end"])[0]):
                # Legacy decision follow-up also deduplicates against user
                # sources without publication metadata. Event-scoped reuse
                # requires a representative valid for that event's window.
                _associate(doc, task)
                if _event_metadata(task)["event_ids"]:
                    by_url[url] = doc
                record.update(status="duplicate", reason="duplicate_body")
                return
        doc = make_document("Title:\n" + row.get("title", "") + "\n\nContent:\n" + text,
                            {"title": row.get("title", ""), "url": url, "datepublished": published}, provider)
        doc["search_phase"] = current_phase
        _associate(doc, task)
        documents.append(doc)
        by_hash[digest] = doc
        by_url[url] = doc
        record.update(status="accepted", reason="body_available")

    def run(task, provider, current_phase, *, is_followup=False):
        nonlocal remaining_initial, remaining_followup, call_ceiling
        entry = {**task, "provider": provider, "phase": current_phase}
        report["queries"].append(entry)
        error = None
        if time.monotonic() - started >= max_seconds:
            error = "elapsed_budget_exhausted"
        elif usage["search_calls"] >= limits["max_search_calls"]:
            error = "search_budget_exhausted"
        elif is_followup and usage["followup_queries"] >= limits["max_followup_queries"]:
            error = "followup_budget_exhausted"
        elif usage["parse_calls"] >= limits["max_parse_calls"]:
            error = "parse_budget_exhausted"
        if error:
            entry["error"] = error
            log_progress(f"{provider.title()} Search: Skipped {current_phase} search: {error}.")
            return
        if not is_followup:
            reserve = detail_reserve - detail_spent
            available = max(0, limits["max_parse_calls"] - usage["parse_calls"] - reserve)
            call_ceiling = usage["parse_calls"] + math.ceil(available / max(1, remaining_initial))
            remaining_initial -= 1
        else:
            available = max(0, limits["max_parse_calls"] - usage["parse_calls"])
            call_ceiling = usage["parse_calls"] + math.ceil(available / max(1, remaining_followup))
            remaining_followup -= 1
        label = f"{provider.title()} Search"
        suffix = {"followup": " (detail follow-up)", "decision_followup": " (decision follow-up)",
                  "event_followup": " (event follow-up)",
                  "event_body_followup": " (event body follow-up)"}.get(current_phase, "")
        log_progress(f"Start: {label}{suffix}")
        if is_followup:
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
            count = options[("followup_" if is_followup else "") + provider + "_count"]
            entry["requested_count"] = count
            usage["search_calls"] += 1
            report["summary"]["search_calls"] += 1
            if is_followup:
                usage["followup_queries"] += 1
                report["summary"]["followup_queries"] += 1
            rows = search(provider, task["query"], count, task["start"], task["end"])
            entry["result_count"] = len(rows)
            log_progress(f"{label}: Get {len(rows)} search results.")
            for row in rows[:count]:
                candidate(row, task, provider, current_phase)
        except Exception as exc:
            entry["error"] = type(exc).__name__ + ": search failed"
            log_progress(f"{label}: Search failed ({type(exc).__name__}).")
        save()

    try:
        if followup_tasks is not None:
            for task, provider in scheduled:
                if usage["followup_queries"] >= limits["max_followup_queries"]:
                    break
                run(task, provider, followup_phase, is_followup=True)
            followup_label = "Event follow-up" if followup_phase.startswith("event_") else "Decision follow-up"
            log_progress(f"{followup_label}: Retrieved {len(documents)} new source(s); "
                         "no further search rounds. Missing details remain undocumented.")
            return documents
        for task, provider in scheduled:
            run(task, provider, phase)
        if not auto_followup:
            return documents
        # One bounded round for observed missing source bodies, not missing facts.
        remaining_followup = min(
            sum(key not in good for key in gaps) * len(providers),
            max(0, limits["max_search_calls"] - usage["search_calls"]),
            max(0, limits["max_followup_queries"] - usage["followup_queries"]))
        for key, gap in list(gaps.items()):
            if key in good:
                continue
            task = dict(gap)
            title = gap.get("title", "").replace('"', "")
            task["query"] += f' "{title}" transcript full text questions answers 全文 实录 问答'
            for provider in providers:
                if key in good or usage["followup_queries"] >= limits["max_followup_queries"]:
                    break
                repair_phase = "event_body_followup" if phase.startswith("event_") else "followup"
                run(task, provider, repair_phase, is_followup=True)
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
