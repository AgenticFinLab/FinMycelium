"""Exercise actual prompt execution and persistence without network/model packages."""
import ast
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_epg_validation_integration as integration
from finmy.builder.agent_build import prompts as legacy
from finmy.builder.agent_build.person_prompts import get_person_prompts, schema_for_agent

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "finmy/builder/agent_build/structure.py").read_text()


def configuration():
    return {"graph_config": {}, "reconstruction": {"mode": "person", "subject": {
        "subject_id": "person_warren_buffett", "name": "Warren Buffett",
        "aliases": ["巴菲特"], "coverage_start": "2022", "coverage_end": "2023",
        "scope": "OXY-related statements and documented investment decisions"}}}


def outputs():
    f = integration.field
    episode = {"episode_id": "E1", "name": f("OXY statement"), "index_in_stage": 0,
               "start_time": f("2023-05"), "end_time": f("2023-05")}
    skeleton = {"event_id": "buffett_oxy", "title": f("Buffett OXY selected history"),
                "event_type": f("unknown"), "start_time": f("2023-05"),
                "end_time": f("2023-05"), "stages": [{"stage_id": "S1", "name": f("Statements"),
                "index_in_event": 0, "start_time": f("2023-05"), "end_time": f("2023-05"),
                "episodes": [episode]}]}
    return {
        "SkeletonReconstructor": skeleton,
        "SkeletonChecker": copy.deepcopy(skeleton),
        "ParticipantReconstructor": {"participants": [{"participant_id": "P_4",
            "name": f("Warren Buffett", ["Warren Buffett made a statement."]),
            "participant_type": f("individual"), "actions": []}]},
        "TransactionReconstructor": {"transactions": []},
        "EpisodeReconstructor": {**episode, "descriptions": [f("Statement")],
            "participants": "Results of ParticipantReconstructor",
            "transactions": "Results of TransactionReconstructor", "participant_relations": []},
        "StageDescriptionReconstructor": {"descriptions": [f("Selected statements")]},
        "EventDescriptionReconstructor": {"descriptions": [f("Selected OXY history")]},
    }


class PersonBuilderTest(unittest.TestCase):
    setUp = integration.IntegrationTest.setUp

    def test_legacy_person_prompt_helpers_remain_usable(self):
        self.builder.build_config = configuration()
        self.builder.agents_lm = object()
        self.builder.get_save_name = lambda name, index: f"{name}-{index}"
        expected = outputs()
        captured = []
        active = [None]

        def infer(engine, request, **kwargs):
            user = request.user_msg.format(**kwargs)
            captured.append((active[0], request.system_msg, user))
            value = copy.deepcopy(expected[active[0]])
            return types.SimpleNamespace(response=value, to_dict=lambda: {"response": value})

        def invoke(state, config):
            for name in expected:
                active[0] = name
                self.builder.execute_agent(state, name)
            return state

        self.builder.graph = lambda: types.SimpleNamespace(invoke=invoke)
        globals_ = self.builder.execute_agent.__globals__
        build_input = types.SimpleNamespace(
            user_query=types.SimpleNamespace(query_text="巴菲特 OXY", key_words=["OXY"]),
            samples=[types.SimpleNamespace(content="Warren Buffett made a statement.")])
        with patch.dict(globals_, {"InferInput": types.SimpleNamespace,
                                 "run_single_inference": infer,
                                 "_STRUCTURE_SPEC_FULL": SOURCE}):
            system, user = self.builder._get_agent_prompts()
            state = {"build_input": build_input, "agent_results": [], "agent_executed": [],
                     "cost": [], "agent_system_msgs": system, "agent_user_msgs": user}
            invoke(state, {})
            final = self.builder.integrate_results(state)
        self.assertEqual(len(captured), 7)
        for agent, system, user in captured:
            with self.subTest(agent=agent):
                self.assertIn("person_warren_buffett", user)
                self.assertIn("OXY-related statements", user)
                self.assertNotIn("financial-event type identification", system)
                self.assertNotIn("Collapse of FTX", system)
                self.assertIn("task, not factual evidence", system)
        self.assertEqual(final["stages"][0]["episodes"][0]["transactions"], [])

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

    def test_empty_person_skeleton_has_actionable_error(self):
        for skeleton in ({"stages": []}, {"stages": [{"episodes": []}]}, {"stages": "bad"}):
            with self.subTest(skeleton=skeleton), self.assertRaisesRegex(ValueError, "Person reconstruction"):
                self.builder._check_person_skeleton(skeleton)

    def test_person_schema_keeps_fields_without_domain_examples(self):
        for agent in get_person_prompts()[0]:
            text = schema_for_agent(SOURCE, agent)
            tree = ast.parse(text)
            self.assertTrue(tree.body)
            for node in tree.body:
                self.assertIsNone(ast.get_docstring(node))
                self.assertTrue(all(isinstance(item, ast.AnnAssign) for item in node.body))
            self.assertNotIn("financial shock", text)
            self.assertNotIn("Ponzi Scheme", text)
        participant = schema_for_agent(SOURCE, "ParticipantReconstructor")
        self.assertIn("participant_id: str", participant)
        self.assertIn("actions: List[Action]", participant)


if __name__ == "__main__":
    unittest.main()
