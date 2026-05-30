"""Routing parity tests for ContextEventBuilder execution budgets."""

from types import SimpleNamespace
import unittest

from finmy.generic import DataSample, UserQueryInput

from test_event_builder_registry import _install_external_dependency_stubs_if_missing


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _skeleton():
    return {
        "event_id": "EVT-ROUTE",
        "title": _vf("Routing event"),
        "event_type": _vf("financial event"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Investigation"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Screening"),
                        "start_time": _vf("2026-01-01"),
                        "end_time": _vf("2026-01-01"),
                    }
                ],
            }
        ],
    }


def _build_input():
    return SimpleNamespace(
        user_query=UserQueryInput(
            query_text="routing event",
            key_words=["routing", "event"],
        ),
        samples=[
            DataSample(
                sample_id="s1",
                raw_data_id="r1",
                content="The screening episode is supported by one primary source.",
                category="article",
                knowledge_field="finance",
            )
        ],
    )


def _state(plan_entry):
    skeleton = _skeleton()
    return {
        "build_input": _build_input(),
        "context_assets": None,
        "agent_results": [
            {"SkeletonReconstructor": skeleton},
            {"SkeletonChecker": skeleton},
            {
                "ParticipantReconstructor": {
                    "participants": [
                        {
                            "participant_id": "P1",
                            "name": _vf("Alpha"),
                            "participant_type": _vf("organization"),
                        }
                    ]
                },
                "_meta": {"episode_locator": {"stage_index": 0, "episode_index": 0}},
            },
        ],
        "agent_executed": [
            "SkeletonReconstructor",
            "SkeletonChecker",
            "ParticipantReconstructor",
        ],
        "cost": [],
        "episode_execution_plan": {
            "episodes": [
                {
                    "stage_index": 0,
                    "episode_index": 0,
                    "stage_id": "S1",
                    "episode_id": "E1",
                    "mode": "full",
                    "participant_tier": "compact",
                    "transaction_tier": "skip",
                    "episode_detail_tier": "compact",
                    "conflict_guard": "standard",
                    "compactness_hint": "Skip transaction reconstruction.",
                    **plan_entry,
                }
            ]
        },
    }


class EventBuilderRoutingRegressionTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()

    def test_participant_route_honors_transaction_skip_tier(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        builder = ContextEventBuilder.__new__(ContextEventBuilder)

        route = builder._route_after_participant_reconstructor(_state({}))

        self.assertEqual(route, "EpisodeReconstructor")

    def test_episode_prompt_uses_empty_transactions_for_skip_tier(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        builder = ContextEventBuilder.__new__(ContextEventBuilder)

        _, _, episode_budget, extra = builder._prompt_context_for_agent(
            _state({}),
            "EpisodeReconstructor",
        )

        self.assertEqual(episode_budget["transaction_tier"], "skip")
        self.assertEqual(extra["TargetEpisode"]["transactions"], [])
        self.assertEqual(
            extra["TargetEpisode"]["participants"][0]["participant_id"],
            "P1",
        )

    def test_execute_agent_records_budget_tiers_in_episode_metadata(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {"event_builder_config": {"max_context_chars": 400}}
        builder._infer_and_parse_json = lambda *args, **kwargs: {
            "descriptions": [_vf("Episode reconstructed without transactions.")]
        }

        state = _state(
            {
                "transaction_tier": "skip",
                "episode_detail_tier": "compact",
                "conflict_guard": "strict",
                "compactness_hint": "Use compact detail and skip transactions.",
            }
        )

        builder.execute_agent(state, "EpisodeReconstructor")

        meta = state["agent_results"][-1]["_meta"]
        self.assertEqual(meta["execution_mode"], "full")
        self.assertTrue(meta["transaction_step_skipped"])
        self.assertEqual(meta["transaction_tier"], "skip")
        self.assertEqual(meta["episode_detail_tier"], "compact")
        self.assertEqual(meta["conflict_guard"], "strict")
        self.assertIn("skip transactions", meta["compactness_hint"])


if __name__ == "__main__":
    unittest.main()
