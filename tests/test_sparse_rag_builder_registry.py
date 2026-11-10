"""Contract tests for the sparse RAG builder registry entry."""

import dataclasses
import importlib.util
import sys
import types
import unittest


def _install_langgraph_stub_if_missing():
    if "langgraph" in sys.modules:
        return
    if importlib.util.find_spec("langgraph") is not None:
        return

    langgraph_mod = types.ModuleType("langgraph")
    graph_mod = types.ModuleType("langgraph.graph")
    state_mod = types.ModuleType("langgraph.graph.state")

    class MessagesState(dict):
        pass

    class StateGraph:
        def __init__(self, *args, **kwargs):
            pass

        def add_node(self, *args, **kwargs):
            pass

        def add_edge(self, *args, **kwargs):
            pass

        def compile(self):
            return CompiledStateGraph()

    class CompiledStateGraph:
        pass

    graph_mod.MessagesState = MessagesState
    graph_mod.StateGraph = StateGraph
    graph_mod.START = "__start__"
    graph_mod.END = "__end__"
    state_mod.CompiledStateGraph = CompiledStateGraph

    sys.modules.setdefault("langgraph", langgraph_mod)
    sys.modules.setdefault("langgraph.graph", graph_mod)
    sys.modules.setdefault("langgraph.graph.state", state_mod)


def _install_lmbase_stub_if_missing():
    if "lmbase" in sys.modules:
        return
    if importlib.util.find_spec("lmbase") is not None:
        return

    lmbase_mod = types.ModuleType("lmbase")
    inference_mod = types.ModuleType("lmbase.inference")
    api_call_mod = types.ModuleType("lmbase.inference.api_call")
    inference_base_mod = types.ModuleType("lmbase.inference.base")
    utils_mod = types.ModuleType("lmbase.utils")
    tools_mod = types.ModuleType("lmbase.utils.tools")

    class LangChainAPIInference:
        def __init__(self, *args, **kwargs):
            pass

    class InferInput:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class InferOutput:
        response = ""

        def to_dict(self):
            return {"response": self.response}

    class BaseContainer:
        pass

    api_call_mod.LangChainAPIInference = LangChainAPIInference
    api_call_mod.InferInput = InferInput
    inference_base_mod.InferInput = InferInput
    inference_base_mod.InferOutput = InferOutput
    tools_mod.BaseContainer = BaseContainer

    sys.modules.setdefault("lmbase", lmbase_mod)
    sys.modules.setdefault("lmbase.inference", inference_mod)
    sys.modules.setdefault("lmbase.inference.api_call", api_call_mod)
    sys.modules.setdefault("lmbase.inference.base", inference_base_mod)
    sys.modules.setdefault("lmbase.utils", utils_mod)
    sys.modules.setdefault("lmbase.utils.tools", tools_mod)


def _install_external_dependency_stubs_if_missing():
    _install_langgraph_stub_if_missing()
    _install_lmbase_stub_if_missing()


class SparseRagBuilderRegistryTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()

    def test_sparse_rag_builder_is_registered_under_public_builder_type(self):
        from finmy.builder.registry import builder_factory

        self.assertIn("SparseRagBuilder", builder_factory)
        builder_cls = builder_factory["SparseRagBuilder"]
        self.assertEqual("SparseRagBuilder", builder_cls.__name__)
        self.assertEqual("finmy.builder.sparse_build.main_build", builder_cls.__module__)


if __name__ == "__main__":
    unittest.main()
