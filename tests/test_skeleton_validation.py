import unittest
import json
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

from finmy.context.assets import EvidenceAssetBundle


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
            for key, value in kwargs.items():
                setattr(self, key, value)

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
    return module


try:
    import finmy.builder.agent_build.main_build as main_build_module
except ModuleNotFoundError as exc:
    missing_module = exc.name or ""
    if missing_module.split(".")[0] not in {"langgraph", "lmbase"}:
        raise
    main_build_module = _load_builder_module()

AgentEventBuilder = main_build_module.AgentEventBuilder


def _vf(value):
    return {
        "value": value,
        "evidence_source_contents": [],
        "reasons": [],
        "confidence": 1.0,
    }


def _episode(name="Episode 1", start="2025-01-01", end="2025-01-02"):
    return {
        "episode_id": "E1",
        "name": _vf(name),
        "index_in_stage": 0,
        "start_time": _vf(start),
        "end_time": _vf(end),
    }


def _stage(name="Stage 1", episodes=None, start="2025-01-01", end="2025-01-02"):
    return {
        "stage_id": "S1",
        "name": _vf(name),
        "index_in_event": 0,
        "start_time": _vf(start),
        "end_time": _vf(end),
        "episodes": episodes if episodes is not None else [_episode()],
    }


def _skeleton(title="Demo Event", stages=None):
    return {
        "event_id": "demo_event",
        "title": _vf(title),
        "event_type": _vf("demo"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": stages if stages is not None else [_stage()],
    }


def _build_input(sample_contents):
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="demo query", key_words=["demo"]),
        samples=[SimpleNamespace(content=content) for content in sample_contents],
        context_assets=EvidenceAssetBundle.empty(),
    )


def _participant(participant_id="P_1", name="Participant 1"):
    return {
        "participant_id": participant_id,
        "name": _vf(name),
        "participant_type": "organization",
        "base_role": _vf("counterparty"),
        "attributes": {},
        "actions": [],
    }


def _transaction_participants():
    return {
        "participants": [
            {
                "participant_id": "P_1",
                "name": _vf("Participant 1"),
                "participant_type": "organization",
                "base_role": _vf("payer"),
                "attributes": {},
                "actions": [],
            },
            {
                "participant_id": "P_2",
                "name": _vf("Participant 2"),
                "participant_type": "organization",
                "base_role": _vf("receiver"),
                "attributes": {},
                "actions": [],
            },
        ]
    }


def _episode_transactions():
    return {
        "transactions": [
            {
                "transaction_id": "T_1",
                "name": _vf("Transaction 1"),
                "transaction_type": _vf("transfer"),
                "timestamp": _vf("2025-01-01"),
                "details": _vf("Episode-level transaction"),
                "from_participant_id": "P_1",
                "to_participant_id": "P_2",
                "instruments": [],
            }
        ]
    }


def _full_episode(name="Episode 1", start="2025-01-01", end="2025-01-02"):
    return {
        "episode_id": "E1",
        "name": _vf(name),
        "index_in_stage": 0,
        "descriptions": [_vf("episode description")],
        "start_time": _vf(start),
        "end_time": _vf(end),
        "participants": [_participant()],
        "participant_relations": [],
        "transactions": [],
    }


def _full_stage(name="Stage 1", episodes=None, start="2025-01-01", end="2025-01-02"):
    return {
        "stage_id": "S1",
        "name": _vf(name),
        "index_in_event": 0,
        "descriptions": [_vf("stage description")],
        "start_time": _vf(start),
        "end_time": _vf(end),
        "episodes": episodes if episodes is not None else [_full_episode()],
    }


def _full_skeleton(title="Demo Event", stages=None):
    return {
        "event_id": "demo_event",
        "title": _vf(title),
        "event_type": _vf("demo"),
        "descriptions": [_vf("event description")],
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": stages if stages is not None else [_full_stage()],
    }


class SkeletonValidationTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

    def _install_single_response_inference(self, response_text):
        call_count = {"value": 0}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input, prompt_kwargs
            call_count["value"] += 1
            return SimpleNamespace(
                response=response_text,
                to_dict=lambda: {"response": response_text},
            )

        original_run_single_inference = main_build_module.run_single_inference
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        main_build_module.run_single_inference = fake_run_single_inference
        return call_count

    def test_blank_strings_are_treated_as_unknown_values(self):
        self.assertTrue(self.builder._is_unknown_value("   "))

    def test_validate_skeleton_rejects_empty_stages(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton(stages=[]))
        self.assertFalse(valid)
        self.assertEqual(reason, "no_stages")

    def test_validate_skeleton_rejects_zero_total_episodes(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(stages=[_stage(episodes=[])])
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "no_episodes")

    def test_validate_skeleton_rejects_stage_with_zero_episodes(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(stages=[_stage(episodes=[]), _stage(name="Stage 2")])
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "empty_stage_detected")

    def test_validate_skeleton_rejects_unknown_title(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(title="unknown")
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_event_title")

    def test_validate_skeleton_rejects_blank_title(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton(title="   "))
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_event_title")

    def test_validate_skeleton_rejects_semantically_empty_stage_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        name="unknown",
                        start="unknown",
                        end="unknown",
                        episodes=[_episode()],
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_stage_fields")

    def test_validate_skeleton_rejects_blank_only_stage_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        name="   ",
                        start=" ",
                        end="\t",
                        episodes=[_episode()],
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_stage_fields")

    def test_validate_skeleton_rejects_semantically_empty_episode_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        episodes=[
                            _episode(name="unknown", start="unknown", end="unknown")
                        ]
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_episode_fields")

    def test_validate_skeleton_rejects_blank_only_episode_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[_stage(episodes=[_episode(name=" ", start="\n", end="\t")])]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_episode_fields")

    def test_validate_skeleton_accepts_minimal_meaningful_structure(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton())
        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_get_event_skeleton_prefers_latest_checker_result(self):
        state = {
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonChecker": _skeleton(title="first checker")},
                {"SkeletonReconstructor": _skeleton(title="second recon")},
                {"SkeletonChecker": _skeleton(title="second checker")},
            ]
        }
        result = self.builder._get_event_skeleton(state)
        self.assertEqual(result["title"]["value"], "second checker")

    def test_get_event_skeleton_falls_back_to_latest_reconstructor_result(self):
        state = {
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonReconstructor": _skeleton(title="second recon")},
            ]
        }
        result = self.builder._get_event_skeleton(state)
        self.assertEqual(result["title"]["value"], "second recon")

    def test_skeleton_checker_uses_latest_reconstructor_result_as_input(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["prompt_kwargs"] = prompt_kwargs
            captured["infer_input"] = infer_input
            return SimpleNamespace(
                response='{"event_id":"checked","title":{"value":"checked"},"stages":[{"episodes":[{}]}]}',
                to_dict=lambda: {"response": "raw"},
            )

        original_run_single_inference = main_build_module.run_single_inference
        original_extract_json_response = main_build_module.extract_json_response
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        self.addCleanup(
            setattr,
            main_build_module,
            "extract_json_response",
            original_extract_json_response,
        )
        main_build_module.run_single_inference = fake_run_single_inference
        main_build_module.extract_json_response = lambda _result: {"checked": True}

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonReconstructor": _skeleton(title="latest recon")},
            ],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user prompt"},
        }

        updated_state = self.builder.execute_agent(state, "SkeletonChecker")

        self.assertIn('"latest recon"', captured["prompt_kwargs"]["ProposedSkeleton"])
        self.assertNotIn('"first recon"', captured["prompt_kwargs"]["ProposedSkeleton"])
        self.assertEqual(updated_state["agent_results"][-1], {"SkeletonChecker": {"checked": True}})

    def test_skeleton_checker_retries_once_when_json_output_is_truncated(self):
        responses = [
            SimpleNamespace(
                response='{"event_id":"broken"',
                to_dict=lambda: {"response": '{"event_id":"broken"'},
            ),
            SimpleNamespace(
                response=json.dumps(_skeleton(title="checked skeleton")),
                to_dict=lambda: {"response": json.dumps(_skeleton(title="checked skeleton"))},
            ),
        ]
        call_count = {"value": 0}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input, prompt_kwargs
            idx = call_count["value"]
            call_count["value"] += 1
            return responses[idx]

        original_run_single_inference = main_build_module.run_single_inference
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        main_build_module.run_single_inference = fake_run_single_inference

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonReconstructor": _skeleton(title="latest recon")}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user prompt"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        updated_state = self.builder.execute_agent(state, "SkeletonChecker")

        self.assertEqual(call_count["value"], 2)
        self.assertEqual(
            updated_state["agent_results"][-1]["SkeletonChecker"]["title"]["value"],
            "checked skeleton",
        )

    def test_skeleton_checker_uses_compacted_skeleton_payload_to_reduce_echo_size(self):
        captured = {}
        verbose_skeleton = _skeleton(title="latest recon")
        verbose_skeleton["title"]["evidence_source_contents"] = ["x" * 200]
        verbose_skeleton["title"]["reasons"] = ["y" * 120]
        verbose_skeleton["stages"][0]["name"]["evidence_source_contents"] = ["z" * 200]
        verbose_skeleton["stages"][0]["episodes"][0]["name"]["evidence_source_contents"] = [
            "episode evidence" * 20
        ]

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton(title="checked skeleton")),
                to_dict=lambda: {"response": json.dumps(_skeleton(title="checked skeleton"))},
            )

        original_run_single_inference = main_build_module.run_single_inference
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        main_build_module.run_single_inference = fake_run_single_inference

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonReconstructor": verbose_skeleton}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user prompt"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "SkeletonChecker")

        proposed = json.loads(captured["prompt_kwargs"]["ProposedSkeleton"])
        self.assertEqual(proposed["title"]["value"], "latest recon")
        self.assertEqual(proposed["title"]["evidence_source_contents"], [])
        self.assertEqual(proposed["title"]["reasons"], [])
        self.assertEqual(proposed["stages"][0]["name"]["evidence_source_contents"], [])
        self.assertEqual(
            proposed["stages"][0]["episodes"][0]["name"]["evidence_source_contents"], []
        )

    def test_participant_reconstructor_retries_once_when_json_output_is_truncated(self):
        responses = [
            SimpleNamespace(
                response='{"participants":[{"participant_id":"P_1"',
                to_dict=lambda: {"response": '{"participants":[{"participant_id":"P_1"'},
            ),
            SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
                to_dict=lambda: {"response": json.dumps({"participants": [_participant()]})},
            ),
        ]
        call_count = {"value": 0}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input, prompt_kwargs
            idx = call_count["value"]
            call_count["value"] += 1
            return responses[idx]

        original_run_single_inference = main_build_module.run_single_inference
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        main_build_module.run_single_inference = fake_run_single_inference

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )
        self.builder._should_use_shadow_local_context = lambda _agent_name: False
        self.builder._build_local_context_package = lambda state, agent_name: None
        self.builder._attach_local_context_prompt_kwargs = (
            lambda prompt_kwargs, local_context: None
        )
        self.builder._rewrite_heavy_agent_user_msg_template = (
            lambda agent_name, template: template
        )
        self.builder._current_episode_sequence_index = lambda state: 0
        self.builder._get_episode_by_sequence_index = lambda event_skeleton, current_count: (
            0,
            0,
            event_skeleton["stages"][0],
            event_skeleton["stages"][0]["episodes"][0],
            {"stage_index": 0, "episode_index": 0, "stage_id": "S1", "episode_id": "E1"},
        )
        self.builder._get_episode_execution_plan_entry = lambda plan, stage_index, episode_index: {
            "mode": "full",
            "participant_tier": "standard",
            "conflict_guard": "standard",
            "detail_tier": "standard",
        }
        self.builder._episode_execution_mode = lambda plan_entry: "full"
        self.builder._transaction_step_skipped = lambda plan_entry, execution_mode: False
        self.builder._build_stage_sparse_cache = (
            lambda state, stage_index, belong_state: {}
        )
        self.builder._attach_stage_sparse_cache_prompt_kwargs = (
            lambda prompt_kwargs, stage_sparse_cache: None
        )
        self.builder._collect_reconstructed_participants_structure = (
            lambda state: _full_skeleton()
        )
        self.builder._attach_compact_heavy_agent_prompt_kwargs = (
            lambda prompt_kwargs, build_ipt, target_episode: None
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(title="checked skeleton")}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"ParticipantReconstructor": "user prompt"},
            "episode_execution_plan": {"episodes": []},
            "stage_sparse_cache": {},
        }

        updated_state = self.builder.execute_agent(state, "ParticipantReconstructor")

        self.assertEqual(call_count["value"], 2)
        self.assertEqual(
            updated_state["agent_results"][-1]["ParticipantReconstructor"]["participants"][0]["participant_id"],
            "P_1",
        )

    def test_participant_reconstructor_recovers_after_empty_retry_response(self):
        responses = [
            SimpleNamespace(
                response='{"participants":[{"participant_id":"P_1"',
                to_dict=lambda: {"response": '{"participants":[{"participant_id":"P_1"'},
            ),
            SimpleNamespace(
                response="",
                to_dict=lambda: {"response": ""},
            ),
            SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
                to_dict=lambda: {"response": json.dumps({"participants": [_participant()]})},
            ),
        ]
        call_count = {"value": 0}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input, prompt_kwargs
            idx = call_count["value"]
            call_count["value"] += 1
            return responses[idx]

        original_run_single_inference = main_build_module.run_single_inference
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        main_build_module.run_single_inference = fake_run_single_inference

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )
        self.builder._should_use_shadow_local_context = lambda _agent_name: False
        self.builder._build_local_context_package = lambda state, agent_name: None
        self.builder._attach_local_context_prompt_kwargs = (
            lambda prompt_kwargs, local_context: None
        )
        self.builder._rewrite_heavy_agent_user_msg_template = (
            lambda agent_name, template: template
        )
        self.builder._current_episode_sequence_index = lambda state: 0
        self.builder._get_episode_by_sequence_index = lambda event_skeleton, current_count: (
            0,
            0,
            event_skeleton["stages"][0],
            event_skeleton["stages"][0]["episodes"][0],
            {"stage_index": 0, "episode_index": 0, "stage_id": "S1", "episode_id": "E1"},
        )
        self.builder._get_episode_execution_plan_entry = lambda plan, stage_index, episode_index: {
            "mode": "full",
            "participant_tier": "standard",
            "conflict_guard": "standard",
            "detail_tier": "standard",
        }
        self.builder._episode_execution_mode = lambda plan_entry: "full"
        self.builder._transaction_step_skipped = lambda plan_entry, execution_mode: False
        self.builder._build_stage_sparse_cache = (
            lambda state, stage_index, belong_state: {}
        )
        self.builder._attach_stage_sparse_cache_prompt_kwargs = (
            lambda prompt_kwargs, stage_sparse_cache: None
        )
        self.builder._collect_reconstructed_participants_structure = (
            lambda state: _full_skeleton()
        )
        self.builder._attach_compact_heavy_agent_prompt_kwargs = (
            lambda prompt_kwargs, build_ipt, target_episode: None
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(title="checked skeleton")}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"ParticipantReconstructor": "user prompt"},
            "episode_execution_plan": {"episodes": []},
            "stage_sparse_cache": {},
        }

        updated_state = self.builder.execute_agent(state, "ParticipantReconstructor")

        self.assertEqual(call_count["value"], 3)
        self.assertEqual(
            updated_state["agent_results"][-1]["ParticipantReconstructor"]["participants"][0]["participant_id"],
            "P_1",
        )

    def test_participant_reconstructor_recovers_mild_wrapper_junk_without_retry(self):
        response_text = "analysis notes {not json} final payload: " + json.dumps(
            {"participants": [_participant()]}
        )
        call_count = self._install_single_response_inference(response_text)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )
        self.builder._should_use_shadow_local_context = lambda _agent_name: False
        self.builder._build_local_context_package = lambda state, agent_name: None
        self.builder._attach_local_context_prompt_kwargs = (
            lambda prompt_kwargs, local_context: None
        )
        self.builder._rewrite_heavy_agent_user_msg_template = (
            lambda agent_name, template: template
        )
        self.builder._current_episode_sequence_index = lambda state: 0
        self.builder._get_episode_by_sequence_index = lambda event_skeleton, current_count: (
            0,
            0,
            event_skeleton["stages"][0],
            event_skeleton["stages"][0]["episodes"][0],
            {"stage_index": 0, "episode_index": 0, "stage_id": "S1", "episode_id": "E1"},
        )
        self.builder._get_episode_execution_plan_entry = lambda plan, stage_index, episode_index: {
            "mode": "full",
            "participant_tier": "standard",
            "conflict_guard": "standard",
            "detail_tier": "standard",
        }
        self.builder._episode_execution_mode = lambda plan_entry: "full"
        self.builder._transaction_step_skipped = lambda plan_entry, execution_mode: False
        self.builder._build_stage_sparse_cache = (
            lambda state, stage_index, belong_state: {}
        )
        self.builder._attach_stage_sparse_cache_prompt_kwargs = (
            lambda prompt_kwargs, stage_sparse_cache: None
        )
        self.builder._collect_reconstructed_participants_structure = (
            lambda state: _full_skeleton()
        )
        self.builder._attach_compact_heavy_agent_prompt_kwargs = (
            lambda prompt_kwargs, build_ipt, target_episode: None
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(title="checked skeleton")}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"ParticipantReconstructor": "user prompt"},
            "episode_execution_plan": {"episodes": []},
            "stage_sparse_cache": {},
        }

        updated_state = self.builder.execute_agent(state, "ParticipantReconstructor")

        self.assertEqual(call_count["value"], 1)
        self.assertEqual(
            updated_state["agent_results"][-1]["ParticipantReconstructor"]["participants"][0]["participant_id"],
            "P_1",
        )

    def test_episode_reconstructor_recovers_mild_wrapper_junk_without_retry(self):
        response_text = "analysis notes {not json} final payload: " + json.dumps(
            _full_episode()
        )
        call_count = self._install_single_response_inference(response_text)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()},
                {"TransactionReconstructor": _episode_transactions()},
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorSys
            },
            "agent_user_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        updated_state = self.builder.execute_agent(state, "EpisodeReconstructor")

        self.assertEqual(call_count["value"], 1)
        self.assertEqual(
            updated_state["agent_results"][-1]["EpisodeReconstructor"]["episode_id"],
            "E1",
        )

    def test_stage_description_reconstructor_recovers_mild_wrapper_junk_without_retry(self):
        response_text = "analysis notes {not json} final payload: " + json.dumps(
            {"descriptions": [_vf("stage description")], "stage_id": "S1"}
        )
        call_count = self._install_single_response_inference(response_text)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        stage = _skeleton()["stages"][0]
        stage["episodes"] = [
            {
                "episode_id": "E1",
                "name": _vf("Episode 1"),
                "index_in_stage": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-01"),
                "participants": _transaction_participants()["participants"],
                "transactions": _episode_transactions()["transactions"],
                "participant_relations": [],
                "descriptions": [],
            }
        ]

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [
                {"SkeletonChecker": {"stages": [stage]}},
                {"EpisodeReconstructor": stage["episodes"][0]},
            ],
            "agent_executed": ["SkeletonChecker", "EpisodeReconstructor"],
            "cost": [],
            "agent_system_msgs": {"StageDescriptionReconstructor": "sys"},
            "agent_user_msgs": {"StageDescriptionReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        updated_state = self.builder.execute_agent(state, "StageDescriptionReconstructor")

        self.assertEqual(call_count["value"], 1)
        self.assertEqual(
            updated_state["agent_results"][-1]["StageDescriptionReconstructor"]["descriptions"][0]["value"],
            "stage description",
        )

    def test_stage_description_reconstructor_still_fails_on_unrecoverable_truncation(self):
        call_count = self._install_single_response_inference("broken output {no close")

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        stage = _skeleton()["stages"][0]
        stage["episodes"] = [
            {
                "episode_id": "E1",
                "name": _vf("Episode 1"),
                "index_in_stage": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-01"),
                "participants": _transaction_participants()["participants"],
                "transactions": _episode_transactions()["transactions"],
                "participant_relations": [],
                "descriptions": [],
            }
        ]

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [
                {"SkeletonChecker": {"stages": [stage]}},
                {"EpisodeReconstructor": stage["episodes"][0]},
            ],
            "agent_executed": ["SkeletonChecker", "EpisodeReconstructor"],
            "cost": [],
            "agent_system_msgs": {"StageDescriptionReconstructor": "sys"},
            "agent_user_msgs": {"StageDescriptionReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with self.assertRaisesRegex(
            ValueError,
            "StageDescriptionReconstructor returned invalid JSON after 3 attempt",
        ):
            self.builder.execute_agent(state, "StageDescriptionReconstructor")
        self.assertEqual(call_count["value"], 3)

    def test_graph_persists_skeleton_retry_metadata_across_actual_routing(self):
        call_counts = {
            "SkeletonReconstructor": 0,
            "SkeletonChecker": 0,
            "ParticipantReconstructor": 0,
            "TransactionReconstructor": 0,
            "EpisodeReconstructor": 0,
            "StageDescriptionReconstructor": 0,
            "EventDescriptionReconstructor": 0,
        }
        observed_retry_state = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input

            def _response(payload):
                return SimpleNamespace(
                    response=json.dumps(payload),
                    to_dict=lambda: {"response": json.dumps(payload)},
                )

            if "ProposedSkeleton" in prompt_kwargs:
                call_counts["SkeletonChecker"] += 1
                if call_counts["SkeletonChecker"] == 1:
                    return _response(_skeleton(stages=[]))
                return _response(_full_skeleton())
            if "TargetStage" in prompt_kwargs:
                call_counts["StageDescriptionReconstructor"] += 1
                return _response({"descriptions": [_vf("stage description")], "stage_id": "S1"})
            if "EventCascade" in prompt_kwargs:
                call_counts["EventDescriptionReconstructor"] += 1
                return _response({"descriptions": [_vf("event description")]})
            if "StageSkeleton" in prompt_kwargs:
                call_counts["EpisodeReconstructor"] += 1
                episode = _full_episode()
                episode["descriptions"] = [_vf("episode description")]
                return _response(episode)
            if "ReconstructedParticipants" in prompt_kwargs:
                call_counts["ParticipantReconstructor"] += 1
                return _response({"participants": [_participant()]})
            if "TargetEpisode" in prompt_kwargs:
                call_counts["TransactionReconstructor"] += 1
                return _response({"transactions": []})

            if call_counts["SkeletonReconstructor"] == 1:
                return _response(_skeleton(stages=[]))
            return _response(_full_skeleton())

        original_run_single_inference = main_build_module.run_single_inference
        original_extract_json_response = main_build_module.extract_json_response
        original_execute_agent = self.builder.execute_agent

        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        self.addCleanup(
            setattr,
            main_build_module,
            "extract_json_response",
            original_extract_json_response,
        )
        self.addCleanup(
            setattr,
            self.builder,
            "execute_agent",
            original_execute_agent,
        )

        main_build_module.run_single_inference = fake_run_single_inference
        main_build_module.extract_json_response = lambda result: json.loads(result)

        def wrapped_execute_agent(state, agent_name):
            if agent_name == "SkeletonReconstructor":
                call_counts["SkeletonReconstructor"] += 1
                if call_counts["SkeletonReconstructor"] == 2:
                    observed_retry_state["skeleton_retry_count"] = state[
                        "skeleton_retry_count"
                    ]
                    observed_retry_state["skeleton_validation_reason"] = state[
                        "skeleton_validation_reason"
                    ]
            elif agent_name not in {
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
                "EpisodeReconstructor",
                "StageDescriptionReconstructor",
                "EventDescriptionReconstructor",
            }:
                self.fail(f"unexpected agent: {agent_name}")
            return original_execute_agent(state, agent_name)

        self.builder.execute_agent = wrapped_execute_agent
        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": "sys",
                "SkeletonChecker": "sys",
                "ParticipantReconstructor": "sys",
                "TransactionReconstructor": "sys",
                "EpisodeReconstructor": "sys",
                "StageDescriptionReconstructor": "sys",
                "EventDescriptionReconstructor": "sys",
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": "user",
                "SkeletonChecker": "user",
                "ParticipantReconstructor": "user",
                "TransactionReconstructor": "user",
                "EpisodeReconstructor": "user",
                "StageDescriptionReconstructor": "user",
                "EventDescriptionReconstructor": "user",
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
            "messages": [],
        }

        final_state = self.builder.graph().invoke(state, config={"recursion_limit": 25})

        self.assertEqual(observed_retry_state["skeleton_retry_count"], 1)
        self.assertEqual(observed_retry_state["skeleton_validation_reason"], "no_stages")
        self.assertEqual(final_state["skeleton_retry_count"], 1)
        self.assertEqual(call_counts["SkeletonReconstructor"], 2)
        self.assertEqual(call_counts["SkeletonChecker"], 2)
        self.assertEqual(final_state["skeleton_validation_reason"], "")

    def test_route_after_checker_retries_once_for_non_empty_content(self):
        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 1,
            "skeleton_validation_reason": "",
        }
        next_node = self.builder._route_after_skeleton_checker(state)
        self.assertEqual(next_node, "SkeletonReconstructor")
        self.assertEqual(state["skeleton_retry_count"], 1)

    def test_route_after_checker_fails_early_for_empty_content(self):
        state = {
            "build_input": _build_input([""]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        with self.assertLogs(main_build_module.__name__, level="ERROR") as captured:
            with self.assertRaisesRegex(ValueError, "Insufficient source content"):
                self.builder._route_after_skeleton_checker(state)
        self.assertIn("Insufficient source content", "\n".join(captured.output))

    def test_route_after_checker_stops_after_retry_budget_is_exhausted(self):
        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 2,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Invalid event skeleton"):
            self.builder._route_after_skeleton_checker(state)

    def test_route_after_reconstructor_fails_early_when_content_is_empty(self):
        state = {
            "build_input": _build_input([""]),
            "agent_results": [{"SkeletonReconstructor": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Insufficient source content"):
            self.builder._route_after_skeleton_reconstructor(state)
