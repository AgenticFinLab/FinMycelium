"""Candidate discovery -> real per-event search state, entirely offline."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from finmy.runner.enhanced_subject_search import collect_enhanced_sources
from finmy.runner.event_followup_config import followup_enabled


class InitialStorylineSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.subject = {"subject_id": "person_buffett", "name": "Warren Buffett",
                        "coverage_start": "2022", "coverage_end": "2023", "scope": "Documented activities"}
        self.config = {
            "search_config": {"mode": "agent", "event_search": {
                "max_search_requests": 2, "max_read_sources": 1,
                "max_model_calls": 4, "max_concurrent_events": 2,
                "reuse_sources": False}, "enhancement": {
                "providers": ["bocha", "baidu"], "max_search_requests": 4,
                "max_read_sources": 2, "max_model_calls": 10,
                "max_builder_material_chars": 60000, "allow_network": False,
                "lm_name": "deepseek/search-fixture"}},
            "all_content_config": {"max_content_length": 60000},
            "builder_config": {"builder_type": "SparseRagBuilder", "reconstruction": {
                "mode": "person", "subject": self.subject}}}
        self.discovery_calls, self.contexts, self.requests, self.fetches = [], [], [], []
        self.body = "An original report documents the investment and the person's actions. " * 16
        self.candidates = {
            "domains": [{"domain_id": "invest", "label": "Investment activities", "summary": "Investment matters"}],
            "events": [
                {"event_id": "oxy", "domain_id": "invest", "label": "Occidental investment",
                 "summary": "HYPOTHESIS NOT SOURCE: buying and later management contact",
                 "person_connection": "Investigate Buffett's decision and communications",
                 "scope": "The Occidental holding, excluding unrelated portfolio changes",
                 "event_terms": ["Occidental"], "questions": ["What informed the purchase decision?", "What did Buffett communicate to management?"]},
                {"event_id": "japan", "domain_id": "invest", "label": "Japanese trading houses",
                 "summary": "HYPOTHESIS NOT SOURCE: investment and financing development",
                 "person_connection": "Investigate Buffett's investment involvement and visit",
                 "scope": "Trading-house investment, excluding unrelated Japanese companies",
                 "event_terms": ["trading houses"], "questions": ["How did holdings and financing develop?"]}],
            "unresolved": []}

    def discovery(self, system, payload):
        self.discovery_calls.append((system, copy.deepcopy(payload)))
        response = copy.deepcopy(self.candidates)
        response["events"] = response["events"][:payload["max_events"]]
        return response

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

    def transport(self, provider, payload, settings):
        self.requests.append((provider, copy.deepcopy(payload), copy.deepcopy(settings)))
        query = payload["query"] if provider == "bocha" else payload["messages"][0]["content"]
        url = "https://example.test/" + hashlib.sha256(query.encode()).hexdigest()[:16]
        row = {"url": url, "title": "Original filing", "name": "Original filing"}
        return {"data": {"webPages": {"value": [row]}}} if provider == "bocha" else {"references": [row]}

    def fetcher(self, url):
        self.fetches.append(url)
        return self.body.encode(), "txt", "utf-8"

    def collect(self, *, config=None, dependencies=None, **kwargs):
        deps = {"discovery_completion": self.discovery, "model": self.model,
                "transport": self.transport, "fetcher": self.fetcher}
        deps.update(dependencies or {})
        return collect_enhanced_sources("Buffett 2022-2023", [], self.subject,
            config or self.config, self.root, dependencies=deps, **kwargs)

    def test_default_discovers_then_researches_distinct_events_without_postbuild_optin(self):
        self.assertFalse(followup_enabled(self.config))
        before = copy.deepcopy(self.config)
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(self.config, before)
        self.assertEqual(len(self.discovery_calls), 1)
        self.assertEqual(self.discovery_calls[0][1]["original_request"], "Buffett 2022-2023")
        self.assertEqual(len(result["documents"]), 2)
        events = {event["label"]: event for event in result["storyline_plan"]["events"]}
        tasks = {context["task"]["target_name"]: context["task"] for context in self.contexts}
        self.assertEqual(set(tasks), set(events))
        for label, task in tasks.items():
            self.assertEqual(task["target_type"], "event")
            self.assertEqual(task["subject_scope"], self.subject)
            self.assertEqual(task["original_query"], "Buffett 2022-2023")
            self.assertEqual(task["existing_event"]["questions"], events[label]["questions"])
            self.assertEqual(task["existing_event"]["scope"], events[label]["scope"])
            self.assertFalse(task["event_clues_are_evidence"])
        for doc in result["documents"]:
            self.assertEqual(doc["raw_text"], self.body)
            self.assertNotIn("HYPOTHESIS NOT SOURCE", doc["raw_text"])
            self.assertEqual(len(doc["event_ids"]), 1)
            self.assertEqual(doc["event_routes"][0]["event_id"], doc["event_ids"][0])
            self.assertTrue(doc["source_id"])
            self.assertTrue(doc["source_version"])
            self.assertTrue(doc["url"].startswith("https://example.test/"))
        self.assertTrue((self.root / "storyline_discovery/plan.json").exists())
        self.assertFalse((self.root / "enhanced_event_search").exists())

    def test_legacy_person_yaml_uses_one_model_config_for_discovery_and_search(self):
        del self.config["search_config"]["enhancement"]
        self.config["lm_name"] = "deepseek/legacy-pipeline"
        self.config["subject_search"] = {"providers": ["bocha"],
            "max_search_calls": 4, "max_parse_calls": 2}
        original = copy.deepcopy(self.config)
        client = Mock()
        client.with_options.return_value = client
        client.chat.completions.create.return_value = SimpleNamespace(usage=None,
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                content=json.dumps(self.candidates)))])
        factory = Mock(return_value=SimpleNamespace(client=client, model_name="legacy-pipeline"))
        with patch("lmbase.inference.api_call.LangChainAPIInference", factory), \
             patch("dotenv.load_dotenv"):
            result = self.collect(dependencies={"discovery_completion": None})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(factory.call_args.kwargs["lm_name"], "deepseek/legacy-pipeline")
        client.chat.completions.create.assert_called_once()
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(settings.allow_network for _, _, settings in self.requests))
        self.assertTrue(all(settings.lm_name == "deepseek/legacy-pipeline"
                            for _, _, settings in self.requests))
        self.assertEqual(self.config, original)

    def test_existing_agent_discovery_checkpoint_identity_remains_compatible(self):
        from finmy.runner.storyline_discovery import discover_storylines
        discover_storylines("Buffett 2022-2023", [], self.subject, self.config, self.root,
                            completion=self.discovery)
        checkpoint = self.root / "storyline_discovery/checkpoint.json"
        previous = json.loads(checkpoint.read_text())["identity"]
        result = self.collect(dependencies={"discovery_completion":
            lambda *args: self.fail("Existing discovery checkpoint must be reused")})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(json.loads(checkpoint.read_text())["identity"], previous)
        self.assertEqual(len(self.discovery_calls), 1)

    def test_discovery_and_search_calls_have_separate_finite_budgets(self):
        result = self.collect()
        self.assertEqual(result["usage"]["search_calls"], len(self.requests))
        self.assertEqual(result["usage"]["search_calls"], 4)
        self.assertEqual(result["usage"]["parse_calls"], 2)
        self.assertEqual(result["usage"]["search_model_calls"], len(self.contexts))
        self.assertEqual(result["usage"]["discovery_model_calls"], len(self.discovery_calls))
        self.assertEqual(result["usage"]["total_model_calls"], len(self.discovery_calls) + len(self.contexts))
        self.assertLessEqual(result["usage"]["search_model_calls"], 10)
        report = json.loads((self.root / "storyline_search_report.json").read_text())
        self.assertEqual(report["discovery_model_calls"], 1)
        self.assertEqual(report["limits"], {"search_calls": 4, "parse_calls": 2, "search_model_calls": 10})
        self.assertEqual(report["content_limit"], 60000)

    def test_completed_resume_spends_no_discovery_search_read_or_model_calls(self):
        first = self.collect()
        counts = (len(self.discovery_calls), len(self.requests), len(self.fetches), len(self.contexts))
        usage = {}
        second = self.collect(usage=usage)
        self.assertEqual(counts, (len(self.discovery_calls), len(self.requests), len(self.fetches), len(self.contexts)))
        self.assertEqual(first["documents"], second["documents"])
        self.assertEqual(first["usage"], second["usage"])
        self.assertEqual(second["storyline_plan"]["usage"]["new_model_calls"], 0)
        self.assertEqual(usage, second["usage"])

    def test_explicit_disabled_postbuild_budget_does_not_disable_initial_event_research(self):
        self.config["event_followup"] = {"enabled": False, "max_search_calls": 0,
            "max_parse_calls": 0, "max_search_model_calls": 0, "max_model_calls": 0}
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(self.requests), 4)
        self.assertFalse(followup_enabled(self.config))

    def test_prespent_budget_and_resume_never_double_charge_discovery(self):
        usage = {"search_calls": 2, "parse_calls": 1, "search_model_calls": 3}
        first = self.collect(usage=usage)
        self.assertEqual(len(first["storyline_plan"]["events"]), 2)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(len(first["documents"]), 1)
        self.assertEqual(usage["search_calls"], 2 + len(self.requests))
        self.assertEqual(usage["parse_calls"], 1 + len(self.fetches))
        self.assertEqual(usage["search_model_calls"], 3 + len(self.contexts))
        self.assertEqual(usage["discovery_model_calls"], len(self.discovery_calls))
        counts = (len(self.discovery_calls), len(self.contexts), len(self.requests), len(self.fetches))
        second = self.collect(usage=usage)
        self.assertEqual(second["usage"], first["usage"])
        self.assertEqual(counts, (len(self.discovery_calls), len(self.contexts), len(self.requests), len(self.fetches)))
        self.assertLessEqual(usage["search_model_calls"], 10)

    def test_exhausted_external_budget_is_preserved_in_report(self):
        usage = {"search_calls": 4, "parse_calls": 2, "search_model_calls": 10}
        result = self.collect(usage=usage)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["usage"], usage)
        self.assertEqual(len(self.discovery_calls), 1)
        self.assertEqual(len(result["storyline_plan"]["events"]), 2)
        self.assertEqual(self.requests, [])

    def test_invalid_discovery_stops_without_broad_fallback_or_source_generation(self):
        attempts = []
        def invalid(system, payload):
            attempts.append(payload)
            return {"domains": [], "events": "wrong schema"}
        result = self.collect(dependencies={"discovery_completion": invalid})
        self.assertEqual(result["status"], "discovery_failed")
        self.assertEqual(result["documents"], [])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(result["usage"]["search_model_calls"], 0)
        self.assertEqual(result["usage"]["discovery_model_calls"], 2)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.fetches, [])
        self.assertEqual(self.contexts, [])
        checkpoint = json.loads((self.root / "storyline_discovery/checkpoint.json").read_text())
        self.assertEqual(checkpoint["usage"]["model_calls"], 2)
        repeated = self.collect(dependencies={"discovery_completion": invalid})
        self.assertEqual(repeated["status"], "discovery_failed")
        self.assertEqual(len(attempts), 2)

    def test_failed_provider_does_not_silently_turn_candidate_into_evidence(self):
        def failed(provider, payload, settings):
            raise RuntimeError("Offline provider failure")
        result = self.collect(dependencies={"transport": failed})
        self.assertNotEqual(result["status"], "finished")
        self.assertEqual(result["documents"], [])
        self.assertTrue(all(c["task"]["target_type"] == "event" for c in self.contexts))
        report = json.loads((self.root / "storyline_search_report.json").read_text())
        self.assertEqual(len(report["unresolved_events"]), len(result["storyline_plan"]["events"]))

    def test_global_budget_too_small_preserves_discovery_without_starting_tiny_tasks(self):
        self.config["search_config"]["enhancement"]["max_model_calls"] = 2
        result = self.collect()
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["documents"], [])
        self.assertEqual(len(self.discovery_calls), 1)
        self.assertEqual(len(result["storyline_plan"]["events"]), 2)
        self.assertTrue(all(r["status"] == "budget_exhausted" for r in result["reports"]))
        self.assertEqual(self.contexts, [])

    def test_minimum_search_read_finish_allowance_can_complete_one_event(self):
        self.config["search_config"]["enhancement"]["max_model_calls"] = 3
        result = self.collect()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual([record["status"] for record in result["reports"]],
                         ["finished", "budget_exhausted"])
        self.assertEqual(result["usage"]["search_model_calls"], 3)
        self.assertEqual(result["usage"]["search_calls"], 2)
        self.assertEqual(result["usage"]["parse_calls"], 1)
        self.assertEqual(result["reports"][0]["config"]["max_model_calls"], 3)
        self.assertTrue(result["reports"][0]["allocation"]["reduced_to_remaining_budget"])

    def test_discovery_optout_keeps_the_broad_subject_task_explicit(self):
        self.config["search_config"]["storyline_discovery"] = {"enabled": False}
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(self.discovery_calls, [])
        self.assertTrue(all(c["task"]["target_type"] == "person" for c in self.contexts))
        self.assertNotIn("storyline_plan", result)
