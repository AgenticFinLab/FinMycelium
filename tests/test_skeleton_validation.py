import unittest
from types import SimpleNamespace

import finmy.builder.agent_build.main_build as main_build_module
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


def _build_input(sample_contents):
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="demo query", key_words=["demo"]),
        samples=[SimpleNamespace(content=content) for content in sample_contents]
    )


class SkeletonValidationTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

    def test_blank_strings_are_treated_as_unknown_values(self):
        self.assertTrue(self.builder._is_unknown_value("   "))

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

    def test_validate_skeleton_rejects_blank_title(self):
        valid, reason = self.builder._validate_event_skeleton(_skeleton(title="   "))
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_event_title")

    def test_validate_skeleton_rejects_semantically_empty_stage_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        name="unknown",
                        start="unknown",
                        end="unknown",
                        episodes=[_episode()],
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_stage_fields")

    def test_validate_skeleton_rejects_blank_only_stage_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        name="   ",
                        start=" ",
                        end="\t",
                        episodes=[_episode()],
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_stage_fields")

    def test_validate_skeleton_rejects_semantically_empty_episode_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[
                    _stage(
                        episodes=[
                            _episode(name="unknown", start="unknown", end="unknown")
                        ]
                    )
                ]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_episode_fields")

    def test_validate_skeleton_rejects_blank_only_episode_fields(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(
                stages=[_stage(episodes=[_episode(name=" ", start="\n", end="\t")])]
            )
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "unknown_episode_fields")

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

    def test_get_event_skeleton_falls_back_to_latest_reconstructor_result(self):
        state = {
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonReconstructor": _skeleton(title="second recon")},
            ]
        }
        result = self.builder._get_event_skeleton(state)
        self.assertEqual(result["title"]["value"], "second recon")

    def test_skeleton_checker_uses_latest_reconstructor_result_as_input(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["prompt_kwargs"] = prompt_kwargs
            captured["infer_input"] = infer_input
            return SimpleNamespace(
                response='{"event_id":"checked","title":{"value":"checked"},"stages":[{"episodes":[{}]}]}',
                to_dict=lambda: {"response": "raw"},
            )

        original_run_single_inference = main_build_module.run_single_inference
        original_extract_json_response = main_build_module.extract_json_response
        self.addCleanup(
            setattr,
            main_build_module,
            "run_single_inference",
            original_run_single_inference,
        )
        self.addCleanup(
            setattr,
            main_build_module,
            "extract_json_response",
            original_extract_json_response,
        )
        main_build_module.run_single_inference = fake_run_single_inference
        main_build_module.extract_json_response = lambda _result: {"checked": True}

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [
                {"SkeletonReconstructor": _skeleton(title="first recon")},
                {"SkeletonReconstructor": _skeleton(title="latest recon")},
            ],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"SkeletonChecker": "schema {STRUCTURE_SPEC}"},
            "agent_user_msgs": {"SkeletonChecker": "user prompt"},
        }

        updated_state = self.builder.execute_agent(state, "SkeletonChecker")

        self.assertIn('"latest recon"', captured["prompt_kwargs"]["ProposedSkeleton"])
        self.assertNotIn('"first recon"', captured["prompt_kwargs"]["ProposedSkeleton"])
        self.assertEqual(updated_state["agent_results"][-1], {"SkeletonChecker": {"checked": True}})

    def test_route_after_checker_retries_once_for_non_empty_content(self):
        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        next_node = self.builder._route_after_skeleton_checker(state)
        self.assertEqual(next_node, "SkeletonReconstructor")
        self.assertEqual(state["skeleton_retry_count"], 1)

    def test_route_after_checker_fails_early_for_empty_content(self):
        state = {
            "build_input": _build_input([""]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Insufficient source content"):
            self.builder._route_after_skeleton_checker(state)
