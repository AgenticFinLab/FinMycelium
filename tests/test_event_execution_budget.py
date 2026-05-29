"""Focused tests for event_build execution budget routing."""

from types import SimpleNamespace
import unittest

from finmy.generic import DataSample, UserQueryInput


class EventExecutionBudgetTest(unittest.TestCase):
    def test_simple_episode_uses_light_mode_without_context_assets(self):
        from finmy.builder.event_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        build_input = SimpleNamespace(
            user_query=UserQueryInput(query_text="simple event", key_words=[]),
            samples=[],
        )
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": {"value": "Simple background"},
                    "episodes": [
                        {"episode_id": "E1", "name": {"value": "Initial notice"}},
                    ],
                }
            ]
        }

        budget = build_stage_aware_execution_budget(build_input, skeleton)
        episode_budget = budget["episodes"][("S1", "E1")]

        self.assertEqual(episode_budget["mode"], "light")
        self.assertEqual(episode_budget["transaction_tier"], "minimal")
        self.assertEqual(episode_budget["conflict_guard"], "standard")

    def test_money_dense_episode_uses_full_mode(self):
        from finmy.builder.event_build.context_assets import build_evidence_assets
        from finmy.builder.event_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        user_query = UserQueryInput(
            query_text="bitcoin laundering transfer",
            key_words=["bitcoin", "transfer"],
        )
        bundle = build_evidence_assets(
            user_query,
            [
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content=(
                        "The bitcoin transfer moved £23.5 million and "
                        "2.5 million BTC-linked proceeds through shell entities."
                    ),
                    category="money movement",
                    knowledge_field="finance",
                )
            ],
        )
        build_input = SimpleNamespace(user_query=user_query, samples=[])
        skeleton = {
            "stages": [
                {
                    "stage_id": "S2",
                    "name": {"value": "Money movement"},
                    "episodes": [
                        {
                            "episode_id": "E2",
                            "name": {"value": "Bitcoin transfer laundering"},
                        },
                    ],
                }
            ]
        }

        budget = build_stage_aware_execution_budget(
            build_input,
            skeleton,
            context_assets=bundle,
        )
        episode_budget = budget["episodes"][("S2", "E2")]

        self.assertEqual(episode_budget["mode"], "full")
        self.assertEqual(episode_budget["transaction_tier"], "standard")
        self.assertEqual(episode_budget["episode_detail_tier"], "standard")

    def test_missing_context_assets_does_not_crash(self):
        from finmy.builder.event_build.execution_budget import (
            build_stage_aware_execution_budget,
        )

        budget = build_stage_aware_execution_budget(
            build_input=None,
            event_skeleton={"stages": []},
            context_assets=None,
        )

        self.assertEqual(budget, {"stages": [], "episodes": {}})

    def test_budget_prompt_vars_use_explicit_prompt_keys(self):
        from finmy.builder.event_build.execution_budget import episode_budget_prompt_vars

        prompt_vars = episode_budget_prompt_vars(
            {
                "mode": "full",
                "transaction_tier": "standard",
                "episode_detail_tier": "standard",
                "conflict_guard": "strict",
                "compactness_hint": "Use complete participant and transaction detail.",
            }
        )

        self.assertEqual(prompt_vars["EpisodeExecutionMode"], "full")
        self.assertEqual(prompt_vars["TransactionDetailTier"], "standard")
        self.assertEqual(prompt_vars["EpisodeDetailTier"], "standard")
        self.assertEqual(prompt_vars["ConflictGuard"], "strict")
        self.assertIn("complete", prompt_vars["EpisodeCompactnessHint"])


if __name__ == "__main__":
    unittest.main()
