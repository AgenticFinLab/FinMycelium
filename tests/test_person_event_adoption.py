from copy import deepcopy

import pytest

from test_person_event_contract import facts_from_graph, graph, payload
from finmy.person_epg.event.proposals import Receiver, reference, replace_references
from finmy.person_epg.event.records import IdMap, seed_facts


def test_relation_context_addition_and_action_update_are_atomic(graph, payload):
    action = graph['actions'][0]
    context = deepcopy(graph['contexts'][0])
    context['context_id'] = 'NEW-CONTEXT'
    baseline = next(p for p in graph['phases'] if p['phase_id'] == action['phase_id'])['baseline_context_refs'][0]
    delta = {**deepcopy(baseline), 'context_ref_id': 'NEW-REF', 'context_id': 'NEW-CONTEXT'}
    response = dict(contexts=[context], relations=[], phase_context_updates=[], action_context_updates=[dict(
        action_id=action['action_id'], delta_context_refs=[delta], baseline_context_exclusions=[dict(
            context_ref_id='FOREIGN', reason='Invalid exclusion', support=[dict(target='/context_ref_id', mode='A', evidence_ids=[graph['evidence'][0]['evidence_id']])])])],
        evidence=[], pending=[])
    result, report = Receiver(graph, payload, IdMap(), 'atomic').relate(response, action_ids=[action['action_id']], phase_ids=[])
    assert report['rejected']
    assert result['actions'] == graph['actions']
    assert result['contexts'] == graph['contexts']


def test_unassigned_candidate_cannot_be_modified(graph, payload):
    from finmy.person_epg.event.records import seed_facts
    facts = seed_facts(payload)
    facts['evidence'] = deepcopy(graph['evidence'])
    for action in graph['actions']:
        item = deepcopy(action)
        item['phase_id'] = None
        item['support'] = [s for s in item['support'] if s['target'] != '/phase_id']
        item.pop('delta_context_refs', None)
        facts['actions'].append(item)
    first, second = facts['actions'][:2]
    response = dict(decisions=[dict(operation='exclude', input_refs=[reference('actions', second['action_id'])],
        outputs=[], reason='Outside assigned scope', evidence_ids=[])], evidence=[], pending=[])
    result, report = Receiver(facts, payload, IdMap(), 'scope').consolidate(response, {('actions', first['action_id'])})
    assert result['actions'] == facts['actions'] and report['rejected']


def test_remapping_never_rewrites_history_or_prose():
    value = dict(actions=[dict(action_id='old', description='old is literal source text')], lineage=[dict(
        operation='merge', input_refs=[reference('actions', 'old')], output_refs=[reference('actions', 'new')])])
    result = replace_references(value, {'actions': {'old': 'new'}})
    assert result['actions'][0]['action_id'] == 'new'
    assert result['actions'][0]['description'] == value['actions'][0]['description']
    assert result['lineage'] == value['lineage']


def test_malformed_context_neighbor_is_pending_not_a_pipeline_crash(graph, payload):
    action = graph['actions'][0]
    response = dict(contexts=[None], relations=[], phase_context_updates=[], action_context_updates=[
        dict(action_id=action['action_id'], delta_context_refs=None, baseline_context_exclusions=[])], evidence=[], pending=[])
    result, report = Receiver(graph, payload, IdMap(), 'malformed').relate(response, action_ids=[action['action_id']], phase_ids=[])
    assert report['rejected'] and result == graph


def test_supported_split_and_forward_hierarchy_are_adopted_together(graph, payload):
    from finmy.person_epg.event.proposals import graph_from_facts
    from finmy.person_epg.event.records import seed_facts
    from finmy.person_epg.event.validation import check_graph
    facts = seed_facts(payload)
    facts['evidence'] = deepcopy(graph['evidence'])
    facts['entities'] = deepcopy(graph['entities'])
    facts['actions'] = deepcopy(graph['actions'])
    for action in facts['actions']:
        action['phase_id'] = None
        action['support'] = [s for s in action['support'] if s['target'] != '/phase_id']
        action.pop('delta_context_refs', None)
        action.pop('baseline_context_exclusions', None)
    old = facts['actions'][0]
    children = []
    for aid, name in [('received', 'Receive the restriction'), ('acknowledged', 'Acknowledge the restriction')]:
        child = deepcopy(old)
        child.update(action_id=aid, name=name, description=name)
        children.append(child)
    phase_id = graph['actions'][0]['phase_id']
    assignments = [dict(action_id=a['action_id'], phase_id=a['phase_id'],
                        support=[s for s in a['support'] if s['target'] == '/phase_id']) for a in graph['actions'][1:]]
    assignments += [dict(action_id=child['action_id'], phase_id=phase_id,
        support=[dict(target='/phase_id', mode='I', evidence_ids=[], premise_refs=[dict(
            collection='actions', object_id=child['action_id'], field='/time')], reason='Its documented day is within this behavior phase.')]) for child in children]
    overview = {k: deepcopy(graph['event'][k]) for k in ('time', 'summary', 'support')}
    overview = replace_references(overview, {'actions': {old['action_id']: 'received'}})
    phases = deepcopy(graph['phases'])
    for phase in phases:
        phase['baseline_context_refs'] = []
    response = dict(stages=graph['stages'], phases=phases, assignments=assignments,
        split_proposals=[dict(operation='split', input_refs=[reference('actions', old['action_id'])],
            outputs=[dict(collection='actions', record=c) for c in children],
            reason='The source separately describes receipt and acknowledgement.', evidence_ids=[graph['evidence'][2]['evidence_id']])],
        event_overview=overview, evidence=[], pending=[])
    result, report = Receiver(graph_from_facts(facts), payload, IdMap(), 'split').organize(response)
    assert not report['rejected'], report
    assert len(result['actions']) == 4 and all(a['phase_id'] for a in result['actions'])
    assert old['action_id'] not in {a['action_id'] for a in result['actions']}
    assert report['lineage'][0]['operation'] == 'split'
    assert check_graph(result, payload)['valid']



@pytest.mark.parametrize('malformed', [None, [None], [{'collection': 'actions', 'record': None}]])
def test_malformed_split_does_not_abort_independent_assignments(graph, payload, malformed):
    facts = facts_from_graph(graph, payload)
    from finmy.person_epg.event.proposals import graph_from_facts
    phases = deepcopy(graph['phases'])
    for phase in phases:
        phase['baseline_context_refs'] = []
    response = dict(stages=graph['stages'], phases=phases,
        assignments=[dict(action_id=a['action_id'],phase_id=a['phase_id'], support=[s for s in a['support'] if s['target']=='/phase_id'])
                     for a in graph['actions']],
        split_proposals=[dict(operation='split',input_refs=[reference('actions','ACTION-1')], outputs=malformed, reason='Malformed neighbor', evidence_ids=[])],
        event_overview={k:deepcopy(graph['event'][k]) for k in ('time','summary','support')}, evidence=[], pending=[])
    result, report = Receiver(graph_from_facts(facts), payload, IdMap(), 'bad-split-neighbor').organize(response)
    assert report['rejected'] and any(a['phase_id'] for a in result['actions'])


def test_known_actor_role_and_representation_cannot_silently_disappear(graph, payload):
    facts = facts_from_graph(graph, payload)
    action = facts['actions'][0]
    action['actor'].update(capacity='official', role='Chair', on_behalf_of='ENTITY-OFFICE')
    revised = deepcopy(action)
    revised['actor'].pop('role')
    revised['actor'].pop('on_behalf_of')
    response = dict(decisions=[dict(operation='keep', input_refs=[reference('actions', action['action_id'])],
        outputs=[dict(collection='actions', record=revised)], reason='Normalize wording only.', evidence_ids=[])],
        evidence=[], pending=[])
    result, report = Receiver(facts, payload, IdMap(), 'keep-known-fields').consolidate(response, {('actions', action['action_id'])})
    final = next(a for a in result['actions'] if a['action_id']==action['action_id'])
    assert final['actor'].get('role') == 'Chair' and final['actor'].get('on_behalf_of') == 'ENTITY-OFFICE', report


@pytest.mark.parametrize('delete_object', [False, True])
def test_known_object_and_entities_survive_wording_changes(graph, payload, delete_object):
    facts = facts_from_graph(graph, payload)
    action = facts['actions'][0]
    action['object']['entity_refs'] = ['ENTITY-OFFICE']
    revised = deepcopy(action)
    if delete_object:
        revised.pop('object')
    else:
        revised['description'] = 'A reworded acknowledgement of the restriction.'
        revised['object']['description'] = 'The documented disclosure restriction.'
    response = dict(decisions=[dict(operation='keep', input_refs=[reference('actions',action['action_id'])],
        outputs=[dict(collection='actions',record=revised)], reason='Clarify wording.', evidence_ids=[])], evidence=[],pending=[])
    result, report = Receiver(facts,payload,IdMap(),'wording').consolidate(response,{('actions',action['action_id'])})
    assert bool(report['rejected']) == delete_object
    assert next(a for a in result['actions'] if a['action_id']==action['action_id'])['object']['entity_refs'] == ['ENTITY-OFFICE']


def test_explicit_supported_role_correction_is_not_frozen(graph, payload):
    facts = facts_from_graph(graph, payload)
    action = facts['actions'][0]
    action['actor'].update(capacity='official',role='Chair',on_behalf_of='ENTITY-OFFICE')
    revised = deepcopy(action)
    revised['actor']['role'] = 'Director'
    revised['support'].append(dict(target='/actor/role',mode='A',evidence_ids=['EV-3']))
    response = dict(decisions=[dict(operation='keep', input_refs=[reference('actions',action['action_id'])],
        outputs=[dict(collection='actions',record=revised)], reason='Correct the role using the cited record.',evidence_ids=['EV-3'])], evidence=[],pending=[])
    result, report = Receiver(facts,payload,IdMap(),'role-correction').consolidate(response,{('actions',action['action_id'])})
    assert not report['rejected'],report
    assert next(a for a in result['actions'] if a['action_id']==action['action_id'])['actor']['role'] == 'Director'
    assert result['lineage'][-1]['reason'] == response['decisions'][0]['reason']


def test_malformed_assignment_does_not_discard_valid_neighbors(graph, payload):
    from finmy.person_epg.event.proposals import graph_from_facts
    facts = facts_from_graph(graph, payload)
    phases = deepcopy(graph['phases'])
    for phase in phases:
        phase['baseline_context_refs'] = []
    response = dict(stages=graph['stages'], phases=phases,
        assignments=[dict(action_id=[], phase_id='PHASE-1', support=[None])] + [
            dict(action_id=a['action_id'], phase_id=a['phase_id'], support=[s for s in a['support'] if s['target']=='/phase_id'])
            for a in graph['actions']], split_proposals=[], evidence=[], pending=[])
    result, report = Receiver(graph_from_facts(facts),payload,IdMap(),'bad-assignment').organize(response)
    assert report['rejected'] and all(a['phase_id'] for a in result['actions'])


def test_malformed_correction_conflict_does_not_abort_independent_keep(graph, payload):
    facts = facts_from_graph(graph,payload)
    first, second = facts['actions'][:2]
    first['actor'].update(capacity='official', role='Chair')
    revised = deepcopy(first)
    revised['actor']['role'] = 'Director'
    revised['conflicts'] = [dict(target='/actor/role', reason='Source disagreement.', alternatives=[
        dict(value='Chair',support=[None]),
        dict(value='Director',support=[dict(target='/value',mode='A',evidence_ids=['EV-3'])])])]
    response = dict(decisions=[
        dict(operation='keep',input_refs=[reference('actions',first['action_id'])],
            outputs=[dict(collection='actions',record=revised)],reason='Role correction.',evidence_ids=['EV-3']),
        dict(operation='keep',input_refs=[reference('actions',second['action_id'])],
            outputs=[],reason='Keep the independent record.',evidence_ids=[])],evidence=[],pending=[])
    assigned = {('actions',a['action_id']) for a in (first,second)}
    result, report = Receiver(facts,payload,IdMap(),'after').consolidate(response,assigned)
    assert 'decision:1' in report['accepted'] and report['rejected']
    assert next(a for a in result['actions'] if a['action_id']==first['action_id'])['actor']['role']=='Chair'

@pytest.mark.parametrize('field', ['role', 'qualification'])
def test_existing_context_association_metadata_cannot_disappear(graph, payload, field):
    from finmy.person_epg.event.validation import check_graph
    phase = graph['phases'][0]
    known = phase['baseline_context_refs'][0]
    known.update(entity_id='ENTITY-OFFICE', role='Issuing office', qualification='Applies only to external disclosures.')
    known['support'] = [dict(target='',mode='A',evidence_ids=['EV-2'])]
    assert check_graph(graph,payload)['valid']
    replacement = deepcopy(known)
    replacement.pop(field)
    response = dict(contexts=[],relations=[],phase_context_updates=[dict(
        phase_id=phase['phase_id'],baseline_context_refs=[replacement])],action_context_updates=[],evidence=[],pending=[])
    result, report = Receiver(graph,payload,IdMap(),'metadata').relate(response,action_ids=[],phase_ids=[phase['phase_id']])
    updated = next(p for p in result['phases'] if p['phase_id']==phase['phase_id'])['baseline_context_refs'][0]
    assert report['rejected']
    assert updated == known


def test_existing_context_association_can_gain_support_and_a_distinct_role(graph, payload):
    phase = graph['phases'][0]
    known = phase['baseline_context_refs'][0]
    known.update(entity_id='ENTITY-OFFICE', role='Issuing office', qualification='External disclosures only.')
    known['support'] = [dict(target='', mode='A', evidence_ids=['EV-2'])]
    enriched = deepcopy(known)
    enriched['support'].append(dict(target='', mode='A', evidence_ids=['EV-3']))
    distinct = deepcopy(known)
    distinct.update(context_ref_id='NEW-ADVISOR-REF', role='Advisor')
    response = dict(contexts=[], relations=[], phase_context_updates=[dict(
        phase_id=phase['phase_id'], baseline_context_refs=[enriched, distinct])],
        action_context_updates=[], evidence=[], pending=[])
    result, report = Receiver(graph, payload, IdMap(), 'distinct-role').relate(
        response, action_ids=[], phase_ids=[phase['phase_id']])
    assert not report['rejected'], report
    refs = next(p for p in result['phases'] if p['phase_id'] == phase['phase_id'])['baseline_context_refs']
    assert len(refs) == 2
    assert {r['role'] for r in refs} == {'Issuing office', 'Advisor'}
    assert next(r for r in refs if r['context_ref_id'] == known['context_ref_id'])['support'] == enriched['support']
