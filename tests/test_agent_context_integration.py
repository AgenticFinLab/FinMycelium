import json
import importlib
import sys
import types
import unittest
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


def _skeleton():
    return {
        "event_id": "demo_event",
        "title": _vf("Demo Event"),
        "event_type": _vf("demo"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Stage 1"),
                "index_in_event": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-02"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                    }
                ],
            }
        ],
    }


def _participant():
    return {
        "participant_id": "P_1",
        "name": _vf("Participant 1"),
        "participant_type": "organization",
        "base_role": _vf("counterparty"),
        "attributes": {},
        "actions": [],
    }


def _build_input():
    bundle = EvidenceAssetBundle(
        retrieval_policy=EvidenceRetrievalPolicy(),
        index=EvidenceIndex(),
        evidence_cards=[
            EvidenceCard(
                sample_id="sample-1",
                title="sample-1",
                excerpt="alpha episode excerpt",
                tokens=["alpha", "episode"],
            )
        ],
    )
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="alpha episode", key_words=["alpha"]),
        samples=[SimpleNamespace(content="real content")],
        context_assets=bundle,
    )


def _build_compact_input():
    bundle = EvidenceAssetBundle(
        retrieval_policy=EvidenceRetrievalPolicy(),
        index=EvidenceIndex(),
        evidence_cards=[
            EvidenceCard(
                sample_id="sample-1",
                title="sample-1",
                excerpt="alpha episode excerpt",
                tokens=["alpha", "episode"],
            )
        ],
    )
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="alpha episode", key_words=["alpha"]),
        samples=[
            SimpleNamespace(content="  real content  "),
            SimpleNamespace(content="\nsecondary content line\n"),
        ],
        context_assets=bundle,
    )


def _build_shadow_mode_input():
    bundle = EvidenceAssetBundle(
        retrieval_policy=EvidenceRetrievalPolicy(),
        index=EvidenceIndex(),
        evidence_cards=[
            EvidenceCard(
                sample_id="sample-1",
                title="sample-1",
                excerpt="RETRIEVED_CONTEXT_SENTINEL_99 fraud and money laundering",
                tokens=["fraud", "money", "laundering"],
            )
        ],
    )
    return SimpleNamespace(
        user_query=SimpleNamespace(
            query_text="fraud and money laundering",
            key_words=["fraud", "money laundering"],
        ),
        samples=[
            SimpleNamespace(content="CONTENT_ONLY_SENTINEL_42"),
        ],
        context_assets=bundle,
    )


def _build_checker_shadow_mode_input():
    bundle = EvidenceAssetBundle(
        retrieval_policy=EvidenceRetrievalPolicy(),
        index=EvidenceIndex(),
        evidence_cards=[
            EvidenceCard(
                sample_id="sample-1",
                title="sample-1",
                excerpt="CHECKER_RETRIEVED_CONTEXT_SENTINEL_77 reconciliation evidence",
                tokens=["reconciliation", "evidence"],
            )
        ],
    )
    return SimpleNamespace(
        user_query=SimpleNamespace(
            query_text="reconciliation evidence",
            key_words=["reconciliation", "evidence"],
        ),
        samples=[
            SimpleNamespace(content="CHECKER_CONTENT_SENTINEL_55"),
        ],
        context_assets=bundle,
    )


def _build_empty_input():
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="alpha episode", key_words=["alpha"]),
        samples=[SimpleNamespace(content="real content")],
        context_assets=EvidenceAssetBundle.empty(),
    )


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


class AgentContextIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

    def test_skeleton_reconstructor_shadow_mode_keeps_full_content(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_shadow_mode_input(),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorSys
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        additive_context = SimpleNamespace(
            rendered_context="RETRIEVED_CONTEXT_SENTINEL_99 fraud and money laundering",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=additive_context,
        ):
            self.builder.execute_agent(state, "SkeletonReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", captured["infer_input"].user_msg)
        self.assertIn("=== CONTENT BEGIN ===", captured["infer_input"].user_msg)
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", rendered_prompt)
        self.assertIn("=== CONTENT BEGIN ===", rendered_prompt)
        self.assertIn("RETRIEVED_CONTEXT_SENTINEL_99", rendered_prompt)
        self.assertIn("CONTENT_ONLY_SENTINEL_42", rendered_prompt)
        self.assertTrue(captured["prompt_kwargs"]["Content"].strip())
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertNotEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )
        self.assertEqual(captured["prompt_kwargs"]["Content"], "CONTENT_ONLY_SENTINEL_42")

    def test_skeleton_reconstructor_clears_content_when_global_context_is_sufficient(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
                to_dict=lambda: {"response": "raw"},
            )

        sufficient_context = SimpleNamespace(
            rendered_context="SUFFICIENT_RETRIEVED_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="sufficient",
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_shadow_mode_input(),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorSys
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=sufficient_context,
        ):
            self.builder.execute_agent(state, "SkeletonReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "SUFFICIENT_RETRIEVED_CONTEXT")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )
        self.assertEqual(captured["prompt_kwargs"]["Content"], "")
        self.assertIn("SUFFICIENT_RETRIEVED_CONTEXT", rendered_prompt)

    def test_skeleton_reconstructor_preserves_content_when_global_context_falls_back(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
                to_dict=lambda: {"response": "raw"},
            )

        fallback_context = SimpleNamespace(
            rendered_context="FALLBACK_RETRIEVED_CONTEXT",
            summary={"selected_count": 0},
            retrieval_status="fallback_fulltext",
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_shadow_mode_input(),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorSys
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=fallback_context,
        ):
            self.builder.execute_agent(state, "SkeletonReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "FALLBACK_RETRIEVED_CONTEXT")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 0}, ensure_ascii=False),
        )
        self.assertEqual(captured["prompt_kwargs"]["Content"], "CONTENT_ONLY_SENTINEL_42")
        self.assertIn("FALLBACK_RETRIEVED_CONTEXT", rendered_prompt)

    def test_skeleton_reconstructor_exposes_richer_local_context_metadata_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
                to_dict=lambda: {"response": "raw"},
            )

        rich_context = SimpleNamespace(
            rendered_context="RICH_GLOBAL_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
            query_bundle={"scope": "global", "global_phase_hints": ["early", "middle"]},
            budget_summary={"target_card_budget": 3, "used_card_count": 1},
            memory={"selection_rationale": [{"sample_id": "sample-1", "match_kind": "strong"}]},
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_shadow_mode_input(),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorSys
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": main_build_module.EventLayoutReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "SkeletonReconstructor")

        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "RICH_GLOBAL_CONTEXT")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextQueryBundle"],
            json.dumps(
                {"scope": "global", "global_phase_hints": ["early", "middle"]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextBudgetSummary"],
            json.dumps(
                {"target_card_budget": 3, "used_card_count": 1},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextMemory"],
            json.dumps(
                {"selection_rationale": [{"sample_id": "sample-1", "match_kind": "strong"}]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    def test_skeleton_checker_shadow_mode_keeps_full_content(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_checker_shadow_mode_input(),
            "agent_results": [{"SkeletonReconstructor": _skeleton()}],
            "agent_executed": ["SkeletonReconstructor"],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerSys
            },
            "agent_user_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        additive_context = SimpleNamespace(
            rendered_context="CHECKER_RETRIEVED_CONTEXT_SENTINEL_77",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=additive_context,
        ):
            self.builder.execute_agent(state, "SkeletonChecker")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", captured["infer_input"].user_msg)
        self.assertIn("=== CONTENT BEGIN ===", captured["infer_input"].user_msg)
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", rendered_prompt)
        self.assertIn("=== CONTENT BEGIN ===", rendered_prompt)
        self.assertIn("CHECKER_RETRIEVED_CONTEXT_SENTINEL_77", rendered_prompt)
        self.assertIn("CHECKER_CONTENT_SENTINEL_55", rendered_prompt)
        self.assertTrue(captured["prompt_kwargs"]["Content"].strip())
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertNotEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["Content"], "CHECKER_CONTENT_SENTINEL_55")
        self.assertIn(
            "CHECKER_RETRIEVED_CONTEXT_SENTINEL_77",
            captured["prompt_kwargs"]["RetrievedContext"],
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_skeleton_checker_clears_content_when_global_context_is_sufficient(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_checker_shadow_mode_input(),
            "agent_results": [{"SkeletonReconstructor": _skeleton()}],
            "agent_executed": ["SkeletonReconstructor"],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerSys
            },
            "agent_user_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        sufficient_context = SimpleNamespace(
            rendered_context="CHECKER_RETRIEVED_CONTEXT_SENTINEL_77",
            summary={"selected_count": 1},
            retrieval_status="sufficient",
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=sufficient_context,
        ):
            self.builder.execute_agent(state, "SkeletonChecker")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("CHECKER_RETRIEVED_CONTEXT_SENTINEL_77", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContext"],
            "CHECKER_RETRIEVED_CONTEXT_SENTINEL_77",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )
        self.assertEqual(captured["prompt_kwargs"]["Content"], "")

    def test_skeleton_checker_preserves_content_when_global_context_falls_back(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(_skeleton()),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_checker_shadow_mode_input(),
            "agent_results": [{"SkeletonReconstructor": _skeleton()}],
            "agent_executed": ["SkeletonReconstructor"],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerSys
            },
            "agent_user_msgs": {
                "SkeletonChecker": main_build_module.SkeletonCheckerUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        fallback_context = SimpleNamespace(
            rendered_context="CHECKER_FALLBACK_RETRIEVED_CONTEXT",
            summary={"selected_count": 0},
            retrieval_status="fallback_fulltext",
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=fallback_context,
        ):
            self.builder.execute_agent(state, "SkeletonChecker")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("CHECKER_FALLBACK_RETRIEVED_CONTEXT", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContext"],
            "CHECKER_FALLBACK_RETRIEVED_CONTEXT",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 0}, ensure_ascii=False),
        )
        self.assertEqual(captured["prompt_kwargs"]["Content"], "CHECKER_CONTENT_SENTINEL_55")

    def test_participant_reconstructor_receives_retrieved_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {
                "ParticipantReconstructor": main_build_module.ParticipantReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = main_build_module.ParticipantReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("CompactContent", captured["prompt_kwargs"])
        self.assertIn("TargetEpisodeContext", captured["prompt_kwargs"])
        target_episode_context = json.loads(captured["prompt_kwargs"]["TargetEpisodeContext"])
        self.assertEqual(
            target_episode_context,
            {
                "episode_id": "E1",
                "name": "Episode 1",
                "index_in_stage": 0,
                "start_time": "2025-01-01",
                "end_time": "2025-01-02",
                "participant_ids": [],
                "transaction_ids": [],
            },
        )
        self.assertNotIn("participants", target_episode_context)
        self.assertNotIn("transactions", target_episode_context)
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_participant_reconstructor_exposes_compact_payload_contract_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {
                "ParticipantReconstructor": main_build_module.ParticipantReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        rich_context = SimpleNamespace(
            rendered_context="RICH_PARTICIPANT_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
            query_bundle={
                "scope": "episode",
                "stage_name": "Stage 1",
                "episode_name": "Episode 1",
            },
            budget_summary={"target_card_budget": 1, "used_card_count": 1},
            memory={"selection_rationale": [{"matched_fields": ["episode_name"]}]},
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        expected_compact_content = "real content\nsecondary content line"
        self.assertEqual(
            captured["prompt_kwargs"]["Content"],
            "  real content  \n\nsecondary content line\n",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["CompactContent"], expected_compact_content
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("TargetEpisodeContext", captured["prompt_kwargs"])
        self.assertEqual(
            json.loads(captured["prompt_kwargs"]["TargetEpisodeContext"]),
            {
                "episode_id": "E1",
                "name": "Episode 1",
                "index_in_stage": 0,
                "start_time": "2025-01-01",
                "end_time": "2025-01-02",
                "participant_ids": [],
                "transaction_ids": [],
            },
        )
        self.assertIn(expected_compact_content, rendered_prompt)
        self.assertIn('"participant_ids":[]', rendered_prompt)
        self.assertNotIn('"participants": [', rendered_prompt)
        self.assertNotIn('"transactions": [', rendered_prompt)
        self.assertNotIn("  real content  ", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContext"],
            "RICH_PARTICIPANT_CONTEXT",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_participant_reconstructor_receives_minimal_tier_prompt_kwargs(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan_entry = plan["episodes"][0]

        state = {
            "build_input": _build_compact_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {
                "ParticipantReconstructor": main_build_module.ParticipantReconstructorUser
            },
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(
            captured["prompt_kwargs"]["ParticipantDetailTier"],
            plan_entry["participant_tier"],
        )
        self.assertEqual(
            captured["prompt_kwargs"]["ConflictGuard"], plan_entry["conflict_guard"]
        )
        self.assertEqual(plan_entry["mode"], "light")
        self.assertEqual(plan_entry["participant_tier"], "minimal")
        self.assertEqual(plan_entry["conflict_guard"], "standard")
        self.assertIn("ParticipantDetailTier", rendered_prompt)
        self.assertIn("ConflictGuard", rendered_prompt)
        self.assertIn("prefer only the materially necessary actors", rendered_prompt)
        self.assertIn(
            "prefer a group participant over weakly evidenced individual expansion",
            rendered_prompt,
        )
        self.assertIn("cap action volume", rendered_prompt)
        self.assertIn("standard", rendered_prompt)

    def test_light_participant_tier_preserves_id_reuse_but_caps_actor_set(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "participants": [
                            {
                                "participant_id": "P_1",
                                "name": _vf("Participant 1"),
                                "participant_type": "organization",
                                "base_role": _vf("counterparty"),
                                "attributes": {},
                                "actions": [],
                            }
                        ]
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        skeleton = _skeleton()
        skeleton["stages"][0]["episodes"].append(
            {
                "episode_id": "E2",
                "name": _vf("Episode 2"),
                "index_in_stage": 1,
                "start_time": _vf("2025-01-03"),
                "end_time": _vf("2025-01-04"),
            }
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            skeleton,
        )
        plan_entry = plan["episodes"][1]

        state = {
            "build_input": _build_compact_input(),
            "agent_results": [
                {"SkeletonChecker": skeleton},
                {"ParticipantReconstructor": _transaction_participants()},
                {"EpisodeReconstructor": {"episode_id": "E1"}},
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
                "EpisodeReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {
                "ParticipantReconstructor": main_build_module.ParticipantReconstructorUser
            },
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        reconstructed_participants = captured["prompt_kwargs"]["ReconstructedParticipants"]
        first_episode_participants = reconstructed_participants["stages"][0]["episodes"][0][
            "participants"
        ]
        self.assertEqual(
            [participant["participant_id"] for participant in first_episode_participants],
            ["P_1", "P_2"],
        )
        self.assertEqual(
            captured["prompt_kwargs"]["ParticipantDetailTier"],
            plan_entry["participant_tier"],
        )
        self.assertEqual(
            captured["prompt_kwargs"]["ConflictGuard"], plan_entry["conflict_guard"]
        )
        self.assertEqual(plan_entry["mode"], "light")
        self.assertEqual(plan_entry["participant_tier"], "minimal")
        self.assertEqual(plan_entry["conflict_guard"], "standard")
        self.assertIn("ParticipantDetailTier", rendered_prompt)
        self.assertIn("ConflictGuard", rendered_prompt)
        self.assertIn("enable ID reuse", rendered_prompt)
        self.assertIn("reuse the same", rendered_prompt)
        self.assertIn("participant_id", rendered_prompt)
        self.assertIn("prefer only the materially necessary actors", rendered_prompt)
        self.assertEqual(captured["prompt_kwargs"]["TargetEpisode"].episode_id, "E2")

    def test_participant_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {"ParticipantReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = main_build_module.ParticipantReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)

    def test_transaction_reconstructor_receives_retrieved_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"transactions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()}
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {
                "TransactionReconstructor": main_build_module.TransactionReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "TransactionReconstructor")

        rendered_prompt = main_build_module.TransactionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertIn("Episode 1", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["TargetEpisode"].name["value"],
            "Episode 1",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["Content"],
            "real content",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["CompactContent"],
            "real content",
        )
        self.assertEqual(
            json.loads(captured["prompt_kwargs"]["TargetEpisodeContext"]),
            {
                "episode_id": "E1",
                "name": "Episode 1",
                "index_in_stage": 0,
                "start_time": "2025-01-01",
                "end_time": "2025-01-02",
                "participant_ids": ["P_1", "P_2"],
                "transaction_ids": [],
            },
        )

    def test_transaction_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"transactions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()}
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {
                "TransactionReconstructor": main_build_module.TransactionReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "TransactionReconstructor")

        rendered_prompt = main_build_module.TransactionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("TARGET EPISODE BEGIN", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)

    def test_transaction_reconstructor_exposes_compact_payload_contract_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"transactions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()},
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {
                "TransactionReconstructor": main_build_module.TransactionReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        rich_context = SimpleNamespace(
            rendered_context="RICH_TRANSACTION_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
            query_bundle={
                "scope": "episode",
                "stage_name": "Stage 1",
                "episode_name": "Episode 1",
            },
            budget_summary={"target_card_budget": 1, "used_card_count": 1},
            memory={"selection_rationale": [{"matched_fields": ["episode_name"]}]},
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "TransactionReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("CompactContent", captured["prompt_kwargs"])
        self.assertIn("TargetEpisodeContext", captured["prompt_kwargs"])
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextQueryBundle"],
            json.dumps(
                {
                    "scope": "episode",
                    "stage_name": "Stage 1",
                    "episode_name": "Episode 1",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextBudgetSummary"],
            json.dumps(
                {"target_card_budget": 1, "used_card_count": 1},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextMemory"],
            json.dumps(
                {"selection_rationale": [{"matched_fields": ["episode_name"]}]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["Content"],
            "  real content  \n\nsecondary content line\n",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["CompactContent"],
            "real content\nsecondary content line",
        )
        self.assertIn('"participant_ids":["P_1","P_2"]', rendered_prompt)
        self.assertNotIn('"participants": [', rendered_prompt)
        self.assertNotIn('"transactions": [', rendered_prompt)
        self.assertIn("real content\nsecondary content line", rendered_prompt)

    def test_episode_reconstructor_receives_retrieved_context_without_clearing_content(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
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

        self.builder.execute_agent(state, "EpisodeReconstructor")

        infer_input = captured["infer_input"]
        rendered_prompt = infer_input.user_msg.format(**captured["prompt_kwargs"])
        self.assertIn("RetrievedContext", infer_input.user_msg)
        self.assertIn("Content", infer_input.user_msg)
        self.assertIn("RETRIEVED CONTEXT BEGIN", infer_input.user_msg)
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertEqual(captured["prompt_kwargs"]["Content"], "real content")
        self.assertIn("real content", captured["prompt_kwargs"]["Content"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertIn("Content", rendered_prompt)
        self.assertIn("StageSkeleton", rendered_prompt)
        self.assertIn("TargetEpisode", rendered_prompt)
        self.assertIn("Episode 1", rendered_prompt)
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "standard")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_episode_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
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
            "agent_system_msgs": {"EpisodeReconstructor": "sys"},
            "agent_user_msgs": {"EpisodeReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = main_build_module.EpisodeReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("STAGE SKELETON BEGIN", rendered_prompt.upper())
        self.assertIn("TARGET EPISODE BEGIN", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)
        self.assertNotIn("ParticipantDetailTier", captured["prompt_kwargs"])
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "standard")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")

    def test_episode_reconstructor_exposes_richer_local_context_metadata_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
                to_dict=lambda: {"response": "raw"},
            )

        rich_context = SimpleNamespace(
            rendered_context="RICH_EPISODE_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="sufficient",
            query_bundle={
                "scope": "episode",
                "stage_name": "Stage 1",
                "episode_name": "Episode 1",
            },
            budget_summary={"target_card_budget": 1, "used_card_count": 1},
            memory={"selection_rationale": [{"matched_fields": ["episode_name", "entity_hints"]}]},
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
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

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "RICH_EPISODE_CONTEXT")
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextQueryBundle"],
            json.dumps(
                {
                    "scope": "episode",
                    "stage_name": "Stage 1",
                    "episode_name": "Episode 1",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextBudgetSummary"],
            json.dumps(
                {"target_card_budget": 1, "used_card_count": 1},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextMemory"],
            json.dumps(
                {"selection_rationale": [{"matched_fields": ["episode_name", "entity_hints"]}]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["Content"],
            "  real content  \n\nsecondary content line\n",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["CompactContent"],
            "real content\nsecondary content line",
        )
        self.assertIn("real content\nsecondary content line", rendered_prompt)
        self.assertIn("Stage ID: S1", rendered_prompt)
        self.assertIn("- E1: Episode 1", rendered_prompt)
        self.assertIn("Participant IDs: P_1, P_2", rendered_prompt)
        self.assertNotIn('"participants": [', rendered_prompt)
        self.assertNotIn('"transactions": [', rendered_prompt)
        self.assertNotIn('"episodes": [', rendered_prompt)

    def test_episode_reconstructor_attaches_stage_sparse_cache_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
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

        self.builder.execute_agent(state, "EpisodeReconstructor")

        self.assertIn("StageSparseCache", captured["prompt_kwargs"])
        stage_sparse_cache = json.loads(captured["prompt_kwargs"]["StageSparseCache"])
        self.assertEqual(stage_sparse_cache["stage_id"], "S1")
        self.assertEqual(stage_sparse_cache["stage_name"], "Stage 1")
        self.assertIn("stage_evidence_digest", stage_sparse_cache)
        self.assertIn("stage_actor_map", stage_sparse_cache)
        self.assertIn("stage_conflict_summary", stage_sparse_cache)
        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("STAGE SPARSE CACHE BEGIN", rendered_prompt)
        self.assertIn('"stage_name": "Stage 1"', rendered_prompt)

    def test_episode_reconstructor_light_mode_exposes_empty_transactions_and_compact_tier(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2024"),
                        "end_time": _vf("2024"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P_1", "name": _vf("Qian Zhimin")}]
                    },
                    "_meta": {
                        "episode_locator": {
                            "stage_index": 0,
                            "episode_index": 0,
                            "stage_id": "S1",
                            "episode_id": "E1",
                        },
                        "execution_mode": "light",
                    },
                },
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorSys
            },
            "agent_user_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorUser
            },
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

        rich_context = SimpleNamespace(
            rendered_context="RICH_EPISODE_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
            query_bundle={
                "scope": "episode",
                "stage_name": "Stage 1",
                "episode_name": "Episode 1",
            },
            budget_summary={"target_card_budget": 1, "used_card_count": 1},
            memory={"selection_rationale": [{"matched_fields": ["episode_name"]}]},
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "light")
        self.assertEqual(captured["prompt_kwargs"]["TransactionDetailTier"], "compact")
        self.assertIn("EpisodeCompactnessHint", captured["prompt_kwargs"])
        self.assertIn(
            "compact-light-mode",
            captured["prompt_kwargs"]["EpisodeCompactnessHint"],
        )
        self.assertEqual(
            captured["prompt_kwargs"]["EpisodeLocator"],
            {
                "stage_index": 0,
                "episode_index": 0,
                "stage_id": "S1",
                "episode_id": "E1",
            },
        )
        self.assertIn("Transaction IDs: none", captured["prompt_kwargs"]["TargetEpisodeContext"])
        self.assertIn("Participant IDs: P_1", captured["prompt_kwargs"]["TargetEpisodeContext"])
        self.assertIn("real content\nsecondary content line", rendered_prompt)

    def test_episode_reconstructor_injects_minimal_episode_detail_tier(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan["episodes"][0]["mode"] = "full"
        plan["episodes"][0]["transaction_tier"] = "minimal"
        plan["episodes"][0]["episode_detail_tier"] = "minimal"
        plan["episodes"][0]["detail_tier"] = "minimal"
        plan["episodes"][0]["conflict_guard"] = "standard"

        state = {
            "build_input": _build_compact_input(),
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
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "light")
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "minimal")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")
        self.assertIn("EpisodeDetailTier", rendered_prompt)
        self.assertIn("emit at most one concise description", rendered_prompt)
        self.assertIn(
            "preserve timeline anchors but do not add narrative expansion",
            rendered_prompt,
        )
        self.assertIn("include only essential participant_relations", rendered_prompt)
        self.assertIn("EpisodeCompactnessHint", captured["prompt_kwargs"])
        self.assertIn("TransactionDetailTier", captured["prompt_kwargs"])

    def test_episode_reconstructor_promotes_strict_conflict_guard_to_standard(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan["episodes"][0]["mode"] = "full"
        plan["episodes"][0]["episode_detail_tier"] = "compact"
        plan["episodes"][0]["detail_tier"] = "compact"
        plan["episodes"][0]["conflict_guard"] = "strict"

        state = {
            "build_input": _build_compact_input(),
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
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "full")
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "standard")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "strict")
        self.assertEqual(plan["episodes"][0]["episode_detail_tier"], "compact")
        self.assertIn("EpisodeDetailTier", rendered_prompt)
        self.assertIn("ConflictGuard", rendered_prompt)
        self.assertIn(
            "preserve major causal and legal facts while keeping descriptions brief",
            rendered_prompt,
        )

    def test_episode_reconstructor_keeps_compact_tier_when_conflict_guard_is_standard(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan["episodes"][0]["mode"] = "full"
        plan["episodes"][0]["transaction_tier"] = "minimal"
        plan["episodes"][0]["detail_tier"] = "compact"
        plan["episodes"][0]["episode_detail_tier"] = "compact"
        plan["episodes"][0]["conflict_guard"] = "standard"

        state = {
            "build_input": _build_compact_input(),
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
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "light")
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "compact")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")
        self.assertIn("compact-light-mode", captured["prompt_kwargs"]["EpisodeCompactnessHint"])
        self.assertIn("EpisodeDetailTier", rendered_prompt)
        self.assertIn("EpisodeCompactnessHint", rendered_prompt)

    def test_episode_reconstructor_preserves_compact_hint_even_when_mode_is_full(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan["episodes"][0]["mode"] = "full"
        plan["episodes"][0]["transaction_tier"] = "standard"
        plan["episodes"][0]["detail_tier"] = "compact"
        plan["episodes"][0]["episode_detail_tier"] = "compact"
        plan["episodes"][0]["conflict_guard"] = "standard"

        state = {
            "build_input": _build_compact_input(),
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
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "full")
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "compact")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")
        self.assertIn("compact", captured["prompt_kwargs"]["EpisodeCompactnessHint"])
        self.assertNotIn(
            "standard-full-mode", captured["prompt_kwargs"]["EpisodeCompactnessHint"]
        )
        self.assertIn("EpisodeDetailTier", rendered_prompt)
        self.assertIn("EpisodeCompactnessHint", rendered_prompt)

    def test_episode_reconstructor_uses_legacy_detail_tier_when_episode_detail_tier_is_missing(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        plan = self.builder._build_episode_execution_plan(
            _build_compact_input(),
            _skeleton(),
        )
        plan["episodes"][0]["mode"] = "full"
        plan["episodes"][0]["transaction_tier"] = "minimal"
        plan["episodes"][0].pop("episode_detail_tier", None)
        plan["episodes"][0].pop("conflict_guard", None)
        plan["episodes"][0]["detail_tier"] = "compact"

        state = {
            "build_input": _build_compact_input(),
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
            "episode_execution_plan": plan,
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=None,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["EpisodeExecutionMode"], "light")
        self.assertEqual(captured["prompt_kwargs"]["TransactionDetailTier"], "compact")
        self.assertEqual(captured["prompt_kwargs"]["EpisodeDetailTier"], "compact")
        self.assertEqual(captured["prompt_kwargs"]["ConflictGuard"], "standard")
        self.assertIn("EpisodeDetailTier", rendered_prompt)
        self.assertIn(
            "preserve major causal and legal facts while keeping descriptions brief",
            rendered_prompt,
        )

    def test_episode_reconstructor_exposes_compact_payload_contract_additively(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_compact_input(),
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

        rich_context = SimpleNamespace(
            rendered_context="RICH_EPISODE_CONTEXT",
            summary={"selected_count": 1},
            retrieval_status="fallback_fulltext",
            query_bundle={
                "scope": "episode",
                "stage_name": "Stage 1",
                "episode_name": "Episode 1",
            },
            budget_summary={"target_card_budget": 1, "used_card_count": 1},
            memory={"selection_rationale": [{"matched_fields": ["episode_name"]}]},
        )

        with patch.object(
            self.builder,
            "_build_local_context_package",
            return_value=rich_context,
        ):
            self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = captured["infer_input"].user_msg.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("CompactContent", captured["prompt_kwargs"])
        self.assertIn("TargetEpisodeContext", captured["prompt_kwargs"])
        self.assertIn("StageSkeletonContext", captured["prompt_kwargs"])
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextQueryBundle"],
            json.dumps(
                {
                    "scope": "episode",
                    "stage_name": "Stage 1",
                    "episode_name": "Episode 1",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextBudgetSummary"],
            json.dumps(
                {"target_card_budget": 1, "used_card_count": 1},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextMemory"],
            json.dumps(
                {"selection_rationale": [{"matched_fields": ["episode_name"]}]},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self.assertEqual(
            captured["prompt_kwargs"]["Content"],
            "  real content  \n\nsecondary content line\n",
        )
        self.assertEqual(
            captured["prompt_kwargs"]["CompactContent"],
            "real content\nsecondary content line",
        )
        target_context = captured["prompt_kwargs"]["TargetEpisodeContext"]
        self.assertIn("Episode ID: E1", target_context)
        self.assertIn("Episode Name: Episode 1", target_context)
        self.assertIn("Episode Index In Stage: 0", target_context)
        self.assertIn("Participant IDs: P_1, P_2", target_context)
        self.assertIn("Transaction IDs: T_1", target_context)
        self.assertNotIn('"participant_ids"', target_context)
        self.assertNotIn('"transaction_ids"', target_context)
        stage_context = captured["prompt_kwargs"]["StageSkeletonContext"]
        self.assertIn("Stage ID: S1", stage_context)
        self.assertIn("Stage Name: Stage 1", stage_context)
        self.assertIn("Episodes:", stage_context)
        self.assertIn("- E1: Episode 1", stage_context)
        self.assertNotIn('"episode_names"', stage_context)
        self.assertNotIn('"episode_ids"', stage_context)
        self.assertIn("Stage ID: S1", rendered_prompt)
        self.assertIn("- E1: Episode 1", rendered_prompt)
        self.assertNotIn('"episodes": [', rendered_prompt)
        self.assertNotIn('"participants": [', rendered_prompt)
        self.assertNotIn('"transactions": [', rendered_prompt)
        self.assertIn("real content\nsecondary content line", rendered_prompt)

    def test_stage_description_reconstructor_receives_stage_scoped_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"descriptions": [_vf("Stage summary")] }),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

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

        build_input = SimpleNamespace(
            user_query=SimpleNamespace(query_text="alpha stage", key_words=["alpha", "stage"]),
            samples=[SimpleNamespace(content="real content")],
            context_assets=EvidenceAssetBundle(
                retrieval_policy=EvidenceRetrievalPolicy(),
                index=EvidenceIndex(),
                evidence_cards=[
                    EvidenceCard(
                        sample_id="sample-stage",
                        title="sample-stage",
                        excerpt="alpha stage excerpt",
                        tokens=["alpha", "stage"],
                    )
                ],
            ),
        )

        state = {
            "build_input": build_input,
            "agent_results": [
                {"SkeletonChecker": {"stages": [stage]}},
                {"EpisodeReconstructor": stage["episodes"][0]},
            ],
            "agent_executed": ["SkeletonChecker", "EpisodeReconstructor"],
            "cost": [],
            "agent_system_msgs": {"StageDescriptionReconstructor": "sys"},
            "agent_user_msgs": {
                "StageDescriptionReconstructor": main_build_module.StageDescriptionReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "StageDescriptionReconstructor")

        infer_input = captured["infer_input"]
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn(
            "alpha stage excerpt", captured["prompt_kwargs"]["RetrievedContext"]
        )
        self.assertIn("=== TARGET STAGE BEGIN ===", infer_input.user_msg)
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", infer_input.user_msg)
        rendered_prompt = main_build_module.StageDescriptionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("alpha stage excerpt", rendered_prompt)
        self.assertIn("Stage 1", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_stage_description_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"descriptions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

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
            "build_input": _build_empty_input(),
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

        self.builder.execute_agent(state, "StageDescriptionReconstructor")

        rendered_prompt = main_build_module.StageDescriptionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("RetrievedContext", rendered_prompt)
        self.assertIn("TargetStage", rendered_prompt)
        self.assertIn("Content", rendered_prompt)
        self.assertNotIn("alpha stage excerpt", rendered_prompt)


if __name__ == "__main__":
    unittest.main()
