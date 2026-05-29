"""Focused tests for event_build prompt input wiring."""

from types import SimpleNamespace
import unittest

from finmy.generic import DataSample, UserQueryInput

from test_event_builder_registry import _install_external_dependency_stubs_if_missing


class EventPromptInputsTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()

    def test_prompts_include_required_sparse_context_variables(self):
        from finmy.builder.event_build.prompts import (
            ADDITIVE_CONTEXT_POLICY,
            required_prompt_variables,
        )

        required = required_prompt_variables()

        self.assertIn("primary evidence", ADDITIVE_CONTEXT_POLICY.lower())
        self.assertIn("additive evidence", ADDITIVE_CONTEXT_POLICY.lower())
        self.assertIn("never", ADDITIVE_CONTEXT_POLICY.lower())
        self.assertIn("RetrievedContext", required)
        self.assertIn("RetrievedContextSummary", required)
        self.assertIn("EpisodeExecutionMode", required)
        self.assertIn("TransactionDetailTier", required)
        self.assertIn("EpisodeDetailTier", required)

    def test_builder_prompt_kwargs_expose_context_budget_and_primary_content(self):
        from finmy.builder.event_build.context_assets import build_evidence_assets
        from finmy.builder.event_build.execution_budget import (
            build_stage_aware_execution_budget,
        )
        from finmy.builder.event_build.main_build import ContextEventBuilder

        user_query = UserQueryInput(
            query_text="bitcoin laundering transfer",
            key_words=["bitcoin", "transfer"],
        )
        samples = [
            DataSample(
                sample_id="s1",
                raw_data_id="r1",
                content="Primary article says bitcoin transfer moved £23.5 million.",
                category="article",
                knowledge_field="finance",
            )
        ]
        build_input = SimpleNamespace(user_query=user_query, samples=samples)
        context_assets = build_evidence_assets(user_query, samples)
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": {"value": "Money movement"},
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Bitcoin transfer"}},
                    ],
                }
            ]
        }
        budget = build_stage_aware_execution_budget(
            build_input,
            skeleton,
            context_assets=context_assets,
        )
        episode_budget = budget["episodes"][("S1", "E1")]
        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {"event_builder_config": {"max_context_chars": 400}}

        kwargs = builder._build_prompt_kwargs(
            build_input=build_input,
            agent_name="EpisodeReconstructor",
            context_assets=context_assets,
            target_stage="Money movement",
            target_episode="Bitcoin transfer",
            episode_budget=episode_budget,
        )

        self.assertIn("Primary article says", kwargs["Content"])
        self.assertIn("sample_id: s1", kwargs["RetrievedContext"])
        self.assertIn("context_asset_summary:", kwargs["RetrievedContextSummary"])
        self.assertEqual(kwargs["EpisodeExecutionMode"], "full")
        self.assertEqual(kwargs["TransactionDetailTier"], "standard")
        self.assertIn("selected_sample_ids", kwargs["RetrievedContextMemory"])
        self.assertIn("used_card_count", kwargs["RetrievedContextBudgetSummary"])

    def test_format_agent_messages_supplies_all_template_variables(self):
        from finmy.builder.event_build.context_assets import build_evidence_assets
        from finmy.builder.event_build.main_build import ContextEventBuilder

        user_query = UserQueryInput(query_text="alpha transfer", key_words=["alpha"])
        samples = [
            DataSample(
                sample_id="s1",
                raw_data_id="r1",
                content="alpha transfer evidence",
                category="article",
                knowledge_field="finance",
            )
        ]
        build_input = SimpleNamespace(user_query=user_query, samples=samples)
        context_assets = build_evidence_assets(user_query, samples)
        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {"event_builder_config": {"max_context_chars": 400}}

        system_msg, user_msg = builder._format_agent_messages(
            agent_name="EpisodeReconstructor",
            prompt_kwargs=builder._build_prompt_kwargs(
                build_input=build_input,
                agent_name="EpisodeReconstructor",
                context_assets=context_assets,
                target_stage="alpha stage",
                target_episode="alpha transfer",
            ),
        )

        self.assertIn("primary evidence", system_msg.lower())
        self.assertIn("RETRIEVED CONTEXT BEGIN", user_msg)
        self.assertIn("EPISODE EXECUTION MODE", user_msg)
        self.assertIn("alpha transfer evidence", user_msg)

    def test_run_uses_mock_inference_without_external_api(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        class FakeInference:
            def __init__(self):
                self.calls = []

            def run(self, infer_input=None, **kwargs):
                self.calls.append((infer_input, kwargs))
                return SimpleNamespace(
                    response='{"event_id": "EVT-1", "title": "alpha", "stages": []}',
                    to_dict=lambda: {"response": "ok"},
                )

        user_query = UserQueryInput(query_text="alpha transfer", key_words=["alpha"])
        build_input = SimpleNamespace(
            user_query=user_query,
            samples=[
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content="alpha transfer evidence",
                    category="article",
                    knowledge_field="finance",
                )
            ],
        )
        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {"event_builder_config": {"max_context_chars": 400}}
        builder.agents_lm = FakeInference()

        output = builder.run(build_input)

        self.assertEqual(output.event_cascades["event_id"], "EVT-1")
        self.assertEqual(output.extras["builder_type"], "ContextEventBuilder")
        self.assertEqual(
            output.extras["agent_executed"],
            [
                "SkeletonReconstructor",
                "SkeletonChecker",
                "EventDescriptionReconstructor",
            ],
        )
        self.assertEqual(len(builder.agents_lm.calls), 3)
        self.assertIn("RetrievedContext", builder.agents_lm.calls[0][1])
        self.assertIn("ProposedSkeleton", builder.agents_lm.calls[1][1])


if __name__ == "__main__":
    unittest.main()
