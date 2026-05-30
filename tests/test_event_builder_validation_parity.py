"""Validation and JSON recovery parity tests for ContextEventBuilder."""

import json
from types import SimpleNamespace
import unittest


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _valid_skeleton():
    return {
        "event_id": "EVT-VALIDATION",
        "title": _vf("Validation event"),
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


class EventBuilderValidationParityTest(unittest.TestCase):
    def setUp(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        self.builder = ContextEventBuilder.__new__(ContextEventBuilder)

    def test_validate_skeleton_rejects_metadata_only_stage_name(self):
        skeleton = _valid_skeleton()
        skeleton["stages"][0]["name"] = {
            "evidence_source_contents": [],
            "reasons": [],
        }

        valid, reason = self.builder._validate_event_skeleton(skeleton)

        self.assertFalse(valid)
        self.assertIn("stage 0 name", reason.lower())

    def test_validate_skeleton_rejects_metadata_only_episode_name(self):
        skeleton = _valid_skeleton()
        skeleton["stages"][0]["episodes"][0]["name"] = {
            "evidence_source_contents": [],
            "reasons": [],
        }

        valid, reason = self.builder._validate_event_skeleton(skeleton)

        self.assertFalse(valid)
        self.assertIn("episode 0/0 name", reason.lower())

    def test_skeleton_checker_recovers_balanced_json_fragment_without_retry(self):
        skeleton = _valid_skeleton()
        calls = []

        class FakeInference:
            def run(self, infer_input=None, **kwargs):
                calls.append(infer_input)
                if len(calls) > 1:
                    raise AssertionError("SkeletonChecker should recover before retrying")
                return SimpleNamespace(
                    response=(
                        f"prefix {json.dumps(skeleton)} "
                        f"trailing {json.dumps({'extra': True})}"
                    ),
                    to_dict=lambda: {},
                )

        self.builder.agents_lm = FakeInference()

        parsed = self.builder._infer_and_parse_json(
            "SkeletonChecker",
            "system",
            "user",
            {},
            "SkeletonChecker-1",
        )

        self.assertEqual(parsed, skeleton)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
