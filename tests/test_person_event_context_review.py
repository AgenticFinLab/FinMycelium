"""Offline Context review using the authored public-communication example."""
from copy import deepcopy
from types import SimpleNamespace

from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.context import sized_request
from finmy.person_epg.event.grouping import ambiguity_groups
from finmy.person_epg.event.prompts import system_prompt
from finmy.person_epg.event.proposals import Receiver, reference
from finmy.person_epg.event.records import IdMap, compose_context, prompt_json
from finmy.person_epg.event.runtime import EventBuildConfig
from finmy.person_epg.event.validation import check_graph
from test_person_event_contract import facts_from_graph, graph, payload


def test_context_shortlist_considers_a_shared_fact_inside_a_longer_account(graph, payload):
    facts = facts_from_graph(graph, payload)
    first = facts['contexts'][0]
    first['description'] = 'A disclosure restriction covered public statements.'
    second = dict(first, context_id='SECOND', description=(
        'A notice outlined changes to internal reporting. Public statements fell under a disclosure restriction.'))
    other = dict(first, context_id='OTHER', description='The Office elected a new coordinator.')
    belief = dict(first, context_id='BELIEF', perspective='belief')
    later = dict(first, context_id='LATER', time=dict(first['time'], start='2020-03-01', end='2020-03-08'))
    facts['contexts'] = [first, second, other, belief, later]
    before = deepcopy(facts)
    groups = [g for g in ambiguity_groups(facts) if g[0][0] == 'contexts']
    assert groups == [[('contexts', 'CTX-1'), ('contexts', 'SECOND')]]
    assert facts == before


def test_context_merge_preserves_independent_support_and_known_perspective(graph, payload):
    facts = facts_from_graph(graph, payload)
    first = facts['contexts'][0]
    first['description'] = 'A disclosure restriction was in effect.'
    # The other source describes the same restriction during the briefing. Its
    # passage does not independently establish when the restriction ended.
    second = dict(first, context_id='OTHER', description='The restriction applied during the briefing.',
                  support=[dict(target='/description', mode='A', evidence_ids=['EV-4'])])
    facts['contexts'].append(second)
    merged = dict(first, support=[*first['support'], *second['support']])
    ids = [first['context_id'], second['context_id']]
    decision = dict(operation='merge', input_refs=[reference('contexts', cid) for cid in ids],
                    outputs=[dict(collection='contexts', record=merged)], reason='Both sources document the restriction.',
                    evidence_ids=['EV-2', 'EV-4'])
    assigned = {('contexts', cid) for cid in ids}

    def submit():
        return Receiver(facts, payload, IdMap(), 'context-review').consolidate(
            dict(decisions=[decision], evidence=[], pending=[]), assigned)

    result, report = submit()
    assert not report['rejected']
    survivor = next(c for c in result['contexts'] if c['context_id'] == ids[0])
    assert survivor['support'] == merged['support']
    assert result['lineage'][-1]['input_refs'] == decision['input_refs']
    sources = {e['evidence_id']: e['source_id'] for e in result['evidence']}
    assert {sources[e] for s in survivor['support'] if s['target'] == '/description'
            for e in s['evidence_ids']} == {'SRC-1', 'SRC-2'}
    assert {sources[e] for s in survivor['support'] if s['target'] == '/time'
            for e in s['evidence_ids']} == {'SRC-1'}
    second['perspective'] = 'post_hoc'
    rejected, report = submit()
    assert any('perspective' in issue['reason'] for issue in report['rejected'])
    assert rejected['contexts'] == facts['contexts']


def test_joint_request_and_final_report_identify_only_unlinked_content_quotes(graph, payload):
    action = graph['actions'][0]
    action['delta_context_refs'] = []
    # EV-3 supports the content of CTX-2. A different Context uses that same
    # passage only to date the fact; another already applies from the Phase.
    original = graph['contexts'][0]
    timing = dict(original, context_id='DATE-ONLY', support=[
        dict(target='/description', mode='A', evidence_ids=['EV-1']),
        dict(target='/time', mode='A', evidence_ids=['EV-3'])])
    graph['contexts'].append(timing)
    original['support'].append(dict(target='/description', mode='A', evidence_ids=['EV-3']))
    before = deepcopy(graph)
    builder = Construction(SimpleNamespace(payload=payload, config=EventBuildConfig(max_context_chars=60000),
                                           state={'id_map': {}}))
    builder.graph = graph
    request = builder.relation_request(['ACTION-1'], ['PHASE-1'])
    expected = dict(action_id='ACTION-1', context_id='CTX-2', evidence_ids=['EV-3'])
    assert request['context_selection']['context_leads'] == [expected]
    assert not request['context_selection']['uncovered_action_ids']
    assert len(system_prompt('relations')) + len(prompt_json(dict(task=request, read_results=[]))) <= 45000

    report = check_graph(graph, payload)
    leads = [i for i in report['issues'] if i['code'] == 'CONTEXT_LINK_REVIEW']
    assert [(i['object_id'], i['severity'], i['evidence_ids']) for i in leads] == [('CTX-2', 'info', ['EV-3'])]
    assert report['valid'] and 'ACTION-1' in leads[0]['message']
    assert all(i['code'] != 'CONTEXT_LINK_REVIEW' for i in check_graph(graph, payload, complete=False)['issues'])
    assert graph == before

    # At the size needed for the ordinary request, leads may use space otherwise
    # taken by optional full Source records. The source index and passages stay available.
    base = {k: v for k, v in request.items() if k not in ('facts_index', 'related_records', 'context_selection')}
    ordinary = deepcopy(request)
    del ordinary['context_selection']['context_leads']
    limit = len(prompt_json(dict(task=ordinary, read_results=[])))
    tight = sized_request(base, graph, 60000, 60000 - limit)
    def substantive(req):
        return [item for item in req['related_records'] if item['collection'] != 'sources']

    assert substantive(tight) == substantive(ordinary)
    assert tight['facts_index']['sources'] == ordinary['facts_index']['sources']
    assert len(prompt_json(dict(task=tight, read_results=[]))) <= limit


def test_one_context_used_by_a_subset_retains_each_actions_own_role_and_evidence(graph, payload):
    for phase in graph['phases']:
        phase['baseline_context_refs'] = []
    first, briefing, publication = graph['actions']
    office_rule = graph['contexts'][0]['context_id']
    receipt = dict(context_ref_id='receipt', context_id=office_rule, relation_type='knowledge-source',
        entity_id=graph['person']['person_id'],
        support=[dict(target='/relation_type', mode='A', evidence_ids=['EV-3'])])
    public_constraint = dict(context_ref_id='public-constraint', context_id=office_rule, relation_type='constraint',
        support=[dict(target='/relation_type', mode='I', evidence_ids=['EV-2', 'EV-6'],
            reason='The documented restriction applied to public statements on the date Lee published the response.')])
    changes = [
        dict(action_id=first['action_id'], delta_context_refs=[*first['delta_context_refs'], receipt],
             baseline_context_exclusions=[]),
        dict(action_id=publication['action_id'], delta_context_refs=[public_constraint], baseline_context_exclusions=[])]
    result, report = Receiver(graph, payload, IdMap(), 'action-scope').relate(
        dict(contexts=[], relations=[], evidence=[], pending=[], phase_context_updates=[], action_context_updates=changes),
        action_ids=[first['action_id'], publication['action_id']], phase_ids=[])
    assert not report['rejected']
    assert result['contexts'] == graph['contexts']

    def links(action):
        return [entry['reference'] for entry in compose_context(result, action['action_id'])['associations']
                if entry['reference']['context_id'] == office_rule]

    [received], [constraint] = links(first), links(publication)
    assert (received['relation_type'], received['support']) == ('knowledge-source', receipt['support'])
    assert (constraint['relation_type'], constraint['support']) == ('constraint', public_constraint['support'])
    assert links(briefing) == []


def test_inherited_review_respects_exclusions_and_keeps_each_hard_error(graph, payload):
    phase, second = graph['phases'][0], graph['actions'][1]
    ref = phase['baseline_context_refs'][0]
    ref['relation_type'] = 'condition'

    def warning():
        [item] = [i for i in check_graph(graph, payload)['issues'] if i['code'] == 'KNOWLEDGE_REVIEW']
        return item

    item = warning()
    assert (item['object_id'], item['field'], item['evidence_ids']) == ('PHASE-1', '/baseline_context_refs/0', ['EV-2'])
    assert all(x in item['message'] for x in ('CREF-1', 'ACTION-1', 'ACTION-2'))
    assert 'ACTION-3' not in item['message']
    second['baseline_context_exclusions'] = [dict(context_ref_id='CREF-1', reason='Exception for this Action.',
        support=[dict(target='/context_ref_id', mode='A', evidence_ids=['EV-4'])])]
    assert 'ACTION-2' not in warning()['message'] and 'ACTION-1' in warning()['message']
    graph['contexts'][0]['perspective'] = 'post_hoc'
    errors = [i for i in check_graph(graph, payload)['issues'] if i['code'] == 'POST_HOC_CONTEXT']
    assert {i['object_id'] for i in errors} == {'PHASE-1', 'ACTION-1'}
    assert all(i['severity'] == 'error' for i in errors)
