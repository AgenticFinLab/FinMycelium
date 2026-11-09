"""Exact theme projections preserve facts and inform all relation batches."""

import copy
import json
import unittest

from finmy.builder.sparse_build.organization_context import (
    ORGANIZATION_CONTEXT_POLICY_IDENTITY, build_organization_context,
)
from finmy.builder.sparse_build.person_organization import validate_organization
from finmy.builder.sparse_build.relation_candidates import collect_canonical_relations
from test_sparse_person_organization import facts, plan, vf


class SparseOrganizationContextTest(unittest.TestCase):
    def test_exact_detail_projection_distinguishes_all_empty_and_selected(self):
        package, proposal = facts(), plan()
        package["activity_detail"].extend([
            {"activity_id": "A", "detail_index": 1, "value": "Second exact detail", "evidence_set_id": "ES2"},
            {"activity_id": "A", "detail_index": 2, "value": "Third exact detail"},
        ])
        for index, selection in enumerate((None, [], [2, 0]), 1):
            eid = f"E{index}"
            proposal["events"].append({**copy.deepcopy(proposal["events"][0]), "event_id": eid})
            proposal["memberships"].append({"event_id": eid, "activity_id": "A", "detail_indices": selection})
        original = copy.deepcopy((package, proposal))
        context = build_organization_context(package, proposal)
        self.assertEqual((package, proposal), original)
        projections = [theme["activities"][0] for theme in context["themes"]]
        self.assertEqual([row["detail_indices"] for row in projections], [[0], None, [], [2, 0]])
        self.assertEqual([row["detail_mode"] for row in projections], ["selected", "all", "selected", "selected"])
        self.assertEqual([[detail["detail_index"] for detail in row["selected_details"]]
                          for row in projections], [[0], [0, 1, 2], [], [0, 2]])
        self.assertEqual(projections[1]["selected_details"], package["activity_detail"])
        context["themes"][1]["activities"][0]["selected_details"][0]["value"] = "changed"
        context["themes"][0]["summary"]["value"] = "changed"
        self.assertEqual((package, proposal), original)

    def test_original_actors_parties_context_and_evidence_references_survive(self):
        package, proposal = facts(), plan()
        package["action"][0]["evidence_set_id"] = "ES_ACTION"
        package["occurrence"][0].update(evidence_set_id="ES_OCC", start_time_id="T", end_time_id=None)
        package["activity_detail"][0]["evidence_set_id"] = "ES_DETAIL"
        package["relation_occurrence"] = [{"occurrence_id": "O", "relation_id": "ER1"}]
        package["financial_transaction"] = [{"transaction_id": "TX", "occurrence_id": "O",
            "name": "Company transfer", "from_entity_id": "CO", "to_entity_id": "OTHER",
            "timestamp_time_id": "T", "evidence_set_id": "ES_TX"}]
        package["activity"].append({"activity_id": "ATX", "transaction_id": "TX"})
        package["occurrence_participant"].append({"occurrence_id": "O", "entity_id": "CO"})
        proposal["background_occurrence_ids"] = ["O"]
        proposal["memberships"].extend([
            {"event_id": "E", "activity_id": "ATX", "display_title": "Executing transfer"},
            {"event_id": "E", "activity_id": "C:O"},
        ])
        before = copy.deepcopy((package, proposal))
        context = build_organization_context(package, proposal)
        action, transaction, background = context["themes"][0]["activities"]
        self.assertEqual(action["actor_id"], "P")
        self.assertEqual(action["time_refs"], {"timestamp_time_id": "T"})
        self.assertEqual(action["display_title"], "Statement")
        self.assertEqual(action["evidence_set_ids"], ["ES_ACTION", "ES_OCC", "ES_DETAIL"])
        self.assertEqual(action["entity_relation_ids"], ["ER1"])
        self.assertEqual(transaction["fact_ref"], {"table": "financial_transaction", "id": "TX"})
        self.assertEqual(transaction["display_title"], "Executing transfer")
        self.assertEqual((transaction["from_entity_id"], transaction["to_entity_id"]), ("CO", "OTHER"))
        self.assertNotIn("actor_id", transaction)
        self.assertEqual(background["kind"], "context")
        self.assertEqual(background["participant_entity_ids"], ["P", "CO"])
        self.assertEqual(background["fact_ref"], {"table": "occurrence", "id": "O"})
        self.assertEqual(background["time_refs"], {"start_time_id": "T", "end_time_id": None})
        self.assertNotIn("actor_id", background)
        self.assertEqual((package, proposal), before)
        self.assertNotIn("source_document", context)
        self.assertNotIn(package["source_document"][0]["content"], json.dumps(context["themes"][0]["activities"][0]["fact_ref"]))

    def test_existing_context_identity_and_event_local_stage_ids_are_preserved(self):
        package, proposal = facts(), plan()
        package["activity"].append({"activity_id": "BACKGROUND", "context_occurrence_id": "O"})
        package["activity_detail"].append({"activity_id": "BACKGROUND", "detail_index": 0, "value": "Exact background"})
        proposal["events"].append({**copy.deepcopy(proposal["events"][0]), "event_id": "E2"})
        proposal["stages"].append({**copy.deepcopy(proposal["stages"][0]), "event_id": "E2"})
        proposal["memberships"].append({"event_id": "E2", "activity_id": "BACKGROUND", "stage_id": "S", "detail_indices": [0]})
        validate_organization(proposal, package)
        context = build_organization_context(package, proposal)
        self.assertEqual(context["themes"][0]["stages"][0]["activity_ids"], ["A"])
        self.assertEqual(context["themes"][1]["stages"][0]["activity_ids"], ["BACKGROUND"])
        projection = context["themes"][1]["activities"][0]
        self.assertEqual(projection["activity_id"], "BACKGROUND")
        self.assertEqual(projection["selected_details"][0]["value"], "Exact background")

    def test_diagnostics_are_advisory_and_do_not_change_a_valid_plan(self):
        package, proposal = facts(), plan()
        proposal["domains"].append({"domain_id": "D2", "label": "Other domain"})
        proposal["events"].append({**copy.deepcopy(proposal["events"][0]), "event_id": "E2", "domain_id": "D2"})
        proposal["memberships"][0].pop("detail_indices")
        proposal["memberships"].append({"event_id": "E2", "activity_id": "A"})
        before = copy.deepcopy((package, proposal))
        context = build_organization_context(package, proposal)
        codes = {hint["code"] for hint in context["quality_hints"]}
        self.assertTrue({"one_event_per_domain", "shared_activity_all_details", "missing_stage_summary"} <= codes)
        self.assertFalse(context["semantic_support_checked"])
        self.assertEqual(context["organization_context_version"], ORGANIZATION_CONTEXT_POLICY_IDENTITY["version"])
        self.assertEqual((package, proposal), before)
        validate_organization(proposal, package)
        self.assertEqual(context, build_organization_context(package, proposal))

    def test_connectivity_counts_links_without_creating_causal_claims(self):
        package, proposal = facts(), plan()
        for index in range(2, 5):
            package["action"].append({**package["action"][0], "action_id": f"ACT{index}"})
            package["activity"].append({"activity_id": f"A{index}", "action_id": f"ACT{index}"})
            proposal["memberships"].append({"event_id": "E", "activity_id": f"A{index}"})
        proposal["activity_relations"] = [
            {"from_activity_id": left, "to_activity_id": right, "relation_type": "context_for",
             "basis": "source", "description": vf("Source relation")}
            for left, right in (("A", "A2"), ("A2", "A3"))
        ]
        before = copy.deepcopy((package, proposal))
        context = build_organization_context(package, proposal)
        self.assertEqual(context["themes"][0]["relation_components"], [["A", "A2", "A3"], ["A4"]])
        self.assertEqual(context["summary"]["relation_count"], 2)
        self.assertFalse(any("disconnected" in hint["code"] for hint in context["quality_hints"]))
        self.assertEqual((package, proposal), before)

    def test_relation_tasks_use_confirmed_memberships_and_targeted_review(self):
        package, proposal = facts(), plan()
        package['action'].append({**package['action'][0], 'action_id': 'ACT2', 'action_type': 'Explain an earlier statement'})
        package['activity'].append({'activity_id': 'A2', 'action_id': 'ACT2'})
        proposal['events'].append({**copy.deepcopy(proposal['events'][0]), 'event_id': 'E2'})
        proposal['memberships'].append({'event_id': 'E2', 'activity_id': 'A2'})
        before = copy.deepcopy(proposal)
        calls = []
        edge = {'from_activity_id': 'A', 'to_activity_id': 'A2', 'relation_type': 'context_for',
                'basis': 'source', 'description': vf('Supported cross-theme relation')}
        def call(phase, task, ids, validator, name, **kwargs):
            calls.append((phase, copy.deepcopy(task), list(ids)))
            self.assertIn('memberships', task)
            if phase == 'Relations':
                payload = {'candidates': [{'relation': edge, 'assessment': {
                    'supported': True, 'evidence_scope': 'relation', 'from_role': 'context', 'to_role': 'statement',
                    'reason': 'The source describes their contextual connection.', 'needs_review': True,
                    'duplicate_fact': False}}] if 'A' in task['assigned_ids'] else []}
            else:
                payload = {'decisions': [{'candidate_id': c['candidate_id'], 'decision': 'accept',
                                         'reason': 'Relation-level support.'} for c in task['candidates']]}
            validator(payload)
            return payload
        result = collect_canonical_relations(package, proposal, call, lambda *args: None, batch_size=1)
        self.assertEqual(result, [edge])
        self.assertEqual([r[0] for r in calls], ['Relations', 'Relations', 'RelationsReview'])
        self.assertEqual(set(calls[-1][2]), {'A', 'A2'})
        self.assertEqual(proposal, before)


if __name__ == "__main__":
    unittest.main()
