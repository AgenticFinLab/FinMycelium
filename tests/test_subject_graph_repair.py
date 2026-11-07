import copy
import unittest

from finmy.subject_graph.repair import apply_graph_patch


class LocalRepairTests(unittest.TestCase):
    def setUp(self):
        self.graph = {'subject_id': 'person', 'events': [
            {'event_id': 'E1', 'actions': [{'actor_id': 'wrong'}],
             'descriptions': ['a', 'b', 'c'], 'extra': 'unused', 'attributes': {'a/b~c': 1}},
            {'event_id': 'E2', 'details': 'correct' * 10000}], 'entities': [], 'relations': []}
        self.original = copy.deepcopy(self.graph)
        self.errors = [{'path': '/events/0/actions/0/actor_id', 'message': 'bad reference'}]

    def apply(self, patches):
        return apply_graph_patch(self.graph, {'patches': patches}, self.errors)

    def test_one_small_edit_preserves_large_correct_graph(self):
        patch = {'op': 'replace', 'path': '/events/0/actions/0/actor_id', 'value': 'person'}
        fixed = self.apply([patch])
        self.assertEqual(fixed['events'][0]['actions'][0]['actor_id'], 'person')
        self.assertEqual(fixed['events'][1], self.original['events'][1])
        self.assertEqual(self.graph, self.original)

    def test_add_remove_and_escaped_pointer(self):
        fixed = self.apply([
            {'op': 'add', 'path': '/events/0/title', 'value': {'value': 'supported'}},
            {'op': 'remove', 'path': '/events/0/extra'},
            {'op': 'replace', 'path': '/events/0/attributes/a~1b~0c', 'value': 2}])
        self.assertNotIn('extra', fixed['events'][0])
        self.assertEqual(fixed['events'][0]['attributes']['a/b~c'], 2)
        self.assertEqual(self.graph, self.original)

    def test_array_edits_use_original_indices(self):
        fixed = self.apply([
            {'op': 'remove', 'path': '/events/0/descriptions/0'},
            {'op': 'remove', 'path': '/events/0/descriptions/1'},
            {'op': 'replace', 'path': '/events/0/descriptions/2', 'value': 'kept'}])
        self.assertEqual(fixed['events'][0]['descriptions'], ['kept'])

    def test_invalid_batch_is_atomic(self):
        for path in ('', '/', '/events', '/events/0', '/events/1/details', '/subject_id',
                     '/events/0/descriptions/99', '/events/0/descriptions/01', '/events/0/bad~2key'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.apply([{'op': 'replace', 'path': '/events/0/actions/0/actor_id', 'value': 'person'},
                            {'op': 'replace', 'path': path, 'value': 'bad'}])
            self.assertEqual(self.graph, self.original)

    def test_overlapping_paths_and_whole_graph_are_rejected(self):
        with self.assertRaises(ValueError):
            self.apply([{'op': 'replace', 'path': '/events/0/actions', 'value': []},
                        {'op': 'replace', 'path': '/events/0/actions/0/actor_id', 'value': 'person'}])
        with self.assertRaises(ValueError):
            apply_graph_patch(self.graph, self.graph, self.errors)

    def test_final_validation_rejects_new_dangling_reference(self):
        from finmy.subject_graph.validation import validate_subject_graph
        from test_subject_graph_visualizer import fixture as graph_fixture
        graph = graph_fixture()
        self.assertTrue(validate_subject_graph(graph)['valid'])
        errors = [{'path': '/events/0/actions/0/actor_id', 'message': 'test'}]
        fixed = apply_graph_patch(graph, {'patches': [{'op': 'replace',
                                  'path': '/events/0/actions/0/actor_id',
                                  'value': 'unregistered_actor'}]}, errors)
        report = validate_subject_graph(fixed)
        self.assertFalse(report['valid'])
        self.assertTrue(any(e['path'] == '/events/0/actions/0/actor_id' for e in report['errors']))
