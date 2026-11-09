"""Canonical relation lifecycle: only disputed/directional links are reviewed."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_person_canonical_full_flow import CanonicalFixtureInference, vf
from test_sparse_person_full_flow import SparsePersonFullFlowTest
from finmy.builder.sparse_build.main_build import SparseRagBuilder


class RelationLifecycleInference(CanonicalFixtureInference):
    def __init__(self, *, fail_review=False, relation_type="executed_by"):
        super().__init__()
        self.fail_review = fail_review
        self.relation_type = relation_type

    def run(self, infer_input=None, **kwargs):
        request, end = json.JSONDecoder().raw_decode(infer_input.user_msg.lstrip())
        tail = infer_input.user_msg.lstrip()[end:]
        task = json.JSONDecoder().raw_decode(tail.split("\n\nBATCH TASK:\n", 1)[1])[0] if "\n\nBATCH TASK:\n" in tail else {}
        phase = task.get("phase")
        if phase not in {"Relations", "RelationsReview"}:
            return super().run(infer_input, **kwargs)
        self.calls.append((phase, copy.deepcopy(request), copy.deepcopy(task)))
        if phase == "Relations":
            response = {"candidates": [{"relation": {
                "from_activity_id": "A:AUTHORIZATION", "to_activity_id": "T:BITCOIN_TRANSFER",
                "relation_type": self.relation_type, "basis": "source",
                "description": vf("The authorized bitcoin transfer was executed to Beta.")},
                "assessment": {"supported": True, "evidence_scope": "relation",
                    "from_role": "authorization", "to_role": "execution", "needs_review": False,
                    "duplicate_fact": False, "reason": "The source describes authorization and the same transfer."}}]}
        else:
            if self.fail_review:
                raise RuntimeError("Synthetic relation review unavailable")
            response = {"decisions": [{"candidate_id": row["candidate_id"], "decision": "accept",
                                      "reason": "The source supports execution of this authorization."}
                                     for row in task["candidates"]]}
        encoded = json.dumps(response)
        return SimpleNamespace(response=encoded, cost=SimpleNamespace(prompt_tokens=20, completion_tokens=15),
                               extras={"finish_reason": "stop", "reasoning_tokens": 0, "cached_tokens": 0},
                               to_dict=lambda: {"response": encoded})


class SparseRelationReviewLifecycleTest(unittest.TestCase):
    setUp = SparsePersonFullFlowTest.setUp
    artifact = SparsePersonFullFlowTest.artifact

    def make_builder(self, **options):
        inference = RelationLifecycleInference(**options)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=inference):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        return builder, inference

    def test_directional_candidate_is_reviewed_after_placement_and_replays(self):
        builder, inference = self.make_builder()
        output = builder.run(self.inputs)
        phases = [p for p, _, _ in inference.calls]
        self.assertLess(phases.index("Placement"), phases.index("Relations"))
        self.assertLess(phases.index("Relations"), phases.index("RelationsReview"))
        self.assertEqual(phases.count("RelationsReview"), 1)
        self.assertEqual(len(output.extras["person_epg"]["activity_relation"]), 1)
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras["person_epg"])
        self.assertEqual(len(self.artifact(builder, "CallLedger")), len(inference.calls))

    def test_unavailable_relation_review_withholds_only_link_and_keeps_native_output(self):
        builder, _ = self.make_builder(fail_review=True)
        output = builder.run(self.inputs)
        person = output.extras["person_epg"]
        self.assertEqual(len(person["activity"]), 2)
        self.assertEqual(person["activity_relation"], [])
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "completed")
        audit = self.artifact(builder, "PersonOrganization-RelationCandidates-Result")
        self.assertEqual(audit["status"], "partial_requires_content_review")
        self.assertTrue(Path(builder.save_dir, "FinalPersonEPG.html").is_file())
        self.assertEqual(builder.integrate_person_from_files(strict=True), person)

    def test_budget_exhaustion_after_facts_preserves_native_draft(self):
        self.config["sparse_builder_config"]["max_calls"] = 6
        builder, inference = self.make_builder()
        output = builder.run(self.inputs)
        self.assertEqual(len(inference.calls), 6)
        self.assertEqual(len(output.extras["person_epg"]["activity"]), 2)
        self.assertEqual(output.extras["person_epg"]["activity_relation"], [])
        self.assertEqual(self.artifact(builder, "RunManifest")["status"], "completed")
        self.assertEqual(output.extras["event_summary"]["status"], "degraded")

    def test_uncontested_context_link_does_not_require_a_duplicate_full_review(self):
        builder, inference = self.make_builder(relation_type="context_for")
        output = builder.run(self.inputs)
        self.assertNotIn("RelationsReview", [p for p, _, _ in inference.calls])
        self.assertEqual(len(output.extras["person_epg"]["activity_relation"]), 1)


if __name__ == "__main__":
    unittest.main()
