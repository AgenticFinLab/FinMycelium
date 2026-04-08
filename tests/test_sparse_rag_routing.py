import unittest
import sys
import types
from types import SimpleNamespace

if "langgraph" not in sys.modules:
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
    sys.modules["langgraph"] = langgraph_module
    sys.modules["langgraph.graph"] = graph_module
    sys.modules["langgraph.graph.state"] = graph_state_module

if "lmbase" not in sys.modules:
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
    sys.modules["lmbase"] = lmbase_module
    sys.modules["lmbase.inference"] = lmbase_inference_module
    sys.modules["lmbase.inference.base"] = lmbase_inference_base_module
    sys.modules["lmbase.inference.api_call"] = lmbase_inference_api_call_module
    sys.modules["lmbase.utils"] = lmbase_utils_module
    sys.modules["lmbase.utils.tools"] = lmbase_utils_tools_module

from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


class SparseRagRoutingTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

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
                        {"episode_id": "E1", "name": "Arrest"},
                    ],
                },
                {
                    "stage_id": "S2",
                    "episodes": [
                        {"episode_id": "E2", "name": "Money Laundering"},
                    ],
                },
            ]
        }

    def test_build_episode_execution_plan_marks_simple_episode_light(self):
        plan = self.builder._build_episode_execution_plan(
            self._make_build_input(),
            self._make_skeleton(),
        )
        self.assertEqual(plan["S1:E1"]["mode"], "light")

    def test_build_episode_execution_plan_marks_money_dense_episode_full(self):
        plan = self.builder._build_episode_execution_plan(
            self._make_build_input(),
            self._make_skeleton(),
        )
        self.assertEqual(plan["S2:E2"]["mode"], "full")
