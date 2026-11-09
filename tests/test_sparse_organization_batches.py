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


def OrganizationResponses(*, transform=None, shared=False, **kwargs):
    """Current protocol fixture; importing saved v5 data does not execute v5."""
    from test_person_canonical_organization import CanonicalResponses
    adapter = (lambda task, result, name: transform(task, result)) if transform else None
    return CanonicalResponses(adapter, shared=shared)


class SparseOrganizationBatchesTest(unittest.TestCase):
    def organize(self, package, responses):
        from finmy.builder.sparse_build.organization_batches import organize_person_plan
        self.saved = {}
        return organize_person_plan(package, {}, {'name': 'Example person'}, 'English', responses,
                                     lambda value, name: self.saved.update({name: copy.deepcopy(value)}))

    def test_large_plan_preserves_all_facts_without_repeating_complete_sources(self):
        package = many_facts()
        before = copy.deepcopy(package)
        responses = OrganizationResponses()
        result = self.organize(package, responses)
        projected, _ = apply_organization(package, result)
        self.assertEqual(projected['activity'], before['activity'])
        self.assertEqual(projected['source_document'], before['source_document'])
        self.assertEqual(len(result['memberships']), 21)
        self.assertEqual(sum(row['task']['phase'] == 'Placement' for row in responses.calls), 2)
        self.assertEqual(responses.calls[0]['request']['facts']['source_document'], [])
        self.assertTrue(all(row['task']['phase'] not in {'LayoutReview', 'Relevance'} for row in responses.calls))

    def test_length_splits_current_placement_and_preserves_prior_rows(self):
        def damage(task, result):
            if task['phase'] == 'Placement' and len(task['assigned_ids']) > 3:
                raise incomplete()
        responses = OrganizationResponses(transform=damage)
        result = self.organize(many_facts(7, 2), responses)
        self.assertEqual({row['activity_id'] for row in result['memberships']}, {f'A{i}' for i in range(1, 8)})
        self.assertEqual(result['pending_activity_ids'], [])
        self.assertEqual(len(result['memberships']), 7)

    def test_singleton_failure_is_pending_and_other_batch_survives(self):
        def damage(task, result):
            if task['phase'] == 'Placement' and task['assigned_ids'] == ['A21']:
                raise incomplete()
        result = self.organize(many_facts(), OrganizationResponses(transform=damage))
        self.assertEqual(result['pending_activity_ids'], ['A21'])
        self.assertEqual(len(result['memberships']), 20)

    def test_existing_context_is_placed_once_without_new_background_creation(self):
        package = many_facts(3, 2)
        package['activity'].append({'activity_id': 'C:O1', 'context_occurrence_id': 'O1'})
        result = self.organize(package, OrganizationResponses())
        projected, _ = apply_organization(package, result)
        self.assertEqual(sum(r['activity_id'] == 'C:O1' for r in projected['activity']), 1)
        self.assertEqual(result['background_occurrence_ids'], [])

    def test_all_placement_unavailable_does_not_invent_an_event(self):
        def damage(task, result):
            if task['phase'] == 'Placement':
                raise RuntimeError('provider unavailable')
        with self.assertRaisesRegex(ValueError, 'No supported Event placement'):
            self.organize(many_facts(2, 2), OrganizationResponses(transform=damage))
        self.assertIn('PersonOrganizationIsolation', self.saved)


if __name__ == '__main__':
    unittest.main()
