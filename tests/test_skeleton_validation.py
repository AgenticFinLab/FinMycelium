import unittest

from finmy.builder.agent_build.main_build import AgentEventBuilder


def _vf(value):
    return {
        "value": value,
        "evidence_source_contents": [],
        "reasons": [],
        "confidence": 1.0,
    }


def _episode(name="Episode 1", start="2025-01-01", end="2025-01-02"):
    return {
        "episode_id": "E1",
        "name": _vf(name),
        "index_in_stage": 0,
        "start_time": _vf(start),
        "end_time": _vf(end),
    }


def _stage(name="Stage 1", episodes=None, start="2025-01-01", end="2025-01-02"):
    return {
        "stage_id": "S1",
        "name": _vf(name),
        "index_in_event": 0,
        "start_time": _vf(start),
        "end_time": _vf(end),
        "episodes": episodes if episodes is not None else [_episode()],
    }


def _skeleton(title="Demo Event", stages=None):
    return {
        "event_id": "demo_event",
        "title": _vf(title),
        "event_type": _vf("demo"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": stages if stages is not None else [_stage()],
    }


class SkeletonValidationTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

    def test_validate_skeleton_rejects_empty_stages(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton(stages=[]))
        self.assertFalse(valid)
        self.assertEqual(reason, "no_stages")

    def test_validate_skeleton_rejects_zero_total_episodes(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(stages=[_stage(episodes=[])])
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "no_episodes")

    def test_validate_skeleton_rejects_unknown_title(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(title="unknown")
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_event_title")

    def test_validate_skeleton_rejects_semantically_empty_stage_and_episode_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        name="unknown",
                        start="unknown",
                        end="unknown",
                        episodes=[_episode(name="unknown", start="unknown", end="unknown")],
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_stage_fields")

    def test_validate_skeleton_accepts_minimal_meaningful_structure(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton())
        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_get_event_skeleton_prefers_latest_checker_result(self):
        state = {
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonChecker": _skeleton(title="first checker")},
                {"SkeletonReconstructor": _skeleton(title="second recon")},
                {"SkeletonChecker": _skeleton(title="second checker")},
            ]
        }
        result = self.builder._get_event_skeleton(state)
        self.assertEqual(result["title"]["value"], "second checker")

    def test_route_after_checker_retries_once_for_non_empty_content(self):
        state = {
            "build_input": type("BI", (), {"samples": [type("S", (), {"content": "real content"})()]})(),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        next_node = self.builder._route_after_skeleton_checker(state)
        self.assertEqual(next_node, "SkeletonReconstructor")
        self.assertEqual(state["skeleton_retry_count"], 1)

    def test_route_after_checker_fails_early_for_empty_content(self):
        state = {
            "build_input": type("BI", (), {"samples": [type("S", (), {"content": ""})()]})(),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Insufficient source content"):
            self.builder._route_after_skeleton_checker(state)
