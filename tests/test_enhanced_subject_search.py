"""Shared search -> person evidence contracts, with real state and no network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from finmy.runner.enhanced_subject_search import collect_enhanced_sources, enhanced_search_enabled
from finmy.search.pipeline import run_search


class EnhancedSubjectSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.subject = {"subject_id": "person_example", "name": "Example Person",
                        "coverage_start": "2022", "coverage_end": "2023", "scope": "Investments"}
        self.config = {"search_config": {"mode": "agent",
            "storyline_discovery": {"enabled": False}, "enhancement": {
            "providers": ["bocha"], "max_search_requests": 6, "max_read_sources": 6,
            "max_model_calls": 12, "max_builder_material_chars": 60000}},
            "all_content_config": {"max_content_length": 60000},
            "builder_config": {"lm_name": "builder/never-inherit", "reconstruction": {
                "mode": "person", "subject": self.subject}},
            "event_followup": {"max_search_calls": 6, "max_parse_calls": 6,
                               "max_search_model_calls": 12, "max_content_length": 60000}}
        self.requests, self.contexts, self.fetches = [], [], []
        self.body = "\n\n".join("Original acquisition evidence paragraph " + str(i) + "." for i in range(35))

    def model(self, context):
        self.contexts.append(copy.deepcopy(context))
        sources = context["sources"]
        if not sources:
            return {"action": "search", "query": context["task"]["target_name"]}
        unread = next((s for s in sources if not s["reviewed"]), None)
        if unread and context["phase"] != "finalize":
            return {"action": "read_source", "source": unread["source_id"]}
        return {"action": "finish", "source_ids": [s["source_id"] for s in sources if s["reviewed"]],
                "gaps": [], "reason": "supported"}

    def transport(self, provider, payload, config):
        self.requests.append((provider, copy.deepcopy(payload), copy.deepcopy(config)))
        item = {"url": "https://example.org/evidence", "title": "Primary filing",
                "name": "Primary filing", "publishedDate": "2024-02-01"}
        if provider == "bocha":
            return {"data": {"webPages": {"value": [item]}}}
        if provider == "baidu":
            return {"references": [item]}
        return {"results": [{**item, "text": self.body}]}

    def fetcher(self, url):
        self.fetches.append(url)
        return self.body.encode(), "txt", "utf-8"

    def collect(self, **kwargs):
        deps = {"model": self.model, "transport": self.transport, "fetcher": self.fetcher}
        deps.update(kwargs.pop("dependencies", {}))
        return collect_enhanced_sources("Reconstruct documented investments", ["investment"],
            self.subject, kwargs.pop("config", self.config), self.root,
            dependencies=deps, **kwargs)

    def events(self, count=2):
        return [{"event_id": "E:" + str(i), "event_label": "Investment " + str(i),
                 "event_terms": ["investment"], "summary": "Existing thin event"} for i in range(count)]

    def test_full_source_export_preserves_subject_and_independent_model(self):
        self.config["all_content_config"]["max_content_length"] = 840
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["documents"][0]["raw_text"], self.body)
        self.assertGreater(len(self.body), 840)
        row = result["documents"][0]
        self.assertEqual(row["source"], "enhanced")
        self.assertEqual(row["source_status"], "success")
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["published_at_raw"], "2024-02-01")
        self.assertNotIn("event_ids", row)
        saved = json.loads((Path(row["search_run_directory"]) / "run.json").read_text())
        self.assertEqual(saved["task"]["target_type"], "person")
        self.assertEqual(saved["task"]["subject_scope"], self.subject)
        self.assertEqual(saved["config"]["lm_name"], "ark/doubao-seed-2-1-lite-260915")
        handoff = json.loads((Path(row["search_run_directory"]) / "builder_input.json").read_text())
        self.assertLessEqual(sum(len(s["content"]) for s in handoff["samples"]), 840)
        self.assertNotIn("freshness", self.requests[0][1])

    def test_explicit_publication_window_stays_separate_from_event_coverage(self):
        self.config["search_config"]["enhancement"].update(publication_start="2024-01-01", publication_end="2025-12-31")
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(self.requests[0][1]["freshness"], "2024-01-01..2025-12-31")
        self.assertEqual(self.contexts[0]["task"]["subject_scope"]["coverage_start"], "2022")

    def test_deadline_wrapper_preserves_search_model_usage_trace(self):
        decide = self.model

        class MeteredModel:
            last_usage = None

            def __call__(self, context):
                self.last_usage = {"prompt_tokens": 123, "completion_tokens": 45}
                return decide(context)

        result = self.collect(dependencies={"model": MeteredModel()})
        trace = Path(result["documents"][0]["search_run_directory"]) / "trace.jsonl"
        responses = [row for row in map(json.loads, trace.read_text().splitlines())
                     if row.get("action") == "model_response"]
        self.assertEqual(len(responses), 3)
        self.assertTrue(all(row["usage"] == {"prompt_tokens": 123, "completion_tokens": 45}
                            for row in responses))

    def test_provider_requests_and_global_event_limits_are_not_multiplied(self):
        self.config["search_config"]["enhancement"]["providers"] = ["bocha", "baidu"]
        usage = {}
        result = self.collect(events=self.events(3), usage=usage)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(self.requests), 6)
        self.assertEqual(usage["search_calls"], 6)
        self.assertEqual(usage["parse_calls"], 3)
        self.assertEqual(usage["search_model_calls"], 9)
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["documents"][0]["event_ids"], ["E:0", "E:1", "E:2"])
        self.assertEqual(len(result["documents"][0]["event_routes"]), 3)
        self.assertTrue(all(c["task"]["target_type"] == "event" for c in self.contexts))

    def test_completed_rerun_uses_saved_handoff_without_spending_again(self):
        result = self.collect(events=self.events())
        counts = len(self.requests), len(self.contexts), len(self.fetches)
        usage = {}
        repeated = self.collect(events=self.events(), usage=usage)
        self.assertEqual(counts, (len(self.requests), len(self.contexts), len(self.fetches)))
        self.assertEqual(result["documents"], repeated["documents"])
        self.assertEqual(usage, repeated["usage"])

    def test_paused_tasks_reserve_capacity_when_resuming(self):
        self.config["event_followup"]["max_search_model_calls"] = 6
        self.config["event_followup"]["max_search_calls"] = 2
        for _ in range(3):
            result = self.collect(events=self.events(), dependencies={"max_steps": 1})
            self.assertLessEqual(result["usage"]["search_calls"], 2)
            self.assertLessEqual(result["usage"]["search_model_calls"], 6)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(self.contexts), 6)
        self.assertEqual(len(self.requests), 2)

    def test_changed_scope_or_budget_cannot_reset_saved_usage(self):
        self.collect()
        changed = copy.deepcopy(self.config)
        changed["search_config"]["enhancement"]["max_search_requests"] = 30
        with self.assertRaisesRegex(ValueError, "scope/config changed"):
            self.collect(config=changed)

    def test_paused_and_failed_searches_never_export_documents(self):
        result = self.collect(dependencies={"max_steps": 1})
        self.assertEqual(result["status"], "paused")
        self.assertEqual(result["documents"], [])
        failed = self.collect(dependencies={"model": lambda c: "invalid JSON"})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["documents"], [])

    def test_empty_finish_and_tiny_handoff_are_not_admitted(self):
        self.config["all_content_config"]["max_content_length"] = 1
        result = self.collect()
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["documents"], [])

    def test_insufficient_selection_exports_reviewed_material_and_keeps_incomplete_status(self):
        def partial(context):
            action = self.model(context)
            if action["action"] == "finish":
                action.update(reason="insufficient", gaps=["The later disposal remains unverified."])
            return action

        result = self.collect(dependencies={"model": partial})
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(len(result["documents"]), 1)
        row = result["documents"][0]
        self.assertEqual(row["raw_text"], self.body)
        self.assertEqual(row["event_search_status"], "insufficient")
        selection = json.loads((Path(row["search_run_directory"]) / "selection.json").read_text())
        self.assertEqual(selection["reason"], "insufficient")
        self.assertEqual(selection["gaps"], ["The later disposal remains unverified."])
        counts = len(self.requests), len(self.fetches), len(self.contexts)
        repeated = self.collect(dependencies={"model": partial})
        self.assertEqual(repeated["documents"], result["documents"])
        self.assertEqual(repeated["status"], "insufficient")
        self.assertEqual(counts, (len(self.requests), len(self.fetches), len(self.contexts)))

    def test_tampered_complete_manifest_fails_closed(self):
        def tamper(*args, **kwargs):
            result = run_search(*args, **kwargs)
            path = Path(result["run_dir"]) / "complete_material.json"
            data = json.loads(path.read_text())
            data["material_chars"] += 1
            path.write_text(json.dumps(data))
            return result
        result = self.collect(dependencies={"run_search": tamper})
        self.assertEqual(result["status"], "invalid_handoff")
        self.assertEqual(result["documents"], [])

    def test_task_seeds_allowed_but_subject_override_rejected(self):
        result = self.collect(task={"seed_urls": ["https://example.org/seed"]})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(self.requests, [])
        with self.assertRaisesRegex(ValueError, "cannot override"):
            self.collect(task={"target_type": "event"})

    def test_local_file_does_not_require_capacity_for_all_selected_providers(self):
        local = self.root / "source.txt"
        local.write_text(self.body, encoding="utf-8")
        self.config["search_config"]["enhancement"].update(max_search_requests=1, providers=["bocha", "baidu"])
        result = self.collect(task={"local_files": [str(local)]})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["documents"][0]["raw_text"], self.body)
        self.assertEqual(result["usage"]["search_calls"], 0)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.fetches, [])

    def test_saved_manifest_freezes_exported_source_metadata(self):
        def mutate_after_finish(*args, **kwargs):
            result = run_search(*args, **kwargs)
            path = Path(result["run_dir"]) / "run.json"
            state = json.loads(path.read_text())
            for source in state["sources"].values():
                source["title"] = "Changed title after selection"
                source["discoveries"][0]["published_at"] = "2025-06-01"
            path.write_text(json.dumps(state))
            return result
        result = self.collect(dependencies={"run_search": mutate_after_finish})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["documents"][0]["title"], "Primary filing")
        self.assertIsNone(result["documents"][0]["published_at"])
        self.assertEqual(result["documents"][0]["published_at_raw"], "2024-02-01")

    def test_exa_partial_text_retains_source_status_and_skips_refetch(self):
        self.config["search_config"]["enhancement"]["providers"] = ["exa"]
        result = self.collect()
        self.assertEqual(result["documents"][0]["source_status"], "partial")
        self.assertEqual(self.fetches, [])

    def test_no_supplementary_capacity_is_explicit_and_no_models_called(self):
        self.config["event_followup"]["max_search_calls"] = 0
        result = self.collect(events=self.events())
        self.assertEqual(result["documents"], [])
        self.assertEqual([r["status"] for r in result["reports"]], ["budget_exhausted", "budget_exhausted"])
        self.assertEqual(self.contexts, [])

    def test_existing_phase_usage_is_not_reset_without_a_saved_handoff(self):
        usage = {"search_calls": 6, "parse_calls": 6, "search_model_calls": 12}
        result = self.collect(usage=usage)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["usage"], usage)
        self.assertEqual(self.contexts, [])

    def test_configuration_does_not_mutate_and_modes_are_validated(self):
        before = copy.deepcopy(self.config)
        self.collect(events=self.events())
        self.assertEqual(self.config, before)
        self.assertFalse(enhanced_search_enabled({}))
        with self.assertRaises(ValueError):
            enhanced_search_enabled({"search_config": {"mode": "unexpected"}})


if __name__ == "__main__":
    unittest.main()
