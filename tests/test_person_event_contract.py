"""Offline contract tests using only the design's authored example."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from finmy.person_epg.event.records import (
    IdMap, compose_context, ground_quote, seed_facts, sha256, unknown_time, validate_input,
)
from finmy.person_epg.event.validation import check_graph, order_view
from finmy.person_epg.validation import validate_person_epg

FIXTURES = Path(__file__).parent / 'fixtures' / 'person_event'


@pytest.fixture
def payload():
    return json.loads((FIXTURES / 'input.json').read_text())


@pytest.fixture
def graph():
    return json.loads((FIXTURES / 'graph.json').read_text())


def codes(report):
    return {i['code'] for i in report['issues'] if i['severity'] == 'error'}


def test_design_example_is_valid_and_nonmutating(graph, payload):
    before = deepcopy(graph)
    report = check_graph(graph, payload)
    assert report['valid'], report['issues']
    assert graph == before
    assert validate_person_epg(graph)['valid']
    assert 'semantic_support' in report['summary']['not_checked']
    assert check_graph(seed_facts(payload), payload)['valid']


def test_input_extras_preserved_and_unknown_fields_rejected(payload):
    payload['user_query']['extras']['custom'] = {'keep': True}
    before = deepcopy(payload)
    validate_input(payload)
    assert payload == before
    payload['samples'][0]['invented'] = True
    with pytest.raises(ValueError, match='fields'):
        validate_input(payload)


def test_quote_offsets_are_unicode_and_repeated_quote_is_ambiguous():
    sample = dict(sample_id='S', raw_data_id='R', content='甲🙂行动。乙行动。')
    proposal = dict(sample_id='S', quote='行动')
    ambiguous = ground_quote(proposal, {'S': sample}, 'E')
    assert ambiguous['location_status'] == 'ambiguous' and ambiguous['start'] is None
    located = ground_quote({**proposal, 'context_before': '甲🙂'}, {'S': sample}, 'E')
    assert (located['start'], located['end']) == (2, 4)
    assert located['sample_sha256'] == sha256(sample['content'].encode('utf-8'))
    assert ground_quote(proposal, {'S': sample}, 'E', [(0, 5)])['start'] == 2
    assert ground_quote({**proposal, 'quote': 'fabrication'}, {'S': sample}, 'E')['location_status'] == 'unmatched'


def test_stable_program_ids_survive_resume():
    first = IdMap()
    adopted = first.assign('actions', 'A1', 'extract:0')
    restored = IdMap(json.loads(json.dumps(first.mapping)))
    assert restored.assign('actions', 'A1', 'extract:0') == adopted
    assert restored.assign('actions', 'A1', 'extract:1') != adopted


@pytest.mark.parametrize('value', [None, [], {}, {'schema_version': 'invented'}])
def test_invalid_shapes_report_without_crashing(value):
    assert 'SCHEMA_INVALID' in codes(check_graph(value))


def test_missing_references_and_sample_tampering_are_errors(graph, payload):
    graph['actions'][0]['actor']['entity_id'] = 'MISSING'
    graph['evidence'][0]['sample_sha256'] = '0' * 64
    report = check_graph(graph, payload)
    assert {'REFERENCE_MISSING', 'SAMPLE_HASH_MISMATCH'} <= codes(report)


def test_occurrence_windows_do_not_derive_overlap(graph):
    a, b = graph['actions'][:2]
    b['time'] = deepcopy(a['time'])
    relation = dict(relation_id='R-window', from_action_id=a['action_id'], to_action_id=b['action_id'],
                    type='overlaps', basis='derived', support=[dict(target='', mode='I', evidence_ids=[],
                    premise_refs=[dict(collection='actions', object_id=x['action_id'], field='/time') for x in (a, b)],
                    reason='These windows overlap.')])
    graph['relations'] = [relation]
    assert 'DERIVED_RELATION_INVALID' in codes(check_graph(graph))
    a['time'] = unknown_time()
    relation['type'] = 'precedes'
    assert 'DERIVED_RELATION_INVALID' in codes(check_graph(graph))


def test_precedence_cycle_retains_all_raw_edges_but_excludes_all_from_order(graph):
    ids = [a['action_id'] for a in graph['actions']]
    support = [dict(target='', mode='A', evidence_ids=[graph['evidence'][0]['evidence_id']])]
    graph['relations'] = [dict(relation_id='R'+str(i), from_action_id=a, to_action_id=b,
                               type='precedes', basis='asserted', support=deepcopy(support))
                          for i, (a, b) in enumerate(zip(ids, ids[1:] + ids[:1]))]
    original = deepcopy(graph['relations'])
    view = order_view(graph)
    assert not view['relation_ids'] and len(view['excluded']) == 3
    assert graph['relations'] == original
    assert 'TEMPORAL_CONFLICT_UNRECORDED' in codes(check_graph(graph))


def test_context_exclusion_is_supported_and_scoped_to_own_phase(graph):
    action = graph['actions'][0]
    phase = next(p for p in graph['phases'] if p['phase_id'] == action['phase_id'])
    reference = phase['baseline_context_refs'][0]
    support = [dict(target='/context_ref_id', mode='A', evidence_ids=[graph['evidence'][0]['evidence_id']])]
    action['baseline_context_exclusions'] = [dict(context_ref_id='foreign', reason='No longer applies.', support=support)]
    result = compose_context(graph, action['action_id'])
    assert result['issues'] and not result['excluded_ref_ids']
    action['baseline_context_exclusions'][0]['context_ref_id'] = reference['context_ref_id']
    assert compose_context(graph, action['action_id'])['excluded_ref_ids'] == [reference['context_ref_id']]
    assert reference in phase['baseline_context_refs']
    action['baseline_context_exclusions'][0]['support'] = []
    assert not compose_context(graph, action['action_id'])['excluded_ref_ids']


def test_circular_claim_support_is_rejected(graph):
    a, b = graph['actions'][:2]
    for record, other in ((a, b), (b, a)):
        record['support'] = [dict(target='/description', mode='I', evidence_ids=[],
                                 premise_refs=[dict(collection='actions', object_id=other['action_id'], field='/description')],
                                 reason='Depends on the other description.')]
    assert 'SUPPORT_CYCLE' in codes(check_graph(graph))
    for record in (a, b):
        record['support'][0]['premise_refs'][0]['field'] = ''
    assert 'SUPPORT_CYCLE' in codes(check_graph(graph))


def test_empty_hierarchy_is_partial_not_complete(graph):
    graph['stages'] = []
    graph['phases'] = []
    for action in graph['actions']:
        action['phase_id'] = None
    assert not check_graph(graph)['valid']
    assert 'ACTION_PHASE_MISSING' in codes(check_graph(graph, complete=False))


def test_unknown_precedence_does_not_enter_determined_order(graph, payload):
    relation = graph['relations'][0]
    relation['basis'] = 'asserted'
    relation['support'] = []
    relation['gaps'] = [{'target':'', 'reason':'No source establishes the relative order of these actions.'}]
    # Unknown supported status can remain in the raw graph, but not as established precedence.
    view = order_view(graph)
    assert relation['relation_id'] not in view['relation_ids'], view


def test_event_declared_time_conflict_blocks_derived_relation(graph, payload):
    graph['event']['conflicts'] = [dict(target='', reason='The two sources disagree on the first action time.',
        related_refs=[dict(collection='actions', object_id='ACTION-1', field='/time')],
        alternatives=[dict(value=date, support=[dict(target='/value', mode='A', evidence_ids=['EV-3'])])
                      for date in ('2020-02-01','2020-02-04')])]
    report = check_graph(graph, payload)
    assert any(i['code']=='DERIVED_RELATION_INVALID' for i in report['issues']), report


def test_quote_end_cannot_exceed_frozen_sample(graph, payload):
    evidence = next(e for e in graph['evidence'] if e['evidence_id']=='EV-3')
    sample = next(s for s in payload['samples'] if s['sample_id']==evidence['sample_id'])
    assert evidence['end'] == len(sample['content'])
    evidence['end'] += 1000
    report = check_graph(graph, payload)
    assert not report['valid'], report


def test_candidate_missing_endpoint_requires_explicit_gap(graph, payload):
    facts = facts_from_graph(graph, payload)
    facts['relation_candidates'] = [dict(candidate_id='CAND-UNKNOWN', from_action_id='ACTION-1', to_action_id=None,
        type=None, description='The source suggests a link but the target is not identified.',
        support=[dict(target='/description', mode='A', evidence_ids=['EV-3'])])]
    report=check_graph(facts,payload)
    assert not report['valid'], report


@pytest.mark.parametrize('target', ['/actor', '/time', '/object'])
def test_description_support_cannot_cover_other_critical_fields(graph, payload, target):
    action = graph['actions'][0]
    action['support'] = [s for s in action['support'] if s['target'] != target]
    report = check_graph(graph, payload)
    assert 'FIELD_SUPPORT_OR_GAP_REQUIRED' in codes(report)
    assert any(i['field'].startswith(target) for i in report['issues'] if i['code']=='FIELD_SUPPORT_OR_GAP_REQUIRED')


def test_parent_and_explicit_child_support_cover_the_same_actor(graph, payload):
    action = graph['actions'][0]
    parent = next(s for s in action['support'] if s['target']=='/actor')
    action['support'].remove(parent)
    action['support'] += [{**parent, 'target':'/actor/'+key} for key in action['actor']]
    assert check_graph(graph, payload)['valid']


def test_explicit_unknown_time_is_allowed_without_deriving_order(graph, payload):
    action = graph['actions'][0]
    action['time'] = unknown_time()
    action['support'] = [s for s in action['support'] if s['target'] != '/time']
    action.setdefault('gaps', []).append(dict(target='/time', reason='The action date is not established.'))
    graph['relations'] = []
    report = check_graph(graph, payload)
    assert report['valid'], report
    assert not report['order']['relation_ids']


def test_gap_does_not_turn_unsupported_known_time_into_a_derived_premise(graph, payload):
    action = graph['actions'][0]
    action['support'] = [s for s in action['support'] if s['target'] != '/time']
    action.setdefault('gaps', []).append(dict(target='/time', reason='This date remains unverified.'))
    report = check_graph(graph, payload)
    assert 'DERIVED_RELATION_INVALID' in codes(report)
    assert graph['relations'][0]['relation_id'] not in report['order']['relation_ids']


def test_unlocated_evidence_does_not_establish_precedence(graph, payload):
    relation = graph['relations'][0]
    relation.update(basis='asserted', support=[dict(target='',mode='A',evidence_ids=['EV-3'])])
    evidence = next(e for e in graph['evidence'] if e['evidence_id']=='EV-3')
    evidence.update(location_status='unmatched', start=None, end=None)
    assert relation['relation_id'] not in order_view(graph, payload)['relation_ids']


def test_candidate_gaps_preserve_a_partial_relationship_lead(graph, payload):
    facts = facts_from_graph(graph, payload)
    facts['relation_candidates'] = [dict(candidate_id='CAND', from_action_id='ACTION-1', to_action_id=None,
        type=None, description='A relationship lead with an unidentified endpoint and type.',
        support=[dict(target='/from_action_id', mode='A', evidence_ids=['EV-3'])],
        gaps=[dict(target='/'+key, reason='Not established in the available material.') for key in ('to_action_id','type')])]
    assert check_graph(facts, payload)['valid']


@pytest.mark.parametrize('offset', [-1, True, 1.0, 10000])
def test_invalid_quote_offsets_report_without_slice_errors(graph, payload, offset):
    graph['evidence'][0]['start'] = offset
    assert not check_graph(graph, payload)['valid']


def facts_from_graph(graph, payload):
    facts = seed_facts(payload)
    for key in ('entities', 'actions', 'contexts', 'evidence'):
        facts[key] = deepcopy(graph[key])
    for action in facts['actions']:
        action['phase_id'] = None
        action['support'] = [s for s in action['support'] if s['target'] != '/phase_id']
        action.pop('delta_context_refs', None)
        action.pop('baseline_context_exclusions', None)
    return facts


def test_explicit_time_gap_prevents_using_an_old_citation_as_certain(graph, payload):
    action = graph['actions'][0]
    action.setdefault('gaps', []).append(dict(target='/time', reason='The retained date has not been established.'))
    report = check_graph(graph, payload)
    assert 'DERIVED_RELATION_INVALID' in codes(report)
    assert graph['relations'][0]['relation_id'] not in report['order']['relation_ids']


@pytest.mark.parametrize('declared_ids, valid', [(['R0'], False), (['R0', 'R1', 'R2'], True)])
def test_raw_precedence_cycle_is_retained_and_completely_reported(graph, payload, declared_ids, valid):
    from finmy.person_epg.event.proposals import reference
    ids = [a['action_id'] for a in graph['actions']]
    for action in graph['actions']:
        action['time'] = unknown_time()
        action['support'] = [s for s in action['support'] if s['target'] != '/time']
        action.setdefault('gaps', []).append(dict(target='/time', reason='No reliable action date is known.'))
    graph['relations'] = [dict(relation_id='R'+str(i), from_action_id=a, to_action_id=b,
        type='precedes', basis='asserted', support=[dict(target='', mode='A', evidence_ids=['EV-1'])])
        for i, (a,b) in enumerate(zip(ids, ids[1:]+ids[:1]))]
    graph['event']['conflicts'] = [dict(target='', reason='Only this individual precedence claim was marked disputed.',
        related_refs=[reference('relations', rid) for rid in declared_ids], alternatives=[
            dict(value='The first action preceded the second.', support=[dict(target='/value',mode='A',evidence_ids=['EV-1'])]),
            dict(value='That order remains disputed.', support=[dict(target='/value',mode='A',evidence_ids=['EV-2'])])])]
    report = check_graph(graph, payload)
    assert report['valid'] == valid, report
    assert not report['order']['relation_ids']
    assert len(graph['relations']) == 3
    assert all('precedence_cycle' in report['order']['excluded'][rid] for rid in ('R0', 'R1', 'R2'))
    assert ('TEMPORAL_CONFLICT_UNRECORDED' in codes(report)) == (not valid)
