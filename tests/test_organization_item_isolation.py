"""Placement isolation, cache validity, and independent native export regressions."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()
from finmy.builder.sparse_build.organization_partial import PENDING_RELEVANCE
from finmy.builder.sparse_build.organization_batches import partition_placements, _memberships
from finmy.builder.sparse_build.organization_errors import OrganizationValidationError
from finmy.builder.sparse_build.organization_resume import OrganizationResume
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.person_organization import apply_organization
from test_sparse_organization_batches import many_facts
from test_person_canonical_organization import CanonicalResponses, bind_test_evidence
from test_sparse_person_organization import plan, facts, vf
import test_sparse_person_full_flow as lifecycle


class PlacementIsolationTest(unittest.TestCase):
    def setUp(self):
        self.package = bind_test_evidence(many_facts(3, 2))
        self.layout = {'events': [{'event_id': 'E'}]}
        self.ids = ['A1', 'A2', 'A3']
        self.relevance_ids = ['O1', 'O2']
        self.candidate = {
            'memberships': [{'event_id': 'E', 'activity_id': aid} for aid in self.ids],
            'unassigned_reasons': [],
            'occurrence_relevance': [{'occurrence_id': oid, 'subject_relevance': vf('The person spoke.')}
                                     for oid in self.relevance_ids],
            'occurrence_issues': [],
        }

    def partition(self, candidate):
        before = copy.deepcopy((candidate, self.package))
        result = partition_placements(candidate, self.ids, self.relevance_ids, self.layout, self.package)
        self.assertEqual((candidate, self.package), before)
        return result

    def test_unknown_ids_and_invalid_details_do_not_poison_good_rows(self):
        value = copy.deepcopy(self.candidate)
        value['memberships'][1]['detail_indices'] = [999]
        value['memberships'].append({'event_id': 'NO_EVENT', 'activity_id': 'NONEXISTENT'})
        result, audit = self.partition(value)
        self.assertEqual([r['activity_id'] for r in result['memberships']], ['A1', 'A3'])
        self.assertEqual(result['pending_activity_ids'], ['A2'])
        self.assertEqual(result['occurrence_relevance'], value['occurrence_relevance'])
        self.assertEqual([r['kind'] for r in audit], ['invalid_membership', 'invalid_membership'])

    def test_conflicting_relevance_is_pending_without_losing_other_occurrences(self):
        value = copy.deepcopy(self.candidate)
        row = copy.deepcopy(value['occurrence_relevance'][0])
        row['subject_relevance']['value'] = 'Contradictory alternative'
        value['occurrence_relevance'].append(row)
        result, audit = self.partition(value)
        self.assertEqual(result['pending_occurrence_ids'], ['O1'])
        self.assertEqual(result['occurrence_relevance'], [value['occurrence_relevance'][1]])
        self.assertEqual(result['memberships'], value['memberships'])
        self.assertEqual(audit[0]['kind'], 'conflicting_relevance')

    def test_pending_metadata_cannot_be_used_to_accept_uncited_claims(self):
        package, proposal = facts(), plan()
        oid = proposal['occurrence_relevance'][0]['occurrence_id']
        proposal['pending_occurrence_ids'] = [oid]
        with self.assertRaisesRegex(ValueError, 'execution metadata'):
            apply_organization(package, proposal)
        proposal['occurrence_relevance'][0]['subject_relevance'] = copy.deepcopy(PENDING_RELEVANCE)
        person, report = apply_organization(package, proposal)
        self.assertEqual(report['status'], 'partial_organization_requires_review')
        self.assertEqual(person['action'], package['action'])

    def test_membership_errors_report_all_bad_items_at_once(self):
        with self.assertRaises(OrganizationValidationError) as caught:
            _memberships([{'event_id':'missing','activity_id':'X'},
                          {'event_id':'missing','activity_id':'Y'}], {'A'}, self.layout, self.package)
        self.assertEqual(len(caught.exception.report['violations']), 4)

    def test_local_repair_only_requests_pending_occurrence_and_keeps_later_batches(self):
        from finmy.builder.sparse_build.organization_batches import organize_person_plan
        first = [True]
        def damage(task, value, name):
            if task['phase'] == 'Placement' and first[0]:
                first[0] = False
                value['occurrence_relevance'].pop(0)
        responses = CanonicalResponses(damage)
        result = organize_person_plan(bind_test_evidence(many_facts()), {}, {'name':'Example'}, 'English',
                                       responses, lambda *args: None)
        tasks = [c['task'] for c in responses.calls if c['task']['phase']=='Placement']
        self.assertEqual(tasks[1]['assigned_ids'], [])
        self.assertEqual(tasks[1]['relevance_ids'], ['O1'])
        self.assertEqual(tasks[-1]['assigned_ids'], ['A21'])
        self.assertFalse(result.get('pending_occurrence_ids'))
        self.assertEqual(len(result['memberships']), 21)

    def test_unusable_relevance_is_local_to_its_occurrence(self):
        from finmy.builder.sparse_build.organization_batches import organize_person_plan
        def unavailable(task, value, name):
            if task['phase']=='Placement':
                for row in value['occurrence_relevance']:
                    if row['occurrence_id']=='O1':
                        row['subject_relevance']['evidence_source_contents'] = []
        responses = CanonicalResponses(unavailable)
        package = bind_test_evidence(many_facts())
        result = organize_person_plan(package, {}, {'name':'Example'}, 'English',
                                       responses, lambda *args: None)
        person, report = apply_organization(package, result)
        self.assertEqual(report['pending_occurrence_ids'], ['O1'])
        self.assertEqual(person['action'], package['action'])
        self.assertEqual(len(result['memberships']), 21)
        self.assertIn('Relations', [c['task']['phase'] for c in responses.calls])
        self.assertEqual(next(r for r in result['occurrence_relevance'] if r['occurrence_id']=='O6')
                         ['subject_relevance']['value'], 'The person spoke.')


class OrganizationResumeTest(unittest.TestCase):
    def setup_cache(self, status='accepted', finish='stop'):
        self.request = {'facts':{'activity':[], 'activity_detail':[], 'source_document':[{'content':'SOURCE'}]}}
        self.task = {'phase':'EventLayout', 'instructions':'old text','response_schema':{}}
        user = json.dumps(self.request)+'\n\nBATCH TASK:\n'+json.dumps(self.task)
        trace = {'PersonOrganization': {'prompt':[{'role':'system','content':'sys'}, {'role':'user','content':user}],
                                         'response':json.dumps({'answer':1})}}
        b = SparseRagBuilder.__new__(SparseRagBuilder)
        b._organization_resume_history = [{'agent':'PersonOrganization','save_name':'PersonOrganization-EventLayout',
                                          'status':status,'finish_reason':finish,'attempt':1}]
        b._organization_resume_artifacts = {'PersonOrganization-EventLayout.json':json.dumps(trace).encode()}
        b._save_agent_result = Mock()
        b._infer_and_parse_json = Mock(return_value={'new':True})
        self.b = b
        return OrganizationResume(b)

    def user(self, request=None, task=None):
        return json.dumps(request or self.request)+'\n\nBATCH TASK:\n'+json.dumps(task or self.task)

    def test_reuses_complete_prior_candidate_after_current_validation(self):
        for status in ['accepted','invalid_output']:
            cache=self.setup_cache(status)
            validator=Mock()
            self.assertEqual(cache.infer('sys',self.user(),'PersonOrganization-EventLayout',validator),{'answer':1})
            validator.assert_called_once()
            self.b._infer_and_parse_json.assert_not_called()

    def test_source_or_scope_change_invalidates_reuse(self):
        for part in ['source','layout','ids']:
            cache=self.setup_cache()
            request, task=copy.deepcopy(self.request),copy.deepcopy(self.task)
            if part=='source': request['facts']['source_document'][0]['content']='CHANGED'
            elif part=='layout': task['layout']={'events':['NEW']}
            else: task['assigned_ids']=['NEW']
            self.assertEqual(cache.infer('sys',self.user(request,task),'PersonOrganization-EventLayout',lambda v:None),{'new':True})
            self.b._infer_and_parse_json.assert_called_once()

    def test_legacy_derived_catalog_is_recomputed_without_repeating_model_calls(self):
        cache=self.setup_cache()
        request=copy.deepcopy(self.request);request['available_detail_indices']={}
        task={**self.task,'available_detail_indices':{}}
        cache.infer('sys',self.user(request,task),'PersonOrganization-EventLayout',lambda v:None)
        self.b._infer_and_parse_json.assert_not_called()

    def test_semantic_instruction_or_system_change_invalidates_reuse(self):
        for change in ['instructions', 'system']:
            cache = self.setup_cache()
            task = copy.deepcopy(self.task)
            system = 'sys'
            if change == 'instructions':
                task['instructions'] = 'Corrected semantic rule'
            else:
                system = 'Corrected system policy'
            self.assertEqual(cache.infer(system, self.user(task=task), 'PersonOrganization-EventLayout', lambda v:None), {'new':True})
            self.b._infer_and_parse_json.assert_called_once()

    def test_truncated_or_still_invalid_response_is_not_reused(self):
        cache=self.setup_cache(finish='length')
        cache.infer('sys',self.user(),'PersonOrganization-EventLayout',lambda v:None)
        self.b._infer_and_parse_json.assert_called_once()
        cache=self.setup_cache()
        def invalid(v):raise ValueError('not valid today')
        cache.infer('sys',self.user(),'PersonOrganization-EventLayout',invalid)
        self.b._infer_and_parse_json.assert_called_once()


class NativeExportIsolationTest(unittest.TestCase):
    setUp = lifecycle.SparsePersonFullFlowTest.setUp
    builder = lifecycle.SparsePersonFullFlowTest.builder
    artifact = lifecycle.SparsePersonFullFlowTest.artifact

    def test_failed_legacy_projection_preserves_native_json_html_and_replay(self):
        b, sequence=self.builder()
        with patch('finmy.person_epg.compat_projection.project_person_epg',side_effect=ValueError('old temporal scope')):
            output=b.run(self.inputs)
        root=Path(b.save_dir)
        self.assertTrue((root/'FinalPersonEPG.json').exists())
        self.assertTrue((root/'FinalPersonEPG.html').exists())
        self.assertFalse((root/'FinalSubjectGraph.json').exists())
        self.assertIsNone(output.subject_graph)
        self.assertEqual(output.extras['compat_projection']['status'],'failed')
        self.assertEqual(b.integrate_person_from_files(strict=True),output.extras['person_epg'])
