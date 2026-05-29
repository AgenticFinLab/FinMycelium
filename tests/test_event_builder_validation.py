"""Skeleton validation behavior for ContextEventBuilder."""

import unittest
from types import SimpleNamespace


def _vf(value):
    return {"value": value, "evidence_source_contents": [], "reasons": []}


def _valid_skeleton():
    return {
        "event_id": "EVT-1",
        "title": _vf("Valid event"),
        "event_type": _vf("money movement"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Stage one"),
                "index_in_event": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-02"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode one"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                    }
                ],
            }
        ],
    }


class ContextEventBuilderValidationTest(unittest.TestCase):
    def setUp(self):
        from finmy.builder.event_build.main_build import ContextEventBuilder

        self.builder = ContextEventBuilder.__new__(ContextEventBuilder)

    def test_validate_skeleton_rejects_empty_stages(self):
        skeleton = {**_valid_skeleton(), "stages": []}

        valid, reason = self.builder._validate_event_skeleton(skeleton)

        self.assertFalse(valid)
        self.assertIn("stage", reason.lower())

    def test_validate_skeleton_rejects_unknown_title(self):
        skeleton = {**_valid_skeleton(), "title": _vf("unknown")}

        valid, reason = self.builder._validate_event_skeleton(skeleton)

        self.assertFalse(valid)
        self.assertIn("title", reason.lower())

    def test_validate_skeleton_accepts_minimal_meaningful_structure(self):
        valid, reason = self.builder._validate_event_skeleton(_valid_skeleton())

        self.assertTrue(valid, reason)

    def test_json_retry_recovers_on_second_attempt(self):
        responses = ["not json", '{"ok": true}']
        calls = []

        class FakeInference:
            def run(self, infer_input=None, **kwargs):
                calls.append(infer_input)
                return SimpleNamespace(response=responses.pop(0), to_dict=lambda: {})

        self.builder.agents_lm = FakeInference()

        parsed = self.builder._infer_and_parse_json(
            "SkeletonReconstructor",
            "system",
            "user",
            {},
            "SkeletonReconstructor-1",
        )

        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(len(calls), 2)

    def test_syntactic_recovery_extracts_first_balanced_json_fragment(self):
        class FakeInference:
            def run(self, infer_input=None, **kwargs):
                return SimpleNamespace(
                    response='prefix {"participants": []} trailing {"broken":',
                    to_dict=lambda: {},
                )

        self.builder.agents_lm = FakeInference()

        parsed = self.builder._infer_and_parse_json(
            "ParticipantReconstructor",
            "system",
            "user",
            {},
            "ParticipantReconstructor-1",
        )

        self.assertEqual(parsed, {"participants": []})


if __name__ == "__main__":
    unittest.main()
