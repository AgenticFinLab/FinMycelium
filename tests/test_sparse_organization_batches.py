"""Offline bounded organization: every fact survives, every batch owns its IDs."""

import copy
import json
import unittest

from finmy.builder.sparse_build.person_organization import apply_organization
from finmy.person_epg.validation import validate_person_epg
from test_sparse_person_organization import facts, plan, vf


TASK_MARKER = "\n\nBATCH TASK:\n"


def many_facts(activity_count=21, occurrence_count=6):
    package = facts()
    action = copy.deepcopy(package["action"][0])
    occurrence = copy.deepcopy(package["occurrence"][0])
    package["action"], package["activity"], package["activity_detail"] = [], [], []
    package["occurrence"], package["occurrence_participant"] = [], []
    for index in range(occurrence_count):
        oid = f"O{index + 1}"
        package["occurrence"].append({**occurrence, "occurrence_id": oid, "sort_order": index})
        package["occurrence_participant"].append({"occurrence_id": oid, "entity_id": "P"})
    for index in range(activity_count):
        aid, act = f"A{index + 1}", f"ACT{index + 1}"
        package["action"].append({**action, "action_id": act,
                                  "occurrence_id": f"O{index % occurrence_count + 1}",
                                  "sort_order": index // occurrence_count})
        package["activity"].append({"activity_id": aid, "action_id": act})
        package["activity_detail"].append({"activity_id": aid, "detail_index": 0,
                                           "value": f"Preserved detail {index + 1}"})
    package["source_document"][0]["content"] += '\nLiteral {"unchanged": true} and {Query}.\n' * 30
    return package


def incomplete(finish_reason="length", *, refusal=False, tool_calls=False):
    from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError

    return IncompleteCompletionError("PersonOrganization", finish_reason=finish_reason,
                                     refusal=refusal, tool_calls=tool_calls)


class OrganizationResponses:
    """Model substitute that obeys the public callback and validates its replies."""

    def __init__(self, *, transform=None, background=False, shared=False, unassigned=None):
        self.transform = transform
        self.background = background
        self.shared = shared
        self.unassigned = unassigned
        self.calls, self.accepted = [], []

    def __call__(self, system, user, savename, validator):
        if TASK_MARKER in user:
            prefix, raw_task = user.split(TASK_MARKER, 1)
            task = json.loads(raw_task)
            request = json.loads(prefix)
        else:
            prefix, task, request = user, {"phase": "Single"}, json.loads(user)
        self.calls.append({"task": copy.deepcopy(task), "request": request,
                           "prefix": prefix, "savename": savename, "system": system})
        value = self.response(task)
        if self.transform:
            self.transform(task, value)
        validator(value)
        self.accepted.append(copy.deepcopy(task))
        return copy.deepcopy(value)

    def response(self, task):
        phase, ids = task["phase"], task.get("assigned_ids", [])
        if phase == "Single":
            return plan()
        if phase == "Layout":
            result = {name: copy.deepcopy(plan()[name]) for name in ("domains", "events", "stages")}
            if self.shared:
                result["events"].append({**copy.deepcopy(result["events"][0]), "event_id": "E2"})
            return result
        if phase == "Assignments":
            members = [{"event_id": "E", "activity_id": aid, "stage_id": "S"}
                       for aid in ids if aid != self.unassigned]
            if self.shared and "A1" in ids:
                members.append({"event_id": "E2", "activity_id": "A1"})
            return {"memberships": members,
                    "unassigned_reasons": [{"activity_id": self.unassigned,
                                            "reason": "No supported experience assignment."}]
                    if self.unassigned in ids else []}
        if phase == "Relevance":
            backgrounds = [oid for oid in ids if self.background and oid == "O1"]
            return {"occurrence_relevance": [{"occurrence_id": oid,
                                               "subject_relevance": vf("The person spoke.")}
                                              for oid in ids],
                    "background_occurrence_ids": backgrounds,
                    "memberships": [{"event_id": "E", "activity_id": f"C:{oid}"}
                                    for oid in backgrounds], "occurrence_issues": []}
        if phase == "Relations":
            relations = []
            if "A1" in ids and "A21" in task["allowed_activity_ids"]:
                relations.append({"from_activity_id": "A1", "to_activity_id": "A21",
                                  "relation_type": "context_for", "basis": "source",
                                  "description": vf("The first activity gives context for the later activity.")})
            if self.background and "C:O1" in ids:
                relations.append({"from_activity_id": "C:O1", "to_activity_id": "A1",
                                  "relation_type": "context_for", "basis": "source",
                                  "description": vf("The meeting gives context for the statement.")})
            return {"activity_relations": relations}
        if phase == "RelationsReview":
            seen, decisions = set(), []
            for candidate in task["candidates"]:
                relation = candidate["relation"]
                key = tuple(relation[name] for name in
                            ("from_activity_id", "to_activity_id", "relation_type"))
                decision = "reject" if key in seen else "accept"
                seen.add(key)
                decisions.append({"candidate_id": candidate["candidate_id"],
                                  "decision": decision,
                                  "reason": "Supported candidate." if decision == "accept"
                                  else "Another version of this relation was selected."})
            return {"decisions": decisions}
        raise AssertionError(f"Unexpected organization phase {phase}")


class SparseOrganizationBatchesTest(unittest.TestCase):
    def organize(self, package, responses):
        from finmy.builder.sparse_build.organization_batches import organize_person_plan

        self.saved = []
        return organize_person_plan(package, {"stages": []}, {"name": "Example person"},
                                    "English", responses,
                                    lambda data, name: self.saved.append((name, copy.deepcopy(data))))

    def test_small_package_keeps_single_complete_response(self):
        responses = OrganizationResponses()
        result = self.organize(facts(), responses)
        self.assertEqual(result, plan())
        self.assertEqual([call["task"]["phase"] for call in responses.calls], ["Single"])
        self.assertEqual(responses.calls[0]["savename"], "PersonOrganization")
        self.assertEqual(responses.calls[0]["request"]["output_language"], "English")

    def test_large_plan_preserves_all_facts_sources_and_cross_batch_links(self):
        package = many_facts()
        original = copy.deepcopy(package)
        responses = OrganizationResponses(background=True, shared=True, unassigned="A20")
        result = self.organize(package, responses)
        person, report = apply_organization(package, result)
        self.assertEqual(validate_person_epg(person), {"valid": True, "errors": []})
        self.assertEqual(package, original)
        for name in ("entity", "action", "financial_transaction", "time_value", "activity_detail", "source_document"):
            self.assertEqual(person[name], original[name])
        assigned = {row["activity_id"] for row in result["memberships"]}
        unassigned = {row["activity_id"] for row in result["unassigned_reasons"]}
        self.assertEqual((assigned | unassigned) - {"C:O1"}, {f"A{i}" for i in range(1, 22)})
        self.assertEqual(unassigned, {"A20"})
        self.assertEqual(sum(row["activity_id"] == "A1" for row in result["memberships"]), 2)
        self.assertEqual({row["occurrence_id"] for row in result["occurrence_relevance"]},
                         {f"O{i}" for i in range(1, 7)})
        self.assertEqual({(r["from_activity_id"], r["to_activity_id"]) for r in result["activity_relations"]},
                         {("A1", "A21"), ("C:O1", "A1")})
        self.assertEqual(report["background_activity_ids"], ["C:O1"])
        self.assertTrue(self.saved)
        self.assertEqual(len({call["prefix"] for call in responses.calls}), 1)
        self.assertEqual(len({call["system"] for call in responses.calls}), 1)
        for call in responses.calls:
            self.assertEqual(call["request"]["facts"]["source_document"], original["source_document"])
            self.assertEqual(call["request"]["facts"]["action"], original["action"])
            self.assertEqual(call["request"]["facts"]["activity_detail"], original["activity_detail"])
        assignments = [call["task"]["assigned_ids"] for call in responses.calls
                       if call["task"]["phase"] == "Assignments"]
        self.assertEqual(list(map(len, assignments)), [20, 1])
        relevance = [call["task"]["assigned_ids"] for call in responses.calls
                     if call["task"]["phase"] == "Relevance"]
        self.assertEqual(list(map(len, relevance)), [5, 1])
        first_links = next(call["task"] for call in responses.calls if call["task"]["phase"] == "Relations")
        self.assertNotIn("A21", first_links["assigned_ids"])
        self.assertIn("A21", first_links["allowed_activity_ids"])

    def test_length_splits_only_current_list_and_retains_exact_coverage(self):
        def truncate_large_assignments(task, value):
            if task["phase"] == "Assignments" and len(task["assigned_ids"]) > 2:
                raise incomplete()

        responses = OrganizationResponses(transform=truncate_large_assignments)
        result = self.organize(many_facts(), responses)
        self.assertEqual({row["activity_id"] for row in result["memberships"]},
                         {f"A{i}" for i in range(1, 22)})
        self.assertEqual(len(result["memberships"]), 21)
        accepted = [task["assigned_ids"] for task in responses.accepted if task["phase"] == "Assignments"]
        self.assertTrue(all(len(ids) <= 2 for ids in accepted))
        self.assertEqual(sorted(aid for ids in accepted for aid in ids), sorted(f"A{i}" for i in range(1, 22)))
        self.assertEqual(sum(call["task"]["phase"] == "Layout" for call in responses.calls), 1)

    def test_assignment_batch_may_be_entirely_unassigned(self):
        result = self.organize(many_facts(), OrganizationResponses(unassigned="A21"))
        self.assertEqual(result["unassigned_reasons"], [
            {"activity_id": "A21", "reason": "No supported experience assignment."}])
        self.assertNotIn("A21", {row["activity_id"] for row in result["memberships"]})
        self.assertTrue(validate_person_epg(apply_organization(many_facts(), result)[0])["valid"])

    def test_existing_context_and_its_details_remain_visible_and_are_not_recreated(self):
        from finmy.person_epg.sparse_adapter import add_evidence

        package = many_facts()
        package["activity"].append({"activity_id": "B", "context_occurrence_id": "O1"})
        evidence_id = add_evidence(package, {"/value": vf("Existing context detail")})
        detail = {"activity_id": "B", "detail_index": 0,
                  "value": "Existing context detail must remain available to the organizer.",
                  "evidence_set_id": evidence_id}
        package["activity_detail"].append(detail)
        original = copy.deepcopy(package)

        def link_existing_context(task, value):
            if task["phase"] == "Assignments":
                for membership in value["memberships"]:
                    if membership["activity_id"] == "B":
                        membership["detail_indices"] = [0]
            if task["phase"] == "Relations" and "A1" in task["assigned_ids"]:
                value["activity_relations"].append({"from_activity_id": "A1", "to_activity_id": "B",
                    "relation_type": "context_for", "basis": "source", "description": vf("Existing context")})

        responses = OrganizationResponses(transform=link_existing_context)
        result = self.organize(package, responses)
        person, report = apply_organization(package, result)
        self.assertEqual(package, original)
        self.assertEqual(person["activity"], original["activity"])
        self.assertEqual(person["activity_detail"], original["activity_detail"])
        self.assertEqual(report["background_activity_ids"], [])
        self.assertIn("B", {row["activity_id"] for row in result["memberships"]})
        self.assertIn({"event_id": "E", "activity_id": "B", "detail_index": 0},
                      person["event_activity_detail"])
        self.assertIn(("A1", "B"), {(r["from_activity_id"], r["to_activity_id"])
                                     for r in result["activity_relations"]})
        for call in responses.calls:
            self.assertEqual(call["request"]["existing_context_activities"],
                             [{"activity_id": "B", "context_occurrence_id": "O1"}])
            self.assertIn(detail["value"], json.dumps(call["request"]))
            request_facts = call["request"]["facts"]
            self.assertIn(detail, request_facts["activity_detail"])
            self.assertIn(evidence_id, {row["evidence_set_id"] for row in request_facts["evidence_set"]})
            links = [row for row in request_facts["evidence_link"] if row["evidence_set_id"] == evidence_id]
            self.assertTrue(links)
            self.assertTrue({row["span_id"] for row in links}
                            <= {row["span_id"] for row in request_facts["evidence_span"]})
        with self.assertRaisesRegex(ValueError, "Existing background"):
            self.organize(package, OrganizationResponses(background=True))

    def test_small_length_response_falls_back_without_accepting_partial_json(self):
        def truncate_single(task, value):
            if task["phase"] == "Single":
                raise incomplete()

        responses = OrganizationResponses(transform=truncate_single)
        result = self.organize(facts(), responses)
        self.assertEqual(responses.calls[0]["task"]["phase"], "Single")
        self.assertEqual(responses.calls[1]["task"]["phase"], "Layout")
        self.assertEqual(result["memberships"][0]["activity_id"], "A")
        self.assertEqual(result["occurrence_relevance"][0]["occurrence_id"], "O")
        self.assertTrue(validate_person_epg(apply_organization(facts(), result)[0])["valid"])

    def test_non_length_refusal_and_tool_output_do_not_trigger_more_calls(self):
        from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError

        for options in ({"finish_reason": "content_filter"}, {"refusal": True}, {"tool_calls": True}):
            with self.subTest(options=options):
                def fail(task, value):
                    raise incomplete(**options)
                responses = OrganizationResponses(transform=fail)
                with self.assertRaises(IncompleteCompletionError):
                    self.organize(facts(), responses)
                self.assertEqual(len(responses.calls), 1)
                def fail_assignment(task, value):
                    if task["phase"] == "Assignments":
                        raise incomplete(**options)
                responses = OrganizationResponses(transform=fail_assignment)
                with self.assertRaises(IncompleteCompletionError):
                    self.organize(many_facts(), responses)
                self.assertEqual([call["task"]["phase"] for call in responses.calls],
                                 ["Layout", "Assignments"])

    def test_layout_and_single_item_length_fail_without_unbounded_splitting(self):
        from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError

        for fail_phase in ("Layout", "Assignments"):
            with self.subTest(phase=fail_phase):
                def fail(task, value):
                    if task["phase"] == fail_phase:
                        raise incomplete()
                responses = OrganizationResponses(transform=fail)
                with self.assertRaises(IncompleteCompletionError):
                    self.organize(many_facts(), responses)
                calls = [c for c in responses.calls if c["task"]["phase"] == fail_phase]
                self.assertLessEqual(len(calls), 6)
                if fail_phase == "Assignments":
                    self.assertEqual(len(calls[-1]["task"]["assigned_ids"]), 1)

    def test_batch_cannot_change_ids_or_links_owned_by_another_batch(self):
        def wrong_assignment(task, value):
            if task["phase"] == "Assignments":
                value["memberships"].append({"event_id": "E", "activity_id": "A21"})

        def wrong_relevance(task, value):
            if task["phase"] == "Relevance":
                value["occurrence_relevance"].append({"occurrence_id": "O6", "subject_relevance": vf("Outside batch")})

        def wrong_background(task, value):
            if task["phase"] == "Relevance":
                value["background_occurrence_ids"] = ["O6"]
                value["memberships"] = [{"event_id": "E", "activity_id": "C:O6"}]

        def unknown_link_target(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"][0]["to_activity_id"] = "MISSING"

        for mutate in (wrong_assignment, wrong_relevance, wrong_background, unknown_link_target):
            with self.subTest(mutation=mutate.__name__):
                package = many_facts()
                before = copy.deepcopy(package)
                with self.assertRaises(ValueError):
                    self.organize(package, OrganizationResponses(transform=mutate))
                self.assertEqual(package, before)

    def test_known_cross_batch_source_requires_owner_review_before_acceptance(self):
        relation = {"from_activity_id": "A21", "to_activity_id": "A1",
                    "relation_type": "context_for", "basis": "source",
                    "description": vf("Known activity outside this generation batch.")}

        def propose_cross_batch(task, value):
            if task["phase"] == "Relations":
                value["activity_relations"] = [copy.deepcopy(relation)]

        responses = OrganizationResponses(transform=propose_cross_batch)
        result = self.organize(many_facts(), responses)
        self.assertEqual(result["activity_relations"], [relation])
        reviews = [call["task"] for call in responses.calls if call["task"]["phase"] == "RelationsReview"]
        self.assertEqual(len(reviews), 1)
        self.assertIn("A21", reviews[0]["assigned_ids"])
        self.assertEqual(reviews[0]["candidates"][0]["relation"], relation)
        phases = [call["task"]["phase"] for call in responses.calls]
        self.assertLess(max(i for i, phase in enumerate(phases) if phase == "Relations"),
                        min(i for i, phase in enumerate(phases) if phase == "RelationsReview"))

    def test_batch_missing_coverage_or_invalid_references_is_rejected(self):
        def missing_activity(task, value):
            if task["phase"] == "Assignments":
                value["memberships"].pop()

        def missing_occurrence(task, value):
            if task["phase"] == "Relevance":
                value["occurrence_relevance"].pop()

        def wrong_stage(task, value):
            if task["phase"] == "Assignments":
                value["memberships"][0]["stage_id"] = "MISSING"

        def wrong_detail(task, value):
            if task["phase"] == "Assignments":
                value["memberships"][0]["detail_indices"] = [99]

        def unexpected_field(task, value):
            if task["phase"] == "Layout":
                value["action"] = []

        def missing_quote(task, value):
            if task["phase"] == "Layout":
                value["events"][0]["summary"]["evidence_source_contents"] = []

        def duplicate_relevance(task, value):
            if task["phase"] == "Relevance":
                value["occurrence_relevance"].append(copy.deepcopy(value["occurrence_relevance"][0]))

        def scene_requires_reconstruction(task, value):
            if task["phase"] == "Relevance":
                value["occurrence_issues"] = ["The source describes two distinct scenes."]

        for mutate in (missing_activity, missing_occurrence, wrong_stage, wrong_detail,
                       unexpected_field, missing_quote, duplicate_relevance, scene_requires_reconstruction):
            with self.subTest(mutation=mutate.__name__):
                with self.assertRaises(ValueError):
                    self.organize(many_facts(), OrganizationResponses(transform=mutate))


if __name__ == "__main__":
    unittest.main()
