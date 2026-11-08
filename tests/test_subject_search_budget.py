"""Shared event collection budgets and source-reuse contracts; no network calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.subject_search import collect_subject_sources, validate_subject_search_options


SUBJECT = {"name": "Warren Buffett", "coverage_start": "2022", "coverage_end": "2023"}
BODY = "Buffett said Berkshire bought shares and explained the investment. " * 12


def row(url, date="2023-05-01"):
    return {"url": url, "published_at": date, "title": "Documented investment"}


def task(event, suffix="", **extra):
    return {"query": event + suffix, "event_id": event, "event_label": event + " investment",
            "event_terms": [event], **extra}


class SharedSearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.options = {"providers": ["bocha"], "max_parse_calls": 4,
                        "max_search_calls": 4, "max_followup_queries": 0}
        self.usage = {}
        self.calls, self.parses = [], []

    def search(self, provider, query, count, start, end):
        self.calls.append((provider, query, count, start, end))
        return [row("https://example.com/" + query + str(i)) for i in range(4)]

    def parse(self, url):
        self.parses.append(url)
        return {"text": BODY + url}

    def collect(self, name, tasks, **kwargs):
        return collect_subject_sources(
            "Buffett activities", [], SUBJECT, kwargs.pop("options", self.options),
            kwargs.pop("search", self.search), kwargs.pop("parse", self.parse), self.root / name,
            usage=self.usage, initial_tasks=tasks, auto_followup=False, **kwargs)

    def test_cumulative_parse_ceilings_reserve_and_resume_without_reset(self):
        self.collect("discovery", [task("seed")], options={**self.options, "max_parse_calls": 1})
        self.collect("events", [task("OXY"), task("BYD")])
        self.assertEqual(len(self.parses), 4)
        self.assertEqual(self.usage["parse_calls"], 4)
        self.assertEqual(sum("OXY" in url for url in self.parses), 2)
        self.assertEqual(sum("BYD" in url for url in self.parses), 1)
        self.assertEqual(self.usage["search_calls"], 3)
        self.assertEqual(len(set(self.usage["attempted_urls"])), 4)
        json.dumps(self.usage, allow_nan=False)

    def test_search_budget_is_shared_even_when_providers_return_no_rows(self):
        self.options["max_search_calls"] = 1
        def empty(*args):
            self.calls.append(args)
            return []
        self.collect("first", [task("OXY")], search=empty)
        self.collect("second", [task("BYD")], search=empty)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.usage["search_calls"], 1)
        self.assertEqual(self.parses, [])
        report = json.loads((self.root / "second/subject_search_report.json").read_text())
        self.assertEqual(report["queries"][0]["error"], "search_budget_exhausted")

    def test_zero_search_budget_cannot_trigger_parser(self):
        self.options["max_search_calls"] = 0
        self.assertEqual(self.collect("none", [task("OXY")]), [])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.parses, [])

    def test_elapsed_time_does_not_restart_for_next_event(self):
        clock = [100.0]
        self.options["max_elapsed_seconds"] = 1
        with patch("finmy.runner.subject_search.time.monotonic", side_effect=lambda: clock[0]):
            self.collect("first", [task("OXY")], search=lambda *a: [])
            clock[0] = 102.0
            self.collect("second", [task("BYD")])
        self.assertEqual(self.usage["started_at"], 100.0)
        self.assertEqual(self.usage["search_calls"], 1)
        self.assertEqual(self.parses, [])

    def test_followup_provider_calls_share_global_ledger(self):
        options = {**self.options, "max_followup_queries": 1}
        for name in ("first", "second"):
            collect_subject_sources("Buffett activities", [], SUBJECT, options,
                                    lambda *a: self.calls.append(a) or [], self.parse,
                                    self.root / name, followup_tasks=[task("OXY")],
                                    usage=self.usage, followup_phase="event_followup")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.usage["followup_queries"], 1)
        self.assertEqual(self.usage["search_calls"], 1)
        self.assertEqual(self.calls[0][2], 2)

    def test_duplicate_url_adds_event_route_without_reparse(self):
        search = lambda *a: [row("https://example.com/shared")]
        first = self.collect("first", [task("OXY")], search=search)
        second = self.collect("second", [task("BYD")], search=search, known_documents=first)
        self.assertEqual(second, [])
        self.assertEqual(len(self.parses), 1)
        self.assertEqual(first[0]["event_ids"], ["OXY", "BYD"])
        self.assertEqual(first[0]["event_terms"], ["OXY", "BYD"])
        self.assertEqual(first[0]["event_routes"], [
            {"event_id": "OXY", "event_label": "OXY investment", "event_terms": ["OXY"]},
            {"event_id": "BYD", "event_label": "BYD investment", "event_terms": ["BYD"]}])

    def test_duplicate_body_reuses_single_source_and_both_routes(self):
        first = self.collect("first", [task("OXY")],
                             search=lambda *a: [row("https://example.com/a")],
                             parse=lambda url: {"text": BODY})
        second = self.collect("second", [task("BYD")],
                              search=lambda *a: [row("https://example.com/b")],
                              parse=lambda url: {"text": BODY}, known_documents=first)
        self.assertEqual(second, [])
        self.assertEqual(first[0]["event_ids"], ["OXY", "BYD"])
        self.assertEqual(self.usage["parse_calls"], 2)

    def test_duplicate_url_still_obeys_narrower_publication_window(self):
        first = self.collect("first", [task("OXY")], search=lambda *a: [row("https://example.com/shared")])
        self.collect("second", [task("BYD", start="2022-01-01", end="2022-12-31")],
                     search=lambda *a: [row("https://example.com/shared", "2022-05-01")],
                     known_documents=first)
        self.assertEqual(first[0]["event_ids"], ["OXY"])
        self.assertEqual(len(self.parses), 1)

    def test_duplicate_text_with_different_dates_keeps_valid_source_for_task(self):
        first = self.collect("first", [task("OXY")], search=lambda *a: [row("https://example.com/a")],
                             parse=lambda url: {"text": BODY})
        second = self.collect("second", [task("BYD", start="2022-01-01", end="2022-12-31")],
                              search=lambda *a: [row("https://example.com/b", "2022-05-01")],
                              parse=lambda url: {"text": BODY}, known_documents=first)
        self.assertEqual(first[0]["event_ids"], ["OXY"])
        self.assertEqual(second[0]["url"], "https://example.com/b")
        self.assertEqual(second[0]["event_ids"], ["BYD"])

    def test_failed_fetch_is_charged_and_not_retried_by_another_event(self):
        def broken(url):
            self.parses.append(url)
            raise TimeoutError("fixture")
        for name in ("OXY", "BYD"):
            self.collect(name, [task(name)], search=lambda *a: [row("https://example.com/broken")], parse=broken)
        self.assertEqual(len(self.parses), 1)
        self.assertEqual(self.usage["parse_calls"], 1)

    def test_task_round_robin_precedes_second_event_facet(self):
        self.options.update(providers=["bocha", "baidu"], max_search_calls=8)
        self.collect("fair", [task("OXY", "_one"), task("OXY", "_two"), task("BYD", "_one")],
                     search=lambda *args: self.calls.append(args) or [])
        self.assertEqual([(p, q) for p, q, *_ in self.calls], [
            ("bocha", "OXY_one"), ("bocha", "BYD_one"), ("bocha", "OXY_two"),
            ("baidu", "OXY_one"), ("baidu", "BYD_one"), ("baidu", "OXY_two")])

    def test_parse_shares_use_runnable_search_slots_not_entire_plan(self):
        # Two calls were already spent finding events. Only two of six planned
        # event/provider calls can run; both should receive their four parses.
        self.usage.update(search_calls=2, parse_calls=0)
        options = {**self.options, "providers": ["bocha", "baidu"],
                   "max_search_calls": 4, "max_parse_calls": 8}
        self.collect("limited", [task("OXY"), task("BYD"), task("Japan")], options=options)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.parses), 8)
        self.assertEqual(sum("OXY" in url for url in self.parses), 4)
        self.assertEqual(sum("BYD" in url for url in self.parses), 4)
        self.assertEqual(self.usage["search_calls"], 4)
        report = json.loads((self.root / "limited/subject_search_report.json").read_text())
        self.assertEqual(len(report["queries"]), 6)
        self.assertTrue(all(q.get("error") == "search_budget_exhausted" for q in report["queries"][2:]))

    def test_followup_events_share_remaining_parse_quota(self):
        # First gap must not consume all four remaining parses, even when the
        # provider returns four new usable sources for each event.
        self.usage.update(search_calls=1, parse_calls=2, followup_queries=0)
        options = {**self.options, "max_parse_calls": 6, "max_search_calls": 3,
                   "max_followup_queries": 2, "followup_bocha_count": 4}
        docs = collect_subject_sources(
            "Buffett activities", [], SUBJECT, options, self.search, self.parse,
            self.root / "followup-fair", usage=self.usage,
            followup_tasks=[task("OXY"), task("BYD"), task("Japan")],
            followup_phase="event_followup", auto_followup=False)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(sum("OXY" in url for url in self.parses), 2)
        self.assertEqual(sum("BYD" in url for url in self.parses), 2)
        self.assertEqual({doc["event_ids"][0] for doc in docs}, {"OXY", "BYD"})
        self.assertEqual(self.usage["parse_calls"], 6)
        self.assertEqual(self.usage["search_calls"], 3)
        self.assertEqual(self.usage["followup_queries"], 2)

    def test_event_short_body_repair_keeps_event_routing_and_is_not_recursive(self):
        options = {**self.options, "max_followup_queries": 3}
        calls = []
        def search(*args):
            calls.append(args)
            return [row("https://example.com/thin" if len(calls) == 1 else "https://example.com/full")]
        def parse(url):
            return {"text": "Short event report" if url.endswith("thin") else BODY}
        docs = collect_subject_sources(
            "Buffett activities", [], SUBJECT, options, search, parse,
            self.root / "body-repair", usage=self.usage,
            initial_tasks=[task("OXY")], phase="event_initial", auto_followup=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(docs[0]["event_ids"], ["OXY"])
        self.assertEqual(docs[0]["event_routes"][0]["event_terms"], ["OXY"])
        self.assertEqual(docs[0]["search_phase"], "event_body_followup")
        self.assertEqual(self.usage["followup_queries"], 1)
        self.assertIn("transcript full text", calls[1][1])

    def test_event_failed_fetch_can_trigger_one_bounded_body_search(self):
        options = {**self.options, "max_followup_queries": 1}
        calls = []
        def search(*args):
            calls.append(args)
            return [row("https://example.com/broken" if len(calls) == 1 else "https://example.com/also-thin")]
        def parse(url):
            if url.endswith("broken"):
                raise TimeoutError("fixture")
            return {"text": "Still thin"}
        docs = collect_subject_sources(
            "Buffett activities", [], SUBJECT, options, search, parse,
            self.root / "failed-body", usage=self.usage,
            initial_tasks=[task("OXY")], phase="event_initial", auto_followup=True)
        self.assertEqual(docs, [])
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.usage["followup_queries"], 1)
        report = json.loads((self.root / "failed-body/subject_search_report.json").read_text())
        self.assertEqual(report["queries"][-1]["event_id"], "OXY")
        self.assertEqual(report["queries"][-1]["phase"], "event_body_followup")
        self.assertTrue(any(g["reason"] == "body_fetch_failed" and not g["resolved"] for g in report["gaps"]))

    def test_explicit_provider_and_configured_counts(self):
        options = {**self.options, "providers": ["bocha", "baidu"], "baidu_count": 7}
        self.collect("provider", [task("OXY", provider="baidu")], options=options,
                     search=lambda *args: self.calls.append(args) or [])
        self.assertEqual([(p, n) for p, _, n, *_ in self.calls], [("baidu", 7)])

    def test_invalid_limits_fail_before_network(self):
        for key in ("max_parse_calls", "max_search_calls", "max_followup_queries", "max_links_per_index"):
            for value in (None, float("inf"), True, -1):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_subject_search_options({key: value})
        for key in ("bocha_count", "baidu_count", "followup_bocha_count", "followup_baidu_count"):
            for value in (None, 0, 51, True):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_subject_search_options({key: value})
        for value in (None, 0, float("inf"), float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_subject_search_options({"max_elapsed_seconds": value})

    def test_event_tasks_cannot_expand_global_publication_window(self):
        with self.assertRaises(ValueError):
            self.collect("outside", [task("OXY", start="2021-01-01", end="2023-12-31")])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.parses, [])


if __name__ == "__main__":
    unittest.main()
