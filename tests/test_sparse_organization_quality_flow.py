"""V6 event organization derives stages only after accepted fact placement."""
import copy
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.sparse_build.organization_batches import organize_person_plan
from finmy.builder.sparse_build.person_organization import apply_organization
from test_person_canonical_organization import CanonicalResponses, bind_test_evidence
from test_sparse_organization_batches import many_facts


class OrganizationQualityFlowTest(unittest.TestCase):
    def organize(self, transform=None, shared=False):
        self.package = bind_test_evidence(many_facts(3, 2))
        self.original = copy.deepcopy(self.package)
        self.saved = {}
        self.responses = CanonicalResponses(transform, shared=shared)
        return organize_person_plan(self.package, {}, {'name': 'Example person'}, 'English',
            self.responses, lambda value, name: self.saved.update({name: copy.deepcopy(value)}))

    def test_layout_names_events_without_generating_early_summaries_or_stages(self):
        result = self.organize()
        task = self.responses.calls[0]['task']
        self.assertEqual(task['phase'], 'EventLayout')
        self.assertNotIn('summary', task['response_schema']['properties']['events']['items']['properties'])
        self.assertNotIn('stages', task['response_schema']['properties'])
        self.assertEqual(self.package, self.original)
        output, _ = apply_organization(self.package, result)
        for table in ('entity', 'action', 'time_value', 'activity_detail', 'source_document'):
            self.assertEqual(output[table], self.original[table])

    def test_invalid_layout_is_not_silently_accepted(self):
        for change in ('unknown_domain', 'invented_facts'):
            with self.subTest(change=change):
                def mutate(task, result, name):
                    if task['phase'] == 'EventLayout':
                        if change == 'unknown_domain':
                            result['events'][0]['domain_id'] = 'UNKNOWN'
                        else:
                            result['action'] = [{'action_id': 'invented'}]
                with self.assertRaises(ValueError):
                    self.organize(mutate)
                self.assertEqual([r['task']['phase'] for r in self.responses.calls], ['EventLayout'])
                self.assertEqual(self.package, self.original)

    def test_stage_free_event_is_valid_without_a_stage_quota(self):
        def no_stages(task, result, name):
            if task['phase'] == 'EventStructure':
                result['stages'] = []
                for row in result['stage_assignments']:
                    row['stage_id'] = None
        result = self.organize(no_stages)
        self.assertEqual(result['stages'], [])
        self.assertEqual(result['pending_event_ids'], [])
        self.assertTrue(all(r.get('stage_id') is None for r in result['memberships']))

    def test_unbound_summary_quote_is_local_and_original_facts_survive(self):
        def invalid_summary(task, result, name):
            if task['phase'] == 'EventStructure' and task['event']['event_id'] == 'E2':
                result['summary']['evidence_source_contents'] = ['This quotation is not in the source.']
        result = self.organize(invalid_summary, shared=True)
        self.assertEqual(result['pending_event_ids'], ['E2'])
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(len(result['memberships']), 4)
        output, status = apply_organization(self.package, result)
        self.assertEqual(status['status'], 'partial_organization_requires_review')
        self.assertEqual(output['action'], self.original['action'])
        self.assertTrue(any(r['event_id'] == 'E' for r in output['stage']))

    def test_stage_pass_cannot_move_an_activity_into_another_event(self):
        def wrong_owner(task, result, name):
            if task['phase'] == 'EventStructure' and task['event']['event_id'] == 'E2':
                result['stage_assignments'].append({'activity_id': 'A3', 'stage_id': 'S'})
        result = self.organize(wrong_owner, shared=True)
        self.assertEqual(result['pending_event_ids'], ['E2'])
        self.assertEqual([r['activity_id'] for r in result['memberships'] if r['event_id'] == 'E2'], ['A1'])
        self.assertEqual(self.package, self.original)


if __name__ == '__main__':
    unittest.main()
