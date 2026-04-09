import json
import importlib
import os
import sys
import types
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


def _build_langgraph_shims():
    langgraph_module = types.ModuleType("langgraph")
    graph_module = types.ModuleType("langgraph.graph")
    graph_state_module = types.ModuleType("langgraph.graph.state")

    class _MessagesState(dict):
        pass

    class _StateGraph:
        def __init__(self, *args, **kwargs):
            pass

        def add_node(self, *args, **kwargs):
            return None

        def set_entry_point(self, *args, **kwargs):
            return None

        def add_conditional_edges(self, *args, **kwargs):
            return None

        def add_edge(self, *args, **kwargs):
            return None

        def compile(self, *args, **kwargs):
            return None

    graph_module.StateGraph = _StateGraph
    graph_module.END = "END"
    graph_module.MessagesState = _MessagesState
    graph_state_module.CompiledStateGraph = object
    langgraph_module.graph = graph_module
    return {
        "langgraph": langgraph_module,
        "langgraph.graph": graph_module,
        "langgraph.graph.state": graph_state_module,
    }


def _build_lmbase_shims():
    lmbase_module = types.ModuleType("lmbase")
    lmbase_inference_module = types.ModuleType("lmbase.inference")
    lmbase_inference_base_module = types.ModuleType("lmbase.inference.base")
    lmbase_inference_api_call_module = types.ModuleType("lmbase.inference.api_call")
    lmbase_utils_module = types.ModuleType("lmbase.utils")
    lmbase_utils_tools_module = types.ModuleType("lmbase.utils.tools")

    class _BaseContainer:
        pass

    class _LangChainAPIInference:
        def __init__(self, *args, **kwargs):
            pass

    class _InferInput:
        def __init__(self, *args, **kwargs):
            pass

    class _InferOutput:
        def __init__(self, *args, **kwargs):
            self.response = ""

        def to_dict(self):
            return {}

    lmbase_inference_base_module.InferInput = _InferInput
    lmbase_inference_base_module.InferOutput = _InferOutput
    lmbase_inference_module.InferInput = _InferInput
    lmbase_inference_module.InferOutput = _InferOutput
    lmbase_inference_api_call_module.LangChainAPIInference = _LangChainAPIInference
    lmbase_utils_tools_module.BaseContainer = _BaseContainer
    lmbase_module.inference = lmbase_inference_module
    lmbase_module.utils = lmbase_utils_module
    return {
        "lmbase": lmbase_module,
        "lmbase.inference": lmbase_inference_module,
        "lmbase.inference.base": lmbase_inference_base_module,
        "lmbase.inference.api_call": lmbase_inference_api_call_module,
        "lmbase.utils": lmbase_utils_module,
        "lmbase.utils.tools": lmbase_utils_tools_module,
    }


def _load_builder_module():
    fake_modules = {}
    fake_modules.update(_build_langgraph_shims())
    fake_modules.update(_build_lmbase_shims())
    with patch.dict(sys.modules, fake_modules):
        sys.modules.pop("finmy.builder.agent_build.main_build", None)
        module = importlib.import_module("finmy.builder.agent_build.main_build")
    return module.AgentEventBuilder, module


class SparseRagRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.AgentEventBuilder, cls.main_build_module = _load_builder_module()

    def setUp(self):
        self.builder = self.AgentEventBuilder.__new__(self.AgentEventBuilder)

    def _make_build_input(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(token_counts={"s1": 50, "s2": 70}),
            evidence_cards=[
                EvidenceCard(
                    sample_id="s1",
                    title="simple arrest episode",
                    excerpt="simple arrest episode",
                    source_char_count=0,
                    time_hints=["2024-05"],
                    entity_hints=["Qian Zhimin"],
                    action_hints=["arrested"],
                    money_hints=[],
                    quality_flags=[],
                ),
                EvidenceCard(
                    sample_id="s2",
                    title="money movement episode",
                    excerpt="money movement episode",
                    source_char_count=0,
                    time_hints=["2018", "2019"],
                    entity_hints=["Qian Zhimin", "Seng Hok Ling"],
                    action_hints=["transferred", "laundered"],
                    money_hints=["2.5 million", "properties"],
                    quality_flags=["money_dense"],
                ),
            ],
        )
        return SimpleNamespace(
            user_query=SimpleNamespace(query_text="q", key_words=["fraud"]),
            samples=[SimpleNamespace(content="alpha"), SimpleNamespace(content="beta")],
            context_assets=bundle,
        )

    def _make_skeleton(self):
        return {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}},
                    ],
                },
                {
                    "stage_id": "S2",
                    "episodes": [
                        {"episode_id": "E2", "name": {"value": "Money Laundering"}},
                    ],
                },
            ]
        }

    def _plan_entry(self, plan, stage_index, episode_index):
        for entry in plan["episodes"]:
            locator = entry["locator"]
            if (
                locator["stage_index"] == stage_index
                and locator["episode_index"] == episode_index
            ):
                return entry
        self.fail(f"No plan entry for stage {stage_index}, episode {episode_index}")

    def test_build_episode_execution_plan_marks_simple_episode_light(self):
        plan = self.builder._build_episode_execution_plan(
            self._make_build_input(),
            self._make_skeleton(),
        )
        self.assertEqual(self._plan_entry(plan, 0, 0)["mode"], "light")

    def test_build_episode_execution_plan_marks_money_dense_episode_full(self):
        plan = self.builder._build_episode_execution_plan(
            self._make_build_input(),
            self._make_skeleton(),
        )
        self.assertEqual(self._plan_entry(plan, 1, 0)["mode"], "full")

    def test_stage_aware_budget_marks_relation_and_timeline_complex_episodes_conservatively(self):
        from finmy.builder.agent_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        build_input = SimpleNamespace(
            user_query=SimpleNamespace(
                query_text="legal timeline reconstruction",
                key_words=["legal", "timeline"],
            ),
            samples=[
                SimpleNamespace(content="stage one remains simple and direct."),
                SimpleNamespace(
                    content="stage two legal timeline review with court hearing dates and conflicting chronology."
                ),
            ],
            context_assets=EvidenceAssetBundle.empty(),
        )
        event_skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": {"value": "Simple background"},
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Initial contact"}},
                    ],
                },
                {
                    "stage_id": "S2",
                    "name": {"value": "Legal timeline reconstruction"},
                    "episodes": [
                        {"episode_id": "E4", "name": {"value": "Court timeline review"}},
                    ],
                },
            ]
        }

        budget = build_stage_aware_execution_budget(build_input, event_skeleton)

        self.assertEqual(budget["stages"][0]["timeline_complexity"], "low")
        self.assertEqual(budget["stages"][1]["timeline_complexity"], "high")
        self.assertEqual(
            budget["episodes"][("S2", "E4")]["episode_detail_tier"], "standard"
        )
        self.assertEqual(
            budget["episodes"][("S1", "E1")]["conflict_guard"], "standard"
        )
        self.assertEqual(budget["episodes"][("S1", "E1")]["mode"], "light")
        self.assertIn(
            budget["episodes"][("S1", "E1")]["participant_tier"],
            {"minimal", "compact"},
        )

    def test_stage_aware_budget_sets_conflict_guard_when_source_overlap_is_ambiguous(self):
        from finmy.builder.agent_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        build_input = SimpleNamespace(
            user_query=SimpleNamespace(
                query_text="conflicting witness accounts and overlapping reports",
                key_words=["conflict", "overlap"],
            ),
            samples=[
                SimpleNamespace(
                    content="witness A says the transfer happened on Monday while witness B says Tuesday."
                ),
                SimpleNamespace(
                    content="witness A and witness B repeat the same names, dates, and events with inconsistent timing."
                ),
            ],
            context_assets=EvidenceAssetBundle(
                retrieval_policy=EvidenceRetrievalPolicy(),
                index=EvidenceIndex(token_counts={"s1": 10, "s2": 12}),
                evidence_cards=[
                    EvidenceCard(
                        sample_id="s1",
                        title="conflicting witness account",
                        excerpt="witness A says Monday",
                        source_char_count=0,
                        time_hints=["monday", "tuesday"],
                        entity_hints=["witness a", "witness b"],
                        action_hints=["transfer"],
                        money_hints=[],
                        quality_flags=["source_overlap", "conflict_heavy"],
                    ),
                    EvidenceCard(
                        sample_id="s2",
                        title="overlapping report",
                        excerpt="same names and dates",
                        source_char_count=0,
                        time_hints=["monday", "tuesday"],
                        entity_hints=["witness a", "witness b"],
                        action_hints=["report"],
                        money_hints=[],
                        quality_flags=["source_overlap", "conflict_heavy"],
                    ),
                ],
            ),
        )
        event_skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": {"value": "Overlapping conflict stage"},
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Ambiguous source overlap"}},
                    ],
                }
            ]
        }

        budget = build_stage_aware_execution_budget(build_input, event_skeleton)

        self.assertEqual(
            budget["episodes"][("S1", "E1")]["conflict_guard"], "strict"
        )

    def test_stage_aware_budget_keeps_unrelated_simple_stage_light_when_evidence_cards_only_match_complex_stage(self):
        from finmy.builder.agent_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        build_input = SimpleNamespace(
            user_query=SimpleNamespace(
                query_text="legal timeline and witness conflict",
                key_words=["timeline", "conflict"],
            ),
            samples=[
                SimpleNamespace(content="simple background summary with no overlap."),
                SimpleNamespace(
                    content="court timeline review of conflicting witness account."
                ),
            ],
            context_assets=EvidenceAssetBundle(
                retrieval_policy=EvidenceRetrievalPolicy(),
                index=EvidenceIndex(token_counts={"s1": 7, "s2": 11}),
                evidence_cards=[
                    EvidenceCard(
                        sample_id="s1",
                        title="court timeline review",
                        excerpt="witness timeline and conflicting account",
                        source_char_count=0,
                        time_hints=["2024-05", "2024-06"],
                        entity_hints=["witness a", "witness b"],
                        action_hints=["review"],
                        money_hints=[],
                        quality_flags=["source_overlap", "conflict_heavy"],
                    ),
                    EvidenceCard(
                        sample_id="s2",
                        title="witness conflict review",
                        excerpt="timeline and court hearing account",
                        source_char_count=0,
                        time_hints=["2024-05", "2024-06"],
                        entity_hints=["witness a", "witness b"],
                        action_hints=["hear"],
                        money_hints=[],
                        quality_flags=["source_overlap", "conflict_heavy"],
                    ),
                ],
            ),
        )
        event_skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": {"value": "Simple background"},
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Initial contact"}},
                    ],
                },
                {
                    "stage_id": "S2",
                    "name": {"value": "Legal timeline reconstruction"},
                    "episodes": [
                        {"episode_id": "E4", "name": {"value": "Court timeline review"}},
                    ],
                },
            ]
        }

        budget = build_stage_aware_execution_budget(build_input, event_skeleton)

        self.assertEqual(budget["stages"][0]["timeline_complexity"], "low")
        self.assertEqual(budget["episodes"][("S1", "E1")]["conflict_guard"], "standard")
        self.assertEqual(budget["episodes"][("S1", "E1")]["mode"], "light")
        self.assertEqual(budget["episodes"][("S2", "E4")]["conflict_guard"], "strict")
        self.assertEqual(budget["episodes"][("S2", "E4")]["mode"], "full")

    def test_run_initializes_empty_episode_execution_plan(self):
        build_input = self._make_build_input()
        observed_state = {}

        class DummyApp:
            def invoke(self, state, config=None):
                observed_state.update(state)
                return state

        self.builder._get_agent_prompts = lambda: ({}, {})
        self.builder.graph = lambda: DummyApp()
        self.builder.integrate_results = lambda state: state
        self.builder.integrate_from_files = lambda: {}
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.build_config = {"graph_config": {}}

        self.builder.run(build_input)

        self.assertEqual(observed_state["episode_execution_plan"], {"episodes": []})

    def test_skeleton_checker_populates_episode_execution_plan(self):
        build_input = self._make_build_input()
        skeleton = self._make_skeleton()
        state = {
            "build_input": build_input,
            "agent_results": [{"SkeletonReconstructor": skeleton}],
            "agent_executed": ["SkeletonReconstructor"],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "system {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user"},
            "episode_execution_plan": {"episodes": []},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        fake_output = types.SimpleNamespace(
            response="{}",
            to_dict=lambda: {"response": "{}"},
        )

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder._build_local_context_package = lambda *args, **kwargs: None
        self.builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        self.builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"
        self.builder._validate_event_skeleton = lambda skeleton_dict: (True, "")

        with patch.object(
            self.main_build_module, "run_single_inference", return_value=fake_output
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value=skeleton,
        ):
            self.builder.execute_agent(state, "SkeletonChecker")

        self.assertEqual(len(state["episode_execution_plan"]["episodes"]), 2)
        self.assertEqual(
            self._plan_entry(state["episode_execution_plan"], 0, 0)["mode"],
            "light",
        )

    def test_skeleton_checker_populates_stage_aware_execution_budget(self):
        skeleton = self._make_skeleton()
        state = {
            "build_input": self._make_build_input(),
            "agent_results": [{"SkeletonReconstructor": skeleton}],
            "agent_executed": ["SkeletonReconstructor"],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "system {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user"},
            "episode_execution_plan": {"episodes": []},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        fake_output = types.SimpleNamespace(
            response=json.dumps(skeleton),
            to_dict=lambda: {"response": "{}"},
        )

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder._build_local_context_package = lambda *args, **kwargs: None
        self.builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        self.builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"
        self.builder._validate_event_skeleton = lambda skeleton_dict: (True, "")

        with patch.object(
            self.main_build_module, "run_single_inference", return_value=fake_output
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value=skeleton,
        ):
            self.builder.execute_agent(state, "SkeletonChecker")

        entry = self._plan_entry(state["episode_execution_plan"], 0, 0)
        self.assertEqual(entry["locator"]["stage_id"], "S1")
        self.assertEqual(entry["locator"]["episode_id"], "E1")
        self.assertIn(entry["mode"], {"light", "full"})
        self.assertIn(entry["participant_tier"], {"minimal", "compact", "standard"})
        self.assertIn(
            entry["transaction_tier"], {"skip", "minimal", "compact", "standard"}
        )
        self.assertIn(entry["episode_detail_tier"], {"compact", "standard"})
        self.assertIn(entry["conflict_guard"], {"standard", "strict"})

    def test_route_after_participant_reconstructor_uses_budget_transaction_tier(self):
        state = {
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "full",
                        "transaction_tier": "skip",
                        "detail_tier": "standard",
                    }
                ]
            },
            "agent_results": [],
        }

        self.builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}},
                    ],
                }
            ]
        }
        self.builder.extract_latest_episode = lambda _skeleton, _count: (
            {"stage_id": "S1", "index_in_event": 0},
            {"episode_id": "E1", "name": {"value": "Arrest"}, "index_in_stage": 0},
        )

        self.assertEqual(
            self.builder._route_after_participant_reconstructor(state),
            "EpisodeReconstructor",
        )

    def test_skeleton_checker_uses_locator_order_when_episode_ids_are_blank(self):
        skeleton = {
            "stages": [
                {
                    "stage_id": "",
                    "name": {"value": "Simple background"},
                    "episodes": [
                        {
                            "episode_id": "",
                            "name": {"value": "Initial contact"},
                        }
                    ],
                },
                {
                    "stage_id": "",
                    "name": {"value": "Legal timeline reconstruction"},
                    "episodes": [
                        {
                            "episode_id": "",
                            "name": {"value": "Court timeline review"},
                        }
                    ],
                },
            ]
        }

        plan = self.builder._build_episode_execution_plan(
            self._make_build_input(),
            skeleton,
        )

        first_entry = self._plan_entry(plan, 0, 0)
        second_entry = self._plan_entry(plan, 1, 0)
        self.assertEqual(first_entry["locator"]["stage_index"], 0)
        self.assertEqual(second_entry["locator"]["stage_index"], 1)
        self.assertNotEqual(first_entry["mode"], second_entry["mode"])
        self.assertNotEqual(first_entry["transaction_tier"], second_entry["transaction_tier"])

    def test_episode_reconstructor_full_mode_with_skip_transaction_tier_keeps_transactions_empty(self):
        builder = self.builder
        builder.agents_lm = object()
        builder.save_traces = lambda *args, **kwargs: None
        builder._build_local_context_package = lambda *args, **kwargs: None
        builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"

        state = {
            "build_input": self._make_build_input(),
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                    }
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    }
                },
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"EpisodeReconstructor": "sys"},
            "agent_user_msgs": {"EpisodeReconstructor": "user"},
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "full",
                        "transaction_tier": "skip",
                        "detail_tier": "standard",
                    }
                ]
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        fake_output = types.SimpleNamespace(
            response=json.dumps(
                {
                    "episode_id": "E1",
                    "name": {"value": "Arrest"},
                    "index_in_stage": 0,
                    "participants": "Results of ParticipantReconstructor",
                    "transactions": "Results of TransactionReconstructor",
                    "participant_relations": [],
                    "descriptions": [],
                }
            ),
            to_dict=lambda: {"response": "{}"},
        )

        with patch.object(
            self.main_build_module, "run_single_inference", return_value=fake_output
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value={
                "episode_id": "E1",
                "name": {"value": "Arrest"},
                "index_in_stage": 0,
                "participants": "Results of ParticipantReconstructor",
                "transactions": "Results of TransactionReconstructor",
                "participant_relations": [],
                "descriptions": [],
            },
        ):
            builder.execute_agent(state, "EpisodeReconstructor")

        self.assertTrue(state["agent_results"][-1]["_meta"]["transaction_step_skipped"])

        final_cascade = builder.integrate_results(state)
        episode = final_cascade["stages"][0]["episodes"][0]
        self.assertEqual(episode["transactions"], [])
        self.assertEqual(episode["participants"][0]["participant_id"], "P1")

    def test_route_after_participant_reconstructor_skips_transaction_for_light_episode(self):
        state = {
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    }
                ]
            },
            "agent_results": [],
        }

        self.builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}},
                    ],
                }
            ]
        }
        self.builder.extract_latest_episode = lambda _skeleton, _count: (
            {"stage_id": "S1", "index_in_event": 0},
            {"episode_id": "E1", "name": {"value": "Arrest"}, "index_in_stage": 0},
        )

        self.assertEqual(
            self.builder._route_after_participant_reconstructor(state),
            "EpisodeReconstructor",
        )

    def test_route_after_participant_reconstructor_keeps_full_episode_on_full_mode(self):
        state = {
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "full",
                        "detail_tier": "standard",
                    }
                ]
            },
            "agent_results": [],
        }

        self.builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Money Laundering"},
                        },
                    ],
                }
            ]
        }
        self.builder.extract_latest_episode = lambda _skeleton, _count: (
            {"stage_id": "S1", "index_in_event": 0},
            {
                "episode_id": "E1",
                "name": {"value": "Money Laundering"},
                "index_in_stage": 0,
            },
        )

        self.assertEqual(
            self.builder._route_after_participant_reconstructor(state),
            "TransactionReconstructor",
        )

    def test_episode_reconstructor_light_mode_receives_compactness_hint(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": {"value": "Arrest"},
                        "index_in_stage": 0,
                        "start_time": {"value": "2025-01-01", "reason": "evidence"},
                        "end_time": {"value": "2025-01-02", "reason": "evidence"},
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
                to_dict=lambda: {"response": "raw"},
            )

        builder = self.builder
        builder.agents_lm = object()
        builder.save_traces = lambda *args, **kwargs: None
        builder._build_local_context_package = lambda *args, **kwargs: None
        builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"

        state = {
            "build_input": self._make_build_input(),
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                    }
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    }
                },
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"EpisodeReconstructor": "sys"},
            "agent_user_msgs": {"EpisodeReconstructor": "user"},
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    }
                ]
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.main_build_module, "run_single_inference", side_effect=fake_run_single_inference
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value={},
        ):
            builder.execute_agent(state, "EpisodeReconstructor")

        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "light")
        self.assertEqual(captured["prompt_kwargs"]["TransactionDetailTier"], "compact")
        self.assertIn("EpisodeCompactnessHint", captured["prompt_kwargs"])
        self.assertIn(
            "compact-light-mode",
            captured["prompt_kwargs"]["EpisodeCompactnessHint"],
        )
        self.assertIn("P1", captured["prompt_kwargs"]["TargetEpisodeContext"])

    def test_route_after_participant_reconstructor_uses_global_cursor_after_light_episode(self):
        state = {
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "EpisodeReconstructor",
                "ParticipantReconstructor",
            ],
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    },
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        },
                        "mode": "full",
                        "detail_tier": "standard",
                    },
                ]
            },
            "agent_results": [],
        }

        self.builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}},
                        {"episode_id": "E2", "name": {"value": "Money Laundering"}},
                    ],
                }
            ]
        }

        self.assertEqual(
            self.builder._route_after_participant_reconstructor(state),
            "TransactionReconstructor",
        )

    def test_transaction_reconstructor_targets_second_episode_after_light_first_episode(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(response="{}", to_dict=lambda: {})

        builder = self.builder
        builder.agents_lm = object()
        builder.save_traces = lambda *args, **kwargs: None
        builder._build_local_context_package = lambda *args, **kwargs: None
        builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"
        builder._attach_compact_heavy_agent_prompt_kwargs = (
            lambda *args, **kwargs: None
        )
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                        },
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                        },
                    ],
                }
            ]
        }

        state = {
            "build_input": self._make_build_input(),
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                    },
                                    {
                                        "episode_id": "E2",
                                        "name": {"value": "Money Laundering"},
                                        "index_in_stage": 1,
                                    },
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    }
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E1",
                        "name": {"value": "Arrest"},
                        "index_in_stage": 0,
                        "participants": [{"participant_id": "P1"}],
                        "transactions": [],
                        "participant_relations": [],
                        "descriptions": [],
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P2"}]
                    }
                },
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "EpisodeReconstructor",
                "ParticipantReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {"TransactionReconstructor": "user"},
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    },
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        },
                        "mode": "full",
                        "detail_tier": "standard",
                    },
                ]
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.main_build_module, "run_single_inference", side_effect=fake_run_single_inference
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value={},
        ):
            builder.execute_agent(state, "TransactionReconstructor")

        self.assertEqual(captured["prompt_kwargs"]["TargetEpisode"].episode_id, "E2")

    def test_transaction_reconstructor_local_context_targets_second_episode_after_light_first_episode(self):
        captured = {}

        class FakeLocalContextBuilder:
            def build(self, request, bundle):
                captured["request"] = request
                return SimpleNamespace(
                    rendered_context="CTX",
                    summary={},
                    query_bundle={},
                    budget_summary={},
                    memory={},
                    retrieval_status="sufficient",
                )

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            return SimpleNamespace(response="{}", to_dict=lambda: {})

        builder = self.builder
        builder.agents_lm = object()
        builder.save_traces = lambda *args, **kwargs: None
        builder._rewrite_heavy_agent_user_msg_template = lambda *args, **kwargs: "user"
        builder._attach_compact_heavy_agent_prompt_kwargs = (
            lambda *args, **kwargs: None
        )
        builder._attach_local_context_prompt_kwargs = lambda *args, **kwargs: None
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                        },
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                        },
                    ],
                }
            ]
        }

        state = {
            "build_input": self._make_build_input(),
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                    },
                                    {
                                        "episode_id": "E2",
                                        "name": {"value": "Money Laundering"},
                                        "index_in_stage": 1,
                                    },
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    }
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E1",
                        "name": {"value": "Arrest"},
                        "index_in_stage": 0,
                        "participants": [{"participant_id": "P1"}],
                        "transactions": [],
                        "participant_relations": [],
                        "descriptions": [],
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P2"}]
                    }
                },
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "EpisodeReconstructor",
                "ParticipantReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {"TransactionReconstructor": "user"},
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    },
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        },
                        "mode": "full",
                        "detail_tier": "standard",
                    },
                ]
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.main_build_module, "LocalContextBuilder", return_value=FakeLocalContextBuilder()
        ), patch.object(
            self.main_build_module, "run_single_inference", side_effect=fake_run_single_inference
        ), patch.object(
            self.main_build_module,
            "extract_json_response",
            return_value={},
        ):
            builder.execute_agent(state, "TransactionReconstructor")

        self.assertEqual(captured["request"].target_episode, "Money Laundering")

    def test_integrate_results_preserves_light_episode_empty_transactions_and_keeps_full_episode_transactions(self):
        builder = self.builder
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                        },
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                        },
                    ],
                }
            ]
        }

        state = {
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                        "participants": [],
                                        "transactions": [],
                                    },
                                    {
                                        "episode_id": "E2",
                                        "name": {"value": "Money Laundering"},
                                        "index_in_stage": 1,
                                        "participants": [],
                                        "transactions": [],
                                    },
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    }
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E1",
                        "name": {"value": "Arrest"},
                        "index_in_stage": 0,
                        "participants": [{"participant_id": "P1"}],
                        "transactions": [],
                        "participant_relations": [],
                        "descriptions": [],
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P2"}]
                    }
                },
                {
                    "TransactionReconstructor": {
                        "transactions": [
                            {
                                "transaction_id": "T_1",
                                "name": {"value": "Transaction 1"},
                                "transaction_type": {"value": "transfer"},
                                "timestamp": {"value": "2025-01-01"},
                                "details": {"value": "Episode-level transaction"},
                                "from_participant_id": "P_1",
                                "to_participant_id": "P_2",
                                "instruments": [],
                            }
                        ]
                    }
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E2",
                        "name": {"value": "Money Laundering"},
                        "index_in_stage": 1,
                        "participants": [{"participant_id": "P2"}],
                        "transactions": [],
                        "participant_relations": [],
                        "descriptions": [],
                    }
                },
            ],
            "episode_execution_plan": {
                "episodes": [
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "mode": "light",
                        "detail_tier": "compact",
                    },
                    {
                        "locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        },
                        "mode": "full",
                        "detail_tier": "standard",
                    },
                ]
            },
        }

        final_cascade = builder.integrate_results(state)
        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["transactions"], [])
        self.assertEqual(episodes[1]["transactions"][0]["transaction_id"], "T_1")

    def test_integrate_from_files_replays_mixed_light_then_full_transactions_correctly(self):
        builder = self.builder
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}, "index_in_stage": 0},
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                        },
                    ],
                }
            ]
        }

        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Arrest"}, "index_in_stage": 0},
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                        },
                    ],
                }
            ]
        }
        participant_one = {"participants": [{"participant_id": "P1"}]}
        participant_two = {"participants": [{"participant_id": "P2"}]}
        transaction_two = {
            "transactions": [
                {
                    "transaction_id": "T_1",
                    "name": {"value": "Transaction 1"},
                    "transaction_type": {"value": "transfer"},
                    "timestamp": {"value": "2025-01-01"},
                    "details": {"value": "Episode-level transaction"},
                    "from_participant_id": "P_1",
                    "to_participant_id": "P_2",
                    "instruments": [],
                }
            ]
        }
        episode_one = {
            "episode_id": "E1",
            "name": {"value": "Arrest"},
            "index_in_stage": 0,
            "participants": [{"participant_id": "P1"}],
            "transactions": [],
            "participant_relations": [],
            "descriptions": [],
        }
        episode_two = {
            "episode_id": "E2",
            "name": {"value": "Money Laundering"},
            "index_in_stage": 1,
            "participants": [{"participant_id": "P2"}],
            "transactions": [],
            "participant_relations": [],
            "descriptions": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            builder.save_dir = tmpdir
            files = {
                "SkeletonChecker-1-Result.json": {"stages": skeleton["stages"]},
                "ParticipantReconstructor-2-Result.json": participant_one,
                "EpisodeReconstructor-3-Result.json": episode_one,
                "ParticipantReconstructor-4-Result.json": participant_two,
                "TransactionReconstructor-5-Result.json": transaction_two,
                "EpisodeReconstructor-6-Result.json": episode_two,
            }
            for filename, payload in files.items():
                with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
                    json.dump(payload, f)

            final_cascade = builder.integrate_from_files()

        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["transactions"], [])
        self.assertEqual(episodes[1]["transactions"][0]["transaction_id"], "T_1")

    def test_integrate_results_uses_episode_locator_when_transaction_result_missing(self):
        builder = self.builder
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                            "participants": [],
                            "transactions": [],
                        },
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                            "participants": [],
                            "transactions": [],
                        },
                    ],
                }
            ]
        }

        state = {
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                        "participants": [],
                                        "transactions": [],
                                    },
                                    {
                                        "episode_id": "E2",
                                        "name": {"value": "Money Laundering"},
                                        "index_in_stage": 1,
                                        "participants": [],
                                        "transactions": [],
                                    }
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    },
                    "_meta": {
                        "episode_locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        }
                    },
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E2",
                        "name": {"value": "Money Laundering"},
                        "index_in_stage": 1,
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    },
                    "_meta": {
                        "episode_locator": {
                            "stage_index": 0,
                            "episode_index": 1,
                            "stage_id": "S1",
                            "episode_id": "E2",
                        },
                        "execution_mode": "light",
                    },
                },
            ],
            "agent_executed": ["ParticipantReconstructor", "EpisodeReconstructor"],
        }

        final_cascade = builder.integrate_results(state)
        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["participants"], [])
        self.assertEqual(episodes[0]["transactions"], [])
        self.assertEqual(episodes[1]["participants"][0]["participant_id"], "P1")
        self.assertEqual(episodes[1]["transactions"], [])

    def test_integrate_results_discards_fabricated_light_mode_transactions_without_transaction_result(self):
        builder = self.builder
        builder._get_event_skeleton = lambda _state: {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                            "participants": [],
                            "transactions": [],
                        }
                    ],
                }
            ]
        }

        state = {
            "agent_results": [
                {
                    "SkeletonChecker": {
                        "stages": [
                            {
                                "stage_id": "S1",
                                "episodes": [
                                    {
                                        "episode_id": "E1",
                                        "name": {"value": "Arrest"},
                                        "index_in_stage": 0,
                                        "participants": [],
                                        "transactions": [],
                                    }
                                ],
                            }
                        ]
                    }
                },
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P1"}]
                    },
                    "_meta": {
                        "episode_locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "execution_mode": "light",
                        "detail_tier": "compact",
                    },
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E1",
                        "name": {"value": "Arrest"},
                        "index_in_stage": 0,
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": [
                            {
                                "transaction_id": "T_fake",
                                "name": {"value": "Fabricated"},
                            }
                        ],
                        "participant_relations": [],
                        "descriptions": [],
                    },
                    "_meta": {
                        "episode_locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "execution_mode": "light",
                        "detail_tier": "compact",
                    },
                },
            ],
            "agent_executed": ["ParticipantReconstructor", "EpisodeReconstructor"],
        }

        final_cascade = builder.integrate_results(state)
        episode = final_cascade["stages"][0]["episodes"][0]
        self.assertEqual(episode["participants"][0]["participant_id"], "P1")
        self.assertEqual(episode["transactions"], [])

    def test_integrate_from_files_uses_episode_locator_when_replay_results_only_cover_second_episode(self):
        builder = self.builder
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Arrest"},
                            "index_in_stage": 0,
                            "participants": [],
                            "transactions": [],
                        },
                        {
                            "episode_id": "E2",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 1,
                            "participants": [],
                            "transactions": [],
                        },
                    ],
                }
            ]
        }
        participant_two = {"participants": [{"participant_id": "P2"}]}
        episode_two = {
            "episode_id": "E2",
            "name": {"value": "Money Laundering"},
            "index_in_stage": 1,
            "participants": "Results of ParticipantReconstructor",
            "transactions": "Results of TransactionReconstructor",
            "participant_relations": [],
            "descriptions": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            builder.save_dir = tmpdir
            files = {
                "SkeletonChecker-1-Result.json": skeleton,
                "ParticipantReconstructor-2-Stage0-Episode1-Result.json": participant_two,
                "EpisodeReconstructor-3-Stage0-Episode1-Result.json": episode_two,
            }
            for filename, payload in files.items():
                with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
                    json.dump(payload, f)

            final_cascade = builder.integrate_from_files()

        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["participants"], [])
        self.assertEqual(episodes[0]["transactions"], [])
        self.assertEqual(episodes[1]["participants"][0]["participant_id"], "P2")
        self.assertEqual(episodes[1]["transactions"], [])

    def test_integrate_from_files_restores_execution_mode_metadata_for_full_episode(self):
        builder = self.builder
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 0,
                            "participants": [],
                            "transactions": [],
                        }
                    ],
                }
            ]
        }
        participant_one = {
            "ParticipantReconstructor": {
                "participants": [{"participant_id": "P1"}]
            },
            "_meta": {
                "episode_locator": {
                    "stage_index": 0,
                    "episode_index": 0,
                    "stage_id": "S1",
                    "episode_id": "E1",
                },
                "execution_mode": "full",
                "detail_tier": "standard",
            },
        }
        episode_one = {
            "EpisodeReconstructor": {
                "episode_id": "E1",
                "name": {"value": "Money Laundering"},
                "index_in_stage": 0,
                "participants": "Results of ParticipantReconstructor",
                "transactions": [
                    {
                        "transaction_id": "T_1",
                        "name": {"value": "Transaction 1"},
                    }
                ],
                "participant_relations": [],
                "descriptions": [],
            },
            "_meta": {
                "episode_locator": {
                    "stage_index": 0,
                    "episode_index": 0,
                    "stage_id": "S1",
                    "episode_id": "E1",
                },
                "execution_mode": "full",
                "detail_tier": "standard",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            builder.save_dir = tmpdir
            files = {
                "SkeletonChecker-1-Result.json": skeleton,
                "ParticipantReconstructor-2-Stage0-Episode0-Result.json": participant_one,
                "EpisodeReconstructor-3-Stage0-Episode0-Result.json": episode_one,
            }
            for filename, payload in files.items():
                with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
                    json.dump(payload, f)

            final_cascade = builder.integrate_from_files()

        episode = final_cascade["stages"][0]["episodes"][0]
        self.assertEqual(episode["participants"][0]["participant_id"], "P1")
        self.assertEqual(episode["transactions"][0]["transaction_id"], "T_1")

    def test_integrate_from_files_full_episode_without_transaction_artifact_clears_placeholder(self):
        builder = self.builder
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "episodes": [
                        {
                            "episode_id": "E1",
                            "name": {"value": "Money Laundering"},
                            "index_in_stage": 0,
                            "participants": [],
                            "transactions": [],
                        }
                    ],
                }
            ]
        }
        participant_one = {
            "ParticipantReconstructor": {
                "participants": [{"participant_id": "P1"}]
            },
            "_meta": {
                "episode_locator": {
                    "stage_index": 0,
                    "episode_index": 0,
                    "stage_id": "S1",
                    "episode_id": "E1",
                },
                "execution_mode": "full",
                "detail_tier": "standard",
            },
        }
        episode_one = {
            "EpisodeReconstructor": {
                "episode_id": "E1",
                "name": {"value": "Money Laundering"},
                "index_in_stage": 0,
                "participants": "Results of ParticipantReconstructor",
                "transactions": "Results of TransactionReconstructor",
                "participant_relations": [],
                "descriptions": [],
            },
            "_meta": {
                "episode_locator": {
                    "stage_index": 0,
                    "episode_index": 0,
                    "stage_id": "S1",
                    "episode_id": "E1",
                },
                "execution_mode": "full",
                "detail_tier": "standard",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            builder.save_dir = tmpdir
            files = {
                "SkeletonChecker-1-Result.json": skeleton,
                "ParticipantReconstructor-2-Stage0-Episode0-Result.json": participant_one,
                "EpisodeReconstructor-3-Stage0-Episode0-Result.json": episode_one,
            }
            for filename, payload in files.items():
                with open(os.path.join(tmpdir, filename), "w", encoding="utf-8") as f:
                    json.dump(payload, f)

            final_cascade = builder.integrate_from_files()

        episode = final_cascade["stages"][0]["episodes"][0]
        self.assertEqual(episode["participants"][0]["participant_id"], "P1")
        self.assertEqual(episode["transactions"], [])
