"""Provider outages do not erase the other provider's event evidence."""
import json
import unittest

import requests

import test_initial_storyline_search as fixtures


class ProviderFailureFlowTests(unittest.TestCase):
    def test_auth_failure_is_bounded_across_events_and_successful_sources_survive(self):
        fixture = fixtures.InitialStorylineSearchTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.config["search_config"]["event_search"]["max_concurrent_events"] = 1
        calls = []

        def transport(provider, payload, config):
            calls.append(provider)
            if provider == "baidu":
                response = requests.Response()
                response.status_code = 401
                response._content = json.dumps({"error": {"code": "invalid_api_key",
                    "message": "credential-super-secret should never enter saved errors"}}).encode()
                raise requests.HTTPError("credential-super-secret", response=response)
            return fixture.transport(provider, payload, config)

        result = fixture.collect(dependencies={"transport": transport})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(calls.count("baidu"), 2)
        self.assertEqual(calls.count("bocha"), 2)
        self.assertEqual(result["usage"]["search_calls"], 4)
        for document in result["documents"]:
            self.assertEqual(document["raw_text"], fixture.body)
        traces = "\n".join(p.read_text() for p in fixture.root.rglob("trace.jsonl"))
        self.assertNotIn("credential-super-secret", traces)
        self.assertIn("401", traces)
        before = list(calls)
        again = fixture.collect(dependencies={"transport": transport})
        self.assertEqual(again["documents"], result["documents"])
        self.assertEqual(calls, before)


if __name__ == "__main__":
    unittest.main()
