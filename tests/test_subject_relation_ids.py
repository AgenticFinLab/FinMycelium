"""Relation identifiers are local bookkeeping, not grounds to discard a valid graph."""
import copy
import unittest

import test_subject_graph_builder as fixtures
from finmy.subject_graph.build import _unique_record_ids, run_subject_build


def relation(identifier):
    vf = fixtures.vf
    return {'relation_id': identifier, 'from_entity_id': 'buffett', 'to_entity_id': 'berkshire',
            'relation_type': vf('Associated with'), 'valid_from': vf('unknown', None),
            'valid_to': vf('unknown', None), 'event_ids': []}


class RelationIdTests(unittest.TestCase):
    def test_reserves_existing_ids_and_changes_only_collisions(self):
        graph = {'relations': [relation('REL3'), relation('REL3'), relation('REL3_2'), relation('REL3')]}
        original = copy.deepcopy(graph)
        fixed, changes = _unique_record_ids(graph)
        self.assertEqual([r['relation_id'] for r in fixed['relations']], ['REL3', 'REL3_3', 'REL3_2', 'REL3_4'])
        self.assertEqual(graph, original)
        self.assertEqual(len(changes), 2)
        for before, after in zip(graph['relations'], fixed['relations']):
            self.assertEqual({k:v for k,v in before.items() if k != 'relation_id'},
                             {k:v for k,v in after.items() if k != 'relation_id'})
        self.assertEqual(_unique_record_ids(fixed), (fixed, []))

    def test_duplicate_relations_and_unmatched_title_do_not_discard_graph(self):
        build = fixtures.NativeBuildTests(); build.setUp()
        build.events[1]['title']['evidence_source_contents'] = ['Quote absent from supplied text']
        def complete(name, prompt, payload):
            answer = build.complete(name, prompt, payload)
            if name == 'SubjectEventReconstructor':
                answer['relations'] = [relation('REL3'), relation('REL4')]
            return answer
        graph, state, report = run_subject_build(fixtures.input_(), fixtures.config(), complete, build.save)
        self.assertTrue(report['valid'], report)
        self.assertEqual([r['relation_id'] for r in graph['relations']], ['REL3', 'REL4', 'REL3_2', 'REL4_2'])
        self.assertEqual(graph['events'][1]['title']['evidence_status'], 'needs_review')
        self.assertEqual(graph['events'][1]['title']['evidence_source_contents'], ['Quote absent from supplied text'])
        self.assertEqual([r['relation_id'] for r in build.saved['RawSubjectGraph']['relations']], ['REL3', 'REL4']*2)
        self.assertEqual(len(build.saved['subject_record_id_normalization']), 2)
        self.assertNotIn('SubjectGraphRepair', state['agent_executed'])

    def test_unrelated_reference_errors_still_block(self):
        build = fixtures.NativeBuildTests(); build.setUp()
        build.plan['relations'] = [relation('REL3'), relation('REL3')]
        build.plan['relations'][1]['to_entity_id'] = 'missing_entity'
        with self.assertRaisesRegex(ValueError, 'failed validation'):
            run_subject_build(fixtures.input_(), fixtures.config(), build.complete, build.save)


if __name__ == '__main__':
    unittest.main()
