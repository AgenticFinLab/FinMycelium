"""Context allocation preserves evidence access without repeating bulky metadata."""
from copy import deepcopy
import json

from test_person_event_contract import graph, payload, facts_from_graph
from finmy.person_epg.event.context import navigation, sized_request
from finmy.person_epg.event.records import prompt_json
from finmy.person_epg.event.runtime import Corpus, EventBuildConfig


def test_navigation_keeps_identity_and_locations_but_not_parser_bodies(graph, payload):
    facts = facts_from_graph(graph, payload)
    facts['entities'][0]['aliases'] = ['M. Lee']
    facts['actions'][0]['object'] = dict(description='A documented commitment',
        entity_refs=[facts['entities'][0]['entity_id']])
    facts['evidence'][0]['citations'][0]['locator'] = dict(parser_body='unrelated metadata ' * 10000)
    before = deepcopy(facts)
    index = navigation(facts)
    assert index['entities'][0]['aliases'] == ['M. Lee']
    assert index['actions'][0]['object']['entity_refs'] == facts['actions'][0]['object']['entity_refs']
    assert index['actions'][0]['object']['description_preview'] == 'A documented commitment'
    assert index['evidence_index'][0]['start'] == facts['evidence'][0]['citations'][0]['start']
    assert 'locator' not in index['evidence_index'][0]
    assert len(json.dumps(index)) < 10000
    evidence = facts['evidence'][0]
    read = Corpus(payload, facts, EventBuildConfig()).read(dict(tool='read_records', refs=[dict(
        collection='evidence', object_id=evidence['evidence_id'], field='/citations/0/quote')]))
    assert read[0]['value'] == evidence['citations'][0]['quote'] and facts == before


def test_context_compresses_navigation_before_required_body(graph, payload):
    facts = facts_from_graph(graph, payload)
    for action in facts['actions']:
        action['description'] *= 100
    body = dict(sample_id=payload['samples'][0]['sample_id'], start=0,
        end=len(payload['samples'][0]['content']), text=payload['samples'][0]['content'])
    request = sized_request(dict(role='extraction', body=body), facts, 500, 100)
    assert request['body'] == body
    assert request['context_selection']['navigation_preview_chars'] == 0
    assert len(request['facts_index']['actions']) == len(facts['actions'])
    assert not request['related_records']  # Runtime reports the limit; no silent body truncation.


def test_consolidation_supplies_referenced_evidence_without_duplicate_candidates(graph, payload):
    facts = facts_from_graph(graph, payload)
    action = facts['actions'][0]
    base = dict(role='consolidation', assigned=[dict(collection='actions', object_id=action['action_id'], field='')],
        candidates=[dict(collection='actions', record=action)])
    request = sized_request(base, facts, 30000, 4000)
    assert request['candidates'] == base['candidates']
    assert any(r['collection'] == 'evidence' for r in request['related_records'])
    assert not any(r['collection'] == 'actions' and r['record']['action_id'] == action['action_id']
                   for r in request['related_records'])


def test_organization_retains_all_action_navigation_even_with_optional_budget(graph, payload):
    facts = facts_from_graph(graph, payload)
    request = sized_request(dict(role='organization'), facts, 30000, 4000)
    assert {a['action_id'] for a in request['facts_index']['actions']} == {a['action_id'] for a in facts['actions']}
    supplied = {r['record']['evidence_id'] for r in request['related_records'] if r['collection'] == 'evidence'}
    needed = {eid for a in facts['actions'] for s in a['support'] for eid in s['evidence_ids']}
    assert needed <= supplied


def test_relation_request_delivers_each_act_and_the_link_under_one_budget(graph):
    # Background previews compete with the acts and an independently cited linking passage.
    actions = graph['actions']
    context = graph['contexts'][0]
    graph['contexts'].extend(dict(context, context_id=f'CTX-{i}', description='Long background account. ' * 12)
                             for i in range(16))
    graph['relations'] = []
    passage = graph['evidence'][0]
    candidate = dict(candidate_id='lead', from_action_id=actions[0]['action_id'], to_action_id=None,
                     support=[dict(target='/description', mode='A', evidence_ids=[passage['evidence_id']])])
    base = dict(role='relations', assigned_action_ids=[a['action_id'] for a in actions],
                assigned_phase_ids=[], assigned_records=dict(actions=actions, phases=[]), relation_candidates=[candidate])
    original = deepcopy(graph)
    roomy = sized_request(base, graph, 100000, 4000)
    roomy['related_records'] = []
    roomy['context_selection']['related_included'] = 0
    limit = len(prompt_json(dict(task=roomy, read_results=[]))) + 450
    reserve = 4000
    request = sized_request(base, graph, limit + reserve, reserve)
    included = [row['record'] for row in request['related_records'] if row['collection'] == 'evidence']
    ids = {row['evidence_id'] for row in included}
    for action in actions:
        assert any(ids.intersection(s['evidence_ids']) for s in action['support'] if s['target'] == '/description')
    assert passage['evidence_id'] in ids
    assert len(ids) == len(included)
    by_id = {e['evidence_id']: e for e in original['evidence']}
    for row in included:
        source = by_id[row['evidence_id']]
        assert row == {k: source[k] for k in row}
    assert 0 < request['context_selection']['navigation_preview_chars'] < 160
    assert len(prompt_json(dict(task=request, read_results=[]))) <= limit
    assert request['assigned_records'] == base['assigned_records'] and graph == original


def test_repair_identifies_already_adopted_links_at_either_end(graph):
    first, second, third = (a['action_id'] for a in graph['actions'])
    existing = graph['relations'][0]
    other = dict(existing, relation_id='other', from_action_id=first, to_action_id=third)
    graph['relations'] = [existing, other]
    request = sized_request(dict(role='relations', assigned_action_ids=[second], repair_issues=[]),
                            graph, 30000, 4000)
    fields = ('relation_id', 'from_action_id', 'to_action_id', 'type', 'basis')
    assert request['facts_index']['relations'] == [{k: existing[k] for k in fields}]
    assert 'relations' not in navigation(graph, role='organization')
