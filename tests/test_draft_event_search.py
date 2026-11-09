"""Post-build searches consume the existing event table without another planner."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.draft_event_search import collect_draft_event_sources, draft_event_options
from finmy.runner.event_followup_config import initial_search_options, normalize_followup_config, followup_enabled


SUBJECT = {"name": "Warren Buffett", "coverage_start": "2022", "coverage_end": "2023"}
BODY = "Buffett said the investment was executed after reviewing company materials. " * 20


class DraftEventSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"subject_search": {"providers": ["bocha"], "max_followup_queries": 0},
                       "event_followup": {"enabled": True, "queries_per_event": 1}}
        self.calls, self.parses = [], []
        self.usage = {}

    def search(self, provider, query, count, start, end):
        self.calls.append((provider, query, count, start, end))
        return [{"url": f"https://example.com/{len(self.calls)}", "title": "Primary evidence",
                 "published_at": "2023-05-06"}]

    def parse(self, url):
        self.parses.append(url)
        return {"text": BODY + url, "links": []}

    def collect(self, events, **kwargs):
        return collect_draft_event_sources({"event": events}, "Buffett activities 2022–2023", [],
            SUBJECT, self.config, self.root, usage=self.usage,
            search=kwargs.pop("search", self.search), parse=kwargs.pop("parse", self.parse), **kwargs)

    def report(self):
        return json.loads((self.root / "draft_event_search_plan.json").read_text())

    def test_label_only_existing_event_searches_without_model_or_quote_gate(self):
        docs = self.collect([{"event_id": "oxy", "label": "西方石油投资", "summary": ""}])
        self.assertEqual(len(docs), 1)
        self.assertIn("西方石油投资", self.calls[0][1])
        self.assertEqual(docs[0]["event_ids"], ["oxy"])
        self.assertEqual(self.report()["event_discovery_model_calls"], 0)
        self.assertEqual(self.report()["events"][0]["source"], "initial_person_epg")

    def test_omitted_followup_does_not_search_or_parse(self):
        self.config.pop("event_followup")
        docs = self.collect([{"event_id": "oxy", "label": "西方石油投资"}])
        self.assertEqual(docs, [])
        self.assertFalse(self.calls)
        self.assertFalse(self.parses)
        self.assertEqual(self.report()["status"], "disabled")

    def test_no_events_returns_without_search_and_keeps_original_available(self):
        docs = self.collect([])
        self.assertEqual(docs, [])
        self.assertFalse(self.calls)
        self.assertEqual(self.report()["status"], "no_draft_events")

    def test_no_arbitrary_event_count_gate_and_unsearched_events_are_reported(self):
        self.config["event_followup"]["max_search_calls"] = 3
        events = [{"event_id": str(i), "label": "Investment " + str(i)} for i in range(9)]
        self.collect(events)
        report = self.report()
        self.assertEqual(len(report["events"]), 9)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual([e["event_id"] for e in report["events"] if e["search_calls"]], ["0", "1", "2"])
        self.assertEqual(sum(e["status"] == "not_searched_budget" for e in report["events"]), 6)

    def test_every_event_gets_base_query_before_deeper_query(self):
        self.config["event_followup"].update(queries_per_event=2, max_search_calls=3)
        self.collect([{"event_id": "a", "label": "Energy investment"},
                      {"event_id": "b", "label": "Insurance acquisition"}])
        queries = [row[1] for row in self.calls]
        self.assertIn("Energy investment", queries[0])
        self.assertIn("Insurance acquisition", queries[1])
        self.assertIn("Energy investment", queries[2])
        self.assertIn("full text", queries[2])
        self.assertNotIn("具体行动", " ".join(queries))

    def test_supplementary_search_and_parse_caps_are_cumulative_within_phase(self):
        self.usage.update(started_at=time.monotonic(), search_calls=10, parse_calls=38, followup_queries=0)
        self.config["event_followup"].update(max_search_calls=12, max_parse_calls=40)
        def many(*args):
            rows = self.search(*args)
            return [dict(rows[0], url=f"https://example.com/{len(self.calls)}/{i}") for i in range(10)]
        self.collect([{"event_id": "a", "label": "Event A"}, {"event_id": "b", "label": "Event B"}],
                     search=many)
        self.assertEqual(self.usage["search_calls"], 12)
        self.assertEqual(self.usage["parse_calls"], 40)
        self.assertEqual(len(self.parses), 2)
        self.assertTrue(any("/1/" in url for url in self.parses))
        self.assertTrue(any("/2/" in url for url in self.parses))

    def test_event_dates_do_not_narrow_reporting_window(self):
        self.collect([{"event_id": "oxy", "label": "OXY investment", "start": "2019-01-01",
                       "end": "2019-01-02", "timestamp": "2022-03-01"}])
        self.assertEqual(self.calls[0][3:], ("2022-01-01", "2023-12-31"))

    def test_same_source_reused_for_events_without_duplicate_fetch(self):
        self.collect([{"event_id": "a", "label": "Event A"}, {"event_id": "b", "label": "Event B"}],
            search=lambda *args: [{"url": "https://example.com/shared", "title": "Original material",
                                  "published_at": "2023-05-06"}])
        self.assertEqual(len(self.parses), 1)
        docs = json.loads((self.root / "draft_event_search_sources.json").read_text())
        self.assertEqual(docs[0]["event_ids"], ["a", "b"])
        self.assertEqual(self.report()["events"][1]["status"], "sources_reused")

    def test_original_sources_gain_event_association_without_fetch(self):
        known = {"url": "https://example.com/known", "raw_text": BODY, "published_at": "2023-05-06"}
        docs = self.collect([{"event_id": "a", "label": "Event A"}], known_documents=[known],
            search=lambda *args: [{"url": known["url"], "title": "Known evidence",
                                  "published_at": "2023-05-06"}])
        self.assertEqual(docs, [])
        self.assertEqual(known["event_ids"], ["a"])
        self.assertFalse(self.parses)

    def test_duplicate_id_ignored_but_thin_title_and_missing_id_are_accepted(self):
        self.collect([{"event_id": "a", "label": "Investment A"},
                      {"event_id": "a", "label": "Duplicate"}, {"title": "Investment B"}])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.report()["skipped_events"][0]["reason"], "duplicate_event_id")
        self.assertEqual(self.report()["events"][1]["event_label"], "Investment B")

    def test_search_failure_is_nonfatal_and_audited(self):
        def fail(*args):
            raise RuntimeError("secret must not be logged")
        docs = self.collect([{"event_id": "a", "label": "Event A"}], search=fail)
        self.assertEqual(docs, [])
        self.assertEqual(self.report()["events"][0]["status"], "search_failed")
        self.assertNotIn("secret", (self.root / "draft_event_search_plan.json").read_text())

    def test_invalid_optional_budget_records_failure_without_network(self):
        self.config["event_followup"]["max_search_calls"] = None
        self.assertEqual(self.collect([{"label": "Event A"}]), [])
        self.assertFalse(self.calls)
        self.assertEqual(self.report()["error"], "ValueError")

    def test_expired_supplementary_clock_does_not_start_new_search(self):
        self.usage["started_at"] = time.monotonic() - 301
        self.assertEqual(self.collect([{"label": "Event A"}]), [])
        self.assertFalse(self.calls)
        self.assertEqual(self.report()["status"], "budget_exhausted")

    def test_thin_source_can_use_bounded_full_text_repair(self):
        self.config["subject_search"]["max_followup_queries"] = 1
        self.config["event_followup"].update(max_search_calls=4, max_parse_calls=4)
        def body(url):
            return {"text": "index" if url.endswith("1") else BODY, "links": []}
        docs = self.collect([{"event_id": "oxy", "label": "OXY investment"}], parse=body)
        self.assertTrue(docs)
        self.assertLessEqual(self.usage["search_calls"], 4)
        self.assertLessEqual(self.usage["parse_calls"], 4)
        self.assertEqual(docs[0]["event_ids"], ["oxy"])
        self.assertIn("full text", self.calls[-1][1])

    def test_search_config_result_counts_are_honored(self):
        self.config["search_config"] = {"bocha_count": 7}
        self.collect([{"label": "Event A"}])
        self.assertEqual(self.calls[0][2], 7)
        self.config["subject_search"]["bocha_count"] = 5
        self.assertEqual(draft_event_options(self.config)[1]["bocha_count"], 5)

    def test_initial_caps_are_unchanged_and_supplementary_caps_are_separate(self):
        config = {"reconstruction": {"mode": "person", "subject": {**SUBJECT, "subject_id": "buffett"}},
                  "subject_search": {"max_search_calls": 7, "max_parse_calls": 19,
                                     "max_elapsed_seconds": 91},
                  "event_followup": {"enabled": True, "max_search_calls": 11, "max_parse_calls": 29,
                                     "max_elapsed_seconds": 123}}
        normalized = normalize_followup_config(config)
        first = initial_search_options(normalized)
        second, search_options = draft_event_options(normalized)
        self.assertEqual((first["max_search_calls"], first["max_parse_calls"], first["max_elapsed_seconds"]),
                         (7, 19, 91))
        self.assertEqual((search_options["max_search_calls"], search_options["max_parse_calls"],
                          search_options["max_elapsed_seconds"]), (11, 29, 123))
        self.assertEqual(normalized["all_content_config"]["max_content_length"], 120000)
        self.assertEqual(second["max_content_length"], 120000)
        self.assertNotIn("all_content_config", config)

    def test_separate_default_supplement_is_not_capped_by_initial_limits(self):
        self.config["subject_search"].update(max_search_calls=0, max_parse_calls=0,
                                             max_elapsed_seconds=1)
        docs = self.collect([{"event_id": "a", "label": "Event A"}])
        self.assertEqual(len(docs), 1)
        self.assertEqual(self.report()["budget_scope"], "supplementary_phase")
        self.assertEqual(self.report()["limits"]["subject_search"]["max_search_calls"], 12)

    def test_providers_rotate_without_starving_later_events(self):
        self.config["subject_search"]["providers"] = ["bocha", "baidu"]
        self.config["event_followup"].update(max_search_calls=4, queries_per_event=2)
        self.collect([{"event_id": str(i), "label": "Event " + str(i)} for i in range(3)])
        self.assertEqual([c[0] for c in self.calls], ["bocha", "baidu", "bocha", "baidu"])
        self.assertEqual([t["event_id"] for t in self.report()["scheduled_tasks"]], ["0", "1", "2", "0"])

    def test_queries_use_existing_entities_actions_and_times_without_fixed_topics(self):
        self.config["event_followup"]["queries_per_event"] = 2
        package = {"graph": {"subject_entity_id": "p"},
                   "event": [{"event_id": "e", "label": "Building and visiting partner holdings",
                              "summary": "In April Lin met Northstar executives after the acquisition."}],
                   "entity": [{"entity_id": "p", "name": "Lin"},
                              {"entity_id": "n", "name": "Northstar"}],
                   "event_activity": [{"event_id": "e", "activity_id": "a"}],
                   "activity": [{"activity_id": "a", "action_id": "act"}],
                   "action": [{"action_id": "act", "actor_id": "p", "action_type": "met Northstar executives",
                               "timestamp_time_id": "t", "occurrence_id": "o"}],
                   "occurrence_participant": [{"occurrence_id": "o", "entity_id": "n"}],
                   "time_value": [{"time_id": "t", "value": "2023-04-11"}]}
        collect_draft_event_sources(package, "Lin 2023", [], {**SUBJECT, "name": "Lin"},
            self.config, self.root, usage=self.usage, search=self.search, parse=self.parse)
        self.assertIn("Northstar", self.calls[0][1])
        self.assertNotIn("April", self.calls[0][1])
        self.assertIn("2023", self.calls[0][1])
        self.assertNotIn("Building and visiting", self.calls[0][1])
        self.assertIn("met Northstar executives", self.calls[1][1])
        self.assertIn("Northstar", self.report()["events"][0]["event_terms"])
        self.assertEqual(self.report()["events"][0]["activity_count"], 1)

    def test_independent_content_and_model_budgets_reject_unbounded_values(self):
        for key in ("max_content_length", "max_document_chars", "max_model_calls"):
            for invalid in (None, True, -1, float("inf")):
                with self.subTest(key=key, value=invalid):
                    with self.assertRaises(ValueError):
                        draft_event_options({"event_followup": {key: invalid}})
        for invalid in (None, True, 0, -1, float("inf"), float("nan")):
            with self.subTest(seconds=invalid):
                with self.assertRaises(ValueError):
                    draft_event_options({"event_followup": {"max_elapsed_seconds": invalid}})

    def test_post_build_followup_requires_explicit_opt_in(self):
        base = {"reconstruction": {"mode": "person", "subject": {**SUBJECT, "subject_id": "buffett"}}}
        for settings in (None, {}, {"max_model_calls": 24}, {"enabled": False}):
            with self.subTest(settings=settings):
                config = {**base, "event_followup": settings}
                self.assertFalse(followup_enabled(config))
                self.assertFalse(draft_event_options(config)[0]["enabled"])
                self.assertEqual(normalize_followup_config(config), config)
        enabled = {**base, "event_followup": {"enabled": True}}
        self.assertTrue(followup_enabled(enabled))
        self.assertTrue(normalize_followup_config(enabled)["event_followup"]["enabled"])

    def test_repair_round_defaults_and_overrides_survive_normalization(self):
        base = {"reconstruction": {"mode": "person", "subject": {**SUBJECT, "subject_id": "buffett"}}}
        for configured in (None, 0, 1, 3):
            with self.subTest(configured=configured):
                config = {**base, "event_followup": {"enabled": True} if configured is None else
                          {"enabled": True, "max_repair_rounds_per_event": configured}}
                normalized = normalize_followup_config(config)
                options, _ = draft_event_options(normalized)
                self.assertEqual(options["max_repair_rounds_per_event"], 1 if configured is None else configured)
                self.assertEqual(options["max_model_calls"], 24)
                self.assertEqual(options["max_content_length"], 120000)
                self.assertEqual(normalized["all_content_config"]["max_content_length"], 120000)
                self.assertEqual(config["event_followup"], {"enabled": True} if configured is None else
                                 {"enabled": True, "max_repair_rounds_per_event": configured})

    def test_repair_round_cap_rejects_unbounded_or_mistyped_values(self):
        for value in (None, True, False, -1, 4, 1.0, "1", float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_repair_rounds_per_event"):
                    draft_event_options({"event_followup": {"max_repair_rounds_per_event": value}})


if __name__ == "__main__":
    unittest.main()
