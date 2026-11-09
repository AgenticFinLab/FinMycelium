"""Offline discovery ledger, repair, scope and transport contracts."""
import copy
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from finmy.runner.storyline_discovery import (
    DISCOVERY_PROMPT, StorylineDiscoveryError, discover_storylines, normalize_plan,
    _live_completion,
)


def candidate():
    return {"domains": [{"domain_id": "d1", "label": "Projects", "summary": "Project work"}],
        "events": [{"event_id": "e1", "domain_id": "d1", "label": "Alpha project",
                    "summary": "Investigate Alpha", "person_connection": "Person's involvement",
                    "scope": "Alpha project, excluding Beta", "event_terms": ["Alpha"],
                    "questions": ["What did the person do on Alpha?"]}], "unresolved": []}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.subject = {"subject_id": "p1", "name": "Research subject", "aliases": [],
                        "coverage_start": "2022", "coverage_end": "2023", "scope": "Documented work"}
        self.config = {"search_config": {"enhancement": {"allow_network": False,
            "lm_name": "deepseek/deepseek-chat", "timeout": 42,
            "generation_config": {"max_tokens": 4096}},
            "storyline_discovery": {"max_model_calls": 2, "max_events": 8}}}

    def run_discovery(self, **kwargs):
        return discover_storylines("Research subject 2022-2023", [], self.subject,
            self.config, self.root, **kwargs)

    def checkpoint(self):
        return json.loads((self.root / "storyline_discovery/checkpoint.json").read_text())

    def test_candidate_plan_ids_scope_and_cache(self):
        before = copy.deepcopy(self.subject)
        calls = []
        def complete(system, payload):
            self.assertIn("JSON", system)
            self.assertEqual(payload["subject_scope"], self.subject)
            calls.append(payload)
            return candidate()
        plan = self.run_discovery(completion=complete)
        self.assertEqual(plan["subject"], before)
        self.assertEqual(self.subject, before)
        self.assertTrue(plan["candidate_only"])
        self.assertEqual(plan["status"], "candidates")
        self.assertTrue(plan["events"][0]["event_id"].startswith("storyline:"))
        self.assertEqual(plan["events"][0]["domain_id"], plan["domains"][0]["domain_id"])
        self.assertEqual(plan["usage"], {"model_calls": 1, "new_model_calls": 1})
        replay = self.run_discovery(completion=lambda *a: self.fail("Cache made a model call"))
        self.assertEqual(replay["usage"], {"model_calls": 1, "new_model_calls": 0})
        self.assertEqual(len(calls), 1)
        self.assertTrue((self.root / "storyline_discovery/plan.json").is_file())

    def test_malformed_response_repair_consumes_same_two_call_budget(self):
        calls = []
        def complete(system, payload):
            calls.append(payload)
            return "invalid JSON" if len(calls) == 1 else candidate()
        plan = self.run_discovery(completion=complete)
        self.assertEqual(plan["usage"]["model_calls"], 2)
        self.assertEqual(calls[1]["repair"]["previous_response"], "invalid JSON")
        self.assertEqual([x["status"] for x in self.checkpoint()["attempts"]], ["invalid_response", "completed"])

    def test_failed_schema_does_not_reset_budget_on_resume(self):
        calls = []
        def malformed(*args):
            calls.append(1)
            return {"domains": [], "events": [{}]}
        with self.assertRaises(StorylineDiscoveryError) as first:
            self.run_discovery(completion=malformed)
        self.assertEqual(first.exception.usage, {"model_calls": 2, "new_model_calls": 2})
        with self.assertRaises(StorylineDiscoveryError) as resumed:
            self.run_discovery(completion=lambda *a: self.fail("Budget reset"))
        self.assertEqual(resumed.exception.usage, {"model_calls": 2, "new_model_calls": 0})
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.root / "storyline_discovery/plan.json").exists())

    def test_provider_errors_are_not_prompt_repaired_or_logged_verbatim(self):
        calls = []
        def fail(*args):
            calls.append(1)
            raise ValueError("https://provider.test/?api_key=SECRET")
        with self.assertRaises(StorylineDiscoveryError):
            self.run_discovery(completion=fail)
        checkpoint = self.checkpoint()
        self.assertEqual(len(calls), 1)
        self.assertEqual(checkpoint["status"], "failed")
        self.assertNotIn("SECRET", json.dumps(checkpoint))

    def test_changed_scope_cannot_reuse_plan(self):
        self.run_discovery(completion=lambda *a: candidate())
        self.subject["coverage_end"] = "2024"
        with self.assertRaisesRegex(ValueError, "scope/config changed"):
            self.run_discovery(completion=lambda *a: self.fail("Changed scope called model"))

    def test_duplicate_labels_or_ids_and_unknown_domain_fail(self):
        for field in ("domain_id", "event_id", "event_label", "unknown_domain"):
            value = candidate()
            if field == "domain_id": value["domains"].append(copy.deepcopy(value["domains"][0]))
            elif field == "unknown_domain": value["events"][0]["domain_id"] = "missing"
            else:
                row = copy.deepcopy(value["events"][0])
                if field == "event_label": row["event_id"] = "different-id"
                else: row["label"] = "Different event"
                value["events"].append(row)
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_plan(value, self.subject, 8)

    def test_resource_cap_is_not_a_required_count(self):
        plan = normalize_plan(candidate(), self.subject, 8)
        self.assertEqual(len(plan["events"]), 1)
        with self.assertRaisesRegex(ValueError, "resource cap"):
            normalize_plan(candidate(), self.subject, 0)
        with self.assertRaises(StorylineDiscoveryError):
            self.run_discovery(completion=lambda *a: {"domains": [], "events": [], "unresolved": ["Identity unresolved"]})
        self.assertEqual(self.checkpoint()["usage"]["model_calls"], 1)
        self.assertEqual(self.checkpoint()["status"], "insufficient")

    def test_optional_source_previews_are_bounded_and_do_not_mutate_sources(self):
        sources = [{"raw_text": "Source text. " * 1000, "title": "Source", "url": "https://example.test"} for _ in range(8)]
        original = copy.deepcopy(sources)
        def complete(system, payload):
            self.assertLessEqual(sum(len(s["content"]) for s in payload["seed_sources"]), 12000)
            self.assertTrue(all(s["partial_preview"] for s in payload["seed_sources"]))
            return candidate()
        self.run_discovery(completion=complete, seed_sources=sources)
        self.assertEqual(sources, original)

    def test_network_disabled_prevents_adapter_creation(self):
        complete = _live_completion(self.config["search_config"]["enhancement"])
        with self.assertRaises(PermissionError):
            complete(DISCOVERY_PROMPT, {})

    def test_live_transport_uses_search_model_json_mode_no_hidden_retries(self):
        enhancement = copy.deepcopy(self.config["search_config"]["enhancement"])
        enhancement["allow_network"] = True
        client = Mock()
        client.with_options.return_value = client
        client.chat.completions.create.return_value = types.SimpleNamespace(
            usage=types.SimpleNamespace(model_dump=lambda: {"total_tokens": 20}),
            choices=[types.SimpleNamespace(finish_reason="stop", message=types.SimpleNamespace(content=json.dumps(candidate())))])
        factory = Mock(return_value=types.SimpleNamespace(client=client, model_name="deepseek-chat"))
        stub = types.ModuleType("lmbase.inference.api_call")
        stub.LangChainAPIInference = factory
        with patch.dict("sys.modules", {"lmbase.inference.api_call": stub}), patch("dotenv.load_dotenv"):
            complete = _live_completion(enhancement)
            result = complete(DISCOVERY_PROMPT, {"original_request": "short input"})
        self.assertEqual(json.loads(result), candidate())
        self.assertEqual(factory.call_args.kwargs["lm_name"], "deepseek/deepseek-chat")
        client.with_options.assert_called_once_with(max_retries=0, timeout=42)
        self.assertEqual(client.chat.completions.create.call_args.kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(complete.last_usage, {"total_tokens": 20})


if __name__ == "__main__":
    unittest.main()
