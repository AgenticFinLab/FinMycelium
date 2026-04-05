import json
import unittest
from types import SimpleNamespace

import finmy.builder.agent_build.main_build as main_build_module
from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


def _vf(value):
    return {
        "value": value,
        "evidence_source_contents": [],
        "reasons": [],
        "confidence": 1.0,
    }


def _skeleton():
    return {
        "event_id": "demo_event",
        "title": _vf("Demo Event"),
        "event_type": _vf("demo"),
        "start_time": _vf("2025-01-01"),
        "end_time": _vf("2025-01-02"),
        "stages": [
            {
                "stage_id": "S1",
                "name": _vf("Stage 1"),
                "index_in_event": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-02"),
                "episodes": [
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                    }
                ],
            }
        ],
    }


def _participant():
    return {
        "participant_id": "P_1",
        "name": _vf("Participant 1"),
        "participant_type": "organization",
        "base_role": _vf("counterparty"),
        "attributes": {},
        "actions": [],
    }


def _build_input():
    bundle = EvidenceAssetBundle(
        retrieval_policy=EvidenceRetrievalPolicy(),
        index=EvidenceIndex(),
        evidence_cards=[
            EvidenceCard(
                sample_id="sample-1",
                title="sample-1",
                excerpt="alpha episode excerpt",
                tokens=["alpha", "episode"],
            )
        ],
    )
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="alpha episode", key_words=["alpha"]),
        samples=[SimpleNamespace(content="real content")],
        context_assets=bundle,
    )


def _build_empty_input():
    return SimpleNamespace(
        user_query=SimpleNamespace(query_text="alpha episode", key_words=["alpha"]),
        samples=[SimpleNamespace(content="real content")],
        context_assets=EvidenceAssetBundle.empty(),
    )


def _transaction_participants():
    return {
        "participants": [
            {
                "participant_id": "P_1",
                "name": _vf("Participant 1"),
                "participant_type": "organization",
                "base_role": _vf("payer"),
                "attributes": {},
                "actions": [],
            },
            {
                "participant_id": "P_2",
                "name": _vf("Participant 2"),
                "participant_type": "organization",
                "base_role": _vf("receiver"),
                "attributes": {},
                "actions": [],
            },
        ]
    }


def _episode_transactions():
    return {
        "transactions": [
            {
                "transaction_id": "T_1",
                "name": _vf("Transaction 1"),
                "transaction_type": _vf("transfer"),
                "timestamp": _vf("2025-01-01"),
                "details": _vf("Episode-level transaction"),
                "from_participant_id": "P_1",
                "to_participant_id": "P_2",
                "instruments": [],
            }
        ]
    }


class AgentContextIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.builder = AgentEventBuilder.__new__(AgentEventBuilder)

    def test_participant_reconstructor_receives_retrieved_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": [_participant()]}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {"ParticipantReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = main_build_module.ParticipantReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_participant_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"participants": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [{"SkeletonChecker": _skeleton()}],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": {"ParticipantReconstructor": "sys"},
            "agent_user_msgs": {"ParticipantReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "ParticipantReconstructor")

        rendered_prompt = main_build_module.ParticipantReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)

    def test_transaction_reconstructor_receives_retrieved_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"transactions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()}
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {"TransactionReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "TransactionReconstructor")

        rendered_prompt = main_build_module.TransactionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertIn("Episode 1", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["TargetEpisode"].name["value"],
            "Episode 1",
        )

    def test_transaction_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"transactions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()}
            ],
            "agent_executed": ["SkeletonChecker", "ParticipantReconstructor"],
            "cost": [],
            "agent_system_msgs": {"TransactionReconstructor": "sys"},
            "agent_user_msgs": {"TransactionReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "TransactionReconstructor")

        rendered_prompt = main_build_module.TransactionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("TARGET EPISODE BEGIN", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)

    def test_episode_reconstructor_receives_retrieved_context_without_clearing_content(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()},
                {"TransactionReconstructor": _episode_transactions()},
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorSys
            },
            "agent_user_msgs": {
                "EpisodeReconstructor": main_build_module.EpisodeReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "EpisodeReconstructor")

        infer_input = captured["infer_input"]
        rendered_prompt = infer_input.user_msg.format(**captured["prompt_kwargs"])
        self.assertIn("RetrievedContext", infer_input.user_msg)
        self.assertIn("Content", infer_input.user_msg)
        self.assertIn("RETRIEVED CONTEXT BEGIN", infer_input.user_msg)
        self.assertIn("alpha episode excerpt", captured["prompt_kwargs"]["RetrievedContext"])
        self.assertEqual(captured["prompt_kwargs"]["Content"], "real content")
        self.assertIn("real content", captured["prompt_kwargs"]["Content"])
        self.assertIn("alpha episode excerpt", rendered_prompt)
        self.assertIn("RETRIEVED CONTEXT BEGIN", rendered_prompt)
        self.assertIn("Content", rendered_prompt)
        self.assertIn("StageSkeleton", rendered_prompt)
        self.assertIn("TargetEpisode", rendered_prompt)
        self.assertIn("Episode 1", rendered_prompt)
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_episode_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps(
                    {
                        "episode_id": "E1",
                        "name": _vf("Episode 1"),
                        "index_in_stage": 0,
                        "start_time": _vf("2025-01-01"),
                        "end_time": _vf("2025-01-02"),
                        "participants": "Results of ParticipantReconstructor",
                        "transactions": "Results of TransactionReconstructor",
                        "participant_relations": [],
                        "descriptions": [],
                    }
                ),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [
                {"SkeletonChecker": _skeleton()},
                {"ParticipantReconstructor": _transaction_participants()},
                {"TransactionReconstructor": _episode_transactions()},
            ],
            "agent_executed": [
                "SkeletonChecker",
                "ParticipantReconstructor",
                "TransactionReconstructor",
            ],
            "cost": [],
            "agent_system_msgs": {"EpisodeReconstructor": "sys"},
            "agent_user_msgs": {"EpisodeReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "EpisodeReconstructor")

        rendered_prompt = main_build_module.EpisodeReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("STAGE SKELETON BEGIN", rendered_prompt.upper())
        self.assertIn("TARGET EPISODE BEGIN", rendered_prompt)
        self.assertIn("real content", rendered_prompt)
        self.assertNotIn("alpha episode excerpt", rendered_prompt)

    def test_stage_description_reconstructor_receives_stage_scoped_context(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"descriptions": [_vf("Stage summary")] }),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        stage = _skeleton()["stages"][0]
        stage["episodes"] = [
            {
                "episode_id": "E1",
                "name": _vf("Episode 1"),
                "index_in_stage": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-01"),
                "participants": _transaction_participants()["participants"],
                "transactions": _episode_transactions()["transactions"],
                "participant_relations": [],
                "descriptions": [],
            }
        ]

        build_input = SimpleNamespace(
            user_query=SimpleNamespace(query_text="alpha stage", key_words=["alpha", "stage"]),
            samples=[SimpleNamespace(content="real content")],
            context_assets=EvidenceAssetBundle(
                retrieval_policy=EvidenceRetrievalPolicy(),
                index=EvidenceIndex(),
                evidence_cards=[
                    EvidenceCard(
                        sample_id="sample-stage",
                        title="sample-stage",
                        excerpt="alpha stage excerpt",
                        tokens=["alpha", "stage"],
                    )
                ],
            ),
        )

        state = {
            "build_input": build_input,
            "agent_results": [
                {"SkeletonChecker": {"stages": [stage]}},
                {"EpisodeReconstructor": stage["episodes"][0]},
            ],
            "agent_executed": ["SkeletonChecker", "EpisodeReconstructor"],
            "cost": [],
            "agent_system_msgs": {"StageDescriptionReconstructor": "sys"},
            "agent_user_msgs": {
                "StageDescriptionReconstructor": main_build_module.StageDescriptionReconstructorUser
            },
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "StageDescriptionReconstructor")

        infer_input = captured["infer_input"]
        self.assertIn("RetrievedContext", captured["prompt_kwargs"])
        self.assertIn(
            "alpha stage excerpt", captured["prompt_kwargs"]["RetrievedContext"]
        )
        self.assertIn("RetrievedContext", infer_input.user_msg)
        self.assertIn("TargetStage", infer_input.user_msg)
        self.assertIn("Stage 1", captured["prompt_kwargs"]["TargetStage"])
        self.assertEqual(
            captured["prompt_kwargs"]["RetrievedContextSummary"],
            json.dumps({"selected_count": 1}, ensure_ascii=False),
        )

    def test_stage_description_reconstructor_uses_empty_retrieved_context_when_no_matches(self):
        captured = {}

        def fake_run_single_inference(_lm, infer_input, **prompt_kwargs):
            captured["infer_input"] = infer_input
            captured["prompt_kwargs"] = prompt_kwargs
            return SimpleNamespace(
                response=json.dumps({"descriptions": []}),
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
        main_build_module.extract_json_response = lambda result: json.loads(result)

        self.builder.agents_lm = object()
        self.builder.save_traces = lambda *args, **kwargs: None
        self.builder.get_save_name = lambda agent_name, execution_idx: (
            f"{agent_name}-{execution_idx}"
        )

        stage = _skeleton()["stages"][0]
        stage["episodes"] = [
            {
                "episode_id": "E1",
                "name": _vf("Episode 1"),
                "index_in_stage": 0,
                "start_time": _vf("2025-01-01"),
                "end_time": _vf("2025-01-01"),
                "participants": _transaction_participants()["participants"],
                "transactions": _episode_transactions()["transactions"],
                "participant_relations": [],
                "descriptions": [],
            }
        ]

        state = {
            "build_input": _build_empty_input(),
            "agent_results": [
                {"SkeletonChecker": {"stages": [stage]}},
                {"EpisodeReconstructor": stage["episodes"][0]},
            ],
            "agent_executed": ["SkeletonChecker", "EpisodeReconstructor"],
            "cost": [],
            "agent_system_msgs": {"StageDescriptionReconstructor": "sys"},
            "agent_user_msgs": {"StageDescriptionReconstructor": "user"},
            "skeleton_retry_count": 0,
            "skeleton_validation_reason": "",
        }

        self.builder.execute_agent(state, "StageDescriptionReconstructor")

        rendered_prompt = main_build_module.StageDescriptionReconstructorUser.format(
            **captured["prompt_kwargs"]
        )
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContext"], "")
        self.assertEqual(captured["prompt_kwargs"]["RetrievedContextSummary"], "{}")
        self.assertIn("RetrievedContext", rendered_prompt)
        self.assertIn("TargetStage", rendered_prompt)
        self.assertIn("Content", rendered_prompt)
        self.assertNotIn("alpha stage excerpt", rendered_prompt)


if __name__ == "__main__":
    unittest.main()
