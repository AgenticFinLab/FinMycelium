"""Full-flow behavior tests for ContextEventBuilder."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from finmy.generic import DataSample, UserQueryInput

from test_event_builder_registry import _install_external_dependency_stubs_if_missing


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _skeleton():
    return {
        "event_id": "EVT-1",
        "title": _vf("Bitcoin laundering event"),
        "event_type": _vf("money laundering"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Money movement"),
                "index_in_event": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-02"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Bitcoin transfer"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                    }
                ],
            }
        ],
    }


class _SequencedInference:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, infer_input=None, **kwargs):
        if not self.responses:
            raise AssertionError("Unexpected inference call")
        response = self.responses.pop(0)
        self.calls.append((infer_input, kwargs))
        return SimpleNamespace(
            response=response,
            to_dict=lambda: {"response": response},
        )


class ContextEventBuilderFullFlowTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()

    def _build_input(self):
        return SimpleNamespace(
            user_query=UserQueryInput(
                query_text="bitcoin laundering transfer",
                key_words=["bitcoin", "transfer"],
            ),
            samples=[
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content=(
                        "On 2025-01-01 Alpha transferred £23.5 million in bitcoin "
                        "to Beta during a laundering investigation."
                    ),
                    category="article",
                    knowledge_field="finance",
                )
            ],
        )

    def test_run_executes_full_agent_flow_and_integrates_results(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        skeleton = _skeleton()
        participant_result = {
            "participants": [
                {
                    "participant_id": "P_1",
                    "name": _vf("Alpha"),
                    "participant_type": _vf("organization"),
                    "attributes": [],
                    "actions": [],
                },
                {
                    "participant_id": "P_2",
                    "name": _vf("Beta"),
                    "participant_type": _vf("organization"),
                    "attributes": [],
                    "actions": [],
                },
            ]
        }
        transaction_result = {
            "transactions": [
                {
                    "transaction_id": "T_1",
                    "name": _vf("Bitcoin transfer"),
                    "transaction_type": _vf("crypto transfer"),
                    "timestamp": _vf("2025-01-01"),
                    "details": [_vf("Alpha transferred £23.5 million in bitcoin.")],
                    "from_participant_id": "P_1",
                    "to_participant_id": "P_2",
                    "instruments": [],
                }
            ]
        }
        episode_result = {
            **skeleton["stages"][0]["episodes"][0],
            "participants": "Results of ParticipantReconstructor",
            "transactions": "Results of TransactionReconstructor",
            "participant_relations": [],
            "descriptions": [_vf("Alpha moved bitcoin to Beta.")],
        }
        stage_description = {"descriptions": [_vf("The stage covers the bitcoin flow.")]}
        event_description = {
            "descriptions": [_vf("The event describes a bitcoin laundering transfer.")]
        }

        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {
            "event_builder_config": {"max_context_chars": 600},
            "graph_config": {"recursion_limit": 50},
        }
        builder.agents_lm = _SequencedInference(
            [
                json.dumps(skeleton),
                json.dumps(skeleton),
                json.dumps(participant_result),
                json.dumps(transaction_result),
                json.dumps(episode_result),
                json.dumps(stage_description),
                json.dumps(event_description),
            ]
        )

        output = builder.run(self._build_input())

        self.assertEqual(
            output.extras["agent_executed"],
            [
                "SkeletonReconstructor",
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
                "EpisodeReconstructor",
                "StageDescriptionReconstructor",
                "EventDescriptionReconstructor",
            ],
        )
        episode = output.event_cascades["stages"][0]["episodes"][0]
        self.assertEqual(episode["participants"], participant_result["participants"])
        self.assertEqual(episode["transactions"], transaction_result["transactions"])
        self.assertEqual(
            output.event_cascades["stages"][0]["descriptions"],
            stage_description["descriptions"],
        )
        self.assertEqual(
            output.event_cascades["descriptions"],
            event_description["descriptions"],
        )
        self.assertEqual(
            json.loads(builder.agents_lm.calls[1][1]["ProposedSkeleton"]),
            skeleton,
        )
        self.assertFalse(builder.agents_lm.responses)

    def test_run_persists_replayable_result_files(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        skeleton = _skeleton()
        participant_result = {"participants": []}
        transaction_result = {"transactions": []}
        episode_result = {
            **skeleton["stages"][0]["episodes"][0],
            "participants": "Results of ParticipantReconstructor",
            "transactions": "Results of TransactionReconstructor",
            "participant_relations": [],
            "descriptions": [_vf("The transfer episode is reconstructed.")],
        }
        stage_description = {"descriptions": [_vf("Stage description")]}
        event_description = {"descriptions": [_vf("Event description")]}

        with tempfile.TemporaryDirectory() as save_dir:
            builder = ContextEventBuilder.__new__(ContextEventBuilder)
            builder.build_config = {
                "event_builder_config": {"max_context_chars": 600},
                "graph_config": {"recursion_limit": 50},
            }
            builder.save_dir = save_dir
            builder.agents_lm = _SequencedInference(
                [
                    json.dumps(skeleton),
                    json.dumps(skeleton),
                    json.dumps(participant_result),
                    json.dumps(transaction_result),
                    json.dumps(episode_result),
                    json.dumps(stage_description),
                    json.dumps(event_description),
                ]
            )

            output = builder.run(self._build_input())
            replayed = builder.integrate_from_files()

        self.assertEqual(replayed, output.event_cascades)

    def test_light_episode_skips_transaction_reconstructor(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        skeleton = _skeleton()
        skeleton["stages"][0]["name"] = _vf("Background")
        skeleton["stages"][0]["episodes"][0]["name"] = _vf("Initial notice")
        participant_result = {"participants": []}
        episode_result = {
            **skeleton["stages"][0]["episodes"][0],
            "participants": "Results of ParticipantReconstructor",
            "transactions": "Results of TransactionReconstructor",
            "participant_relations": [],
            "descriptions": [_vf("A compact notice episode.")],
        }
        stage_description = {"descriptions": [_vf("Stage description")]}
        event_description = {"descriptions": [_vf("Event description")]}
        build_input = SimpleNamespace(
            user_query=UserQueryInput(query_text="simple notice", key_words=[]),
            samples=[
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content="A simple notice was published.",
                    category="article",
                    knowledge_field="finance",
                )
            ],
        )
        builder = ContextEventBuilder.__new__(ContextEventBuilder)
        builder.build_config = {
            "event_builder_config": {"max_context_chars": 600},
            "graph_config": {"recursion_limit": 50},
        }
        builder.agents_lm = _SequencedInference(
            [
                json.dumps(skeleton),
                json.dumps(skeleton),
                json.dumps(participant_result),
                json.dumps(episode_result),
                json.dumps(stage_description),
                json.dumps(event_description),
            ]
        )

        output = builder.run(build_input)

        self.assertEqual(
            output.extras["agent_executed"],
            [
                "SkeletonReconstructor",
                "SkeletonChecker",
                "ParticipantReconstructor",
                "EpisodeReconstructor",
                "StageDescriptionReconstructor",
                "EventDescriptionReconstructor",
            ],
        )
        episode = output.event_cascades["stages"][0]["episodes"][0]
        self.assertEqual(episode["transactions"], [])
        self.assertFalse(builder.agents_lm.responses)

    def test_replay_prefers_checker_skeleton_regardless_of_file_order(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        draft = _skeleton()
        draft["title"] = _vf("Draft skeleton")
        checked = _skeleton()
        checked["title"] = _vf("Checked skeleton")
        event_description = {"descriptions": [_vf("Event description")]}

        with tempfile.TemporaryDirectory() as save_dir:
            Path(save_dir, "SkeletonChecker-1-Result.json").write_text(
                json.dumps(checked),
                encoding="utf-8",
            )
            Path(save_dir, "SkeletonReconstructor-1-Result.json").write_text(
                json.dumps(draft),
                encoding="utf-8",
            )
            Path(save_dir, "EventDescriptionReconstructor-1-Result.json").write_text(
                json.dumps(event_description),
                encoding="utf-8",
            )
            builder = ContextEventBuilder.__new__(ContextEventBuilder)
            builder.save_dir = save_dir

            with patch(
                "finmy.builder.event_build.main_build.os.listdir",
                return_value=[
                    "SkeletonChecker-1-Result.json",
                    "SkeletonReconstructor-1-Result.json",
                    "EventDescriptionReconstructor-1-Result.json",
                ],
            ):
                replayed = builder.integrate_from_files()

        self.assertEqual(replayed["title"], checked["title"])


if __name__ == "__main__":
    unittest.main()
