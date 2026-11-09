"""Real builder lifecycle with synthetic relation proposals and mock review.

The fake accept decision exercises scheduling, audit and replay; it is not a
gold factual judgment or evidence that the synthetic relation is entailed.
"""

import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.base import BuildInput
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.organization_batches import TASK_SEPARATOR
from finmy.generic import DataSample, UserQueryInput
from test_sparse_person_full_flow import (
    EmbeddedPersonData, ROLES, SOURCE, cited, extraction_responses, organization_plan,
)
from test_sparse_rag_builder_full_flow import _vf


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PHASES = ["Layout", "LayoutReview", "Assignments", "Assignments", "Relevance",
                   "Relations", "Relations", "RelationsReview"]


class RelationLifecycleInference:
    """Return the same known global edge from every generation batch."""

    def __init__(self):
        self.extraction = extraction_responses()
        original = self.extraction[2]["participants"][0]["actions"][0]
        self.extraction[2]["participants"][0]["actions"] = [
            {**copy.deepcopy(original), "name": _vf(f"Synthetic action {index + 1}")}
            for index in range(21)
        ]
        self.calls, self.tasks, self.requests = [], [], []
        self.proposal = None

    def run(self, infer_input=None, **kwargs):
        self.calls.append((infer_input, kwargs))
        if self.extraction:
            value = self.extraction.pop(0)
        else:
            prefix, raw_task = infer_input.user_msg.split(TASK_SEPARATOR, 1)
            # Organization inference appends a factual detail-reference catalog
            # after the task JSON; parse the task without treating that metadata
            # as part of the JSON document.
            request, task = json.loads(prefix), json.JSONDecoder().raw_decode(raw_task)[0]
            self.tasks.append(copy.deepcopy(task))
            self.requests.append(request)
            value = self.organization_response(task, request)
        response = json.dumps(value, ensure_ascii=False)
        return SimpleNamespace(
            response=response, cost=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            extras={"finish_reason": "stop", "reasoning_tokens": 0, "cached_tokens": 0},
            to_dict=lambda: {"response": response},
        )

    def organization_response(self, task, request):
        phase, ids = task["phase"], task.get("assigned_ids", [])
        if phase in {"Layout", "LayoutReview"}:
            return {key: copy.deepcopy(organization_plan()[key])
                    for key in ("domains", "events", "stages")}
        if phase == "Assignments":
            return {"memberships": [{"event_id": "PERSON_E1", "stage_id": "PERSON_S1",
                                      "activity_id": aid} for aid in ids],
                    "unassigned_reasons": []}
        if phase == "Relevance":
            return {"occurrence_relevance": [
                {"occurrence_id": oid, "subject_relevance": cited("Alpha made the transfer.")}
                for oid in ids], "background_occurrence_ids": [], "memberships": [],
                "occurrence_issues": []}
        if phase == "Relations":
            all_ids = [row["activity_id"] for row in request["facts"]["activity"]]
            self.proposal = {"from_activity_id": all_ids[-1], "to_activity_id": all_ids[0],
                             "relation_type": "context_for", "basis": "source",
                             "description": cited("Synthetic context link for lifecycle testing.")}
            return {"activity_relations": [copy.deepcopy(self.proposal)]}
        if phase == "RelationsReview":
            return {"decisions": [{"candidate_id": row["candidate_id"], "decision": "accept",
                                    "reason": "Synthetic mock review; not a factual gold judgment."}
                                   for row in task["candidates"]]}
        raise AssertionError(f"Unexpected phase: {phase}")


class SparseRelationReviewLifecycleTest(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.config = yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"]
        self.config["save_folder"] = str(self.root / "runs")
        self.config["reconstruction"]["subject"] = {
            "subject_id": "person_alpha", "name": "Alpha", "scope": "Synthetic lifecycle fixture",
            "coverage_start": "2025-01-01", "coverage_end": "2025-01-02",
        }
        self.config["sparse_builder_config"].update(output_language="English", max_json_attempts=2)
        self.inputs = BuildInput(UserQueryInput(query_text="Alpha bitcoin transfer", key_words=["Alpha"]),
                                 [DataSample(sample_id="s1", raw_data_id="r1", content=SOURCE,
                                             category="article", knowledge_field="finance")])

    def make_builder(self):
        inference = RelationLifecycleInference()
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=inference):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        return builder, inference

    def artifact(self, builder, name):
        return json.loads(Path(builder.save_dir, f"{name}.json").read_text())

    def assert_collected_both_origins(self, audit, inference):
        self.assertEqual(len(audit["generation_batches"]), 2)
        self.assertEqual(len(audit["candidates"]), 1)
        candidate = audit["candidates"][0]
        self.assertEqual(candidate["relation"], inference.proposal)
        self.assertEqual(candidate["owner_batch"], "RelationsOwner-002")
        self.assertTrue(candidate["cross_batch"])
        self.assertEqual([row["batch_name"] for row in candidate["origins"]],
                         ["PersonOrganization-Relations-001", "PersonOrganization-Relations-002"])
        self.assertEqual([row["cross_batch"] for row in candidate["origins"]], [True, False])
        self.assertEqual([row["item_index"] for row in candidate["origins"]], [0, 0])
        self.assertTrue(all(row["candidate_ids"] == [candidate["candidate_id"]]
                            for row in audit["generation_batches"]))
        return candidate

    def test_global_candidate_finishes_every_batch_then_review_and_strict_replay(self):
        builder, inference = self.make_builder()
        output = builder.run(self.inputs)
        self.assertEqual([task["phase"] for task in inference.tasks], EXPECTED_PHASES)
        generated = [task for task in inference.tasks if task["phase"] == "Relations"]
        self.assertEqual([len(task["assigned_ids"]) for task in generated], [20, 3])
        self.assertNotIn(inference.proposal["from_activity_id"], generated[0]["assigned_ids"])
        self.assertIn(inference.proposal["from_activity_id"], generated[1]["assigned_ids"])
        for request in inference.requests:
            self.assertEqual(len(request["facts"]["activity"]), 23)
            self.assertEqual(request["facts"]["source_document"][0]["content"], SOURCE)

        audit = self.artifact(builder, "PersonOrganization-RelationCandidates-Result")
        candidate = self.assert_collected_both_origins(audit, inference)
        self.assertEqual(audit["status"], "reviewed_requires_content_review")
        self.assertEqual(len(audit["review_batches"]), 1)
        self.assertEqual(candidate["decision"]["decision"], "accept")
        self.assertFalse(audit["semantic_approval"])
        review_task = inference.tasks[-1]
        self.assertEqual([row["candidate_id"] for row in review_task["candidates"]], [candidate["candidate_id"]])
        plan = self.artifact(builder, "PersonOrganization-Result")
        self.assertEqual(plan["activity_relations"], [inference.proposal])
        person = output.extras["person_epg"]
        self.assertEqual(len(person["activity_relation"]), 1)
        self.assertEqual(person["activity_relation"][0]["from_activity_id"], inference.proposal["from_activity_id"])
        self.assertEqual(person["activity_relation"][0]["to_activity_id"], inference.proposal["to_activity_id"])
        self.assertFalse(output.extras["person_acceptance"]["semantic_approval"])

        ledger = self.artifact(builder, "CallLedger")
        self.assertEqual(len(inference.calls), 15)
        self.assertEqual(len(ledger), 15)
        self.assertEqual([row["agent"] for row in ledger], ROLES[:7] + ["PersonOrganization"] * 8)
        self.assertTrue(all(row["status"] == "accepted" for row in ledger))
        self.assertEqual(ledger[-1]["save_name"], "PersonOrganization-RelationsReview-001")
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["usage"]["calls"], 15)
        self.assertEqual(manifest["usage"]["prompt_tokens"], 150)
        self.assertEqual(manifest["usage"]["completion_tokens"], 75)
        self.assertEqual(output.extras["calls"], ledger)
        self.assertEqual(manifest["organization_execution_version"], 4)
        self.assertIn("PersonOrganization-Context-Result.json", manifest["artifact_sha256"])
        context = self.artifact(builder, "PersonOrganization-Context-Result")
        for task in inference.tasks:
            if task["phase"] in {"Relations", "RelationsReview"}:
                self.assertEqual(task["organization_context"], context)
        html = Path(builder.save_dir, "FinalPersonEPG.html").read_text()
        self.assertEqual(json.loads(EmbeddedPersonData(html).payload), person)
        self.assertEqual(self.artifact(builder, "PersonRenderStatus")["status"], "completed")
        replay = SparseRagBuilder.__new__(SparseRagBuilder)
        replay.save_dir, replay.build_config = builder.save_dir, {}
        with patch.object(inference, "run", side_effect=AssertionError("Replay must be offline")):
            self.assertEqual(replay.integrate_person_from_files(strict=True), person)
        context_path = Path(builder.save_dir, "PersonOrganization-Context-Result.json")
        context_path.write_text(json.dumps({**context, "tampered": True}))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            replay.integrate_person_from_files(strict=True)

    def test_layout_review_obeys_original_call_budget_without_silent_acceptance(self):
        self.config["sparse_builder_config"]["max_calls"] = 8
        builder, inference = self.make_builder()
        with self.assertRaisesRegex(RuntimeError, "call limit"):
            builder.run(self.inputs)
        self.assertEqual([task["phase"] for task in inference.tasks], ["Layout"])
        self.assertEqual(len(inference.calls), 8)
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "failed")
        self.assertTrue(Path(builder.save_dir, "PersonOrganization-Layout-Plan-Result.json").exists())
        self.assertTrue(Path(builder.save_dir, "FinalEventCascade.json").exists())
        self.assertFalse(Path(builder.save_dir, "PersonOrganization-Result.json").exists())
        self.assertFalse(Path(builder.save_dir, "FinalPersonEPG.json").exists())

    def test_budget_exhausted_before_review_keeps_candidates_without_final_person(self):
        self.config["sparse_builder_config"]["max_calls"] = 14
        builder, inference = self.make_builder()
        with self.assertRaisesRegex(RuntimeError, "call limit"):
            builder.run(self.inputs)
        self.assertEqual([task["phase"] for task in inference.tasks], EXPECTED_PHASES[:-1])
        self.assertEqual(len(inference.calls), 14)
        audit = self.artifact(builder, "PersonOrganization-RelationCandidates-Result")
        candidate = self.assert_collected_both_origins(audit, inference)
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["failure"]["error_type"], "RuntimeError")
        self.assertEqual(audit["review_batches"], [])
        self.assertIsNone(candidate["decision"])
        self.assertFalse(audit["semantic_approval"])
        manifest = self.artifact(builder, "RunManifest")
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["usage"]["calls"], 14)
        ledger = self.artifact(builder, "CallLedger")
        self.assertEqual(len(ledger), 14)
        self.assertEqual(ledger[-1]["save_name"], "PersonOrganization-Relations-002")
        for name in ("PersonOrganization-Result.json", "FinalPersonEPG.json", "FinalPersonEPG.html"):
            self.assertFalse(Path(builder.save_dir, name).exists())
        self.assertTrue(Path(builder.save_dir, "FinalEventCascade.json").is_file())


if __name__ == "__main__":
    unittest.main()
