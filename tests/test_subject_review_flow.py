"""Review envelope, temporal assignment and duplicate-speech integration regressions."""
import copy
import unittest

from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.coverage_review import apply_statement_merges, find_statement_duplicates
from finmy.subject_graph.event_sources import restrict_event_evidence
from finmy.subject_graph.repair import apply_graph_patch
from finmy.subject_graph.validation import validate_subject_graph
import test_subject_graph_builder as fixtures
from test_subject_graph_builder import config, input_, vf, SOURCE


class ReviewFlowTests(unittest.TestCase):
    setUp = fixtures.NativeBuildTests.setUp
    save = fixtures.NativeBuildTests.save
    complete = fixtures.NativeBuildTests.complete

    def review(self, response):
        def complete(name, system, payload):
            if name == 'SubjectEventReviewer' and payload['TargetEvent']['event_id'] == 'E1':
                return response
            return self.complete(name, system, payload)
        return run_subject_build(input_(), config(), complete, self.save)[0]

    def correction(self):
        return {'reason': 'Qualify the interpretation', 'patches': [
            {'op': 'replace', 'path': '/event/actions/E1_A1/details/0',
             'value': vf('Expressed a view; no personal purchase is established')}]}

    def test_missing_empty_lists_and_singleton_correction_are_accepted(self):
        response = {'corrections': self.correction()}
        original = copy.deepcopy(response)
        graph = self.review(response)
        self.assertIn('no personal purchase', graph['events'][0]['actions'][0]['details'][0]['value'])
        self.assertEqual(response, original)
        self.assertEqual(len(self.saved['subject_event_detail_review'][0]['corrections']['accepted']), 1)

    def test_singleton_addition_is_accepted(self):
        graph = self.review({'event_additions': {'event_id': 'E1', 'action_details': [
            {'action_id': 'E1_A1', 'details': [vf('Explained his view of the company')]}]}})
        self.assertEqual(len(graph['events'][0]['actions'][0]['details']), 2)

    def test_invalid_addition_does_not_discard_valid_correction(self):
        graph = self.review({'corrections': [self.correction()], 'event_additions': 'invalid'})
        detail = self.saved['subject_event_detail_review'][0]
        self.assertIn('no personal purchase', graph['events'][0]['actions'][0]['details'][0]['value'])
        self.assertIn('event_additions must be', detail['error'])
        self.assertEqual(len(detail['corrections']['accepted']), 1)

    def test_invalid_corrections_do_not_discard_valid_addition(self):
        graph = self.review({'corrections': 'invalid', 'event_additions': {
            'event_id': 'E1', 'descriptions': [vf('A documented public statement')]}})
        self.assertEqual(len(graph['events'][0]['descriptions']), 2)
        self.assertIn('corrections must be', self.saved['subject_event_detail_review'][0]['corrections']['error'])

    def test_outside_plan_is_dated_background_before_detail_calls(self):
        self.plan['events'][0]['start_time'] = vf('2021-10')
        self.plan['events'][0]['end_time'] = vf('2021-11')
        graph, _, report = run_subject_build(input_(), config(), self.complete, self.save)
        self.assertTrue(report['valid'], report)
        self.assertEqual([e['event_id'] for e in graph['events']], ['E2'])
        self.assertTrue(any('2021-10' in d['value'] for d in graph['descriptions']))
        self.assertFalse(any(payload.get('TargetEvent', {}).get('event_id') == 'E1'
                             for _, _, payload in self.calls))
        self.assertEqual(self.saved['subject_scope_review'][0]['event_id'], 'E1')

    def test_corrected_outside_event_becomes_background_instead_of_retaining_wrong_date(self):
        graph = self.review({'corrections': [{'reason': 'The described purchase was earlier', 'patches': [
            {'op': 'replace', 'path': '/event/start_time', 'value': vf('2021-10')},
            {'op': 'replace', 'path': '/event/end_time', 'value': vf('2021-11')}]}]})
        self.assertEqual([e['event_id'] for e in graph['events']], ['E2'])
        self.assertTrue(any('2021-10' in d['value'] for d in graph['descriptions']))
        self.assertTrue(self.saved['subject_event_detail_review'][0]['corrections']['accepted'])
        self.assertTrue(self.saved['subject_scope_review'])

    def test_later_participation_is_excluded_with_dependents_not_redated_unknown(self):
        graph = run_subject_build(input_(), config(), self.complete, self.save)[0]
        event = graph['events'][1]
        later = copy.deepcopy(graph['events'][0]['participations'][0])
        later.update(participation_id='E2_P2', start_time=vf('2023-08'), end_time=vf('2023-08'))
        event['participations'].append(later)
        act = copy.deepcopy(graph['events'][0]['actions'][0])
        act.update(action_id='E2_A2', timestamp=vf('unknown', None))
        event['actions'].append(act)
        sources = [{'source_id': 'S1', 'content': SOURCE}]
        result, records = restrict_event_evidence(graph, {e['event_id']: e for e in graph['events']},
                                                  {'E1': sources, 'E2': sources}, sources)
        self.assertEqual([p['entity_id'] for p in result['events'][1]['participations']], ['berkshire'])
        self.assertEqual([a['action_id'] for a in result['events'][1]['actions']], ['E2_A1'])
        archived = next(r['record'] for r in records if r['path'].endswith('/participations/1'))
        self.assertEqual(archived['start_time']['value'], '2023-08')


class StatementMergeTests(unittest.TestCase):
    def setUp(self):
        build = fixtures.NativeBuildTests(); build.setUp()
        self.graph = run_subject_build(input_(), config(), build.complete, build.save)[0]
        self.sources = [{'source_id': 'S1', 'content': SOURCE}]
        self.allocation = {'E1': self.sources, 'E2': self.sources}
        meeting, investment = self.graph['events']
        meeting['start_time'] = meeting['end_time'] = vf('2023-05-06')
        meeting['title'] = vf('Annual meeting')
        for p in meeting['participations']:
            p['start_time'] = p['end_time'] = vf('2023-05-06')
        action = meeting['actions'][0]
        action['timestamp'] = vf('2023-05-06')
        action['action_type'] = vf('Explained investment rationale')
        investment['start_time'] = vf('2023-01')
        duplicate = copy.deepcopy(action)
        duplicate['action_id'] = 'E2_A2'
        duplicate['details'] = [vf('Reported comparison, actual trade price is unspecified')]
        investment['actions'].append(duplicate)
        participant = copy.deepcopy(meeting['participations'][0])
        participant['participation_id'] = 'E2_P2'
        investment['participations'].append(participant)
        self.proposal = {'keep_event_id': 'E1', 'keep_action_id': 'E1_A1',
                         'remove_event_id': 'E2', 'remove_action_id': 'E2_A2',
                         'reason': 'Same utterance occurred at the annual meeting'}

    def merge(self, proposal=None):
        return apply_statement_merges(self.graph, [proposal or self.proposal], self.allocation, self.sources)

    def test_same_speech_merges_details_and_preserves_investment(self):
        original = copy.deepcopy(self.graph)
        result, _, report = self.merge()
        self.assertEqual(len(report['accepted']), 1, report)
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(result['events'][1]['actions'], original['events'][1]['actions'][:1])
        self.assertEqual(result['events'][1]['transactions'], original['events'][1]['transactions'])
        self.assertEqual(len(result['events'][0]['actions'][0]['details']), 2)
        self.assertEqual(find_statement_duplicates(result), [])
        self.assertTrue(validate_subject_graph(result, [SOURCE])['valid'])
        self.assertEqual(self.graph, original)

    def test_exact_timestamp_inside_same_day_is_supported(self):
        for event in self.graph['events']:
            for action in event['actions']:
                if action['actor_id'] == 'buffett':
                    action['timestamp'] = vf('2023-05-06T10:00:00Z')
        self.assertTrue(self.merge()[2]['accepted'])

    def test_different_date_same_quote_is_not_merged(self):
        self.graph['events'][1]['actions'][-1]['timestamp'] = vf('2023-05-07')
        result, _, report = self.merge()
        self.assertEqual(result, self.graph)
        self.assertTrue(report['rejected'])

    def test_broad_investment_event_cannot_be_selected_as_keeper(self):
        proposal = {**self.proposal, 'keep_event_id': 'E2', 'keep_action_id': 'E2_A2',
                    'remove_event_id': 'E1', 'remove_action_id': 'E1_A1'}
        result, _, report = self.merge(proposal)
        self.assertEqual(result, self.graph)
        self.assertIn('actual day', report['rejected'][0]['reason'])

    def test_bad_addition_does_not_block_global_statement_merge(self):
        build = fixtures.NativeBuildTests(); build.setUp()
        build.events = copy.deepcopy(self.graph['events'])
        build.plan['events'] = [{**copy.deepcopy(e), 'actions': [], 'participations': []}
                                for e in build.events]
        def complete(name, system, payload):
            if name == 'SubjectCoverageReviewer':
                self.assertTrue(payload['PossibleDuplicateStatements'])
                return {'event_additions': 'bad', 'statement_merges': self.proposal}
            return build.complete(name, system, payload)
        graph, state, _ = run_subject_build(input_(), config(), complete, build.save)
        self.assertEqual(len(state['agent_executed']), 6)
        self.assertEqual(find_statement_duplicates(graph), [])
        self.assertTrue(build.saved['subject_coverage_review']['statement_merges']['accepted'])

    def test_statement_merge_precedes_event_merge_using_original_ids(self):
        quote = 'At the annual meeting on May 6, 2023 Buffett explained the investment.'
        source = input_()
        source.samples[0].content += ' ' + quote
        build = fixtures.NativeBuildTests(); build.setUp()
        build.events = copy.deepcopy(self.graph['events'])
        for event in build.events:
            event['title'] = vf('Annual meeting', quote)
            event['descriptions'] = [vf('Annual meeting discussion', quote)]
            event['start_time'] = event['end_time'] = vf('2023-05-06', quote)
            for row in event['participations']:
                row['start_time'] = row['end_time'] = vf('2023-05-06', quote)
            for row in event['actions']:
                row['timestamp'] = vf('2023-05-06', quote)
        build.plan['events'] = [{**copy.deepcopy(e), 'actions': [], 'participations': []}
                                for e in build.events]
        def complete(name, system, payload):
            if name == 'SubjectCoverageReviewer':
                return {'statement_merges': [self.proposal], 'event_merges': [{
                    'keep_event_id': 'E1', 'remove_event_id': 'E2',
                    'reason': 'Same documented meeting', 'evidence_source_contents': [quote]}]}
            return build.complete(name, system, payload)
        graph, _, report = run_subject_build(source, config(), complete, build.save)
        self.assertTrue(report['valid'], report)
        self.assertEqual(len(graph['events']), 1)
        review = build.saved['subject_coverage_review']
        self.assertTrue(review['statement_merges']['accepted'], review)
        self.assertTrue(review['event_merges']['accepted'], review)
        self.assertEqual(find_statement_duplicates(graph), [])


class RepairDateGuardTests(unittest.TestCase):
    def test_temporal_repair_cannot_hide_conflict_by_erasing_known_date(self):
        graph = {'events': [{'participations': [{'start_time': vf('2022-05-01')}]}]}
        errors = [{'path': '/events/0/participations/0',
                   'message': 'Time is wholly outside the containing interval'}]
        paths = [('/events/0/participations/0/start_time', vf('unknown', None)),
                 ('/events/0/participations/0/start_time/value', 'unknown'),
                 ('/events/0/participations/0', {'start_time': vf('unknown', None)})]
        for path, value in paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                apply_graph_patch(graph, {'patches': [{'op': 'replace', 'path': path, 'value': value}]}, errors)
        # Evidence failures can legitimately leave the date unresolved.
        fixed = apply_graph_patch(graph, {'patches': [{'op': 'replace', 'path': paths[0][0],
                                                       'value': vf('unknown', None)}]},
                                  [{'path': paths[0][0], 'message': 'Evidence quote is absent'}])
        self.assertEqual(fixed['events'][0]['participations'][0]['start_time']['value'], 'unknown')


if __name__ == '__main__':
    unittest.main()
