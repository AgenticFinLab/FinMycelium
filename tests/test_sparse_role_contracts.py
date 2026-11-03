"""Cross-role data flow and schema regression tests with synthetic events."""

import copy
import unittest
from types import SimpleNamespace

from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.validation import validate_cascade, validate_role, validate_skeleton
from finmy.generic import DataSample, UserQueryInput


def vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def cascade():
    return {
        "event_id": "synthetic-storm", "title": vf("Storm response"),
        "event_type": vf("emergency response"), "descriptions": [],
        "stages": [
            {
                "stage_id": f"S{index + 1}", "name": vf(name),
                "index_in_event": index, "descriptions": [],
                "episodes": [{
                    "episode_id": "E1", "name": vf(name), "index_in_stage": 0,
                    "descriptions": [vf("episode-detail-marker")],
                    "participants": [{
                        "participant_id": "P_1", "name": vf("Local service"),
                        "actions": [{"name": vf("action-detail-marker"), "details": []}],
                    }],
                    "participant_relations": [], "transactions": [],
                }],
            } for index, name in enumerate(("Warning", "Recovery"))
        ],
    }


class RoleContractTest(unittest.TestCase):
    def setUp(self):
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {"sparse_builder_config": {"enable_sparse_routing": False}}
        self.inputs = SimpleNamespace(
            user_query=UserQueryInput(query_text="Storm response", key_words=[]),
            samples=[DataSample(sample_id="s1", raw_data_id="r1", content="A storm warning preceded recovery.")],
        )

    def state(self):
        graph = cascade()
        episode = graph["stages"][0]["episodes"][0]
        locator = self.builder._episode_locator(0, 0, "S1", "E1")
        results = [
            {"SkeletonChecker": graph},
            {"ParticipantReconstructor": {"participants": episode["participants"]}, "_meta": {"episode_locator": locator}},
            {"EpisodeReconstructor": episode, "_meta": {"episode_locator": locator}},
        ]
        return {
            "build_input": self.inputs, "agent_results": results,
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor", "EpisodeReconstructor"],
            "episode_execution_plan": self.builder._build_episode_execution_plan(self.inputs, graph),
        }

    def render(self, state, role):
        stage, episode, budget, extra = self.builder._prompt_context_for_agent(state, role)
        kwargs = self.builder._build_prompt_kwargs(
            self.inputs, role, target_stage=stage, target_episode=episode,
            episode_budget=budget, **extra,
        )
        return self.builder._format_agent_messages(role, kwargs)

    def test_all_roles_receive_shared_structure_definitions(self):
        roles, _ = self.builder._get_agent_prompts()
        for role in roles:
            with self.subTest(role=role):
                kwargs = self.builder._build_prompt_kwargs(self.inputs, role)
                system, _ = self.builder._format_agent_messages(role, kwargs)
                self.assertIn("class VerifiableField", system)
                self.assertIn("evidence_source_contents", system)
                self.assertNotIn("{STRUCTURE_SPEC}", system)

    def test_next_stage_participant_sees_previous_identity(self):
        state = self.state()
        state["agent_executed"].append("StageDescriptionReconstructor")
        _, user = self.render(state, "ParticipantReconstructor")
        self.assertIn('"participant_id": "P_1"', user)
        self.assertIn("action-detail-marker", user)
        self.assertIn("Recovery", user)

    def test_stage_and_event_descriptions_see_completed_graph_content(self):
        for role in ("StageDescriptionReconstructor", "EventDescriptionReconstructor"):
            with self.subTest(role=role):
                _, user = self.render(self.state(), role)
                self.assertIn("episode-detail-marker", user)
                self.assertIn("action-detail-marker", user)

    def test_disabled_sparse_routing_is_full_for_every_episode(self):
        plan = self.builder._build_episode_execution_plan(self.inputs, cascade())
        self.assertEqual(len(plan["episodes"]), 2)
        for entry in plan["episodes"]:
            self.assertEqual(entry["mode"], "full")
            self.assertEqual(entry["transaction_tier"], "standard")
            self.assertFalse(self.builder._transaction_step_skipped(entry))

    def test_minimal_transaction_tier_is_not_skip(self):
        self.assertFalse(self.builder._transaction_step_skipped({"mode": "light", "transaction_tier": "minimal"}))
        self.assertTrue(self.builder._transaction_step_skipped({"mode": "full", "transaction_tier": "skip"}))

    def test_full_graph_validation_does_not_mutate_input(self):
        graph = cascade()
        before = copy.deepcopy(graph)
        validate_cascade(graph)
        self.assertEqual(graph, before)

    def test_invalid_shapes_ids_and_references_are_rejected(self):
        mutations = [
            lambda g: g.update(stages=[]),
            lambda g: g["stages"].append(copy.deepcopy(g["stages"][0])),
            lambda g: g["stages"][0].update(index_in_event=True),
            lambda g: g["title"].update(confidence=2),
            lambda g: g["stages"][0]["episodes"][0].update(participants="placeholder"),
            lambda g: g["stages"][0]["episodes"][0]["participants"].append(
                copy.deepcopy(g["stages"][0]["episodes"][0]["participants"][0])),
            lambda g: g["stages"][0]["episodes"][0]["participants"][0].update(attributes=[]),
            lambda g: g["stages"][0]["episodes"][0].update(participant_relations=[{
                "from_participant_id": "P_1", "to_participant_id": "missing",
            }]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                graph = cascade()
                mutate(graph)
                with self.assertRaises(ValueError):
                    validate_cascade(graph)

    def test_role_outputs_cannot_add_unrecognized_top_level_fields(self):
        for role, key in (("ParticipantReconstructor", "participants"),
                          ("TransactionReconstructor", "transactions"),
                          ("EventDescriptionReconstructor", "descriptions")):
            with self.subTest(role=role):
                with self.assertRaises(ValueError):
                    validate_role(role, {key: [], "extra": "unexpected"})

    def test_skeleton_rejects_duplicate_episode_within_stage(self):
        graph = cascade()
        graph["stages"][0]["episodes"].append(copy.deepcopy(graph["stages"][0]["episodes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_skeleton(graph)


if __name__ == "__main__":
    unittest.main()
