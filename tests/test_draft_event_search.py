"""Existing EPG events and optional budgets feed the sole search agent."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.runner.draft_event_search import collect_draft_event_sources, draft_event_options
from finmy.runner.event_followup_config import normalize_followup_config, followup_enabled


SUBJECT = {"name": "Warren Buffett", "subject_id": "buffett",
           "coverage_start": "2022", "coverage_end": "2023"}


class DraftEventSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"event_followup": {"enabled": True}}
        self.collector = self.enterContext(patch(
            "finmy.runner.enhanced_subject_search.collect_enhanced_sources",
            return_value={"documents": [], "reports": [], "status": "insufficient"}))

    def collect(self, events, **kwargs):
        return collect_draft_event_sources({"event": events}, "Buffett activities 2022–2023", [],
            SUBJECT, self.config, self.root, **kwargs)

    def report(self):
        return json.loads((self.root / "draft_event_search_plan.json").read_text())

    def test_label_only_existing_event_reaches_agent_without_discovery_or_date_gate(self):
        self.collect([{"event_id": "oxy", "label": "西方石油投资", "start": "2019-01-01"}])
        events = self.collector.call_args.kwargs["events"]
        self.assertEqual(events[0]["event_label"], "西方石油投资")
        self.assertFalse(events[0]["query_scope_is_evidence"])
        self.assertNotIn("publication_window", self.report())
        self.assertEqual(self.report()["event_discovery_model_calls"], 0)
        self.assertEqual(self.report()["backend"], "agent")

    def test_omitted_followup_never_starts_agent(self):
        self.config.pop("event_followup")
        self.assertEqual(self.collect([{"label": "Occidental investment"}]), [])
        self.collector.assert_not_called()
        self.assertEqual(self.report()["status"], "disabled")

    def test_no_events_keeps_initial_available(self):
        self.assertEqual(self.collect([]), [])
        self.collector.assert_not_called()
        self.assertEqual(self.report()["status"], "no_draft_events")

    def test_all_events_reach_agent_and_duplicate_ids_are_reported(self):
        events = [{"event_id": str(i), "label": "Investment " + str(i)} for i in range(9)]
        events += [{"event_id": "0", "label": "Duplicate"}, {"title": "Missing ID"}]
        self.collect(events)
        self.assertEqual(len(self.collector.call_args.kwargs["events"]), 10)
        self.assertEqual(self.report()["skipped_events"][0]["reason"], "duplicate_event_id")
        self.assertEqual(self.report()["events"][-1]["event_label"], "Missing ID")

    def test_acquisition_failure_is_nonfatal_and_does_not_expose_credentials(self):
        self.collector.side_effect = RuntimeError("secret must not be logged")
        self.assertEqual(self.collect([{"label": "Event A"}]), [])
        self.assertEqual(self.report()["error"], "RuntimeError")
        self.assertNotIn("secret", (self.root / "draft_event_search_plan.json").read_text())

    def test_invalid_budget_records_failure_before_acquisition(self):
        self.config["event_followup"]["max_search_calls"] = None
        self.assertEqual(self.collect([{"label": "Event A"}]), [])
        self.collector.assert_not_called()
        self.assertEqual(self.report()["error"], "ValueError")

    def test_original_sources_use_canonical_comparison_without_rewriting_archives(self):
        known = {"url": "https://EXAMPLE.org/investment#old", "raw_text": "Original text"}
        doc = {"url": "https://example.org/investment", "raw_text": "Original text", "event_ids": ["a"]}
        self.collector.return_value.update(documents=[doc], status="finished")
        original = copy.deepcopy([known, doc])
        self.assertEqual(self.collect([{"event_id": "a", "label": "Event A"}],
            known_documents=[known, {"url": None}, {"url": "archive.txt"}]), [])
        self.assertEqual([known, doc], original)
        self.assertEqual(self.report()["new_documents"], 0)

    def test_local_source_without_public_url_does_not_discard_other_material(self):
        sources = [{"url": url, "raw_text": "Supplied source", "event_ids": ["a"]}
                   for url in ("file:///saved/report.txt", None, "http://[", {"unexpected": "url"})]
        sources.append({"url": "https://example.org/report", "raw_text": "Public source", "event_ids": ["a"]})
        self.collector.return_value.update(documents=sources, status="finished")
        self.assertEqual(self.collect([{"event_id": "a", "label": "Event A"}]), sources)

    def test_event_metadata_keeps_entities_actions_and_dates_for_agent(self):
        package = {"graph": {"subject_entity_id": "p"},
                   "event": [{"event_id": "e", "label": "Partner holdings",
                              "summary": "In April Lin met Northstar executives after the acquisition."}],
                   "entity": [{"entity_id": "p", "name": "Lin"}, {"entity_id": "n", "name": "Northstar"}],
                   "event_activity": [{"event_id": "e", "activity_id": "a"}],
                   "activity": [{"activity_id": "a", "action_id": "act"}],
                   "action": [{"action_id": "act", "actor_id": "p", "action_type": "met Northstar executives",
                               "timestamp_time_id": "t", "occurrence_id": "o"}],
                   "occurrence_participant": [{"occurrence_id": "o", "entity_id": "n"}],
                   "time_value": [{"time_id": "t", "value": "2023-04-11"}]}
        collect_draft_event_sources(package, "Lin 2023", [], {**SUBJECT, "name": "Lin"}, self.config, self.root)
        event = self.collector.call_args.kwargs["events"][0]
        self.assertIn("Northstar", event["event_terms"])
        self.assertEqual(event["activity_clues"], ["met Northstar executives"])
        self.assertEqual(event["year_clues"], ["2023"])
        self.assertEqual(event["activity_count"], 1)

    def test_initial_and_supplementary_budgets_remain_independent(self):
        config = {"reconstruction": {"mode": "person", "subject": SUBJECT},
                  "search_config": {"enhancement": {"max_search_requests": 7, "max_read_sources": 19}},
                  "event_followup": {"enabled": True, "max_search_calls": 11, "max_parse_calls": 29}}
        normalized = normalize_followup_config(config)
        self.assertEqual(normalized["search_config"], config["search_config"])
        self.assertEqual(normalized["event_followup"]["max_search_calls"], 11)
        self.assertEqual(normalized["event_followup"]["max_parse_calls"], 29)
        self.assertEqual(normalized["all_content_config"]["max_content_length"], 120000)
        self.assertNotIn("all_content_config", config)

    def test_obsolete_collector_options_cannot_disable_or_limit_agent_supplement(self):
        config = {"reconstruction": {"mode": "person", "subject": SUBJECT},
                  "subject_search": {"enabled": False, "providers": ["obsolete"], "max_search_calls": 0},
                  "event_followup": {"enabled": True, "queries_per_event": 999,
                                     "max_followup_queries": 0, "max_relevance_model_calls": 0}}
        self.assertTrue(followup_enabled(config))
        options = draft_event_options(normalize_followup_config(config))
        self.assertEqual(options["max_search_calls"], 12)
        for removed in ("queries_per_event", "max_followup_queries", "max_relevance_model_calls"):
            self.assertNotIn(removed, options)

    def test_independent_content_and_model_budgets_reject_unbounded_values(self):
        for key in ("max_content_length", "max_document_chars", "max_model_calls"):
            for invalid in (None, True, -1, float("inf")):
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    draft_event_options({"event_followup": {key: invalid}})
        for invalid in (None, True, 0, -1, float("inf"), float("nan")):
            with self.subTest(seconds=invalid), self.assertRaises(ValueError):
                draft_event_options({"event_followup": {"max_elapsed_seconds": invalid}})

    def test_post_build_followup_requires_explicit_opt_in(self):
        base = {"reconstruction": {"mode": "person", "subject": SUBJECT}}
        for settings in (None, {}, {"max_model_calls": 24}, {"enabled": False}):
            config = {**base, "event_followup": settings}
            self.assertFalse(followup_enabled(config))
            self.assertFalse(draft_event_options(config)["enabled"])
            self.assertEqual(normalize_followup_config(config), config)
        self.assertTrue(followup_enabled({**base, "event_followup": {"enabled": True}}))

    def test_repair_budget_survives_normalization(self):
        for rounds in (0, 1, 3):
            config = {"reconstruction": {"mode": "person", "subject": SUBJECT},
                      "event_followup": {"enabled": True, "max_repair_rounds_per_event": rounds}}
            self.assertEqual(normalize_followup_config(config)["event_followup"]["max_repair_rounds_per_event"], rounds)
        for invalid in (None, True, -1, 4, 1.0, "1"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "max_repair_rounds_per_event"):
                draft_event_options({"event_followup": {"max_repair_rounds_per_event": invalid}})


if __name__ == "__main__":
    unittest.main()
