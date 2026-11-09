"""Canonical organization regressions: placement first, isolated failures, reuse."""
import copy
import json
import unittest
from types import SimpleNamespace

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.sparse_build.organization_batches import organize_person_plan, TASK_SEPARATOR, partition_placements
from finmy.builder.sparse_build.organization_context import scoped_organization_request
from finmy.builder.sparse_build.organization_resume import OrganizationResume, request_identity
from finmy.builder.sparse_build.organization_details import detail_reference_catalog, resolve_detail_references
from finmy.builder.sparse_build.person_organization import apply_organization
from finmy.builder.sparse_build.relation_candidates import normalize_response_direction
from test_sparse_person_organization import facts, vf
from test_sparse_organization_batches import many_facts


def bind_test_evidence(package):
    from finmy.person_epg.sparse_adapter import add_evidence
    for row in package['action']:
        row['evidence_set_id'] = add_evidence(package, {'/action_type': vf(row['action_type'])})
    return package


class CanonicalResponses:
    def __init__(self, transform=None, shared=False):
        self.calls = []
        self.transform = transform
        self.shared = shared

    def __call__(self, system, user, name, validator):
        prefix, raw = user.split(TASK_SEPARATOR, 1)
        request, task = json.loads(prefix), json.loads(raw)
        self.calls.append({'task': task, 'request': request, 'name': name})
        phase, ids = task['phase'], task.get('assigned_ids', [])
        if phase == 'EventLayout':
            result = {'domains': [{'domain_id': 'D', 'label': 'Public communication'}],
                      'events': [{'event_id': 'E', 'domain_id': 'D', 'label': 'Documented communication',
                                  'process_scope': 'A specific documented communication process.'}]}
            if self.shared:
                result['events'].append({'event_id': 'E2', 'domain_id': 'D', 'label': 'Related experience',
                                         'process_scope': 'A related documented experience.'})
        elif phase == 'Placement':
            result = {'memberships': [{'event_id': 'E', 'activity_id': aid, 'detail_indices': ([request['available_detail_indices'][aid][0]]
                                                         if request['available_detail_indices'][aid] else None)}
                                      for aid in ids], 'unassigned_reasons': [],
                      'occurrence_relevance': [{'occurrence_id': oid, 'subject_relevance': vf('The person spoke.')}
                                               for oid in task['relevance_ids']], 'occurrence_issues': []}
            if self.shared and ids:
                result['memberships'].append({'event_id': 'E2', 'activity_id': ids[0], 'detail_indices': []})
        elif phase == 'EventStructure':
            eid = task['event']['event_id']
            result = {'summary': vf('The person made a statement.'),
                      'stages': [{'event_id': eid, 'stage_id': 'S', 'label': 'Public statement',
                                  'boundary_reason': vf('The person made a public statement.')}],
                      'stage_assignments': [{'activity_id': aid, 'stage_id': 'S'} for aid in ids]}
        elif phase == 'Relations':
            result = {'candidates': []}
        elif phase == 'RelationsReview':
            result = {'decisions': [{'candidate_id': c['candidate_id'], 'decision': 'accept',
                                     'reason': 'The source establishes the response to the proposal.',
                                     'response_activity_id': 'A2', 'trigger_activity_id': 'A1'}
                                    for c in task['candidates']]}
        else:
            raise AssertionError(phase)
        if self.transform:
            self.transform(task, result, name)
        validator(result)
        return result


class CanonicalOrganizationTest(unittest.TestCase):
    def run_plan(self, package=None, responses=None):
        self.saved = {}
        self.responses = responses or CanonicalResponses()
        self.package = bind_test_evidence(package or many_facts(3, 2))
        return organize_person_plan(self.package, {}, {'name': 'Example person'}, 'English',
                                    self.responses, lambda value, name: self.saved.update({name: copy.deepcopy(value)}))

    def test_memberships_precede_stages_and_summary(self):
        result = self.run_plan()
        phases = [r['task']['phase'] for r in self.responses.calls]
        self.assertEqual(phases, ['EventLayout', 'Placement', 'EventStructure', 'Relations'])
        self.assertNotIn('LayoutReview', phases)
        self.assertNotIn('Relevance', phases)
        task = next(r['task'] for r in self.responses.calls if r['task']['phase'] == 'EventStructure')
        self.assertEqual({r['activity_id'] for r in task['memberships']}, {'A1', 'A2', 'A3'})
        self.assertNotIn('summary', task['event'])
        output, report = apply_organization(self.package, result)
        self.assertEqual(output['activity'], self.package['activity'])
        self.assertEqual(len(output['event_activity']), 3)

    def test_shared_activity_is_one_fact_with_distinct_detail_projections(self):
        result = self.run_plan(responses=CanonicalResponses(shared=True))
        output, _ = apply_organization(self.package, result)
        self.assertEqual(len(output['activity']), 3)
        self.assertEqual(len([r for r in output['event_activity'] if r['activity_id'] == 'A1']), 2)
        self.assertEqual([r['detail_mode'] for r in output['event_activity'] if r['activity_id'] == 'A1'], ['selected', 'selected'])

    def test_bad_detail_selection_repairs_only_its_activity(self):
        def transform(task, result, name):
            if task['phase'] == 'Placement' and not name.endswith('Repair'):
                result['memberships'][1]['detail_indices'] = [800]
        result = self.run_plan(responses=CanonicalResponses(transform))
        repair = next(r['task'] for r in self.responses.calls if r['name'].endswith('Repair'))
        self.assertEqual(repair['assigned_ids'], ['A2'])
        self.assertEqual({r['activity_id'] for r in result['memberships']}, {'A1', 'A2', 'A3'})
        self.assertEqual(result['pending_activity_ids'], [])

    def test_failed_targeted_placement_keeps_other_members(self):
        def transform(task, result, name):
            if task['phase'] == 'Placement':
                for row in result['memberships']:
                    if row['activity_id'] == 'A2':
                        row['detail_indices'] = [800]
        result = self.run_plan(responses=CanonicalResponses(transform))
        self.assertEqual({r['activity_id'] for r in result['memberships']}, {'A1', 'A3'})
        self.assertEqual(result['pending_activity_ids'], ['A2'])
        output, report = apply_organization(self.package, result)
        self.assertEqual(len(output['activity']), 3)
        self.assertEqual(report['status'], 'partial_organization_requires_review')

    def test_occurrence_problem_does_not_mark_peers_pending(self):
        def transform(task, result, name):
            if task['phase'] == 'Placement' and 'O1' in task['relevance_ids']:
                result['occurrence_issues'] = [{'occurrence_id': 'O1', 'reason': 'Two distinct scenes require review.'}]
        result = self.run_plan(responses=CanonicalResponses(transform))
        self.assertEqual(result['pending_occurrence_ids'], ['O1'])
        self.assertEqual(len(result['memberships']), 3)
        self.assertNotEqual(result['occurrence_relevance'][1]['subject_relevance']['value'], 'Person relevance review pending.')

    def test_event_summary_failure_is_local_and_keeps_memberships(self):
        def transform(task, result, name):
            if task['phase'] == 'EventStructure' and task['event']['event_id'] == 'E2':
                raise RuntimeError('provider unavailable')
        result = self.run_plan(responses=CanonicalResponses(transform, shared=True))
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(len(result['memberships']), 4)
        self.assertEqual(self.saved['PersonOrganizationIsolation']['pending_events'], ['E2'])
        self.assertTrue(any(r['event_id'] == 'E' for r in result['stages']))

    def test_layout_context_does_not_repeat_source_documents(self):
        self.run_plan()
        self.assertEqual(self.responses.calls[0]['request']['facts']['source_document'], [])
        self.assertEqual(len(self.responses.calls[0]['request']['global_activity_index']), 3)

    def test_context_keeps_whole_related_source_and_omits_unrelated_source(self):
        package = bind_test_evidence(facts())
        package['source_document'].append({'document_id': 'UNRELATED', 'content': 'An unrelated report in full.'})
        request = scoped_organization_request(package, {'name': 'Example person'}, ['A'])
        docs = request['facts']['source_document']
        self.assertEqual([r['document_id'] for r in docs], ['DOC'])
        self.assertEqual(docs[0]['content'], package['source_document'][0]['content'])
        self.assertEqual(len(request['source_catalog']), 2)

    def test_direction_uses_roles_and_directional_candidates_are_reviewed(self):
        package = many_facts(2, 2)
        package['action'][0]['action_type'] = 'Propose replacing chairman'
        package['action'][1]['action_type'] = 'Vote against replacement proposal'
        def transform(task, result, name):
            if task['phase'] == 'Relations':
                result['candidates'] = [{'relation': {'from_activity_id': 'A1', 'to_activity_id': 'A2',
                    'relation_type': 'responds_to', 'basis': 'source', 'description': vf('The vote responds to the proposal.')},
                    'assessment': {'supported': True, 'evidence_scope': 'relation', 'from_role': 'proposal',
                        'to_role': 'response', 'reason': 'The vote decides the proposal.', 'needs_review': False,
                        'duplicate_fact': False, 'response_activity_id': 'A2', 'trigger_activity_id': 'A1'}}]
        result = self.run_plan(package, CanonicalResponses(transform))
        self.assertEqual([(r['from_activity_id'], r['to_activity_id']) for r in result['activity_relations']], [('A2', 'A1')])
        self.assertEqual(sum(r['task']['phase'] == 'RelationsReview' for r in self.responses.calls), 1)

    def test_endpoint_only_quote_cannot_accept_a_semantic_edge(self):
        package = many_facts(2, 2)
        package['action'][1]['action_type'] = 'Different action'
        def transform(task, result, name):
            if task['phase'] == 'Relations':
                result['candidates'] = [{'relation': {'from_activity_id': 'A1', 'to_activity_id': 'A2',
                    'relation_type': 'context_for', 'basis': 'source', 'description': vf('Context.')},
                    'assessment': {'supported': True, 'evidence_scope': 'endpoints_only', 'from_role': 'earlier',
                        'to_role': 'later', 'reason': 'Both appear in source.', 'needs_review': False, 'duplicate_fact': False}}]
        result = self.run_plan(package, CanonicalResponses(transform))
        self.assertEqual(result['activity_relations'], [])


class CanonicalOrganizationCacheTest(unittest.TestCase):
    def user(self, version=6, instructions='First semantic rule'):
        return json.dumps({'organization_semantic_version': version, 'facts': {'activity': [], 'activity_detail': []}}) + TASK_SEPARATOR + json.dumps({'phase': 'EventLayout', 'instructions': instructions, 'response_schema': {}})

    def test_semantic_version_and_instructions_invalidate_cache(self):
        self.assertNotEqual(request_identity(self.user()), request_identity(self.user(version=7)))
        self.assertNotEqual(request_identity(self.user()), request_identity(self.user(instructions='Fixed semantic rule')))

    def test_reused_result_survives_another_recovery_without_original_trace(self):
        saved = {}
        builder = SimpleNamespace(_organization_resume_artifacts={}, _organization_resume_history=[], _call_records=[],
            _save_agent_result=lambda value, name: saved.update({name+'-Result.json': json.dumps(value).encode()}),
            _infer_and_parse_json=lambda *args, **kwargs: {'answer': 1})
        first = OrganizationResume(builder)
        first.infer('system', self.user(), 'PersonOrganization-EventLayout', lambda value: None)
        builder._organization_resume_artifacts = copy.deepcopy(saved)
        builder._infer_and_parse_json = lambda *args, **kwargs: self.fail('Unexpected new model call')
        second = OrganizationResume(builder)
        self.assertEqual(second.infer('system', self.user(), 'PersonOrganization-EventLayout', lambda value: None), {'answer': 1})
        builder._organization_resume_artifacts = copy.deepcopy(saved)
        third = OrganizationResume(builder)
        self.assertEqual(third.infer('system', self.user(), 'PersonOrganization-EventLayout', lambda value: None), {'answer': 1})

    def test_pending_repair_is_retried_after_resuming_accepted_placement_rows(self):
        package = bind_test_evidence(many_facts(3, 2))
        def damage(task, result, name):
            if task['phase'] == 'Placement':
                for row in result['memberships']:
                    if row['activity_id'] == 'A2':
                        row['detail_indices'] = [800]
        saved = {}
        responses = CanonicalResponses(damage)
        builder = SimpleNamespace(_organization_resume_artifacts={}, _organization_resume_history=[], _call_records=[],
            _save_agent_result=lambda value, name: saved.update({name+'-Result.json': json.dumps(value).encode()}))
        builder._infer_and_parse_json = lambda agent, system, user, kwargs, name, validator: responses(system, user, name, validator)
        first = organize_person_plan(package, {}, {}, 'English', OrganizationResume(builder).infer, lambda *args: None)
        self.assertEqual(first['pending_activity_ids'], ['A2'])
        builder._organization_resume_artifacts = copy.deepcopy(saved)
        responses = CanonicalResponses()
        second = organize_person_plan(package, {}, {}, 'English', OrganizationResume(builder).infer, lambda *args: None)
        self.assertEqual(second['pending_activity_ids'], [])
        placement_calls = [c for c in responses.calls if c['task']['phase'] == 'Placement']
        self.assertEqual(len(placement_calls), 1)
        self.assertTrue(placement_calls[0]['name'].endswith('Repair'))
        self.assertEqual(placement_calls[0]['task']['assigned_ids'], ['A2'])

    def test_stable_detail_reference_survives_index_reordering(self):
        package = bind_test_evidence(many_facts(2, 2))
        before = detail_reference_catalog(package)
        ref = before['A1'][0]['detail_ref']
        package['activity_detail'][0]['detail_index'] = 13
        after = detail_reference_catalog(package)
        self.assertEqual(after['A1'][0]['detail_ref'], ref)
        self.assertEqual(resolve_detail_references({'event_id': 'E', 'activity_id': 'A1', 'detail_refs': [ref]}, after)
                         ['detail_indices'], [13])
        with self.assertRaisesRegex(ValueError, 'Unknown stable'):
            resolve_detail_references({'event_id': 'E', 'activity_id': 'A2', 'detail_refs': [ref]}, after)


if __name__ == '__main__':
    unittest.main()
