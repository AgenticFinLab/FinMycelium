"""Shared search -> person evidence contracts, with real state and no network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from finmy.runner.enhanced_subject_search import collect_enhanced_sources
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
                "mode": "person", "subject": self.subject}}}
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

    def test_single_event_exports_full_originals_without_subject_scope(self):
        self.config["builder_config"]["reconstruction"] = {"mode": "event"}
        result = collect_enhanced_sources("Reconstruct acquisition 2023", [], {},
            self.config, self.root, dependencies={"model": self.model,
                "transport": self.transport, "fetcher": self.fetcher})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["documents"][0]["raw_text"], self.body)
        self.assertEqual(self.contexts[0]["task"]["target_type"], "event")
        self.assertEqual(self.contexts[0]["task"]["query_text"], "Reconstruct acquisition 2023")
        self.assertNotIn("subject_scope", self.contexts[0]["task"])


    def test_completed_rerun_uses_saved_handoff_without_spending_again(self):
        result = self.collect()
        counts = len(self.requests), len(self.contexts), len(self.fetches)
        usage = {}
        repeated = self.collect(usage=usage)
        self.assertEqual(counts, (len(self.requests), len(self.contexts), len(self.fetches)))
        self.assertEqual(result["documents"], repeated["documents"])
        self.assertEqual(usage, repeated["usage"])

    def test_paused_initial_search_resumes_within_its_saved_budget(self):
        self.config["search_config"]["enhancement"].update(max_model_calls=3, max_search_requests=1)
        for _ in range(3):
            result = self.collect(dependencies={"max_steps": 1})
            self.assertLessEqual(result["usage"]["search_calls"], 1)
            self.assertLessEqual(result["usage"]["search_model_calls"], 3)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(self.contexts), 3)
        self.assertEqual(len(self.requests), 1)

    def test_retired_followup_settings_do_not_affect_initial_search_or_resume(self):
        self.config["event_followup"] = "malformed retired settings"
        result = self.collect()
        counts = len(self.requests), len(self.contexts), len(self.fetches)
        self.config["event_followup"] = {"enabled": True, "max_search_calls": 0,
                                        "max_content_length": 0}
        repeated = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["documents"], repeated["documents"])
        self.assertEqual(counts, (len(self.requests), len(self.contexts), len(self.fetches)))

    def test_changed_scope_or_budget_cannot_reset_saved_usage(self):
        self.collect()
        changed = copy.deepcopy(self.config)
        changed["search_config"]["enhancement"]["max_search_requests"] = 30
        with self.assertRaisesRegex(ValueError, "scope/config changed"):
            self.collect(config=changed)


    def test_one_damaged_selected_original_keeps_other_verified_documents(self):
        def transport(provider, payload, config):
            return {"data": {"webPages": {"value": [
                {"url": "https://example.org/first", "name": "First original"},
                {"url": "https://example.org/second", "name": "Second original"}]}}}

        def corrupt_after_finish(*args, **kwargs):
            result = run_search(*args, **kwargs)
            task_root = Path(result["run_dir"]).parent.parent
            next(task_root.glob("sources/*/*/raw")).write_bytes(b"damaged")
            return result

        result = self.collect(dependencies={"run_search": corrupt_after_finish,
            "transport": transport,
            "fetcher": lambda url: ((self.body + " Original: " + url).encode(), "txt", "utf-8")})
        self.assertEqual(len(result["documents"]), 1)
        self.assertFalse(result.get("complete", False))
        self.assertEqual(result["reports"][0]["status"], "insufficient")
        self.assertEqual(result["reports"][0]["errors"][0]["stage"], "source_integrity")
        self.assertTrue(result["reports"][0]["gaps"])


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


    def test_exa_partial_text_retains_source_status_and_skips_refetch(self):
        self.config["search_config"]["enhancement"]["providers"] = ["exa"]
        result = self.collect()
        self.assertEqual(result["documents"][0]["source_status"], "partial")
        self.assertEqual(self.fetches, [])


if __name__ == "__main__":
    unittest.main()
