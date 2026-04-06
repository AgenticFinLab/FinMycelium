import unittest
import sys
import types
from unittest.mock import patch

def _install_test_dependency_stubs() -> None:
    def ensure_module(name: str) -> types.ModuleType:
        module = sys.modules.get(name)
        if module is None:
            module = types.ModuleType(name)
            sys.modules[name] = module
        return module

    dotenv_module = ensure_module("dotenv")
    if not hasattr(dotenv_module, "load_dotenv"):
        dotenv_module.load_dotenv = lambda *args, **kwargs: False

    lmbase_module = ensure_module("lmbase")
    lmbase_module.__path__ = []

    lmbase_utils_module = ensure_module("lmbase.utils")
    lmbase_utils_module.__path__ = []
    lmbase_tools_module = ensure_module("lmbase.utils.tools")

    class BaseContainer:
        pass

    class BlockBasedStoreManager:
        def __init__(self, *args, **kwargs):
            pass

        def save(self, *args, **kwargs):
            return None

        def load(self, *args, **kwargs):
            return {"text": ""}

    lmbase_tools_module.BaseContainer = BaseContainer
    lmbase_tools_module.BlockBasedStoreManager = BlockBasedStoreManager
    lmbase_utils_module.tools = lmbase_tools_module

    lmbase_inference_module = ensure_module("lmbase.inference")
    lmbase_inference_module.__path__ = []
    lmbase_api_call_module = ensure_module("lmbase.inference.api_call")

    class LangChainAPIInference:
        def __init__(self, *args, **kwargs):
            pass

        def _inference(self, messages):
            return types.SimpleNamespace(response="")

    lmbase_api_call_module.LangChainAPIInference = LangChainAPIInference
    lmbase_api_call_module.InferInput = type("InferInput", (), {})
    lmbase_api_call_module.InferOutput = type("InferOutput", (), {})
    lmbase_inference_module.api_call = lmbase_api_call_module
    lmbase_inference_module.LangChainAPIInference = LangChainAPIInference
    lmbase_inference_module.InferInput = lmbase_api_call_module.InferInput
    lmbase_inference_module.InferOutput = lmbase_api_call_module.InferOutput

    langgraph_module = ensure_module("langgraph")
    langgraph_module.__path__ = []
    langgraph_graph_module = ensure_module("langgraph.graph")

    class MessagesState:
        pass

    class StateGraph:
        pass

    langgraph_graph_module.MessagesState = MessagesState
    langgraph_graph_module.StateGraph = StateGraph
    langgraph_graph_module.START = "START"
    langgraph_graph_module.END = "END"
    langgraph_state_module = ensure_module("langgraph.graph.state")

    class CompiledStateGraph:
        pass

    langgraph_state_module.CompiledStateGraph = CompiledStateGraph
    langgraph_graph_module.state = langgraph_state_module

    spacy_module = ensure_module("spacy")
    spacy_module.__path__ = []
    if not hasattr(spacy_module, "load"):
        spacy_module.load = lambda *args, **kwargs: object()
    spacy_matcher_module = ensure_module("spacy.matcher")

    class Matcher:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            return None

        def __call__(self, doc):
            return []

    spacy_matcher_module.Matcher = Matcher
    spacy_module.matcher = spacy_matcher_module


_install_test_dependency_stubs()

from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
)
from finmy.converter import convert_to_build_input
from finmy.generic import DataSample, MetaSample, UserQueryInput


class ConvertToBuildInputContextAssetsTest(unittest.TestCase):
    def test_preserves_supplied_context_assets_bundle(self):
        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha"])
        meta_samples = [
            MetaSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                location="meta-1",
                time="2025-01-01 00:00:00 UTC",
                category="risk",
                knowledge_field="finance",
                tag="tag-1",
                method="method-1",
            )
        ]
        context_assets = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(token_counts={"alpha": 1}),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="alpha excerpt",
                    tokens=["alpha"],
                )
            ],
        )

        with patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            build_input = convert_to_build_input(
                user_query=user_query,
                meta_samples=meta_samples,
                context_assets=context_assets,
            )

        self.assertIs(build_input.context_assets, context_assets)

    def test_build_evidence_assets_removes_skip_to_main_content_boilerplate(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Skip to main content Search for Careers Contact About us "
                "Qian Zhimin ran the Blue Sky Ponzi scheme and later laundered funds."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Skip to main content", excerpt)
        self.assertTrue(excerpt.startswith("Qian Zhimin"))
        self.assertIn("Blue Sky", excerpt)

    def test_build_evidence_assets_preserves_legitimate_leading_cnn_text(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Ad Feedback CNN analysis linked Qian Zhimin to laundering."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Ad Feedback", excerpt)
        self.assertTrue(excerpt.startswith("CNN analysis"))
        self.assertIn("Qian Zhimin", excerpt)

    def test_build_evidence_assets_preserves_legitimate_leading_cnn_reports_text(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Skip to main content CNN reports Qian Zhimin fled China."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Skip to main content", excerpt)
        self.assertTrue(excerpt.startswith("CNN reports"))
        self.assertIn("Qian Zhimin", excerpt)


if __name__ == "__main__":
    unittest.main()
