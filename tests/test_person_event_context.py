"""Context allocation preserves evidence access without repeating bulky metadata."""
from copy import deepcopy
import json

from test_person_event_contract import graph, payload, facts_from_graph
from finmy.person_epg.event.context import navigation, sized_request
from finmy.person_epg.event.runtime import Corpus, EventBuildConfig


def test_navigation_keeps_identity_and_locations_but_not_parser_bodies(graph, payload):
    facts = facts_from_graph(graph, payload)
    facts['entities'][0]['aliases'] = ['M. Lee']
    facts['actions'][0]['object'] = dict(description='A documented commitment',
        entity_refs=[facts['entities'][0]['entity_id']])
    facts['evidence'][0]['locator'] = dict(parser_body='unrelated metadata ' * 10000)
    before = deepcopy(facts)
    index = navigation(facts)
    assert index['entities'][0]['aliases'] == ['M. Lee']
    assert index['actions'][0]['object']['entity_refs'] == facts['actions'][0]['object']['entity_refs']
    assert index['actions'][0]['object']['description_preview'] == 'A documented commitment'
    assert index['evidence_index'][0]['start'] == facts['evidence'][0]['start']
    assert 'locator' not in index['evidence_index'][0]
    assert len(json.dumps(index)) < 10000
    evidence = facts['evidence'][0]
    read = Corpus(payload, facts, EventBuildConfig()).read(dict(tool='read_records', refs=[dict(
        collection='evidence', object_id=evidence['evidence_id'], field='/quote')]))
    assert read[0]['value'] == evidence['quote'] and facts == before


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
