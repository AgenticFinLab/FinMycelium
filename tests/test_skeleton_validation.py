import unittest
import json
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


def _participant(participant_id="P_1", name="Participant 1"):
    return {
        "participant_id": participant_id,
        "name": _vf(name),
        "participant_type": "organization",
        "base_role": _vf("counterparty"),
        "attributes": {},
        "actions": [],
    }


def _full_episode(name="Episode 1", start="2025-01-01", end="2025-01-02"):
    return {
        "episode_id": "E1",
        "name": _vf(name),
        "index_in_stage": 0,
        "descriptions": [_vf("episode description")],
        "start_time": _vf(start),
        "end_time": _vf(end),
        "participants": [_participant()],
        "participant_relations": [],
        "transactions": [],
    }


def _full_stage(name="Stage 1", episodes=None, start="2025-01-01", end="2025-01-02"):
    return {
        "stage_id": "S1",
        "name": _vf(name),
        "index_in_event": 0,
        "descriptions": [_vf("stage description")],
        "start_time": _vf(start),
        "end_time": _vf(end),
        "episodes": episodes if episodes is not None else [_full_episode()],
    }


def _full_skeleton(title="Demo Event", stages=None):
    return {
        "event_id": "demo_event",
        "title": _vf(title),
        "event_type": _vf("demo"),
        "descriptions": [_vf("event description")],
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": stages if stages is not None else [_full_stage()],
    }


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

    def test_validate_skeleton_rejects_stage_with_zero_episodes(self):
        valid, reason = self.builder._validate_event_skeleton(
            _skeleton(stages=[_stage(episodes=[]), _stage(name="Stage 2")])
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "empty_stage_detected")

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

    def test_graph_persists_skeleton_retry_metadata_across_actual_routing(self):
        call_counts = {
            "SkeletonReconstructor": 0,
            "SkeletonChecker": 0,
            "ParticipantReconstructor": 0,
            "TransactionReconstructor": 0,
            "EpisodeReconstructor": 0,
            "StageDescriptionReconstructor": 0,
            "EventDescriptionReconstructor": 0,
        }
        observed_retry_state = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            del infer_input

            def _response(payload):
                return SimpleNamespace(
                    response=json.dumps(payload),
                    to_dict=lambda: {"response": json.dumps(payload)},
                )

            if "ProposedSkeleton" in prompt_kwargs:
                call_counts["SkeletonChecker"] += 1
                if call_counts["SkeletonChecker"] == 1:
                    return _response(_skeleton(stages=[]))
                return _response(_full_skeleton())
            if "TargetStage" in prompt_kwargs:
                call_counts["StageDescriptionReconstructor"] += 1
                return _response({"descriptions": [_vf("stage description")], "stage_id": "S1"})
            if "EventCascade" in prompt_kwargs:
                call_counts["EventDescriptionReconstructor"] += 1
                return _response({"descriptions": [_vf("event description")]})
            if "StageSkeleton" in prompt_kwargs:
                call_counts["EpisodeReconstructor"] += 1
                episode = _full_episode()
                episode["descriptions"] = [_vf("episode description")]
                return _response(episode)
            if "ReconstructedParticipants" in prompt_kwargs:
                call_counts["ParticipantReconstructor"] += 1
                return _response({"participants": [_participant()]})
            if "TargetEpisode" in prompt_kwargs:
                call_counts["TransactionReconstructor"] += 1
                return _response({"transactions": []})

            if call_counts["SkeletonReconstructor"] == 1:
                return _response(_skeleton(stages=[]))
            return _response(_full_skeleton())

        original_run_single_inference = main_build_module.run_single_inference
        original_extract_json_response = main_build_module.extract_json_response
        original_execute_agent = self.builder.execute_agent

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
        self.addCleanup(
            setattr,
            self.builder,
            "execute_agent",
            original_execute_agent,
        )

        main_build_module.run_single_inference = fake_run_single_inference
        main_build_module.extract_json_response = lambda result: json.loads(result)

        def wrapped_execute_agent(state, agent_name):
            if agent_name == "SkeletonReconstructor":
                call_counts["SkeletonReconstructor"] += 1
                if call_counts["SkeletonReconstructor"] == 2:
                    observed_retry_state["skeleton_retry_count"] = state[
                        "skeleton_retry_count"
                    ]
                    observed_retry_state["skeleton_validation_reason"] = state[
                        "skeleton_validation_reason"
                    ]
            elif agent_name not in {
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
                "EpisodeReconstructor",
                "StageDescriptionReconstructor",
                "EventDescriptionReconstructor",
            }:
                self.fail(f"unexpected agent: {agent_name}")
            return original_execute_agent(state, agent_name)

        self.builder.execute_agent = wrapped_execute_agent
        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {
                "SkeletonReconstructor": "sys",
                "SkeletonChecker": "sys",
                "ParticipantReconstructor": "sys",
                "TransactionReconstructor": "sys",
                "EpisodeReconstructor": "sys",
                "StageDescriptionReconstructor": "sys",
                "EventDescriptionReconstructor": "sys",
            },
            "agent_user_msgs": {
                "SkeletonReconstructor": "user",
                "SkeletonChecker": "user",
                "ParticipantReconstructor": "user",
                "TransactionReconstructor": "user",
                "EpisodeReconstructor": "user",
                "StageDescriptionReconstructor": "user",
                "EventDescriptionReconstructor": "user",
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
            "messages": [],
        }

        final_state = self.builder.graph().invoke(state, config={"recursion_limit": 25})

        self.assertEqual(observed_retry_state["skeleton_retry_count"], 1)
        self.assertEqual(observed_retry_state["skeleton_validation_reason"], "no_stages")
        self.assertEqual(final_state["skeleton_retry_count"], 1)
        self.assertEqual(call_counts["SkeletonReconstructor"], 2)
        self.assertEqual(call_counts["SkeletonChecker"], 2)
        self.assertEqual(final_state["skeleton_validation_reason"], "")

    def test_route_after_checker_retries_once_for_non_empty_content(self):
        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 1,
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
        with self.assertLogs(main_build_module.__name__, level="ERROR") as captured:
            with self.assertRaisesRegex(ValueError, "Insufficient source content"):
                self.builder._route_after_skeleton_checker(state)
        self.assertIn("Insufficient source content", "\n".join(captured.output))

    def test_route_after_checker_stops_after_retry_budget_is_exhausted(self):
        state = {
            "build_input": _build_input(["real content"]),
            "agent_results": [{"SkeletonChecker": _skeleton(stages=[])}],
            "skeleton_retry_count": 2,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Invalid event skeleton"):
            self.builder._route_after_skeleton_checker(state)

    def test_route_after_reconstructor_fails_early_when_content_is_empty(self):
        state = {
            "build_input": _build_input([""]),
            "agent_results": [{"SkeletonReconstructor": _skeleton(stages=[])}],
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "Insufficient source content"):
            self.builder._route_after_skeleton_reconstructor(state)
