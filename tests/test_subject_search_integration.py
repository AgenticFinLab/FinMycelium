"""Bounded retrieval contracts using fake search and parser adapters only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.subject_search import collect_subject_sources


SUBJECT = {"name": "Warren Buffett", "coverage_start": None, "coverage_end": None}
BODY = ("Warren Buffett said that Berkshire invests for long-term returns. "
        "Question: How do you assess risk? Answer: We keep cash to meet obligations. " * 12)


def result(url, date="2023-05-06", title="Warren Buffett annual meeting transcript"):
    return {"url": url, "title": title, "published_at": date, "snippet": "Annual meeting"}


class SubjectSearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.options = {"providers": ["bocha"], "max_queries": 16,
                        "topics": ["meeting"], "max_followup_queries": 0,
                        "max_parse_calls": 40, "max_links_per_index": 2,
                        "results_per_query": 4, "min_body_chars": 600}

    def run_search(self, search, parse, query="Warren Buffett annual meeting during 2023"):
        return collect_subject_sources(query, [], SUBJECT, self.options,
                                       search, parse, self.directory)

    def report(self):
        return json.loads((self.directory / "subject_search_report.json").read_text())

    def test_full_range_requests_10_and_20_even_with_old_four_result_setting(self):
        self.options.update({"providers": ["bocha", "baidu"],
                             "results_per_query": 4, "max_followup_queries": 3})
        calls, parsed, messages = [], [], []
        query = "Buffett activities 2022–2023"

        def search(provider, text, count, start, end):
            calls.append((provider, count, start, end, text))
            # Also verify that extra results from a provider respect its count.
            return [result(f"https://www.example.com/{provider}/{i}",
                           title="Buffett documented activity") for i in range(count + 2)]

        def parse(url):
            parsed.append(url)
            return {"text": BODY + url, "links": []}

        docs = collect_subject_sources(query, ["Berkshire"], SUBJECT, self.options,
                                       search, parse, self.directory, messages.append)
        self.assertEqual([(p, n, start, end) for p, n, start, end, _ in calls],
                         [("bocha", 10, "2022-01-01", "2023-12-31"),
                          ("baidu", 20, "2022-01-01", "2023-12-31")])
        self.assertEqual(len(parsed), 30)
        self.assertEqual(len(docs), 30)
        self.assertEqual(len(set(parsed)), 30)
        self.assertTrue(all(query in text and "Berkshire" in text for *_, text in calls))
        self.assertEqual([m for m in messages if m.startswith("Start:")],
                         ["Start: Bocha Search", "Start: Baidu Search"])
        self.assertIn("Bocha Search: Get 12 search results.", messages)
        self.assertIn("Baidu Search: Get 22 search results.", messages)
        self.assertEqual(sum(": Parsing " in m for m in messages), 30)
        for provider, _, start, end, text in calls:
            self.assertIn(f"{provider.title()} Search: Query: {text}", messages)
            self.assertIn(f"{provider.title()} Search: Publication date range: {start} to {end}.", messages)
        self.assertIn("Detail follow-up: No additional search needed.", messages)
        self.assertEqual(self.report()["summary"]["followup_queries"], 0)

    def test_date_gate_precedes_fetch_and_unknown_dates_do_not_pass(self):
        rows = [result("https://www.example.com/current", "2026-01-01"),
                result("https://www.example.com/undated", None),
                result("https://www.example.com/meeting")]
        parsed = []

        def parse(url):
            parsed.append(url)
            return {"text": BODY, "links": []}

        docs = self.run_search(lambda *a: rows, parse)
        self.assertEqual(parsed, ["https://www.example.com/meeting"])
        self.assertEqual([d["url"] for d in docs], parsed)
        self.assertEqual(docs[0]["published_at"], "2023-05-06")
        report = self.report()
        self.assertEqual(len(report["candidates"]), 3)
        self.assertTrue(all(q["start"] == "2023-01-01" and q["end"] == "2023-12-31"
                            for q in report["queries"]))

    def test_index_child_requires_its_own_date_and_real_body(self):
        index = "https://www.example.com/index"
        undated = "https://www.example.com/transcript-undated"
        dated = "https://www.example.com/transcript-2023"
        parsed = []

        def parse(url):
            parsed.append(url)
            if url == index:
                return {"text": "Annual meeting video index. Watch video. Transcript links.",
                        "links": [{"url": undated, "text": "2023 Warren Buffett full transcript"},
                                  {"url": dated, "text": "2023 Warren Buffett full transcript"}]}
            return {"text": BODY, "links": [],
                    "published_at": "2023-05-06" if url == dated else None}

        docs = self.run_search(lambda *a: [result(index, title="Annual meeting video index")], parse)
        self.assertIn(dated, parsed)
        self.assertEqual([d["url"] for d in docs], [dated])
        self.assertNotIn(index, [d["url"] for d in docs])
        self.assertNotIn(undated, [d["url"] for d in docs])

    def test_substantial_meeting_speech_does_not_trigger_followup(self):
        self.options["max_followup_queries"] = 3
        queries = []

        def search(provider, query, count, start, end):
            queries.append(query)
            return [result("https://www.example.com/meeting")]

        docs = self.run_search(search, lambda url: {"text": BODY, "links": []})
        self.assertEqual(len(docs), 1)
        self.assertEqual(len(queries), 1)
        self.assertEqual(self.report()["summary"]["followup_queries"], 0)

    def test_missing_meeting_details_trigger_bounded_scoped_followup(self):
        self.options["max_followup_queries"] = 1
        calls = []

        def search(provider, query, count, start, end):
            calls.append(query)
            return [result("https://www.example.com/index" if len(calls) == 1
                           else "https://www.example.com/transcript")]

        def parse(url):
            return {"text": "Watch annual meeting video. Video duration 7 hours." if url.endswith("index") else BODY,
                    "links": []}

        docs = self.run_search(search, parse)
        self.assertEqual(len(calls), 2)
        self.assertEqual([d["url"] for d in docs], ["https://www.example.com/transcript"])
        report = self.report()
        self.assertEqual(report["summary"]["followup_queries"], 1)
        self.assertTrue(all(q["start"] == "2023-01-01" and q["end"] == "2023-12-31"
                            for q in report["queries"]))

    def test_followup_logs_actual_request_reason_and_completion(self):
        self.options.update(providers=["bocha", "baidu"], max_followup_queries=2)
        messages, calls = [], []

        def search(provider, query, count, start, end):
            calls.append((provider, query, count, start, end))
            return [result("https://www.example.com/index")]

        collect_subject_sources("Buffett activities 2022–2023", [], SUBJECT, self.options,
                                search, lambda url: {"text": "Watch video", "links": []},
                                self.directory, messages.append)
        self.assertEqual([call[2] for call in calls], [10, 20, 10, 20])
        for provider, query, _, start, end in calls[2:]:
            label = provider.title() + " Search"
            self.assertIn(f"Start: {label} (detail follow-up)", messages)
            self.assertIn(f"{label}: Reason: Retrieved body is too short.", messages)
            self.assertIn(f"{label}: Query: {query}", messages)
            self.assertIn(f"{label}: Publication date range: {start} to {end}.", messages)
        self.assertIn("Detail follow-up: Stopped with 1 unresolved source gap(s); "
                      "follow-up round or configured limit reached.", messages)
        self.assertNotIn("Detail follow-up: No additional search needed.", messages)

    def test_search_failure_is_visible_and_not_reported_as_no_gap(self):
        messages = []
        def search(*args):
            raise TimeoutError("fixture")
        collect_subject_sources("Buffett 2023", [], SUBJECT, self.options, search,
                                lambda url: None, self.directory, messages.append)
        self.assertIn("Bocha Search: Search failed (TimeoutError).", messages)
        self.assertIn("Detail follow-up: Search incomplete; see search errors above.", messages)
        self.assertNotIn("Detail follow-up: No additional search needed.", messages)

    def test_parse_budget_and_cross_query_dedup_are_global(self):
        self.options.update({"max_parse_calls": 1, "topics": ["meeting", "interview"],
                             "max_followup_queries": 0})
        parsed = []

        def parse(url):
            parsed.append(url)
            return {"text": BODY, "links": []}

        docs = self.run_search(lambda *a: [result("https://www.example.com/a"),
                                           result("https://www.example.com/b")], parse)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(docs), 1)
        self.assertEqual(self.report()["summary"]["parse_calls"], 1)

    def test_page_publication_overrides_stale_in_scope_search_metadata(self):
        docs = self.run_search(
            lambda *a: [result("https://www.example.com/updated-page")],
            lambda url: {"text": BODY, "links": [], "published_at": "2026-11-01"})
        self.assertEqual(docs, [])
        self.assertEqual(self.report()["candidates"][0]["published_at"], "2026-11-01")
        self.assertEqual(self.report()["candidates"][0]["status"], "rejected")

    def test_parse_failure_does_not_abort_remaining_sources(self):
        broken = "https://www.example.com/broken"
        usable = "https://www.example.com/usable"

        def parse(url):
            if url == broken:
                raise TimeoutError("fixture timeout")
            return {"text": BODY, "links": []}

        docs = self.run_search(lambda *a: [result(broken), result(usable)], parse)
        self.assertEqual([d["url"] for d in docs], [usable])
        report = self.report()
        self.assertEqual(report["summary"]["parse_calls"], 2)
        self.assertIn("parse_error", report["candidates"][0]["reason"])

    def test_one_full_range_per_provider_with_fair_parse_budget(self):
        self.options.update({"max_parse_calls": 4, "results_per_query": 4,
                             "providers": ["bocha", "baidu"]})
        parsed = []

        def search(provider, query, count, start, end):
            return [result(f"https://www.example.com/{provider}/{i}", start)
                    for i in range(4)]

        def parse(url):
            parsed.append(url)
            return {"text": BODY + url, "links": []}

        docs = self.run_search(search, parse, "Warren Buffett annual meetings during 2022–2023")
        self.assertEqual(len(parsed), 4)
        self.assertEqual(sum("/bocha/" in u for u in parsed), 2)
        self.assertEqual(sum("/baidu/" in u for u in parsed), 2)
        self.assertEqual(len(docs), 4)
        queries = self.report()["queries"]
        self.assertEqual(len(queries), 2)
        self.assertTrue(all((q["start"], q["end"]) == ("2022-01-01", "2023-12-31") for q in queries))

    def test_index_body_can_use_reserved_detail_fetch(self):
        self.options.update({"max_parse_calls": 8, "max_followup_queries": 1,
                             "topics": ["meeting", "interview"]})
        def search(provider, query, count, start, end):
            return [result(f"https://www.example.com/index/{start[:4]}", start)]
        def parse(url):
            if "/index/" in url:
                return {"text": "Video index", "links": [
                    {"url": url.replace("/index/", "/transcript/"), "text": "full transcript"}]}
            return {"text": BODY + url, "links": [], "published_at": url[-4:] + "-05-06"}
        docs = self.run_search(search, parse, "Warren Buffett 2022–2023 meetings and interviews")
        self.assertEqual(len(docs), 1)
        self.assertEqual(self.report()["summary"]["followup_queries"], 0)
        self.assertTrue(all("/transcript/" in d["url"] for d in docs))
        self.assertLessEqual(self.report()["summary"]["parse_calls"], 8)

    def test_unrelated_good_source_does_not_resolve_missing_meeting(self):
        self.options["max_followup_queries"] = 1
        calls = []
        def search(provider, query, count, start, end):
            calls.append(query)
            if len(calls) == 1:
                return [result("https://www.example.com/index"),
                        result("https://www.example.com/donation", title="Buffett donation")]
            return [result("https://www.example.com/transcript")]
        def parse(url):
            return {"text": "Video duration 7 hours" if url.endswith("index") else BODY + url,
                    "links": []}
        docs = self.run_search(search, parse, "Buffett activities 2022–2023")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(docs), 2)
        self.assertTrue(self.report()["gaps"][0]["resolved"])
        self.assertNotIn("transcript", calls[0])
        self.assertIn("transcript", calls[1])

    def test_elapsed_budget_stops_new_fetches_and_queries(self):
        self.options.update({"max_elapsed_seconds": 1, "providers": ["bocha", "baidu"]})
        clock = [0.0]
        searches, parsed = [], []

        def search(provider, query, count, start, end):
            searches.append(query)
            return [result("https://www.example.com/a"), result("https://www.example.com/b")]

        def parse(url):
            parsed.append(url)
            clock[0] = 2.0
            return {"text": BODY, "links": []}

        with patch("finmy.runner.subject_search.time.monotonic", side_effect=lambda: clock[0]):
            self.run_search(search, parse)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(searches), 1)
        self.assertEqual(self.report()["queries"][-1]["error"], "elapsed_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
