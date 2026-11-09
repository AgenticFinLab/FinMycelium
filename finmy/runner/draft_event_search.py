"""Search around events already produced by the initial person EPG.

The existing event table is the search plan. It is not re-discovered or approved
by another model. Event labels guide retrieval; only fetched original text is
returned as evidence for the optional refinement pass.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path

from finmy.runner.scoped_search import search_window
from finmy.runner.subject_search import (
    collect_subject_sources, validate_subject_search_options, _url as _canonical_source_url,
)


# Source-type terms are a fallback only. Concrete activity wording takes priority.
INTENTS = ("", "full text", "filing", "interview")
_NAME_STOPWORDS = set("The In At On As From He She It A An January February March April May June July August "
                      "September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday "
                      "First Second Third This That These Those His Her Their Both After Before During "
                      "Among Without With Since Until Meanwhile Reported According".split())
_QUERY_STOPWORDS = set("a an the of and or in on at to for with by from his her its their "
                       "writing releasing engaging overseeing adjusting building visiting "
                       "commenting receiving continued continuing reported explaining".split())


def draft_event_options(config):
    """Return an independent, finite supplementary phase budget.

    Provider/date policy comes from subject_search. Supplementary cost ceilings do
    not inherit the initial phase's spent ledger or consume its evidence allowance.
    """
    options = config.get("event_followup", {})
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("event_followup must be a mapping")
    options = dict(options)
    if not isinstance(options.get("enabled", True), bool):
        raise ValueError("event_followup.enabled must be a YAML boolean")
    options.setdefault("enabled", True)
    for key, default, minimum in (("max_search_calls", 12, 0), ("max_parse_calls", 40, 0),
                                  ("max_content_length", 60000, 1), ("max_document_chars", 12000, 1),
                                  ("max_relevance_model_calls", 12, 0), ("max_model_calls", 24, 0),
                                  ("max_search_model_calls", 30, 0)):
        value = options.get(key, default)
        if type(value) is not int or value < minimum:
            raise ValueError(f"event_followup.{key} must be a finite integer >= {minimum}")
        options[key] = value
    repair_rounds = options.get("max_repair_rounds_per_event", 1)
    if type(repair_rounds) is not int or not 0 <= repair_rounds <= 3:
        raise ValueError("event_followup.max_repair_rounds_per_event must be an integer in 0..3")
    options["max_repair_rounds_per_event"] = repair_rounds
    for key in ("max_elapsed_seconds", "max_relevance_elapsed_seconds"):
        seconds = options.get(key, 300)
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError(f"event_followup.{key} must be positive and finite")
        options[key] = seconds
    count = options.get("queries_per_event", 2)
    if type(count) is not int or not 1 <= count <= len(INTENTS):
        raise ValueError(f"event_followup.queries_per_event must be in 1..{len(INTENTS)}")
    options["queries_per_event"] = count
    from finmy.runner.enhanced_subject_search import enhanced_search_enabled
    if enhanced_search_enabled(config):
        # The shared agent validates its own provider and publication policy.
        # Legacy Bocha/Baidu-only options do not govern agent acquisition.
        return options, {}
    search_options = dict(config.get("subject_search", {}) or {})
    configured_counts = config.get("search_config", {}) or {}
    for provider in ("bocha", "baidu"):
        key = provider + "_count"
        if key in configured_counts:
            search_options.setdefault(key, configured_counts[key])
    for key in ("max_search_calls", "max_parse_calls", "max_elapsed_seconds"):
        search_options[key] = options[key]
    # Optional supplementary repair cap; other parser/date settings are shared policy.
    if "max_followup_queries" in options:
        search_options["max_followup_queries"] = options["max_followup_queries"]
    return options, validate_subject_search_options(search_options)


def _text(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def _compact(value, words=12, chars=120):
    value = _text(value).replace('"', "")
    parts = [word for word in value.split() if word.lower() not in _QUERY_STOPWORDS]
    return " ".join(parts[:words])[:chars].rstrip()


def _event_clues(package, row, event_id):
    """Use existing graph fields as search clues, never as new source evidence."""
    members = [m for m in package.get("event_activity", []) if m.get("event_id") == event_id]
    member_ids = {m.get("activity_id") for m in members}
    activities = [a for a in package.get("activity", []) if a.get("activity_id") in member_ids]
    actions = {a.get("action_id"): a for a in package.get("action", [])}
    transactions = {t.get("transaction_id"): t for t in package.get("financial_transaction", [])}
    occurrences = {o.get("occurrence_id"): o for o in package.get("occurrence", [])}
    times = {t.get("time_id"): t.get("value", "") for t in package.get("time_value", [])}
    facts, entity_ids, dates, occurrence_ids = [], set(), [], set()
    for activity in activities:
        fact = (actions.get(activity.get("action_id")) or
                transactions.get(activity.get("transaction_id")) or
                occurrences.get(activity.get("context_occurrence_id")) or {})
        phrase = _text(fact.get("action_type") or fact.get("name") or fact.get("title"))
        if phrase:
            facts.append(phrase)
        occurrence_ids.add(fact.get("occurrence_id"))
        for key in ("actor_id", "from_entity_id", "to_entity_id"):
            if fact.get(key):
                entity_ids.add(fact[key])
        for key in ("timestamp_time_id", "start_time_id", "end_time_id"):
            if fact.get(key) in times:
                dates.append(str(times[fact[key]]))
    for participant in package.get("occurrence_participant", []):
        if participant.get("occurrence_id") in occurrence_ids:
            entity_ids.add(participant.get("entity_id"))
    details = [_text(d.get("value")) for d in package.get("activity_detail", [])
               if d.get("activity_id") in member_ids]
    summary = _text(row.get("summary"))
    context = " ".join([_text(row.get("label")), summary] + facts + details)
    subject_id = package.get("graph", {}).get("subject_entity_id")
    aliases = {}
    for alias in package.get("entity_alias", []):
        aliases.setdefault(alias.get("entity_id"), []).append(_text(alias.get("alias")))
    topic_names, other_names = [], []
    for entity in package.get("entity", []):
        entity_id = entity.get("entity_id")
        if entity_id == subject_id:
            continue
        name = _text(entity.get("name"))
        names = [name] + aliases.get(entity_id, [])
        matched = [n for n in names if n and n.casefold() in context.casefold()]
        if matched:
            topic_names.extend(matched)
        elif entity_id in entity_ids and name:
            other_names.append(name)
    # Proper-name phrases in an existing summary are useful when the graph only
    # contains the focal person and employer as entities. No domain vocabulary.
    summary_names = re.findall(
        r"\b[A-Z][a-zA-Z0-9'-]*(?:[ -]+(?:(?:of|and|the)[ ]+)?[A-Z][a-zA-Z0-9'-]*){0,3}\b",
        " ".join([summary] + facts + details))
    subject_names = [_text(e.get("name")) for e in package.get("entity", [])
                     if e.get("entity_id") == subject_id] + aliases.get(subject_id, [])
    for name in summary_names:
        name = re.sub(r"'s\b", "", name)
        parts = name.split()
        while parts and parts[0] in _NAME_STOPWORDS:
            parts.pop(0)
        name = " ".join(parts)
        if not name or name in _NAME_STOPWORDS or len(name) == 1:
            continue
        if any(name.casefold() in n.casefold() for n in subject_names if n):
            continue
        topic_names.append(name)
    names = list(dict.fromkeys(topic_names + other_names))[:6]
    years = sorted(set(re.findall(r"\b(?:18|19|20)\d{2}\b", " ".join(dates) + " " + summary)))
    return {"entity_clues": names, "activity_clues": list(dict.fromkeys(facts))[:8],
            "year_clues": years[:4], "activity_count": len(activities),
            "summary": summary}


def _event_query(event, subject_name, round_index):
    label = _compact(event["event_label"])
    anchors = [label]
    for name in event["entity_clues"]:
        if len(anchors) >= 3:
            break
        if name.casefold() not in " ".join(anchors).casefold():
            anchors.append(_compact(name, words=5, chars=60))
    years = event["year_clues"]
    date_clue = " ".join(years[:1] + years[-1:]) if len(years) > 1 else " ".join(years)
    if round_index:
        facts = event["activity_clues"]
        if facts:
            # Distinct known actions anchor follow-up questions; the exact text
            # remains visible in the plan for checking query quality.
            anchors = [label, _compact(facts[(round_index - 1) % len(facts)], words=10, chars=100)]
        else:
            anchors.append(INTENTS[round_index])
    tokens = [f'"{_text(subject_name).replace(chr(34), "")}"'] + anchors + [date_clue]
    return " ".join(dict.fromkeys(token for token in tokens if token))


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                          encoding="utf-8")


def _log(progress, message):
    logging.info("%s", message)
    if progress:
        progress(message)


def _events(package):
    rows = package.get("event", []) if isinstance(package, dict) else []
    if not isinstance(rows, list):
        return [], [{"reason": "event_table_is_not_a_list"}]
    events, skipped, ids = [], [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            skipped.append({"index": index, "reason": "event_row_is_not_an_object"})
            continue
        label = next((row.get(key).strip() for key in ("label", "title", "name")
                      if isinstance(row.get(key), str) and row[key].strip()), None)
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            event_id = f"draft_event_{index + 1:04d}"
        if not label:
            skipped.append({"index": index, "event_id": event_id, "reason": "empty_event_label"})
            continue
        if event_id in ids:
            skipped.append({"index": index, "event_id": event_id, "reason": "duplicate_event_id"})
            continue
        ids.add(event_id)
        clues = _event_clues(package, row, event_id)
        terms = list(dict.fromkeys([label, _compact(label)] + clues["entity_clues"]))
        events.append({"event_id": event_id, "event_label": label, "event_terms": terms, **clues,
                       "source": "initial_person_epg", "status": "planned",
                       "search_calls": 0, "search_errors": 0, "accepted_documents": 0,
                       "query_scope_is_evidence": False})
    return events, skipped


def _summarize(events, directory):
    path = Path(directory) / "subject_search_report.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for event in events:
        event_id = event["event_id"]
        queries = [q for q in report.get("queries", []) if q.get("event_id") == event_id]
        executed = [q for q in queries if "requested_count" in q]
        accepted = [row for row in report.get("candidates", [])
                    if event_id in row.get("event_ids", []) and row.get("status") == "accepted"]
        reused = [row for row in report.get("candidates", [])
                  if event_id in row.get("event_ids", []) and row.get("status") == "duplicate"]
        event.update(search_calls=len(executed), search_errors=sum("error" in q for q in executed),
                     accepted_documents=len(accepted), reused_documents=len(reused))
        event["status"] = ("sources_found" if accepted else "sources_reused" if reused
                           else "search_failed" if executed and all("error" in q for q in executed)
                           else "searched_no_new_sources" if executed else "not_searched_budget")
    return report.get("queries", [])


def collect_draft_event_sources(package, query, keywords, subject, config, save_dir,
                                progress=None, *, usage=None, search=None, parse=None,
                                known_documents=()):
    """Use every existing event as a candidate within supplementary phase limits.

This function runs after the initial EPG exists. Empty or thin events never
invalidate that initial result. Failures are recorded and return no new sources.
"""
    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    usage = usage if usage is not None else {}
    known_documents = list(known_documents)
    events, skipped = _events(package)
    report = {"version": "draft-event-search-v2", "source": "initial_person_epg",
              "status": "planned", "events": events, "skipped_events": skipped,
              "tasks": [], "queries": [], "new_documents": 0,
              "event_discovery_model_calls": 0, "semantic_support_checked": False,
              "budget_scope": "supplementary_phase"}
    documents = []
    try:
        options, shared = draft_event_options(config)
        report["limits"] = {"event_followup": options, "subject_search": shared}
        if not options["enabled"]:
            report["status"] = "disabled"
            return []
        if not events:
            report["status"] = "no_draft_events"
            _log(progress, "Event follow-up: Initial EPG has no labelled events; kept the initial result.")
            return []
        from finmy.runner.enhanced_subject_search import enhanced_search_enabled, collect_enhanced_sources
        if enhanced_search_enabled(config):
            acquired = collect_enhanced_sources(
                query, keywords, subject, config, target / "draft_event_sources",
                events=events, usage=usage, progress=progress,
            )
            # Each source remains attached to the existing event searched by the
            # shared agent; new event discovery is not an admission requirement.
            documents = acquired["documents"]
            known = {_canonical_source_url(doc.get("url")) for doc in known_documents if doc.get("url")}
            documents = [doc for doc in documents if _canonical_source_url(doc.get("url")) not in known]
            report.update(status=acquired["status"], backend="agent", search_reports=acquired["reports"],
                          new_documents=len(documents))
            outcomes = {row.get("event_id"): row for row in acquired["reports"]}
            for event in events:
                outcome = outcomes.get(event["event_id"], {})
                event.update(status=outcome.get("status", "not_searched"),
                             search_calls=outcome.get("usage", {}).get("search_calls", 0),
                             accepted_documents=sum(event["event_id"] in doc.get("event_ids", [])
                                                    for doc in documents))
            return documents
        first, last = search_window(query, subject, shared)
        start, end = first.isoformat(), last.isoformat()
        report["publication_window"] = {"start": start, "end": end}
        usage.setdefault("started_at", time.monotonic())
        for key in ("search_calls", "parse_calls", "followup_queries"):
            usage.setdefault(key, 0)
            if type(usage[key]) is not int or usage[key] < 0:
                raise ValueError("Invalid supplementary usage counter: " + key)
        search_cap = shared["max_search_calls"]
        parse_cap = shared["max_parse_calls"]
        remaining_search = max(0, search_cap - usage["search_calls"])
        remaining_parse = max(0, parse_cap - usage["parse_calls"])
        report["cumulative_ceilings"] = {"search_calls": search_cap, "parse_calls": parse_cap}
        name = subject.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Event follow-up requires the existing subject name")
        # A sparse event title is already sufficient to search. No source quote,
        # predeclared scope, stage or minimum activity count is required.
        tasks = [{"event_id": event["event_id"], "event_label": event["event_label"],
                  "event_terms": list(event["event_terms"]), "start": start, "end": end,
                  "query": _event_query(event, name, round_index),
                  "intent_index": round_index}
                 for round_index in range(options["queries_per_event"]) for event in events]
        report["tasks"] = tasks
        if (not remaining_search or not remaining_parse or
                time.monotonic() - usage["started_at"] >= shared["max_elapsed_seconds"]):
            report["status"] = "budget_exhausted"
            for event in events:
                event["status"] = "not_searched_budget"
            return []
        # Leave a small part of this same search subbudget for the collector's
        # observed short-page/index-page repair; it never starts another round.
        body_reserve = min(max(0, shared["max_followup_queries"] - usage["followup_queries"]),
                           remaining_search // 4)
        # Give every event one opportunity before deeper queries. Rotate providers
        # across events and rounds, rather than exhausting provider 1 first.
        providers = shared["providers"]
        scheduled = [{**task, "provider": providers[(index % len(events) + task["intent_index"]) % len(providers)]}
                     for index, task in enumerate(tasks)][:remaining_search - body_reserve]
        report.update(scheduled_tasks=scheduled, body_search_reserve=body_reserve)
        if search is None:
            from finmy.runner.scoped_search_api import search
        if parse is None:
            from finmy.runner.scoped_page import parse
        _log(progress, f"Event follow-up: Searching directly around {len(events)} existing EPG event(s).")
        documents = collect_subject_sources(query, keywords, subject,
            {**shared, "max_search_calls": search_cap, "max_parse_calls": parse_cap},
            search, parse, target / "draft_event_sources", progress=progress,
            usage=usage, initial_tasks=scheduled, phase="event_initial", auto_followup=True,
            known_documents=known_documents,
            known_urls=[doc.get("url") for doc in known_documents])
        report["queries"] = _summarize(events, target / "draft_event_sources")
        report.update(status="sources_found" if documents else "no_new_sources", new_documents=len(documents))
        return documents
    except Exception as exc:
        report.update(status="failed", error=type(exc).__name__)
        _log(progress, f"Event follow-up: Unavailable ({type(exc).__name__}); kept the initial EPG.")
        return []
    finally:
        report["usage"] = dict(usage)
        _save(target / "draft_event_search_plan.json", report)
        _save(target / "draft_event_search_sources.json", documents)
