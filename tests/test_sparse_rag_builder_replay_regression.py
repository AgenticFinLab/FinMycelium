"""Replay regression coverage for SparseRagBuilder."""

import json
from pathlib import Path
import tempfile
import unittest

from test_sparse_rag_builder_registry import _install_external_dependency_stubs_if_missing


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _episode(episode_id, name, index):
    return {
        "episode_id": episode_id,
        "name": _vf(name),
        "index_in_stage": index,
        "participants": [],
        "transactions": [],
    }


def _two_episode_skeleton(stage_id="S1", episode_ids=("E1", "E2")):
    return {
        "event_id": "EVT-1",
        "title": _vf("Replay event"),
        "event_type": _vf("money movement"),
        "stages": [
            {
                "stage_id": stage_id,
                "name": _vf("Replay stage"),
                "index_in_event": 0,
                "episodes": [
                    _episode(episode_ids[0], "First episode", 0),
                    _episode(episode_ids[1], "Second episode", 1),
                ],
            }
        ],
    }


def _locator(stage_index, episode_index, stage_id="", episode_id=""):
    return {
        "stage_index": stage_index,
        "episode_index": episode_index,
        "stage_id": stage_id,
        "episode_id": episode_id,
    }


def _write_json(directory, filename, payload):
    Path(directory, filename).write_text(json.dumps(payload), encoding="utf-8")


class SparseRagBuilderReplayRegressionTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()
        from finmy.builder.sparse_build.main_build import SparseRagBuilder

        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)

    def test_integrate_from_files_keeps_blank_id_replay_episodes_distinct(self):
        skeleton = {
            "stages": [
                {
                    "stage_id": "",
                    "name": _vf("First stage"),
                    "episodes": [_episode("", "Blank first", 0)],
                },
                {
                    "stage_id": "",
                    "name": _vf("Second stage"),
                    "episodes": [_episode("", "Blank second", 0)],
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self.builder.save_dir = tmpdir
            _write_json(tmpdir, "SkeletonChecker-1-Result.json", skeleton)
            _write_json(
                tmpdir,
                "ParticipantReconstructor-2-Stage0-Episode0-Result.json",
                {"participants": [{"participant_id": "P1"}]},
            )
            _write_json(
                tmpdir,
                "EpisodeReconstructor-3-Stage0-Episode0-Result.json",
                {
                    "episode_id": "",
                    "name": _vf("First replay episode"),
                    "participants": [{"participant_id": "P1"}],
                    "transactions": [],
                },
            )
            _write_json(
                tmpdir,
                "ParticipantReconstructor-4-Stage1-Episode0-Result.json",
                {"participants": [{"participant_id": "P2"}]},
            )
            _write_json(
                tmpdir,
                "EpisodeReconstructor-5-Stage1-Episode0-Result.json",
                {
                    "episode_id": "",
                    "name": _vf("Second replay episode"),
                    "participants": [{"participant_id": "P2"}],
                    "transactions": [],
                },
            )

            final_cascade = self.builder.integrate_from_files()

        first_episode = final_cascade["stages"][0]["episodes"][0]
        second_episode = final_cascade["stages"][1]["episodes"][0]
        self.assertEqual(first_episode["name"]["value"], "First replay episode")
        self.assertEqual(second_episode["name"]["value"], "Second replay episode")
        self.assertEqual(first_episode["participants"][0]["participant_id"], "P1")
        self.assertEqual(second_episode["participants"][0]["participant_id"], "P2")

    def test_integrate_results_keeps_duplicate_non_empty_ids_distinct(self):
        skeleton = {
            "stages": [
                {
                    "stage_id": "SAME",
                    "name": _vf("First duplicate stage"),
                    "episodes": [_episode("E", "First duplicate", 0)],
                },
                {
                    "stage_id": "SAME",
                    "name": _vf("Second duplicate stage"),
                    "episodes": [_episode("E", "Second duplicate", 0)],
                },
            ]
        }
        state = {
            "agent_results": [
                {"SkeletonChecker": skeleton},
                {
                    "ParticipantReconstructor": {"participants": [{"participant_id": "P1"}]},
                    "_meta": {"episode_locator": _locator(0, 0, "SAME", "E")},
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E",
                        "name": _vf("First duplicate replay"),
                        "participants": [{"participant_id": "P1"}],
                        "transactions": [],
                    },
                    "_meta": {"episode_locator": _locator(0, 0, "SAME", "E")},
                },
                {
                    "ParticipantReconstructor": {"participants": [{"participant_id": "P2"}]},
                    "_meta": {"episode_locator": _locator(1, 0, "SAME", "E")},
                },
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E",
                        "name": _vf("Second duplicate replay"),
                        "participants": [{"participant_id": "P2"}],
                        "transactions": [],
                    },
                    "_meta": {"episode_locator": _locator(1, 0, "SAME", "E")},
                },
            ],
            "episode_execution_plan": {"episodes": []},
        }

        final_cascade = self.builder.integrate_results(state)

        first_episode = final_cascade["stages"][0]["episodes"][0]
        second_episode = final_cascade["stages"][1]["episodes"][0]
        self.assertEqual(first_episode["name"]["value"], "First duplicate replay")
        self.assertEqual(second_episode["name"]["value"], "Second duplicate replay")
        self.assertEqual(first_episode["participants"][0]["participant_id"], "P1")
        self.assertEqual(second_episode["participants"][0]["participant_id"], "P2")

    def test_integrate_from_files_uses_episode_locator_when_result_only_covers_second_episode(self):
        skeleton = _two_episode_skeleton()

        with tempfile.TemporaryDirectory() as tmpdir:
            self.builder.save_dir = tmpdir
            _write_json(tmpdir, "SkeletonChecker-1-Result.json", skeleton)
            _write_json(
                tmpdir,
                "EpisodeReconstructor-2-Stage0-Episode1-Result.json",
                {
                    "episode_id": "E2",
                    "name": _vf("Second replay episode"),
                    "participants": [{"participant_id": "P2"}],
                    "transactions": [],
                },
            )

            final_cascade = self.builder.integrate_from_files()

        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["name"]["value"], "First episode")
        self.assertEqual(episodes[1]["name"]["value"], "Second replay episode")
        self.assertEqual(episodes[1]["participants"][0]["participant_id"], "P2")

    def test_integrate_from_files_replays_mixed_light_then_full_transactions_correctly(self):
        skeleton = _two_episode_skeleton(episode_ids=("E1", "E2"))

        with tempfile.TemporaryDirectory() as tmpdir:
            self.builder.save_dir = tmpdir
            _write_json(tmpdir, "SkeletonChecker-1-Result.json", skeleton)
            _write_json(
                tmpdir,
                "EpisodeReconstructor-2-Stage0-Episode0-Result.json",
                {
                    "episode_id": "E1",
                    "name": _vf("Light replay episode"),
                    "participants": [{"participant_id": "P1"}],
                    "transactions": [{"transaction_id": "UNTRUSTED_LIGHT"}],
                },
            )
            _write_json(
                tmpdir,
                "EpisodeReconstructor-3-Stage0-Episode1-Result.json",
                {
                    "episode_id": "E2",
                    "name": _vf("Full replay episode"),
                    "participants": [{"participant_id": "P2"}],
                    "transactions": [],
                },
            )
            _write_json(
                tmpdir,
                "TransactionReconstructor-4-Stage0-Episode1-Result.json",
                {"transactions": [{"transaction_id": "T_FULL"}]},
            )

            final_cascade = self.builder.integrate_from_files()

        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["transactions"], [])
        self.assertEqual(episodes[1]["transactions"][0]["transaction_id"], "T_FULL")

    def test_integrate_from_files_preserves_wrapped_episode_metadata_without_filename_locator(self):
        skeleton = _two_episode_skeleton()

        with tempfile.TemporaryDirectory() as tmpdir:
            self.builder.save_dir = tmpdir
            _write_json(tmpdir, "SkeletonChecker-1-Result.json", skeleton)
            _write_json(
                tmpdir,
                "ParticipantReconstructor-2-Result.json",
                {
                    "ParticipantReconstructor": {
                        "participants": [{"participant_id": "P2"}]
                    },
                    "_meta": {"episode_locator": _locator(0, 1, "S1", "E2")},
                },
            )
            _write_json(
                tmpdir,
                "EpisodeReconstructor-3-Result.json",
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E2",
                        "name": _vf("Wrapped second replay"),
                        "participants": [{"participant_id": "P2"}],
                        "transactions": [],
                    },
                    "_meta": {"episode_locator": _locator(0, 1, "S1", "E2")},
                },
            )

            final_cascade = self.builder.integrate_from_files()

        episodes = final_cascade["stages"][0]["episodes"]
        self.assertEqual(episodes[0]["name"]["value"], "First episode")
        self.assertEqual(episodes[1]["name"]["value"], "Wrapped second replay")
        self.assertEqual(episodes[1]["participants"][0]["participant_id"], "P2")

    def test_integrate_from_files_respects_skip_metadata_over_transaction_artifact(self):
        skeleton = {
            "stages": [
                {
                    "stage_id": "S1",
                    "name": _vf("Replay stage"),
                    "episodes": [_episode("E1", "Skip transaction episode", 0)],
                }
            ]
        }
        locator = _locator(0, 0, "S1", "E1")

        with tempfile.TemporaryDirectory() as tmpdir:
            self.builder.save_dir = tmpdir
            _write_json(tmpdir, "SkeletonChecker-1-Result.json", skeleton)
            _write_json(
                tmpdir,
                "TransactionReconstructor-2-Stage0-Episode0-Result.json",
                {"transactions": [{"transaction_id": "SHOULD_SKIP"}]},
            )
            _write_json(
                tmpdir,
                "EpisodeReconstructor-3-Stage0-Episode0-Result.json",
                {
                    "EpisodeReconstructor": {
                        "episode_id": "E1",
                        "name": _vf("Skip transaction episode"),
                        "participants": [],
                        "transactions": [{"transaction_id": "PLACEHOLDER"}],
                    },
                    "_meta": {
                        "episode_locator": locator,
                        "execution_mode": "full",
                        "transaction_step_skipped": True,
                        "transaction_tier": "skip",
                    },
                },
            )

            final_cascade = self.builder.integrate_from_files()

        episode = final_cascade["stages"][0]["episodes"][0]
        self.assertEqual(episode["transactions"], [])


if __name__ == "__main__":
    unittest.main()
