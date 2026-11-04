"""Regression checks for Event and Person mode dispatch."""
import unittest

import test_epg_validation_integration as integration
from finmy.builder.agent_build import prompts as legacy


class BuilderModeTests(unittest.TestCase):
    setUp = integration.IntegrationTest.setUp

    def test_event_prompt_strings_are_unchanged(self):
        actual_system, actual_user = self.builder._get_agent_prompts()
        names = {"SkeletonReconstructor": "EventLayoutReconstructor",
                 "SkeletonChecker": "SkeletonChecker", "ParticipantReconstructor": "ParticipantReconstructor",
                 "TransactionReconstructor": "TransactionReconstructor", "EpisodeReconstructor": "EpisodeReconstructor",
                 "StageDescriptionReconstructor": "StageDescriptionReconstructor",
                 "EventDescriptionReconstructor": "EventDescriptionReconstructor"}
        for name, prefix in names.items():
            self.assertEqual(actual_system[name], getattr(legacy, prefix + "Sys"))
            self.assertEqual(actual_user[name], getattr(legacy, prefix + "User"))

    def test_event_run_does_not_emit_person_artifacts(self):
        self.write_results = lambda state: integration.IntegrationTest.write_results(self, state)
        result = integration.IntegrationTest.run_builder(self)
        self.assertNotIn("person_index", result.extras)
        self.assertFalse((self.path / "person_index.json").exists())

    def test_invalid_person_config_stops_before_graph_or_model(self):
        self.builder.build_config = {"reconstruction": {"mode": "person"}}
        self.builder.graph = lambda: self.fail("Graph must not run for invalid scope")
        with self.assertRaises(ValueError):
            self.builder.run(None)



if __name__ == "__main__":
    unittest.main()
