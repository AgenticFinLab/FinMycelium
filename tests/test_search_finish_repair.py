"""Real native finalization, with local originals and no provider calls."""
import json
from pathlib import Path
import tempfile
import unittest

from finmy.search.agent import context_for, run_agent
from finmy.search.handoff import prepare_complete_sources, SourceSelectionError
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


class SearchFinishRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = SearchState(self.root, 'event', task={
            'target_type': 'event', 'target_name': 'Ownership changes',
            'query_text': 'Trace the purchase and later ownership changes.'},
            config=SearchConfig(providers=['bocha', 'baidu'], max_model_calls=12))
        self.store = SourceStore(self.state)
        self.tools = SearchTools(self.state,
            transport=lambda *args: self.fail('No live search expected'),
            fetcher=lambda *args: self.fail('No live fetch expected'))

    def source(self, name, body='A purchase was disclosed, subject to closing.', reviewed=True,
               kind='txt'):
        sid = self.store.register('https://example.test/' + name, title=name)
        if body is not None:
            self.store.save_raw(sid, body.encode(), kind)
            if reviewed:
                self.store.read(sid)
        return sid

    def finalize(self, model, already_spent=10):
        self.state.data['usage']['model'] = already_spent
        self.state.save()
        run_agent(self.state, self.tools, model)

    def test_final_context_exposes_only_inspected_usable_ids(self):
        good = self.source('filing')
        unread = self.source('unread', reviewed=False)
        blocked = self.source('verification',
                              '<h1>Client Challenge</h1><p>A required part of this site couldn’t load.</p>',
                              kind='html')
        self.state.data['usage']['model'] = 10
        context = context_for(self.state)
        self.assertEqual(context['eligible_source_ids'], [good])
        self.assertEqual([row['source_id'] for row in context['sources']], [good])
        self.assertNotIn(unread, context['eligible_source_ids'])
        self.assertNotIn(blocked, context['eligible_source_ids'])

    def test_invalid_finish_feedback_instructs_drop_and_resubmit_not_read(self):
        good, unread = self.source('filing'), self.source('unread', body=None)
        contexts = []
        def model(context):
            contexts.append(context)
            return {'action': 'finish', 'source_ids': [good, unread] if len(contexts) == 1 else [good],
                    'reason': 'supported', 'gaps': ['Exact closing date remains unconfirmed.']}
        self.finalize(model)
        feedback = contexts[1]['feedback']
        self.assertEqual(feedback['invalid_source_ids'], {unread: 'not_inspected'})
        self.assertEqual(feedback['eligible_source_ids'], [good])
        self.assertEqual(feedback['next_action'], 'finish')
        self.assertIn('Do not read or search', feedback['repair'])
        self.assertEqual(self.state.data['status'], 'finished')
        self.assertFalse((self.state.run_dir / 'handoff_repair.json').exists())

    def test_exhausted_oxy_style_finish_preserves_only_model_selected_valid_subset(self):
        good = self.source('selected-filing')
        self.source('not-selected', 'A different source was inspected but never chosen.')
        unread = self.source('unread', body=None)
        calls = []
        def model(context):
            calls.append(context)
            if len(calls) == 1:
                return {'action': 'finish', 'source_ids': [good, unread], 'reason': 'supported',
                        'gaps': ['The holding rationale remains incomplete.']}
            return {'action': 'read_source', 'source': unread}
        self.finalize(model)
        self.assertEqual(self.state.data['usage']['model'], 12)
        self.assertEqual(self.state.data['status'], 'insufficient')
        self.assertEqual(self.state.data['stop_reason'], 'partial_handoff_recovered')
        repair = json.loads((self.state.run_dir / 'handoff_repair.json').read_text())
        self.assertEqual(repair['retained_source_ids'], [good])
        self.assertEqual(repair['rejected_source_ids'], {unread: 'not_inspected'})
        self.assertFalse(repair['coverage_complete'])
        payload = json.loads((self.state.run_dir / 'builder_input.json').read_text())
        self.assertEqual([row['raw_data_id'] for row in payload['samples']], [good])
        selection = json.loads((self.state.run_dir / 'selection.json').read_text())
        self.assertEqual(selection['reason'], 'insufficient')
        self.assertIn('The holding rationale remains incomplete.', selection['gaps'])

    def test_all_unread_selection_cannot_create_recovered_handoff(self):
        unread = self.source('unread', body=None)
        self.finalize(lambda context: {'action': 'finish', 'source_ids': [unread],
                                      'reason': 'supported', 'gaps': []})
        self.assertEqual(self.state.data['status'], 'limit')
        self.assertFalse((self.state.run_dir / 'builder_input.json').exists())

    def test_insufficient_reason_preserves_valid_partial_material(self):
        good = self.source('partial-filing')
        self.finalize(lambda context: {'action': 'finish', 'source_ids': [good],
                       'reason': 'insufficient', 'gaps': ['Later developments not documented.']})
        self.assertEqual(self.state.data['status'], 'insufficient')
        payload = json.loads((self.state.run_dir / 'builder_input.json').read_text())
        self.assertTrue(payload['samples'])
        self.assertFalse((self.state.run_dir / 'handoff_repair.json').exists())

    def test_unknown_id_diagnostics_include_all_invalid_selections(self):
        good = self.source('filing')
        unread = self.source('unread', body=None)
        with self.assertRaises(SourceSelectionError) as error:
            prepare_complete_sources(self.state, [good, 'invented-id', unread])
        self.assertEqual(error.exception.invalid_source_ids,
                         {'invented-id': 'unknown_source', unread: 'not_inspected'})
        self.assertEqual(error.exception.eligible_source_ids, [good])

    def test_evidence_integrity_and_read_offsets_are_not_relaxed(self):
        good = self.source('filing')
        entry = self.state.data['sources'][good]
        entry['read_ranges'][0]['end'] += 100
        with self.assertRaisesRegex(ValueError, 'Invalid inspected source range'):
            prepare_complete_sources(self.state, [good])
        entry['read_ranges'][0]['end'] -= 100
        (self.state.root / 'sources' / good / entry['version'] / 'raw').write_bytes(b'Changed')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            context_for(self.state, finalize=True)

    def test_query_limit_feedback_reports_actual_units_without_truncation(self):
        good = self.source('filing')
        contexts = []
        query = 'A' * 73
        def model(context):
            contexts.append(context)
            if len(contexts) == 1:
                return {'action': 'search', 'query': query}
            return {'action': 'finish', 'source_ids': [good], 'reason': 'low_gain', 'gaps': []}
        self.finalize(model, already_spent=0)
        self.assertEqual(contexts[1]['feedback']['query_units'], 73)
        self.assertEqual(contexts[1]['feedback']['query_max_units'], 72)
        self.assertEqual(self.state.data['usage']['search'], 0)
        trace = (self.state.run_dir / 'trace.jsonl').read_text()
        self.assertIn(query, trace)

    def test_source_pool_refresh_precedes_context_and_requires_local_inspection(self):
        imported = []
        def refresh():
            if not imported:
                imported.append(self.source('shared-candidate', reviewed=False))
        self.tools.refresh_shared_sources = refresh
        contexts = []
        def model(context):
            contexts.append(context)
            if len(contexts) == 1:
                self.assertEqual(context['sources'][0]['source_id'], imported[0])
                self.assertEqual(context['eligible_source_ids'], [])
                return {'action': 'read_source', 'source': imported[0]}
            return {'action': 'finish', 'source_ids': imported, 'reason': 'supported', 'gaps': []}
        self.finalize(model, already_spent=0)
        self.assertEqual(self.state.data['status'], 'finished')
        self.assertEqual(contexts[1]['eligible_source_ids'], imported)


if __name__ == '__main__':
    unittest.main()
