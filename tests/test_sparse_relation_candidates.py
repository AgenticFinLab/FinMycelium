"""Relation candidates keep their provenance until explicit, bounded owner review."""

import copy
import json
import unittest

from finmy.builder.sparse_build.person_organization import apply_organization
from test_sparse_organization_batches import OrganizationResponses, incomplete, many_facts
from test_sparse_person_organization import vf


def relation(start="A1", end="A21", *, text="The source supports this context relation.", kind="context_for"):
    return {"from_activity_id": start, "to_activity_id": end,
            "relation_type": kind, "basis": "source", "description": vf(text)}


def relation_key(row):
    return tuple(row[name] for name in ("from_activity_id", "to_activity_id", "relation_type"))


class SparseRelationCandidatesTest(unittest.TestCase):
    def run_plan(self, responses, package=None):
        from finmy.builder.sparse_build.organization_batches import organize_person_plan

        self.saved = []
        return organize_person_plan(package or many_facts(), {"stages": []},
                                    {"name": "Example person"}, "English", responses,
                                    lambda data, name: self.saved.append((name, copy.deepcopy(data))))

    def audit(self):
        reports = [data for name, data in self.saved if name == "PersonOrganization-RelationCandidates"]
        self.assertTrue(reports, "Candidate audit must survive success and failure")
        return reports[-1]

    def assert_validation_error(self, transform):
        with self.assertRaises(ValueError) as caught:
            self.run_plan(OrganizationResponses(transform=transform))
        self.assertEqual(type(caught.exception).__name__, "OrganizationValidationError")
        self.assertIsInstance(caught.exception.report, dict)
        self.assertEqual(self.audit()["status"], "failed")
        return caught.exception

    def test_global_repeated_lists_run_every_batch_then_deduplicate_with_all_origins(self):
        proposed = [relation(), relation("A21", "A1")]
        count = 0

        def repeat_global_list(task, value):
            nonlocal count
            if task["phase"] == "Relations":
                count += 1
                value["activity_relations"] = copy.deepcopy(proposed)
                if count == 2:
                    value["activity_relations"] = [dict(reversed(list(row.items())))
                                                   for row in value["activity_relations"]]

        responses = OrganizationResponses(transform=repeat_global_list)
        package = many_facts(activity_count=41)
        original = copy.deepcopy(package)
        result = self.run_plan(responses, package)
        self.assertEqual(package, original)
        self.assertEqual({relation_key(row) for row in result["activity_relations"]},
                         {relation_key(row) for row in proposed})
        generation = [call for call in responses.calls if call["task"]["phase"] == "Relations"]
        reviews = [call for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertEqual(len(generation), 3)
        self.assertEqual(len(reviews), 2)
        phases = [call["task"]["phase"] for call in responses.calls]
        self.assertLess(max(i for i, phase in enumerate(phases) if phase == "Relations"),
                        min(i for i, phase in enumerate(phases) if phase == "RelationsReview"))
        audit = self.audit()
        self.assertEqual(audit["execution_version"], 3)
        self.assertEqual(audit["status"], "reviewed_requires_content_review")
        self.assertFalse(audit["semantic_approval"])
        self.assertFalse(audit["semantic_support_checked"])
        self.assertEqual(len(audit["candidates"]), 2)
        for candidate in audit["candidates"]:
            self.assertEqual(len(candidate["origins"]), 3)
            self.assertTrue(candidate["cross_batch"])
            self.assertEqual({origin["batch_name"] for origin in candidate["origins"]},
                             {call["savename"] for call in generation})
            self.assertEqual(candidate["decision"]["decision"], "accept")
            for origin in candidate["origins"]:
                self.assertEqual(origin["cross_batch"],
                                 candidate["relation"]["from_activity_id"] not in origin["assigned_ids"])
        for call in reviews:
            task = call["task"]
            self.assertTrue(all(candidate["relation"]["from_activity_id"] in task["assigned_ids"]
                                for candidate in task["candidates"]))
            self.assertEqual(len(task["assigned_ids"]), 20)
        self.assertTrue(apply_organization(package, result)[0]["activity_relation"])

    def test_variants_are_preserved_together_but_only_one_is_accepted(self):
        variants = [relation(text="First supported wording."), relation(text="Second supported wording.")]

        def propose_variants(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = copy.deepcopy(variants if "A1" in task["assigned_ids"] else variants[:1])

        responses = OrganizationResponses(transform=propose_variants)
        result = self.run_plan(responses)
        audit = self.audit()
        self.assertEqual(len(audit["candidates"]), 2)
        self.assertEqual(sorted(len(candidate["origins"]) for candidate in audit["candidates"]), [1, 2])
        self.assertEqual({candidate["relation"]["description"]["value"] for candidate in audit["candidates"]},
                         {row["description"]["value"] for row in variants})
        reviews = [call["task"] for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(reviews[0]["candidates"]), 2)
        self.assertEqual(len(result["activity_relations"]), 1)
        self.assertIn(result["activity_relations"][0], variants)

    def test_two_accepts_for_same_relation_key_fail_without_publishing_either(self):
        def double_accept(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation(text="Version one."), relation(text="Version two.")]
            if task["phase"] == "RelationsReview":
                for decision in value["decisions"]:
                    decision["decision"] = "accept"

        self.assert_validation_error(double_accept)
        self.assertEqual(len(self.audit()["candidates"]), 2)
        self.assertTrue(all(candidate["decision"] is None for candidate in self.audit()["candidates"]))

    def test_rejected_candidates_remain_in_audit_with_reason(self):
        reason = "The quote describes both endpoints without supporting their relationship."

        def reject_all(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation()]
            if task["phase"] == "RelationsReview":
                for decision in value["decisions"]:
                    decision.update(decision="reject", reason=reason)

        result = self.run_plan(OrganizationResponses(transform=reject_all))
        self.assertEqual(result["activity_relations"], [])
        audit = self.audit()
        self.assertEqual(len(audit["candidates"]), 1)
        self.assertEqual(audit["candidates"][0]["decision"]["reason"], reason)
        self.assertEqual(audit["candidates"][0]["decision"]["decision"], "reject")

    def test_review_must_cover_only_its_candidates_once_with_nonempty_reasons(self):
        def foreign_id(task, value):
            if task["phase"] == "RelationsReview":
                value["decisions"][0]["candidate_id"] = "NOT_ASSIGNED"

        def missing(task, value):
            if task["phase"] == "RelationsReview":
                value["decisions"].pop()

        def duplicate(task, value):
            if task["phase"] == "RelationsReview":
                value["decisions"].append(copy.deepcopy(value["decisions"][0]))

        def blank_reason(task, value):
            if task["phase"] == "RelationsReview":
                value["decisions"][0]["reason"] = "   "

        def rewritten_relation(task, value):
            if task["phase"] == "RelationsReview":
                value["decisions"][0]["relation"] = relation("A21", "A1")

        for mutate in (foreign_id, missing, duplicate, blank_reason, rewritten_relation):
            with self.subTest(mutation=mutate.__name__):
                self.assert_validation_error(mutate)

    def test_review_cannot_decide_a_real_candidate_owned_by_another_batch(self):
        def foreign_owner(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation(), relation("A21", "A1")]
            if task["phase"] == "RelationsReview":
                foreign = next(candidate for candidate in self.audit()["candidates"]
                               if candidate["relation"]["from_activity_id"] not in task["assigned_ids"])
                value["decisions"][0]["candidate_id"] = foreign["candidate_id"]

        self.assert_validation_error(foreign_owner)

    def test_unknown_self_missing_quote_and_unsupported_temporal_are_strict(self):
        def unknown(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation("MISSING", "A1")]

        def self_link(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation("A1", "A1")]

        def missing_quote(task, value):
            if task["phase"] == "Relations":
                row = relation()
                row["description"]["evidence_source_contents"] = []
                value["activity_relations"] = [row]

        def unsupported_temporal(task, value):
            if task["phase"] == "Relations":
                row = relation(kind="executed_by")
                row["basis"] = "temporal"
                value["activity_relations"] = [row]

        def malformed(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [{"from_activity_id": "A1"}]

        for mutate in (unknown, self_link, missing_quote, unsupported_temporal, malformed):
            with self.subTest(mutation=mutate.__name__):
                self.assert_validation_error(mutate)

    def test_review_length_splits_whole_relation_key_groups_preserving_variants(self):
        variants = [relation("A1", "A21", text=f"Version {index}.") for index in range(3)]
        proposed = variants + [relation("A2", "A21"), relation("A3", "A21")]

        def truncate_review(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = copy.deepcopy(proposed)
            if task["phase"] == "RelationsReview":
                keys = {relation_key(candidate["relation"]) for candidate in task["candidates"]}
                if len(keys) > 1:
                    raise incomplete()

        responses = OrganizationResponses(transform=truncate_review)
        result = self.run_plan(responses)
        self.assertEqual(len(result["activity_relations"]), 3)
        reviews = [task for task in responses.accepted if task["phase"] == "RelationsReview"]
        self.assertEqual(len(reviews), 3)
        self.assertEqual(sorted(len(task["candidates"]) for task in reviews), [1, 1, 3])
        self.assertTrue(all(len({relation_key(candidate["relation"]) for candidate in task["candidates"]}) == 1
                            for task in reviews))
        self.assertEqual(len(self.audit()["candidates"]), 5)

    def test_single_key_with_many_variants_cannot_be_split_or_silently_selected(self):
        from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError

        def one_large_key(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation(text=f"Version {index}.") for index in range(5)]
            if task["phase"] == "RelationsReview":
                raise incomplete()

        responses = OrganizationResponses(transform=one_large_key)
        with self.assertRaises(IncompleteCompletionError):
            self.run_plan(responses)
        reviews = [call for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(reviews[0]["task"]["candidates"]), 5)
        self.assertEqual(len(self.audit()["candidates"]), 5)

    def test_failed_review_split_preserves_completed_sibling_decisions(self):
        def fail_later_review(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation("A1", "A21"), relation("A2", "A21")]
            if task["phase"] == "RelationsReview":
                keys = {relation_key(candidate["relation"]) for candidate in task["candidates"]}
                if len(keys) > 1:
                    raise incomplete()
                if next(iter(keys))[0] == "A2":
                    raise TimeoutError("Synthetic later review interruption")

        with self.assertRaises(TimeoutError):
            self.run_plan(OrganizationResponses(transform=fail_later_review))
        candidates = {candidate["relation"]["from_activity_id"]: candidate
                      for candidate in self.audit()["candidates"]}
        self.assertEqual(candidates["A1"]["decision"]["decision"], "accept")
        self.assertIsNone(candidates["A2"]["decision"])

    def test_generation_failure_preserves_previously_collected_candidates(self):
        def second_batch_fails(task, value):
            if task["phase"] == "Relations" and "A21" in task["assigned_ids"]:
                raise TimeoutError("https://example.invalid Authorization: synthetic-secret")

        responses = OrganizationResponses(transform=second_batch_fails)
        with self.assertRaises(TimeoutError):
            self.run_plan(responses)
        self.assertFalse(any(call["task"]["phase"] == "RelationsReview" for call in responses.calls))
        self.assertEqual(len(self.audit()["candidates"]), 1)
        self.assertEqual(self.audit()["failure"]["error_type"], "TimeoutError")
        saved_audit = json.dumps(self.audit())
        for sensitive_text in ("example.invalid", "Authorization", "synthetic-secret"):
            self.assertNotIn(sensitive_text, saved_audit)

    def test_generation_split_keeps_original_owner_scope_for_review(self):
        def split_generation(task, value):
            if task["phase"] == "Relations":
                if len(task["assigned_ids"]) > 10:
                    raise incomplete()
                value["activity_relations"] = [relation()]

        responses = OrganizationResponses(transform=split_generation)
        result = self.run_plan(responses)
        self.assertEqual(result["activity_relations"], [relation()])
        reviews = [call["task"] for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["assigned_ids"], [f"A{i}" for i in range(1, 21)])
        self.assertEqual(len(self.audit()["candidates"][0]["origins"]), 3)

    def test_split_generation_failure_retains_successful_sibling_candidates(self):
        def fail_right_sibling(task, value):
            if task["phase"] == "Relations":
                ids = task["assigned_ids"]
                if len(ids) > 10:
                    raise incomplete()
                if "A11" in ids:
                    raise TimeoutError("Synthetic right sibling interruption")
                value["activity_relations"] = [relation()]

        with self.assertRaises(TimeoutError):
            self.run_plan(OrganizationResponses(transform=fail_right_sibling))
        self.assertEqual(len(self.audit()["candidates"]), 1)
        self.assertEqual(self.audit()["candidates"][0]["relation"], relation())

    def test_review_budget_error_stops_without_spending_more_or_losing_audit(self):
        calls_after_failure = []

        def exhausted(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [relation(), relation("A21", "A1")]
            if task["phase"] == "RelationsReview":
                calls_after_failure.append(task)
                raise RuntimeError("Configured model call limit reached")

        with self.assertRaisesRegex(RuntimeError, "model call limit"):
            self.run_plan(OrganizationResponses(transform=exhausted))
        self.assertEqual(len(calls_after_failure), 1)
        self.assertEqual(len(self.audit()["candidates"]), 2)

    def test_review_prompt_explains_executed_by_direction_and_unsupported_link_rejection(self):
        responses = OrganizationResponses()
        self.run_plan(responses)
        reviews = [call for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertTrue(reviews)
        prompt = reviews[0]["system"] + "\n" + reviews[0]["task"]["instructions"]
        self.assertIn("executed_by", prompt)
        self.assertIn("decision", prompt.lower())
        self.assertIn("execution", prompt.lower())
        self.assertIn("reject", prompt.lower())
        self.assertIn("quote", prompt.lower())

    def test_review_receives_the_complete_new_background_mapping(self):
        responses = OrganizationResponses(background=True)
        self.run_plan(responses)
        reviews = [call["task"] for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertTrue(reviews)
        for task in reviews:
            self.assertEqual(task["background_activities"],
                             [{"activity_id": "C:O1", "context_occurrence_id": "O1"}])

    def test_temporal_diagnostics_distinguish_unknown_contradiction_and_invalid_basis(self):
        from finmy.builder.sparse_build.organization_errors import OrganizationValidationError
        from finmy.builder.sparse_build.relation_candidates import validate_relation_candidates

        for timestamp, kind, expected_code in (
            ("2024-01-03", "precedes", "temporal_contradicted_or_overstated"),
            ("unknown", "precedes", "temporal_unestablished"),
            ("2024-01-03", "executed_by", "invalid_temporal_basis"),
        ):
            with self.subTest(code=expected_code):
                package = many_facts()
                package["time_value"] = [{"time_id": "T", "value": timestamp},
                                         {"time_id": "T2", "value": "2024-01-01"}]
                package["action"][20]["timestamp_time_id"] = "T2"
                original = copy.deepcopy(package)
                proposal = relation(kind=kind)
                proposal["basis"] = "temporal"
                with self.assertRaises(OrganizationValidationError) as caught:
                    validate_relation_candidates({"activity_relations": [proposal]},
                                                 ["A1"], [row["activity_id"] for row in package["activity"]],
                                                 package)
                issues = caught.exception.report["violations"]
                self.assertEqual({issue["code"] for issue in issues}, {expected_code})
                self.assertEqual(issues[0]["left_time_values"], [package["time_value"][0]])
                self.assertEqual(issues[0]["right_time_values"], [package["time_value"][1]])
                self.assertEqual(package, original)

    def test_malformed_row_does_not_hide_other_rows_unknown_reference(self):
        from finmy.builder.sparse_build.organization_errors import OrganizationValidationError
        from finmy.builder.sparse_build.relation_candidates import validate_relation_candidates

        package = many_facts()
        unknown = relation("UNKNOWN", "A1")
        payload = {"activity_relations": [{"from_activity_id": "A1"}, unknown]}
        original = copy.deepcopy(payload)
        with self.assertRaises(OrganizationValidationError) as caught:
            validate_relation_candidates(payload, ["A1"],
                                         [row["activity_id"] for row in package["activity"]], package)
        issues = caught.exception.report["violations"]
        self.assertIn("invalid_shape", {issue["code"] for issue in issues})
        unknown_issue = next(issue for issue in issues if issue["code"] == "unknown_from_activity")
        self.assertEqual(unknown_issue["item"], unknown)
        self.assertIn("1", unknown_issue["path"])
        self.assertEqual(payload, original)


if __name__ == "__main__":
    unittest.main()
