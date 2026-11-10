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

    def overflow_candidates(self):
        value = candidate()
        value['domains'] = [dict(domain_id='d'+str(i), label='Domain '+str(i), summary='Scope')
                            for i in range(3)]
        value['events'] = [dict(candidate()['events'][0], event_id='e'+str(i),
                               label='Event '+str(i), domain_id='d'+str(0 if i < 8 else i-7))
                           for i in range(10)]
        return value

    def test_overflow_selects_eight_and_preserves_late_domains_without_extra_call(self):
        value = self.overflow_candidates()
        calls = Mock(return_value=value)
        calls.last_usage = None
        plan = self.run_discovery(completion=calls)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual([e['label'] for e in plan['events']],
                         ['Event '+str(i) for i in [0, 1, 2, 3, 4, 5, 8, 9]])
        self.assertEqual(len({e['domain_id'] for e in plan['events']}), 3)
        audit = json.loads((self.root / 'storyline_discovery/candidate_selection.json').read_text())
        self.assertEqual([e['label'] for e in audit['deferred_events']], ['Event 6', 'Event 7'])
        self.assertEqual(normalize_plan(plan, self.subject, 8),
                         {k:v for k,v in plan.items() if k != 'usage'})

    def test_more_domains_than_slots_preserves_domain_coverage(self):
        value = self.overflow_candidates()
        plan = normalize_plan(value, self.subject, 2)
        self.assertEqual(len(plan['events']), 3)
        self.assertEqual(len(plan['domains']), 3)


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


    def test_changed_scope_cannot_reuse_plan(self):
        self.run_discovery(completion=lambda *a: candidate())
        self.subject["coverage_end"] = "2024"
        with self.assertRaisesRegex(ValueError, "scope/config changed"):
            self.run_discovery(completion=lambda *a: self.fail("Changed scope called model"))


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
