"""Append-only enrichment preserves the user's already reconstructed facts."""
import copy
import unittest

from finmy.person_epg.schema import JSON_SCHEMA
from finmy.person_epg.validation import validate_person_epg
from finmy.runner.event_additions import empty_additions, merge_event_additions


def package():
    data = {key: [] for key in JSON_SCHEMA['properties'] if key not in ('schema_version', 'graph')}
    data.update(schema_version='person-epg-3.0', graph={
        'graph_id': 'graph', 'schema_version': 'person-epg-3.0', 'subject_entity_id': 'person',
        'subject_type': 'individual', 'title': 'Documented history'})
    data['entity'] = [dict(entity_id='person', name='Investor', entity_type='individual', sort_order=0),
                      dict(entity_id='company', name='Company', entity_type='organization', sort_order=1)]
    data['domain'] = [dict(domain_id='domain', label='Investments', sort_order=0)]
    data['event'] = [dict(event_id='event', domain_id='domain', label='Investment', sort_order=0)]
    data['stage'] = [dict(event_id='event', stage_id='stage', label='Existing stage', sort_order=0)]
    data['occurrence'] = [dict(occurrence_id='occ', title='Read report', subject_relevance='direct', sort_order=0)]
    data['occurrence_participant'] = [dict(occurrence_id='occ', entity_id='person')]
    data['action'] = [dict(action_id='action', occurrence_id='occ', actor_id='person', action_type='Read report', sort_order=0)]
    data['activity'] = [dict(activity_id='activity', action_id='action')]
    data['activity_detail'] = [dict(activity_id='activity', detail_index=0, value='Existing useful fact')]
    data['event_activity'] = [dict(event_id='event', activity_id='activity', stage_id='stage', detail_mode='selected', sort_order=0)]
    data['event_activity_detail'] = [dict(event_id='event', activity_id='activity', detail_index=0)]
    return data


def citation(quote):
    return [dict(document_id='EF_DOC_1', quote=quote)]


def activity(key='buy', kind='action', title='Place order', quote='Investor told Trader to buy shares.'):
    return dict(key=key, kind=kind, title=title, actor_id='person' if kind == 'action' else None,
                from_entity_id='company' if kind == 'transaction' else None, to_entity_id=None,
                time=None, stage_id=None, details=[], citations=citation(quote))


class EventAdditionsTests(unittest.TestCase):
    def setUp(self):
        self.base = package()
        self.assertTrue(validate_person_epg(self.base)['valid'])
        self.sources = [dict(document_id='EF_DOC_1', title='Report', source_url='https://example.com',
            content='Investor read the report. Investor told Trader to buy shares. '
                    'Company bought 100 shares for $500. Trader is an employee. Execution followed the decision.')]

    def merge(self, proposal):
        return merge_event_additions(self.base, 'event', proposal, self.sources)

    def test_append_keeps_every_existing_row_and_resolves_all_new_quotes(self):
        p = empty_additions()
        p['activities'] = [activity()]
        p['activities'][0]['details'] = [dict(value='Trader executes the order.', citations=citation('Investor told Trader to buy shares.'))]
        original = copy.deepcopy(self.base)
        result, report = self.merge(p)
        self.assertEqual(report['status'], 'merged', report)
        self.assertEqual(self.base, original)
        for key, value in original.items():
            self.assertEqual(result[key][:len(value)] if isinstance(value, list) else result[key], value)
        docs = {row['document_id']: row['content'] for row in result['source_document']}
        for span in result['evidence_span']:
            self.assertEqual(docs[span['document_id']][span['char_start']:span['char_end']], span['quote'])
        self.assertTrue(validate_person_epg(result)['valid'])


    def test_unknown_reference_is_atomic_even_after_valid_addition(self):
        p = empty_additions()
        p['activities'] = [activity(), activity(key='bad')]
        p['activities'][1]['actor_id'] = 'hallucinated'
        result, report = self.merge(p)
        self.assertEqual(report['status'], 'rejected')
        self.assertEqual(result, self.base)

    def test_non_verbatim_quote_and_source_collision_reject(self):
        p = empty_additions()
        p['activities'] = [activity(quote='Unsupported statement')]
        self.assertEqual(self.merge(p)[1]['status'], 'rejected')
        self.base['source_document'] = [dict(document_id='EF_DOC_1', content='Different text')]
        p['activities'] = [activity()]
        result, report = self.merge(p)
        self.assertEqual(report['status'], 'rejected')
        self.assertIn('collision', report['reason'])
        self.assertEqual(result, self.base)


    def test_transaction_duplicate_same_claim_is_one_fact(self):
        p = empty_additions()
        quote = 'Company bought 100 shares for $500.'
        first = activity(kind='transaction', title='Purchase shares', quote=quote)
        first['details'] = [dict(value='Paid $500 for 100 shares.', citations=citation(quote))]
        second = copy.deepcopy(first)
        second.update(key='again')
        p['activities'] = [first, second]
        result, report = self.merge(p)
        self.assertEqual(report['status'], 'merged', report)
        self.assertEqual(len(result['financial_transaction']), 1)
        self.assertEqual(len(result['activity']), 2)
        self.assertGreater(report['skipped_duplicates'], 0)

    def test_optional_stage_new_entity_and_local_relation(self):
        p = empty_additions()
        p['entities'] = [dict(key='trader', name='Trader', entity_type='individual', citations=citation('Trader is an employee.'))]
        p['stages'] = [dict(key='execution', label='Execution', summary=None,
            boundary_reason='Decision is followed by execution.', citations=citation('Execution followed the decision.'))]
        p['activities'] = [activity()]
        p['activities'][0]['actor_id'] = 'trader'
        p['activities'][0]['stage_id'] = 'execution'
        p['relations'] = [dict(from_activity_id='activity', to_activity_id='buy', relation_type='precedes',
            description='Decision precedes execution.', citations=citation('Execution followed the decision.'))]
        result, report = self.merge(p)
        self.assertEqual(report['status'], 'merged', report)
        self.assertEqual(len(result['stage']), 2)
        self.assertEqual(result['stage'][0], self.base['stage'][0])
        self.assertEqual(result['activity_relation'][-1]['basis'], 'source')


    def test_repeating_same_action_additions_is_idempotent(self):
        p = empty_additions()
        p['activities'] = [activity()]
        once, report = self.merge(p)
        twice, second = merge_event_additions(once, 'event', p, self.sources)
        self.assertEqual(second['status'], 'no_changes', second)
        self.assertEqual(once, twice)


    def test_same_trade_conflicting_unit_magnitudes_rejected(self):
        p = empty_additions()
        quote = 'Company bought 100 shares for $500.'
        first = activity(kind='transaction', title='Purchase shares', quote=quote)
        first['details'] = [dict(value='Paid 1.55 million dollars', citations=citation(quote))]
        second = copy.deepcopy(first)
        second['key'] = 'again'
        second['details'][0]['value'] = 'Paid 1.55 billion dollars'
        p['activities'] = [first, second]
        self.assertEqual(self.merge(p)[1]['status'], 'rejected')


    def test_same_fact_across_events_reuses_activity_with_new_membership(self):
        self.base['event'].append(dict(event_id='second', domain_id='domain', label='Second', sort_order=1))
        p = empty_additions()
        p['activities'] = [activity()]
        result, report = self.merge(p)
        again, report = merge_event_additions(result, 'second', p, self.sources)
        self.assertEqual(report['status'], 'merged', report)
        self.assertEqual(len(again['activity']), len(result['activity']))
        self.assertEqual(len(again['event_activity']), len(result['event_activity']) + 1)


if __name__ == '__main__':
    unittest.main()
