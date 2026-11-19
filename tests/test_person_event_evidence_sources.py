"""One factual Evidence keeps independently located, source-bound quotations."""
from copy import deepcopy

from test_person_event_contract import payload
from finmy.person_epg.event.context import navigation
from finmy.person_epg.event.proposals import Receiver
from finmy.person_epg.event.records import IdMap, seed_facts
from finmy.person_epg.event.validation import check_graph


def extraction(evidence):
    return dict(entities=[], actions=[], contexts=[], relation_candidates=[],
                evidence=evidence, pending=[], note='Evidence only.')


def test_fact_and_source_support_many_to_many_and_replay(payload):
    ids = IdMap()
    facts = seed_facts(payload)
    first = dict(evidence_id='shared', statement='Mina Lee acted in February 2020.', citations=[
        dict(sample_id='SAMPLE-1', quote='On 1 February 2020, Mina Lee'),
        dict(sample_id='SAMPLE-2', quote='On 3 February 2020, Mina Lee')])
    second = dict(evidence_id='other', statement='A disclosure restriction applied to Lee.', citations=[
        dict(sample_id='SAMPLE-1', quote="The restriction applied to Mina Lee's public statements")])
    facts, report = Receiver(facts, payload, ids, 'extract').extract(extraction([first, second]))
    assert not report['rejected'], report
    assert check_graph(facts, payload)['valid']
    assert len(facts['evidence']) == 2
    shared = next(e for e in facts['evidence'] if e['statement'] == first['statement'])
    assert [c['source_id'] for c in shared['citations']] == ['SRC-1', 'SRC-2']
    assert len([e for e in facts['evidence'] for c in e['citations'] if c['source_id'] == 'SRC-1']) == 2
    assert {row['source_id'] for row in navigation(facts)['evidence_index']
            if row['evidence_id'] == shared['evidence_id']} == {'SRC-1', 'SRC-2'}

    # A new source reading augments the existing fact without changing its ID.
    append = dict(evidence_id=shared['evidence_id'], statement=first['statement'], citations=[
        dict(sample_id='SAMPLE-3', quote='On 5 February 2020, Mina Lee')])
    updated, report = Receiver(facts, payload, ids, 'supplement').extract(extraction([append]))
    assert not report['rejected'], report
    assert len(updated['evidence']) == 2
    assert [c['source_id'] for c in next(e for e in updated['evidence']
            if e['evidence_id'] == shared['evidence_id'])['citations']] == ['SRC-1', 'SRC-2', 'SRC-3']
    replayed, report = Receiver(updated, payload, ids, 'supplement').extract(extraction([append]))
    assert not report['rejected'] and replayed == updated

    # An unlocatable addition cannot damage the previously verified support.
    invalid = deepcopy(append)
    invalid['citations'][0]['quote'] = 'Unpublished claim absent from the sample.'
    retained, report = Receiver(updated, payload, ids, 'bad-supplement').extract(extraction([invalid]))
    assert report['rejected'] and retained['evidence'] == updated['evidence']
    assert retained['pending']  # The failed quotation remains available for review.
