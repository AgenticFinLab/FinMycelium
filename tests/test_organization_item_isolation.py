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


    def test_source_or_scope_change_invalidates_reuse(self):
        for part in ['source','layout','ids']:
            cache=self.setup_cache()
            request, task=copy.deepcopy(self.request),copy.deepcopy(self.task)
            if part=='source': request['facts']['source_document'][0]['content']='CHANGED'
            elif part=='layout': task['layout']={'events':['NEW']}
            else: task['assigned_ids']=['NEW']
            self.assertEqual(cache.infer('sys',self.user(request,task),'PersonOrganization-EventLayout',lambda v:None),{'new':True})
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
