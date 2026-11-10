"""Organization changes memberships, never the underlying attributed facts."""

import copy
import hashlib
import json
from pathlib import Path
import unittest

from finmy.builder.sparse_build.person_organization import (
    apply_organization, organization_request, validate_organization,
)
from finmy.person_epg.validation import validate_person_epg
from test_person_epg_validation import package_fixture


def vf(value, quote="Example person spoke at the meeting."):
    return {"value": value, "evidence_source_contents": [quote] if quote else [],
            "reasons": ["Documented in the supplied source."]}


def facts():
    package = package_fixture()
    for key in ("domain", "event", "stage", "event_activity", "event_activity_detail", "activity_relation"):
        package[key] = []
    package["source_document"] = [{"document_id": "DOC", "content": "Example person spoke at the meeting."}]
    return package


def plan():
    return {
        "domains": [{"domain_id": "D", "label": "Public communication"}],
        "events": [{"event_id": "E", "domain_id": "D", "label": "Documented communication",
                    "summary": vf("The person made a statement.")}],
        "stages": [{"event_id": "E", "stage_id": "S", "label": "Public statement",
                    "boundary_reason": vf("This stage contains the person's public statement.")}],
        "memberships": [{"event_id": "E", "activity_id": "A", "stage_id": "S", "detail_indices": [0]}],
        "occurrence_relevance": [{"occurrence_id": "O", "subject_relevance": vf("The person spoke.")}],
        "background_occurrence_ids": [], "activity_relations": [], "unassigned_reasons": [],
    }


class SparsePersonOrganizationTest(unittest.TestCase):
    def test_organization_preserves_facts_and_input(self):
        package = facts()
        before = copy.deepcopy(package)
        result, report = apply_organization(package, plan())
        self.assertEqual(package, before)
        for table in ("entity", "action", "financial_transaction", "time_value", "activity_detail", "source_document"):
            self.assertEqual(result[table], before[table])
        self.assertEqual(result["event_activity"][0]["detail_mode"], "selected")
        self.assertEqual(result["event_activity_detail"][0]["detail_index"], 0)
        self.assertEqual(validate_person_epg(result), {"valid": True, "errors": []})
        self.assertFalse(report["semantic_support_checked"])

    def test_same_fact_can_belong_to_two_events(self):
        proposal = plan()
        proposal["events"].append({**proposal["events"][0], "event_id": "E2"})
        proposal["memberships"].append({"event_id": "E2", "activity_id": "A", "stage_id": None})
        result, _ = apply_organization(facts(), proposal)
        self.assertEqual(len(result["action"]), 1)
        self.assertEqual(len(result["activity"]), 1)
        self.assertEqual(len(result["event_activity"]), 2)


    def test_invalid_references_and_duplicate_memberships_are_rejected_atomically(self):
        mutations = [
            lambda p: p["memberships"][0].update(activity_id="MISSING"),
            lambda p: p["memberships"][0].update(stage_id="OTHER_EVENT_STAGE"),
            lambda p: p["memberships"][0].update(detail_indices=[5]),
            lambda p: p["memberships"].append(copy.deepcopy(p["memberships"][0])),
            lambda p: p["occurrence_relevance"].clear(),
            lambda p: p["stages"][0]["boundary_reason"].update(evidence_source_contents=[]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                package, proposal = facts(), plan()
                before = copy.deepcopy(package)
                mutate(proposal)
                with self.assertRaises(ValueError):
                    validate_organization(proposal, package)
                self.assertEqual(package, before)

    def test_occurrence_issue_keeps_valid_facts_and_marks_partial(self):
        proposal = plan()
        proposal['occurrence_issues'] = ['O: The episode needs local scene review.']
        result, report = apply_organization(facts(), proposal)
        self.assertEqual(result['action'], facts()['action'])
        self.assertEqual(report['status'], 'partial_organization_requires_review')


    def test_semantic_links_cannot_use_temporal_basis_or_empty_quotes(self):
        for basis, quote in (("temporal", ""), ("source", "")):
            proposal = plan()
            proposal["background_occurrence_ids"] = ["O"]
            proposal["memberships"].append({"event_id": "E", "activity_id": "C:O"})
            proposal["activity_relations"] = [{"from_activity_id": "C:O", "to_activity_id": "A",
                                               "relation_type": "executed_by", "basis": basis,
                                               "description": vf("Execution", quote)}]
            with self.assertRaises(ValueError):
                apply_organization(facts(), proposal)

    def test_temporal_precedence_must_be_established_by_activity_dates(self):
        package = facts()
        package["time_value"][0]["value"] = "2023-05-01"
        package["time_value"].append({"time_id": "T2", "value": "2023-05-02"})
        package["action"].append({**package["action"][0], "action_id": "ACT2", "timestamp_time_id": "T2"})
        package["activity"].append({"activity_id": "A2", "action_id": "ACT2"})
        proposal = plan()
        proposal["memberships"].append({"event_id": "E", "activity_id": "A2"})
        proposal["activity_relations"] = [{"from_activity_id": "A", "to_activity_id": "A2",
                                           "relation_type": "precedes", "basis": "temporal",
                                           "description": vf("The first action precedes the second.", "")}]
        self.assertEqual(len(apply_organization(package, proposal)[0]["activity_relation"]), 1)
        package["time_value"][0]["value"] = "2023-05"
        with self.assertRaisesRegex(ValueError, "known activity times"):
            apply_organization(package, proposal)


if __name__ == "__main__":
    unittest.main()
