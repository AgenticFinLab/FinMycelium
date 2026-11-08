"""Offline organizational review cannot rewrite facts or bypass validation."""

import copy
import unittest

from finmy.builder.sparse_build.organization_batches import organize_person_plan
from finmy.builder.sparse_build.person_organization import apply_organization
from test_sparse_organization_batches import OrganizationResponses, incomplete, many_facts
from test_sparse_person_organization import facts, plan, vf


class OrganizationQualityFlowTest(unittest.TestCase):
    def organize(self, package, responses):
        self.saved = []
        return organize_person_plan(
            package, {"stages": []}, {"name": "Example person"}, "English",
            responses, lambda data, name: self.saved.append((name, copy.deepcopy(data))),
        )

    def test_reviewed_layout_replaces_candidate_before_every_assignment(self):
        def refine(task, value):
            if task["phase"] == "LayoutReview":
                value["domains"][0]["domain_id"] = "D-reviewed"
                value["events"][0].update(event_id="E-reviewed", domain_id="D-reviewed")
                value["stages"][0].update(event_id="E-reviewed", stage_id="S-reviewed",
                                          summary=vf("The person made the documented statement."))
            elif task["phase"] in ("Assignments", "Relevance"):
                for member in value["memberships"]:
                    member["event_id"] = "E-reviewed"
                    if member.get("stage_id"):
                        member["stage_id"] = "S-reviewed"

        package = many_facts()
        before = copy.deepcopy(package)
        responses = OrganizationResponses(transform=refine, background=True)
        result = self.organize(package, responses)
        phases = [call["task"]["phase"] for call in responses.calls]
        self.assertEqual(phases[:3], ["Layout", "LayoutReview", "Assignments"])
        self.assertEqual(phases.count("LayoutReview"), 1)
        review = responses.calls[1]["task"]
        self.assertEqual(review["candidate_layout"]["events"][0]["event_id"], "E")
        for call in responses.calls[2:]:
            self.assertEqual(call["task"]["layout"]["events"][0]["event_id"], "E-reviewed")
        self.assertTrue(all(row["event_id"] == "E-reviewed" for row in result["memberships"]))
        self.assertEqual(package, before)
        rendered, _ = apply_organization(package, result)
        for name in ("entity", "action", "financial_transaction", "time_value",
                     "activity_detail", "source_document"):
            self.assertEqual(rendered[name], before[name])
        saved = dict(self.saved)
        self.assertEqual(saved["PersonOrganization-Layout-Plan"]["events"][0]["event_id"], "E")
        self.assertEqual(saved["PersonOrganization-LayoutReview-Plan"]["events"][0]["event_id"],
                         "E-reviewed")
        self.assertIn("PersonOrganization-Context", saved)
        self.assertIn("PersonOrganization-FinalContext", saved)
        self.assertEqual(len({call["prefix"] for call in responses.calls}), 1)

    def test_review_rejects_invalid_references_quotes_and_fact_arrays(self):
        mutations = [
            lambda value: value["events"][0].update(domain_id="missing"),
            lambda value: value["stages"][0]["summary"].update(evidence_source_contents=[]),
            lambda value: value.update(action=[{"action_id": "invented"}]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                def alter(task, value):
                    if task["phase"] == "LayoutReview":
                        value["stages"][0]["summary"] = vf("Supported summary")
                        mutation(value)
                responses = OrganizationResponses(transform=alter)
                package = many_facts()
                before = copy.deepcopy(package)
                with self.assertRaises(ValueError):
                    self.organize(package, responses)
                self.assertEqual([c["task"]["phase"] for c in responses.calls],
                                 ["Layout", "LayoutReview"])
                self.assertEqual(package, before)
                self.assertEqual([name for name, _ in self.saved], ["PersonOrganization-Layout-Plan"])

    def test_review_incomplete_or_budget_failure_does_not_use_unreviewed_layout(self):
        for failure in (incomplete(), RuntimeError("Call budget exhausted")):
            with self.subTest(failure=type(failure).__name__):
                def fail(task, value):
                    if task["phase"] == "LayoutReview":
                        raise failure
                responses = OrganizationResponses(transform=fail)
                with self.assertRaises(type(failure)):
                    self.organize(many_facts(), responses)
                self.assertEqual([c["task"]["phase"] for c in responses.calls],
                                 ["Layout", "LayoutReview"])
                self.assertEqual([name for name, _ in self.saved], ["PersonOrganization-Layout-Plan"])

    def test_small_complete_plan_keeps_one_call_and_saves_validated_context(self):
        responses = OrganizationResponses()
        package = facts()
        before = copy.deepcopy(package)
        self.assertEqual(self.organize(package, responses), plan())
        self.assertEqual([c["task"]["phase"] for c in responses.calls], ["Single"])
        self.assertEqual([name for name, _ in self.saved], ["PersonOrganization-Context"])
        self.assertEqual(package, before)

    def test_invalid_small_plan_never_emits_context(self):
        def invalid(task, value):
            value["memberships"][0]["activity_id"] = "missing"
        with self.assertRaises(ValueError):
            self.organize(facts(), OrganizationResponses(transform=invalid))
        self.assertEqual(self.saved, [])

    def test_review_can_remove_unsupported_stages_without_forcing_a_quota(self):
        def remove_stages(task, value):
            if task["phase"] == "LayoutReview":
                value["stages"] = []
            elif task["phase"] == "Assignments":
                for member in value["memberships"]:
                    member["stage_id"] = None
        result = self.organize(many_facts(), OrganizationResponses(transform=remove_stages))
        self.assertEqual(result["stages"], [])
        self.assertEqual(len(result["events"]), 1)
        self.assertTrue(all(member.get("stage_id") is None for member in result["memberships"]))


if __name__ == "__main__":
    unittest.main()
