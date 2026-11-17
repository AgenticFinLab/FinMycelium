"""Model-independent regression cases for supported process construction."""
from copy import deepcopy
import socket

import pytest

from test_person_event_contract import graph, payload, facts_from_graph
from finmy.person_epg.event.proposals import Receiver, reference
from finmy.person_epg.event.records import IdMap, unknown_time, ground_quote
from finmy.person_epg.event.grouping import ambiguity_groups


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network prohibited'))


@pytest.mark.parametrize('storyline,description', [
    ('Philanthropy', 'The source links the pledge to its subsequent fulfilment.'),
    ('Family', 'The source links the invitation to the subsequent response.'),
])
def test_supported_candidate_survives_unknown_dates_and_program_id_mapping(graph, payload, storyline, description):
    facts = facts_from_graph(graph, payload)
    facts['storyline']['name'] = payload['user_query']['extras']['person_event']['storyline_name'] = storyline
    actions = deepcopy(facts['actions'][:2])
    facts['actions'] = []
    for n, action in enumerate(actions):
        action['action_id'] = 'temp-' + str(n)
        action['time'] = unknown_time('After the earlier act; calendar date unspecified.')
        action['support'] = [s for s in action['support'] if not s['target'].startswith('/time')]
        action['gaps'] = [dict(target='/time', reason='Calendar endpoints unavailable.')]
    candidate = dict(candidate_id='link', from_action_id='temp-0', to_action_id='temp-1',
        type='precedes', description=description,
        support=[dict(target='', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']])])
    result, report = Receiver(facts, payload, IdMap(), 'extract').extract(dict(
        entities=[], actions=actions, contexts=[], relation_candidates=[candidate], evidence=[], pending=[]))
    assert not report['rejected']
    link = result['relation_candidates'][0]
    assert {link['from_action_id'], link['to_action_id']} == {a['action_id'] for a in result['actions']}
    assert link['support'] == candidate['support']
    assert all(a['time']['start'] is None for a in result['actions'])


def test_unresolved_candidate_retains_lead_without_creating_endpoint(graph, payload):
    facts = facts_from_graph(graph, payload)
    candidate = dict(candidate_id='link', from_action_id=facts['actions'][0]['action_id'], to_action_id=None,
        type=None, description='The source indicates a response but does not identify its antecedent.',
        support=[dict(target='/description', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']]),
                 dict(target='/from_action_id', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']])],
        gaps=[dict(target='/' + k, reason='Not established.') for k in ('to_action_id', 'type')])
    result, report = Receiver(facts, payload, IdMap(), 'lead').extract(dict(
        entities=[], actions=[], contexts=[], relation_candidates=[candidate], evidence=[], pending=[]))
    assert not report['rejected'] and result['actions'] == facts['actions']
    assert result['relation_candidates'][0]['to_action_id'] is None
    candidate['to_action_id'] = 'nonexistent'
    _, report = Receiver(facts, payload, IdMap(), 'invalid-lead').extract(dict(
        entities=[], actions=[], contexts=[], relation_candidates=[candidate], evidence=[], pending=[]))
    assert report['rejected']


def test_unknown_date_and_different_wording_are_nominated_not_merged(graph, payload):
    facts = facts_from_graph(graph, payload)
    a = facts['actions'][0]
    a.update(name='Approve community library grant', description='Approved a grant for the community library.')
    a['time'] = unknown_time()
    a['object'] = dict(description='Community library funding grant', entity_refs=['ENTITY-OFFICE'])
    b = deepcopy(a)
    b.update(action_id='B', name='Authorize the library funding', description='Authorized funding for the community library grant.')
    unrelated = deepcopy(a)
    unrelated.update(action_id='C', name='Discuss family vacation', description='Discussed plans for a family vacation.')
    unrelated['object'] = dict(description='Summer travel plans', entity_refs=[])
    facts['actions'] = [a, b, unrelated]
    before = deepcopy(facts)
    groups = ambiguity_groups(facts)
    assert any({('actions', a['action_id']), ('actions', 'B')} <= set(g) for g in groups)
    assert all(('actions', 'C') not in g for g in groups)
    assert facts == before
    b['time'] = dict(kind='occurrence_window', text='2020', start='2020-01-01', end='2021-01-01',
                     start_precision='year', end_precision='year')
    a['time'] = dict(b['time'], text='2018', start='2018-01-01', end='2019-01-01')
    assert not ambiguity_groups(facts)


def test_common_actor_does_not_force_group_and_large_groups_are_bounded(graph, payload):
    facts = facts_from_graph(graph, payload)
    a = facts['actions'][0]
    a['time'] = unknown_time()
    facts['actions'] = [dict(deepcopy(a), action_id=str(i)) for i in range(200)]
    groups = ambiguity_groups(facts)
    ids = [ref for g in groups for ref in g]
    assert all(len(g) <= 8 for g in groups) and len(ids) == len(set(ids))
    assert groups == ambiguity_groups(facts)


def test_merge_preserves_candidate_support_and_redirects_endpoint(graph, payload):
    from test_person_event_consolidation import duplicate
    facts, decision = duplicate(graph, payload)
    old, survivor = decision['input_refs'][1]['object_id'], decision['input_refs'][0]['object_id']
    other = facts['actions'][1]['action_id']
    candidate = dict(candidate_id='C', from_action_id=old, to_action_id=other, type='precedes',
        description='Supported order.', support=[dict(target='', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']])])
    facts['relation_candidates'] = [candidate]
    result, report = Receiver(facts, payload, IdMap(), 'merge').consolidate(dict(
        decisions=[decision], evidence=[], pending=[]), {('actions', r['object_id']) for r in decision['input_refs']})
    assert not report['rejected']
    assert result['relation_candidates'] == [dict(candidate, from_action_id=survivor)]
    assert result['lineage'][-1]['input_refs'] == decision['input_refs']


@pytest.mark.parametrize('time', [
    dict(text='In 2020', kind='occurrence_window', start='2020-01-01', end='2021-01-01',
         start_precision='year', end_precision='year'),
    dict(text='By March 2020', kind='occurrence_window', start=None, end='2020-04-01',
         start_precision='unknown', end_precision='month'),
    unknown_time('After the earlier commitment; no calendar anchor.'),
])
def test_coarse_relative_and_single_bound_time_remain_usable_facts(graph, payload, time):
    from finmy.person_epg.event.validation import check_graph
    facts = facts_from_graph(graph, payload)
    a = facts['actions'][0]
    a['time'] = time
    a['support'] = [s for s in a['support'] if not s['target'].startswith('/time')]
    a['gaps'] = []
    for side in ('start', 'end'):
        if time[side] is None:
            a['gaps'].append(dict(target='/time/' + side, reason='Not determined by the source.'))
        else:
            a['support'].append(dict(target='/time/' + side, mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']]))
    assert check_graph(facts, payload)['valid']
    assert facts['actions'][0]['time'] == time


def test_independent_cross_phase_relation_is_accepted_without_candidate(graph, payload):
    a, b = graph['actions'][0], graph['actions'][-1]
    # Relation task may discover a link beyond its candidate shortlist, but may not rewrite time.
    edge = dict(relation_id='new-link', from_action_id=b['action_id'], to_action_id=a['action_id'],
        type='responds_to', basis='inferred', support=[dict(target='', mode='I',
        evidence_ids=[graph['evidence'][0]['evidence_id']], premise_refs=[
            dict(reference('actions', x['action_id']), field='/description') for x in (a,b)],
        reason='The cited restriction and the later response refer to the same documented issue.')])
    result, report = Receiver(graph, payload, IdMap(), 'new-relation').relate(dict(
        contexts=[], relations=[edge], phase_context_updates=[], action_context_updates=[dict(
            action_id=b['action_id'], delta_context_refs=b.get('delta_context_refs', []),
            baseline_context_exclusions=b.get('baseline_context_exclusions', []))], evidence=[], pending=[]),
        action_ids=[b['action_id']], phase_ids=[])
    assert not report['rejected']
    assert len(result['relations']) == len(graph['relations']) + 1
    mutable = {'delta_context_refs', 'baseline_context_exclusions'}
    assert [{k:v for k,v in a.items() if k not in mutable} for a in result['actions']] == [
        {k:v for k,v in a.items() if k not in mutable} for a in graph['actions']]


def test_whitespace_repair_preserves_original_slice_offsets_hash_and_audit():
    samples = {'S': dict(sample_id='S', raw_data_id='R', content='前🙂 She pledged\n\t funds. End.')}
    proposal = dict(sample_id='S', quote='She pledged funds.', context_before='wrong hint', start=0, end=18)
    before, audit = deepcopy(proposal), []
    evidence = ground_quote(proposal, samples, 'E', [(0, 30)], audit=audit)
    assert evidence['location_status'] == 'matched'
    assert evidence['quote'] == 'She pledged\n\t funds.'
    assert samples['S']['content'][evidence['start']:evidence['end']] == evidence['quote']
    assert proposal == before and len(audit) == 3
    assert ground_quote(proposal, samples, 'E', [(0, 5)])['location_status'] == 'unmatched'


@pytest.mark.parametrize('text,quote,status', [
    ('A promise. A promise.', 'A promise.', 'ambiguous'),
    ('A\n promise. A\t promise.', 'A promise.', 'ambiguous'),
    ('A promise.', 'a promise.', 'unmatched'),
    ('not now', 'notnow', 'unmatched'),
    ('A promise!', 'A promise.', 'unmatched'),
])
def test_quote_compatibility_never_guesses_wording_or_duplicate_locations(text, quote, status):
    proposal = dict(sample_id='S', quote=quote, context_before='unreliable')
    assert ground_quote(proposal, {'S': dict(sample_id='S', raw_data_id='R', content=text)}, 'E')['location_status'] == status


def test_normalization_is_recorded_by_receiver_without_rewriting_response(graph, payload):
    facts = facts_from_graph(graph, payload)
    sample = payload['samples'][0]
    quote = sample['content'][:sample['content'].index('.') + 1]
    # Only whitespace changes; the stored evidence must still match source bytes.
    proposed = quote.replace(' ', '\n')
    response = dict(entities=[], actions=[], contexts=[], relation_candidates=[], pending=[],
        evidence=[dict(evidence_id='new', sample_id=sample['sample_id'], quote=proposed)],
        note='No additional in-scope acts in this test range.')
    before = deepcopy(response)
    _, report = Receiver(facts, payload, IdMap(), 'quote', {sample['sample_id']: [(0, len(quote))]}).extract(response)
    assert response == before and report['normalizations']


def test_action_evidence_precedes_bulk_context_and_global_time_stays_visible(graph, payload):
    from finmy.person_epg.event.context import sized_request
    first = graph['actions'][0]
    # A very large irrelevant Context must not crowd out the Action's own quotes.
    graph['contexts'][0]['description'] *= 5000
    base = dict(role='relations', assigned_action_ids=[first['action_id']], assigned_phase_ids=[first['phase_id']],
        assigned_records=dict(actions=[first], phases=[p for p in graph['phases'] if p['phase_id'] == first['phase_id']]),
        relation_candidates=[])
    result = sized_request(base, graph, 30000, 4000)
    required = {eid for s in first['support'] for eid in s['evidence_ids']}
    included = {r['record']['evidence_id'] for r in result['related_records'] if r['collection'] == 'evidence'}
    assert required <= included
    others = [a for a in result['facts_index']['actions'] if a['action_id'] != first['action_id']]
    assert all('text_preview' in a['time'] and 'evidence_ids' in a for a in others)
    assert result['facts_index']['sources'][0]['published_at'] == graph['sources'][0]['published_at']
    assert len(result['facts_index']['actions']) == len(graph['actions'])


def test_consolidation_cannot_silently_erase_supported_time(graph, payload):
    facts = facts_from_graph(graph, payload)
    a = facts['actions'][0]
    revised = deepcopy(a)
    revised['time'] = unknown_time()
    revised['gaps'] = [dict(target='/time', reason='Prefer uncertainty.')]
    decision = dict(operation='keep', input_refs=[reference('actions', a['action_id'])],
        outputs=[dict(collection='actions', record=revised)], reason='Reword the fact.', evidence_ids=[])
    result, report = Receiver(facts, payload, IdMap(), 'retain-time').consolidate(dict(
        decisions=[decision], evidence=[], pending=[]), {('actions', a['action_id'])})
    assert report['rejected']
    assert result['actions'] == facts['actions']


def test_supported_time_conflict_can_replace_a_previously_precise_claim(graph, payload):
    facts = facts_from_graph(graph, payload)
    a = facts['actions'][0]
    revised = deepcopy(a)
    revised['time'] = unknown_time('The accounts disagree on the date.')
    revised['gaps'] = [dict(target='/time', reason='Conflicting date claims retained below.')]
    eid = facts['evidence'][0]['evidence_id']
    revised['conflicts'] = [dict(target='/time', reason='Two dated accounts differ.', alternatives=[
        dict(value=deepcopy(a['time']), support=[dict(target='/value',mode='A',evidence_ids=[eid])]),
        dict(value=unknown_time('Date not established'), support=[dict(target='/value',mode='A',evidence_ids=[eid])])])]
    decision = dict(operation='keep', input_refs=[reference('actions', a['action_id'])],
        outputs=[dict(collection='actions',record=revised)], reason='Retain the disputed date without choosing a source.', evidence_ids=[eid])
    result, report = Receiver(facts,payload,IdMap(),'time-conflict').consolidate(dict(
        decisions=[decision],evidence=[],pending=[]), {('actions',a['action_id'])})
    assert not report['rejected']
    retained = next(x for x in result['actions'] if x['action_id'] == a['action_id'])
    assert retained['time']['start'] is None and retained['conflicts'] == revised['conflicts']


def test_unresolved_endpoints_remain_visible_to_relation_discovery(graph, payload):
    from types import SimpleNamespace
    from finmy.person_epg.event.build import Construction
    from finmy.person_epg.event.runtime import EventBuildConfig
    builder = Construction(SimpleNamespace(payload=payload, config=EventBuildConfig(), state={'id_map': {}}))
    builder.graph = graph
    lead = dict(candidate_id='lead',from_action_id=None,to_action_id=None,type='responds_to',
        description='An evidenced response with unresolved action IDs.',
        support=[dict(target='/description',mode='A',evidence_ids=[graph['evidence'][0]['evidence_id']])],
        gaps=[dict(target='/' + k,reason='Endpoint unresolved.') for k in ('from_action_id','to_action_id')])
    builder.facts['relation_candidates'] = [lead]
    request = builder.relation_request([graph['actions'][0]['action_id']], [])
    assert request['relation_candidates'] == [lead]
    assert any(r['collection']=='evidence' and r['record']['evidence_id']==graph['evidence'][0]['evidence_id']
               for r in request['related_records'])
