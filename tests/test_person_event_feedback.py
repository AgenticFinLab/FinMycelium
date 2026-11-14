"""Bounded adoption repair using authored evidence; no remote services."""
from copy import deepcopy
import json

import pytest

from test_person_event_contract import graph, payload, facts_from_graph
from test_person_event_pipeline import SyntheticEventModel, no_network
from finmy.person_epg.event.build import Construction, run_event, body_ranges, brief
from finmy.person_epg.event.proposals import FIELDS, Receiver, reference, replace_references
from finmy.person_epg.event.records import IdMap, seed_facts, unknown_time
from finmy.person_epg.event.runtime import EventBuildConfig, Execution
from finmy.person_epg.event.validation import critical_fields, check_graph


def repair_actor(request, *, fix=True):
    result = {k: [] for k in (*FIELDS['extraction'], 'evidence', 'pending')}
    for issue in request['correction']['issues']:
        for item in issue.get('proposal', []) if isinstance(issue.get('proposal'), list) else []:
            record = deepcopy(item['record'])
            if fix and item['collection'] == 'actions':
                support = next(s for s in record['support'] if s['target'] == '/description')
                record['support'].append({**support, 'target': '/actor'})
            result[item['collection']].append(record)
    return result


def missing_actor_response(base, system, user, name):
    response = base(system, user, name)
    if name == 'extract.0':
        response['actions'][0]['support'] = [s for s in response['actions'][0]['support'] if s['target'] != '/actor']
    return response


def test_alias_additions_reuse_identity_without_overwriting_it(payload):
    facts = seed_facts(payload)
    original = deepcopy(facts['entities'][0])
    original['aliases'] = ['M. Lee', 'M. Lee']
    response = {k: [] for k in (*FIELDS['extraction'], 'evidence', 'pending')}
    response['entities'] = [original]
    result, report = Receiver(facts, payload, IdMap(), 'aliases').extract(response)
    assert not report['rejected']
    assert result['entities'][0]['aliases'] == ['M. Lee']
    changed = deepcopy(original)
    changed['name'] = 'An unrelated person'
    response['entities'] = [changed]
    retained, report = Receiver(result, payload, IdMap(), 'conflict').extract(response)
    assert report['rejected'] and retained['entities'] == result['entities']


def test_rejected_candidate_gets_field_feedback_and_is_repaired_once(tmp_path, payload):
    base, requests = SyntheticEventModel(), []
    def model(system, user, name):
        request = json.loads(user)['task']
        if 'correction' in request:
            requests.append(request)
            assert set(request['correction']['allowed_records']) == {'actions'}
            fields = {i['field'] for r in request['correction']['issues'] for i in r['issues']}
            assert {'/actor/entity_id', '/actor/capacity'} <= fields
            return repair_actor(request)
        return missing_actor_response(base, system, user, name)
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == 'draft', state
    final = json.loads((tmp_path / state['output']).read_text())
    assert len(final['actions']) == 3
    rejected_id = requests[0]['correction']['allowed_records']['actions'][0]
    assert rejected_id in {a['action_id'] for a in final['actions']}
    assert len(requests) == 1 and len(state['calls']) == 6
    assert not json.loads((tmp_path / state['facts']).read_text())['pending']
    before = len(state['calls'])
    resumed = run_event(payload, tmp_path, model=model, resume=True)
    assert resumed['result_status'] == 'draft' and len(resumed['calls']) == before
    assert len(requests) == 1


def test_format_and_adoption_failures_share_the_persisted_allowance(tmp_path, payload):
    base, names = SyntheticEventModel(), []
    def model(system, user, name):
        names.append(name)
        request = json.loads(user)['task']
        if len(names) == 1:
            return 'invalid json'
        if 'correction' in request:
            return repair_actor(request, fix=False)
        return missing_actor_response(base, system, user, name)
    state = run_event(payload, tmp_path, dict(max_json_attempts=3), model=model)
    assert state['result_status'] == 'partial'
    assert sum(n.startswith('extract.0') for n in names) == 3
    count = len(names)
    resumed = run_event(payload, tmp_path, dict(max_json_attempts=3), model=model, resume=True)
    assert len(names) == count and resumed['result_status'] == 'partial'


def test_pause_during_correction_keeps_valid_neighbors_and_attempt_budget(tmp_path, payload):
    base = SyntheticEventModel()
    def model(system, user, name):
        request = json.loads(user)['task']
        if 'correction' in request:
            return repair_actor(request)
        response = missing_actor_response(base, system, user, name)
        if name == 'extract.0':
            (tmp_path / 'pause_requested').write_text('pause')
        return response
    first = run_event(payload, tmp_path, model=model)
    assert first['execution_status'] == 'paused'
    facts = json.loads((tmp_path / first['facts']).read_text())
    assert facts['evidence']  # The first reply was adopted before the pause.
    assert sum(map(len, first['validation_attempts'].values())) == 1
    resumed = run_event(payload, tmp_path, model=model, resume=True)
    assert resumed['result_status'] == 'draft'
    assert sum(map(len, resumed['validation_attempts'].values())) == 1
    assert base.calls.count('extract.0') == 1


def test_generated_field_contract_covers_conditional_object_and_identity(graph):
    action = deepcopy(graph['actions'][0])
    action['object']['entity_refs'] = ['COUNTERPARTY']
    action['actor'].update(capacity='official', role='Chair', on_behalf_of='COMPANY')
    assert {'/object/entity_refs', '/actor/role', '/actor/on_behalf_of'} <= set(critical_fields('actions', action))
    del action['object']
    assert '/object' in critical_fields('actions', action)


def test_consolidation_retries_only_the_unhandled_candidate(tmp_path, graph, payload):
    facts = facts_from_graph(graph, payload)
    first, second = facts['actions'][:2]
    calls = []
    def model(system, user, name):
        request = json.loads(user)['task']
        calls.append(request)
        assigned = request['assigned'] if 'correction' in request else request['assigned'][:1]
        return dict(decisions=[dict(operation='keep', input_refs=[ref], outputs=[],
            reason='Retain the supported independent act.', evidence_ids=[]) for ref in assigned], evidence=[], pending=[])
    construction = Construction(Execution(tmp_path, payload, EventBuildConfig(), model))
    construction.facts = facts
    assigned = {('actions', a['action_id']) for a in (first, second)}
    result, report = construction.receive('consolidate.0', 'consolidation', facts,
        construction.request('consolidation', facts, assigned=[reference(c, oid) for c, oid in sorted(assigned)]), assigned=assigned)
    assert not report['rejected'] and not report['pending'] and not result['pending']
    assert len(calls) == 2 and len(calls[1]['assigned']) == 1
    assert len(result['lineage']) == 2


def test_connected_proposals_can_finish_in_two_corrections_without_repeating_good_records(tmp_path, graph, payload):
    facts = facts_from_graph(graph, payload)
    actions = deepcopy(facts['actions'][:2])
    facts['actions'] = []
    actions[0]['support'] = [s for s in actions[0]['support'] if s['target'] != '/actor']
    candidate = dict(candidate_id='CANDIDATE', from_action_id=actions[0]['action_id'], to_action_id=actions[1]['action_id'],
        type='responds_to', description='The authored record describes a response.',
        support=[dict(target='', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']])])
    calls = []
    def model(system, user, name):
        request = json.loads(user)['task']
        calls.append(request)
        if 'correction' not in request:
            return dict(entities=[], actions=actions, contexts=[], relation_candidates=[candidate], evidence=[], pending=[])
        response = repair_actor(request)
        if len(calls) == 2:
            response['actions'] = response['actions'][:1]
            response['relation_candidates'] = []
        return response
    execution = Execution(tmp_path, payload, EventBuildConfig(), model)
    construction = Construction(execution)
    construction.facts = facts
    result, report = construction.receive('extract.0', 'extraction', facts, construction.request('extraction', facts))
    assert not report['rejected'] and not result['pending']
    assert len(result['actions']) == 2 and len(result['relation_candidates']) == 1
    assert len(calls) == 3
    assert len(calls[-1]['correction']['allowed_records']['actions']) == 1


def test_final_hierarchy_repair_preserves_rejected_ids_and_closes_matching_issues(tmp_path, payload):
    base = SyntheticEventModel()
    def model(system, user, name):
        request = json.loads(user)['task']
        value = base(system, user, name)
        if name == 'organize':
            value['stages'][0]['support'] = [s for s in value['stages'][0]['support'] if s['target'] != '/boundary_reason']
        if name == 'repair.organization':
            maps = {'stages': {}, 'phases': {}}
            retained = {'stages': set(), 'phases': set()}
            for issue in request['repair_issues']:
                record = issue.get('proposal')
                for collection, key in [('stages', 'stage_id'), ('phases', 'phase_id')]:
                    if isinstance(record, dict) and key in record:
                        for item in value[collection]:
                            if item['name'] == record['name']:
                                maps[collection][item[key]] = record[key]
                                retained[collection].add(record[key])
            value = replace_references(value, maps)
            for collection, key in [('stages', 'stage_id'), ('phases', 'phase_id')]:
                value[collection] = [r for r in value[collection] if r[key] in retained[collection]]
            value['assignments'] = [a for a in value['assignments'] if a['action_id'] in request['assigned_action_ids']]
        if name == 'repair.relations':
            # Match the original rejected Context IDs by their descriptions.
            maps = {'contexts': {}, 'context_refs': {}}
            for known in request['facts_index']['contexts']:
                for ctx in value['contexts']:
                    if known.get('description_preview') == ctx['description']:
                        maps['contexts'][ctx['context_id']] = known['context_id']
            for issue in request['repair_issues']:
                record = issue.get('proposal')
                if isinstance(record, dict) and 'context_id' in record:
                    for ctx in value['contexts']:
                        if ctx['description'] == record['description']:
                            maps['contexts'][ctx['context_id']] = record['context_id']
            value = replace_references(value, maps)
            for entry in request['related_records']:
                collection, old = entry['collection'], entry['record']
                if collection == 'phases' and old.get('baseline_context_refs'):
                    for update in value['phase_context_updates']:
                        if update['phase_id'] == old['phase_id']:
                            update['baseline_context_refs'] = deepcopy(old['baseline_context_refs'])
                if collection == 'actions' and old.get('delta_context_refs'):
                    for update in value['action_context_updates']:
                        if update['action_id'] == old['action_id']:
                            update['delta_context_refs'] = deepcopy(old['delta_context_refs'])
        return value
    state = run_event(payload, tmp_path, model=model)
    checks = json.loads((tmp_path / state['checks']).read_text())
    assert state['result_status'] == 'draft', checks['unresolved_tasks']
    assert state['final_repair_used']


def test_read_body_with_unresolved_proposals_is_not_reported_as_unread(tmp_path, payload):
    base = SyntheticEventModel()
    def model(system, user, name):
        request = json.loads(user)['task']
        if 'correction' in request:
            return {k: [] for k in (*FIELDS['extraction'], 'evidence', 'pending')} | {'note': 'No correction supplied.'}
        return missing_actor_response(base, system, user, name)
    state = run_event(payload, tmp_path, model=model)
    checks = json.loads((tmp_path / state['checks']).read_text())
    codes = {i['code'] for i in checks['issues']}
    assert state['result_status'] == 'partial'
    assert all(b['body_status'] == 'processed' for b in state['coverage'])
    assert any(b['proposal_status'] == 'unresolved' for b in state['coverage'])
    assert 'BODY_PROCESSING_INCOMPLETE' not in codes and 'PROPOSALS_UNRESOLVED' in codes
    assert any(r['report']['rejected'] for r in checks['unresolved_tasks'])


def test_failed_body_remains_unprocessed_when_response_never_parses(tmp_path, payload):
    state = run_event(payload, tmp_path, dict(max_json_attempts=1), model=lambda *a: 'invalid')
    assert state['result_status'] != 'draft'
    assert all(b['body_status'] == 'failed' for b in state['coverage'])
    checks = json.loads((tmp_path / state['checks']).read_text())
    assert 'BODY_PROCESSING_INCOMPLETE' in {i['code'] for i in checks['issues']}


@pytest.mark.parametrize('behavior,storyline', [
    ('decided to establish a fund', 'Philanthropy'),
    ('authorized a representative to arrange care', 'Family and health'),
    ('communicated a proposal to colleagues', 'Public communication'),
    ('publicly committed to provide support', 'Philanthropy'),
    ('responded to concerns from a relative', 'Family and health'),
    ('adjusted the planned allocation', 'Securities investments'),
])
def test_supported_official_conduct_survives_unknown_time_and_object(tmp_path, payload, behavior, storyline):
    # These test adoption/assembly, not whether a real model finds the behavior.
    payload['user_query']['extras']['person_event']['storyline_name'] = storyline
    model = SyntheticEventModel()
    model.graph['storyline']['name'] = storyline
    sample = payload['samples'][0]
    first = model.graph['evidence'][0]
    old = first['quote']
    quote = 'In her role as chair, Mina Lee ' + behavior + '. The exact date and further details were not disclosed.'
    sample['content'] = sample['content'].replace(old, quote)
    first['quote'] = quote
    model.bind(payload)
    action = model.graph['actions'][0]
    action.update(name=behavior, description=quote, actor=dict(entity_id=action['actor']['entity_id'],
        capacity='official', role='Chair'), time=unknown_time())
    del action['object']
    action['support'] = [s for s in action['support'] if s['target'] not in ('/time', '/object')]
    action['gaps'] = [dict(target='/time', reason='The date is not disclosed.'),
                      dict(target='/object', reason='No further object details are established.')]
    model.graph['relations'] = [r for r in model.graph['relations'] if not (
        r['basis'] == 'derived' and action['action_id'] in (r['from_action_id'], r['to_action_id']))]
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == 'draft', state
    final = json.loads((tmp_path / state['output']).read_text())
    retained = next(a for a in final['actions'] if a['name'] == behavior)
    assert retained['time']['start'] is None and retained['actor']['capacity'] == 'official'
    assert not state['final_repair_used'] and len(state['calls']) == 5


def test_company_execution_requires_attribution_review_not_automatic_person_rewrite(payload):
    model = SyntheticEventModel()
    quote = 'The office announced a new policy. This source does not identify Mina Lee as its decision maker.'
    evidence = model.graph['evidence'][0]
    payload['samples'][0]['content'] = payload['samples'][0]['content'].replace(evidence['quote'], quote)
    evidence['quote'] = quote
    model.bind(payload)
    action = model.graph['actions'][0]
    action.update(description=quote, actor=dict(entity_id='ENTITY-OFFICE', capacity='unknown'))
    facts = seed_facts(payload)
    request = dict(role='extraction', facts_index=brief(facts), body=next(body_ranges(payload, EventBuildConfig())))
    raw = model('', json.dumps(dict(task=request)), 'extract.0')
    facts, report = Receiver(facts, payload, IdMap(), 'company').extract(raw)
    assert not report['rejected'], report
    retained = next(a for a in facts['actions'] if a['description'] == quote)
    actor = next(e for e in facts['entities'] if e['entity_id'] == retained['actor']['entity_id'])
    assert actor['name'] != facts['person']['name']
    checks = check_graph(facts, payload, complete=False)
    assert any(i['code'] == 'ATTRIBUTION_REVIEW' and i['object_id'] == retained['action_id'] for i in checks['issues'])
    # An explicit semantic decision can exclude the non-focal action; the receiver
    # does not claim that matching the quoted text proves personal attribution.
    ref = reference('actions', retained['action_id'])
    response = dict(decisions=[dict(operation='exclude', input_refs=[ref], outputs=[],
        reason='The source attributes this act only to the office, not the focal person.', evidence_ids=[])],
        evidence=[], pending=[])
    final, report = Receiver(facts, payload, IdMap(), 'exclude-company').consolidate(
        response, assigned={('actions', retained['action_id'])})
    assert not report['rejected'], report
    assert all(a['action_id'] != retained['action_id'] for a in final['actions'])
    assert final['lineage'][-1]['operation'] == 'exclude'
