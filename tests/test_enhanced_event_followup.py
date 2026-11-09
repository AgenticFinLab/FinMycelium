"""Existing EPG events use real shared-search state under one phase budget."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finmy.runner.draft_event_search import collect_draft_event_sources
from finmy.search.pipeline import run_search


class EnhancedEventFollowupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.subject = {"subject_id": "person_example", "name": "Example Person"}
        self.config = {
            "builder_config": {"reconstruction": {"mode": "person", "subject": self.subject}},
            "search_config": {"mode": "agent", "enhancement": {"providers": ["bocha", "baidu"]}},
            # These old collector settings must not block the shared algorithm.
            "subject_search": {"providers": ["legacy-does-not-support-exa"], "max_search_calls": 999},
            "event_followup": {"enabled": True, "max_search_calls": 6, "max_parse_calls": 3,
                               "max_search_model_calls": 9, "max_content_length": 60000},
        }
        self.tasks, self.requests, self.models = [], [], []
        self.text = "An original source describes a documented investment and its rationale."
        self.package = {"event": [{"event_id": "E1", "label": "Occidental investment"}]}
        self.usage = {}

    def model(self, context):
        self.models.append(copy.deepcopy(context))
        if not context["sources"]:
            return {"action": "search", "query": context["task"]["target_name"]}
        unread = next((source for source in context["sources"] if not source["reviewed"]), None)
        if unread:
            return {"action": "read_source", "source": unread["source_id"]}
        return {"action": "finish", "source_ids": [source["source_id"] for source in context["sources"]],
                "gaps": [], "reason": "supported"}

    def transport(self, provider, payload, config):
        self.requests.append((provider, copy.deepcopy(payload)))
        source = {"url": "https://example.org/investment", "title": "Original filing", "name": "Original filing"}
        return ({"data": {"webPages": {"value": [source]}}} if provider == "bocha" else
                {"references": [source]})

    def search_runner(self, task, **kwargs):
        self.tasks.append(copy.deepcopy(task))
        kwargs.update(model=self.model, transport=self.transport,
                      fetcher=lambda url: (self.text.encode(), "txt", "utf-8"))
        return run_search(task, **kwargs)

    def collect(self, **kwargs):
        with patch("finmy.search.pipeline.run_search", self.search_runner), \
             patch("finmy.runner.draft_event_search.search_window", side_effect=AssertionError("date gate")), \
             patch("finmy.runner.draft_event_search.collect_subject_sources", side_effect=AssertionError("legacy collector")):
            return collect_draft_event_sources(self.package, "Reconstruct this person's investments", [],
                self.subject, self.config, self.root, usage=self.usage, **kwargs)

    def report(self):
        return json.loads((self.root / "draft_event_search_plan.json").read_text())

    def test_singleton_thin_event_has_no_date_or_discovery_gate(self):
        before = copy.deepcopy(self.config)
        documents = self.collect()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["event_ids"], ["E1"])
        self.assertEqual(documents[0]["raw_text"], self.text)
        self.assertEqual(self.tasks[0]["target_type"], "event")
        self.assertEqual(self.tasks[0]["target_name"], "Occidental investment")
        self.assertFalse(self.tasks[0]["event_clues_are_evidence"])
        self.assertNotIn("freshness", self.requests[0][1])
        report = self.report()
        self.assertEqual(report["backend"], "agent")
        self.assertEqual(report["status"], "finished")
        self.assertEqual(report["event_discovery_model_calls"], 0)
        self.assertEqual(report["events"][0]["accepted_documents"], 1)
        self.assertEqual(report["events"][0]["search_calls"], 2)
        self.assertEqual(self.config, before)

    def test_multiple_events_share_actual_provider_budget_and_deduplicate(self):
        self.package["event"] += [{"event_id": "E2", "label": "Apple investment"},
                                  {"event_id": "E3", "label": "Railroad acquisition"}]
        documents = self.collect()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["event_ids"], ["E1", "E2", "E3"])
        self.assertEqual(len(documents[0]["event_routes"]), 3)
        self.assertEqual(len(self.requests), 6)
        self.assertEqual(self.usage, {"search_calls": 6, "parse_calls": 3, "search_model_calls": 9})
        report = self.report()
        self.assertEqual(report["status"], "finished")
        self.assertEqual(report["usage"], self.usage)
        self.assertEqual([row["search_calls"] for row in report["events"]], [2, 2, 2])
        counts = len(self.requests), len(self.models)
        repeated = self.collect()
        self.assertEqual(repeated, documents)
        self.assertEqual((len(self.requests), len(self.models)), counts)
        self.assertEqual(self.report()["usage"], self.usage)

    def test_finished_sources_are_exposed_with_partial_phase_status(self):
        self.package["event"].append({"event_id": "E2", "label": "Apple investment"})
        model = self.model
        self.model = lambda context: "not JSON" if context["task"]["event_id"] == "E2" else model(context)
        documents = self.collect()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["event_ids"], ["E1"])
        report = self.report()
        self.assertEqual(report["status"], "partial")
        self.assertEqual([row["status"] for row in report["search_reports"]], ["finished", "failed"])
        self.assertEqual([row["accepted_documents"] for row in report["events"]], [1, 0])

    def test_insufficient_provider_capacity_reports_skipped_event_without_calls(self):
        self.config["event_followup"]["max_search_calls"] = 1
        self.assertEqual(self.collect(), [])
        self.assertEqual(self.tasks, [])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.report()["events"][0]["status"], "budget_exhausted")

    def test_existing_source_url_is_not_appended_again(self):
        self.assertEqual(self.collect(known_documents=[{"url": "https://example.org/investment#old"}]), [])
        self.assertEqual(self.report()["new_documents"], 0)
        self.assertEqual(self.report()["events"][0]["accepted_documents"], 0)


if __name__ == "__main__":
    unittest.main()
