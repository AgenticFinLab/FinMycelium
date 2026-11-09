"""Relation proposals use canonical IDs and local semantic review, not blanket reruns."""
import copy
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.sparse_build.organization_batches import organize_person_plan
from finmy.builder.sparse_build.person_organization import apply_organization
from test_person_canonical_organization import CanonicalResponses, bind_test_evidence
from test_sparse_organization_batches import many_facts
from test_sparse_person_organization import vf


def relation(start='A1', end='A21', kind='context_for'):
    return {'from_activity_id': start, 'to_activity_id': end, 'relation_type': kind,
            'basis': 'source', 'description': vf('The source supports this relation.')}


def candidate(start='A1', end='A2', kind='context_for', **assessment):
    return {'relation': relation(start, end, kind), 'assessment': {
        'supported': True, 'evidence_scope': 'relation', 'from_role': 'documented context',
        'to_role': 'contextualized action', 'reason': 'The source connects these facts.',
        'needs_review': False, 'duplicate_fact': False, **assessment}}


class SparseRelationCandidatesTest(unittest.TestCase):
    def run_plan(self, proposals, *, mutate_review=None, duplicate=False):
        self.package = many_facts(3, 2)
        for index, row in enumerate(self.package['action']):
            row['action_type'] = 'Same action' if duplicate else f'Documented action {index+1}'
        if duplicate:
            for row in self.package['activity_detail']:
                row['value'] = 'Same documented action detail.'
        bind_test_evidence(self.package)
        self.before = copy.deepcopy(self.package)
        self.saved = {}
        def transform(task, result, name):
            if task['phase'] == 'Relations':
                result['candidates'] = copy.deepcopy(proposals)
            elif task['phase'] == 'RelationsReview' and mutate_review:
                mutate_review(task, result)
        self.responses = CanonicalResponses(transform)
        self.result = organize_person_plan(self.package, {}, {'name': 'Example person'}, 'English',
            self.responses, lambda value, name: self.saved.update({name: copy.deepcopy(value)}))
        return self.result

    def test_supported_context_relation_does_not_trigger_unconditional_second_pass(self):
        result = self.run_plan([candidate()])
        self.assertEqual(len(result['activity_relations']), 1)
        self.assertNotIn('RelationsReview', [r['task']['phase'] for r in self.responses.calls])
        self.assertEqual(self.package, self.before)

    def test_invalid_candidate_is_isolated_from_accepted_neighbor(self):
        mutations = {
            'unknown_target': lambda c: c['relation'].update(to_activity_id='UNKNOWN'),
            'self_link': lambda c: c['relation'].update(to_activity_id='A1'),
            'missing_quote': lambda c: c['relation']['description'].update(evidence_source_contents=[]),
            'unbound_quote': lambda c: c['relation']['description'].update(evidence_source_contents=['Not present.']),
            'missing_assessment': lambda c: c.pop('assessment'),
            'endpoint_only': lambda c: c['assessment'].update(evidence_scope='endpoints_only'),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                broken = candidate()
                mutate(broken)
                result = self.run_plan([broken, candidate('A2', 'A3')])
                self.assertEqual([(r['from_activity_id'], r['to_activity_id']) for r in result['activity_relations']], [('A2', 'A3')])
                self.assertTrue(self.saved['PersonOrganization-RelationCandidates']['rejected_attempts'])
                output, _ = apply_organization(self.package, result)
                self.assertEqual(output['action'], self.before['action'])

    def test_duplicate_facts_are_not_hidden_by_an_overlap_edge(self):
        result = self.run_plan([candidate(kind='overlaps')], duplicate=True)
        self.assertEqual(result['activity_relations'], [])
        audit = self.saved['PersonOrganization-RelationCandidates']['rejected_attempts']
        self.assertIn('upstream identity review', audit[0]['reason'])
        self.assertEqual(self.package, self.before)

    def test_explicit_semantic_ambiguity_gets_targeted_review(self):
        result = self.run_plan([candidate(needs_review=True)])
        self.assertEqual(len(result['activity_relations']), 1)
        reviews = [r for r in self.responses.calls if r['task']['phase'] == 'RelationsReview']
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(reviews[0]['task']['candidates']), 1)

    def test_response_direction_is_assembled_from_reviewed_roles(self):
        proposal = candidate(kind='responds_to', response_activity_id='A2', trigger_activity_id='A1')
        result = self.run_plan([proposal])
        self.assertEqual([(r['from_activity_id'], r['to_activity_id']) for r in result['activity_relations']], [('A2', 'A1')])
        self.assertIn('RelationsReview', [r['task']['phase'] for r in self.responses.calls])

    def test_directional_review_without_roles_is_withheld(self):
        def remove_roles(task, result):
            for row in result['decisions']:
                row.pop('response_activity_id', None)
                row.pop('trigger_activity_id', None)
        result = self.run_plan([candidate(kind='responds_to', response_activity_id='A2', trigger_activity_id='A1')], mutate_review=remove_roles)
        self.assertEqual(result['activity_relations'], [])
        self.assertTrue(self.saved['PersonOrganization-RelationCandidates']['pending_candidate_ids'])

    def test_unavailable_review_preserves_graph_and_accepted_unambiguous_edges(self):
        def unavailable(task, result):
            raise RuntimeError('Provider unavailable')
        result = self.run_plan([candidate('A1', 'A2'), candidate('A2', 'A3', needs_review=True)], mutate_review=unavailable)
        self.assertEqual([(r['from_activity_id'], r['to_activity_id']) for r in result['activity_relations']], [('A1', 'A2')])
        output, _ = apply_organization(self.package, result)
        self.assertEqual(output['activity'], self.before['activity'])
        self.assertEqual(self.saved['PersonOrganization-RelationCandidates']['status'], 'partial_requires_content_review')

    def test_conflicting_review_decisions_do_not_silently_choose_a_variant(self):
        first, second = candidate(needs_review=True), candidate(needs_review=True)
        second['relation']['description']['value'] = 'Alternative relation explanation.'
        def reject_conflict(task, result):
            # The reviewer sees all variants for one canonical edge together.
            self.assertEqual(len(task['candidates']), 2)
            for i, row in enumerate(result['decisions']):
                row['decision'] = 'accept' if i == 0 else 'reject'
        result = self.run_plan([first, second], mutate_review=reject_conflict)
        self.assertEqual(len(result['activity_relations']), 1)
        self.assertEqual(result['activity_relations'][0]['description']['value'], first['relation']['description']['value'])

    def test_two_accepted_variants_are_withheld_instead_of_choosing_the_first(self):
        first, second = candidate(needs_review=True), candidate(needs_review=True)
        second['relation']['description']['value'] = 'A conflicting explanation for the same edge.'
        result = self.run_plan([first, second])
        self.assertEqual(result['activity_relations'], [])

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
