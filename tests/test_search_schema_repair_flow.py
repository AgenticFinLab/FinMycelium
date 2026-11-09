"""Search failures retain explicitly selected originals through Builder budgeting."""
import copy
import unittest

from finmy.runner.context_budget import allocate_context
import test_initial_storyline_search as fixtures


class SearchSchemaRepairFlowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InitialStorylineSearchTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        config = self.fixture.config
        config["search_config"]["event_search"].update(max_model_calls=12)
        config["search_config"]["enhancement"].update(
            max_model_calls=24, max_builder_material_chars=120000)
        config["all_content_config"]["max_content_length"] = 120000

    def test_provider_rejection_then_invalid_actions_keep_reviewed_sources(self):
        contexts = []
        queries = {
            "Occidental investment":
                "Buffett Berkshire Activision stake 2022 annual meeting arbitrage comments",
            "Japanese trading houses":
                "Buffett Berkshire charitable share donations 2023 foundations annual gift recipients",
        }

        def model(context):
            contexts.append(copy.deepcopy(context))
            if context["phase"] == "finalize":
                # An aborted research phase must remain incomplete even if a
                # model overstates the confidence of its otherwise valid choice.
                return {"action": "finish", "source_ids": context["eligible_source_ids"],
                        "gaps": [], "reason": "supported"}
            if not context["sources"]:
                return {"action": "search", "query": queries[context["task"]["target_name"]]}
            unread = next((row for row in context["sources"] if not row["reviewed"]), None)
            if unread:
                return {"action": "read_source", "source": unread["source_id"]}
            return {"action": "invalid_operation"}

        result = self.fixture.collect(dependencies={"model": model})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual([row["status"] for row in result["reports"]],
                         ["insufficient", "insufficient"])
        self.assertEqual([provider for provider, *_ in self.fixture.requests], ["bocha", "bocha"])
        self.assertEqual(result["usage"]["search_calls"], 2)
        self.assertEqual(result["usage"]["parse_calls"], 2)
        self.assertLessEqual(result["usage"]["search_model_calls"], 24)
        self.assertEqual(len([c for c in contexts if c["phase"] == "finalize"]), 2)
        for document in result["documents"]:
            self.assertEqual(document["raw_text"], self.fixture.body)
            self.assertTrue(document["source_version"])
            self.assertTrue(document["event_ids"])

        budget = allocate_context(result["documents"], [], self.fixture.config)
        summary = budget["report"]["summary"]
        self.assertEqual(summary["included_documents"], 2)
        self.assertEqual(summary["omitted_documents"], 0)
        self.assertEqual(summary["truncated_documents"], 0)
        self.assertEqual(summary["max_content_length"], 120000)

        counts = (len(contexts), len(self.fixture.requests), len(self.fixture.fetches))
        again = self.fixture.collect(dependencies={"model": model})
        self.assertEqual(again["documents"], result["documents"])
        self.assertEqual(again["usage"], result["usage"])
        self.assertEqual((len(contexts), len(self.fixture.requests), len(self.fixture.fetches)), counts)


if __name__ == "__main__":
    unittest.main()
