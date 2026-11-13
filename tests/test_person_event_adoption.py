from copy import deepcopy

from test_person_event_contract import graph, payload
from finmy.person_epg.event.proposals import Receiver, reference, replace_references
from finmy.person_epg.event.records import IdMap


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
