"""Tests for the lightweight SparseRagBuilder checkpoint replay tool."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from test_sparse_rag_builder_registry import _install_external_dependency_stubs_if_missing


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _skeleton():
    return {
        "event_id": "EVT-CHECKPOINT",
        "title": _vf("Checkpoint event"),
        "event_type": _vf("financial event"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Stage one"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode one"),
                    }
                ],
            }
        ],
    }


def _two_stage_cascade():
    cascade = _skeleton()
    cascade["stages"].append(
        {
            "stage_id": "S2",
            "name": _vf("Stage two"),
            "episodes": [
                {"episode_id": "E2", "name": _vf("Episode two")},
                {"episode_id": "E3", "name": _vf("Episode three")},
            ],
        }
    )
    return cascade


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _load_tool_module():
    tool_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "uTEST"
        / "replay_sparse_rag_builder_checkpoint.py"
    )
    spec = importlib.util.spec_from_file_location(
        "replay_sparse_rag_builder_checkpoint",
        tool_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EventReplayCheckpointToolTest(unittest.TestCase):
    def setUp(self):
        _install_external_dependency_stubs_if_missing()

    def test_summarize_latest_checkpoint_selects_latest_usable_build_output(self):
        tool = _load_tool_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_dir = root / "build_output_old"
            new_dir = root / "build_output_new"
            _write_json(old_dir / "SkeletonChecker-1-Result.json", {"stages": []})
            _write_json(old_dir / "FinalEventCascade.json", {"stages": []})
            _write_json(new_dir / "SkeletonChecker-1-Result.json", _two_stage_cascade())
            _write_json(new_dir / "FinalEventCascade.json", _two_stage_cascade())
            os.utime(old_dir, (1, 1))
            os.utime(new_dir, (2, 2))

            summary = tool.summarize_latest_checkpoint(root)

        self.assertTrue(str(summary["checkpoint_dir"]).endswith("build_output_new"))
        self.assertEqual(summary["skeleton"]["stage_count"], 2)
        self.assertEqual(summary["skeleton"]["episode_count"], 3)
        self.assertEqual(summary["final"]["stage_count"], 2)
        self.assertEqual(summary["final"]["episode_count"], 3)

    def test_summarize_checkpoint_uses_reconstructor_and_integrated_fallback(self):
        tool = _load_tool_module()
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_dir = Path(tmp)
            _write_json(
                checkpoint_dir / "SkeletonReconstructor-1-Result.json",
                _skeleton(),
            )
            _write_json(checkpoint_dir / "IntegratedEventCascade.json", _skeleton())

            summary = tool.summarize_checkpoint_dir(checkpoint_dir)

        self.assertIn("SkeletonReconstructor-1-Result.json", summary["skeleton"]["path"])
        self.assertIn("IntegratedEventCascade.json", summary["final"]["path"])
        self.assertEqual(summary["skeleton"]["stage_count"], 1)
        self.assertEqual(summary["final"]["episode_count"], 1)

    def test_replay_checkpoint_dir_uses_sparse_rag_builder_result_files(self):
        tool = _load_tool_module()
        skeleton = _skeleton()
        episode_result = {
            **skeleton["stages"][0]["episodes"][0],
            "name": _vf("Replayed episode"),
            "participants": [],
            "transactions": [],
            "participant_relations": [],
            "descriptions": [_vf("Replayed from checkpoint files.")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_dir = Path(tmp)
            _write_json(checkpoint_dir / "SkeletonReconstructor-1-Result.json", skeleton)
            _write_json(checkpoint_dir / "SkeletonChecker-2-Result.json", skeleton)
            _write_json(
                checkpoint_dir / "EpisodeReconstructor-3-Stage0-Episode0-Result.json",
                episode_result,
            )

            replayed = tool.replay_checkpoint_dir(checkpoint_dir)

        episode = replayed["stages"][0]["episodes"][0]
        self.assertEqual(episode["name"]["value"], "Replayed episode")
        self.assertEqual(episode["descriptions"][0]["value"], "Replayed from checkpoint files.")


if __name__ == "__main__":
    unittest.main()
