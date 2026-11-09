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
from pathlib import Path

from finmy.search.sources import canonical_url


_NAME_STOPWORDS = set("The In At On As From He She It A An January February March April May June July August "
                      "September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday "
                      "First Second Third This That These Those His Her Their Both After Before During "
                      "Among Without With Since Until Meanwhile Reported According".split())
_QUERY_STOPWORDS = set("a an the of and or in on at to for with by from his her its their "
                       "writing releasing engaging overseeing adjusting building visiting "
                       "commenting receiving continued continuing reported explaining".split())


def draft_event_options(config):
    """Return an independent, finite supplementary phase budget.

    The search agent owns provider and date policy. Supplementary cost ceilings
    do not inherit the initial phase's spent ledger or consume its evidence allowance.
    """
    options = config.get("event_followup", {})
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("event_followup must be a mapping")
    options = dict(options)
    for obsolete in ("max_relevance_model_calls", "max_relevance_elapsed_seconds",
                     "queries_per_event", "max_followup_queries"):
        options.pop(obsolete, None)
    if not isinstance(options.get("enabled", False), bool):
        raise ValueError("event_followup.enabled must be a YAML boolean")
    options.setdefault("enabled", False)
    for key, default, minimum in (("max_search_calls", 12, 0), ("max_parse_calls", 40, 0),
                                  ("max_content_length", 120000, 1), ("max_document_chars", 12000, 1),
                                  ("max_model_calls", 24, 0),
                                  ("max_search_model_calls", 30, 0)):
        value = options.get(key, default)
        if type(value) is not int or value < minimum:
            raise ValueError(f"event_followup.{key} must be a finite integer >= {minimum}")
        options[key] = value
    repair_rounds = options.get("max_repair_rounds_per_event", 1)
    if type(repair_rounds) is not int or not 0 <= repair_rounds <= 3:
        raise ValueError("event_followup.max_repair_rounds_per_event must be an integer in 0..3")
    options["max_repair_rounds_per_event"] = repair_rounds
    for key in ("max_elapsed_seconds",):
        seconds = options.get(key, 300)
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError(f"event_followup.{key} must be positive and finite")
        options[key] = seconds
    return options


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


def collect_draft_event_sources(package, query, keywords, subject, config, save_dir,
                                progress=None, *, usage=None,
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
              "backend": "agent", "new_documents": 0,
              "event_discovery_model_calls": 0, "semantic_support_checked": False,
              "budget_scope": "supplementary_phase"}
    documents = []
    try:
        options = draft_event_options(config)
        report["limits"] = {"event_followup": options}
        if not options["enabled"]:
            report["status"] = "disabled"
            return []
        if not events:
            report["status"] = "no_draft_events"
            _log(progress, "Event follow-up: Initial EPG has no labelled events; kept the initial result.")
            return []
        from finmy.runner.enhanced_subject_search import collect_enhanced_sources
        acquired = collect_enhanced_sources(
            query, keywords, subject, config, target / "draft_event_sources",
            events=events, usage=usage, progress=progress,
        )
        # Normalize only for comparison. Saved source URLs and agent fingerprints
        # remain unchanged, including when a previous run is resumed.
        known = set()
        for document in known_documents:
            try:
                known.add(canonical_url(document.get("url")))
            except (AttributeError, TypeError, ValueError):
                continue  # Local/older sources without a public URL still exist.
        for doc in acquired["documents"]:
            try:
                duplicate = canonical_url(doc.get("url")) in known
            except (AttributeError, TypeError, ValueError):
                duplicate = False  # Locally supplied material has no public URL.
            if not duplicate:
                documents.append(doc)
        report.update(status=acquired["status"], search_reports=acquired["reports"],
                      new_documents=len(documents))
        outcomes = {row.get("event_id"): row for row in acquired["reports"]}
        for event in events:
            outcome = outcomes.get(event["event_id"], {})
            event.update(status=outcome.get("status", "not_searched"),
                         search_calls=outcome.get("usage", {}).get("search_calls", 0),
                         accepted_documents=sum(event["event_id"] in doc.get("event_ids", [])
                                                for doc in documents))
        return documents
    except Exception as exc:
        report.update(status="failed", error=type(exc).__name__)
        _log(progress, f"Event follow-up: Unavailable ({type(exc).__name__}); kept the initial EPG.")
        return []
    finally:
        report["usage"] = dict(usage)
        _save(target / "draft_event_search_plan.json", report)
        _save(target / "draft_event_search_sources.json", documents)
