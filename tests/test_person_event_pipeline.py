"""Synthetic six-step integration; socket connections are forbidden."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from test_person_event_contract import FIXTURES, graph, payload
from finmy.person_epg.event.build import body_ranges, run_event
from finmy.person_epg.event.proposals import Receiver, graph_from_facts, reference, replace_references
from finmy.person_epg.event.records import IdMap, seed_facts, sha256
from finmy.person_epg.event.runtime import EventBuildConfig
from finmy.person_epg.event.validation import check_graph


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Real network is forbidden'))


class SyntheticEventModel:
    """Answers from the authored design, using only IDs actually exposed to the task."""
    last_usage = {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}

    def __init__(self):
        self.graph = json.loads((FIXTURES / 'graph.json').read_text())
        self.calls = []

    def bind(self, payload):
        for evidence in self.graph['evidence']:
            matches = [sample for sample in payload['samples'] if evidence['quote'] in sample['content']]
            assert len(matches) == 1
            sample = matches[0]
            evidence.update(sample_id=sample['sample_id'], source_id=sample['raw_data_id'],
                start=sample['content'].index(evidence['quote']),
                end=sample['content'].index(evidence['quote']) + len(evidence['quote']))

    def __call__(self, system, user, name):
        request = json.loads(user)['task']
        self.calls.append(name)
        role, graph = request['role'], deepcopy(self.graph)
        index = request['facts_index']
        maps = {}
        for collection, key in [('entities', 'entity_id'), ('actions', 'action_id'), ('stages', 'stage_id'), ('phases', 'phase_id')]:
            maps[collection] = {record[key]: next((r[key] for r in index[collection] if r.get('name') == record.get('name')), record[key])
                                for record in graph[collection]}
        maps['evidence'] = {e['evidence_id']: next((r['evidence_id'] for r in index['evidence_index']
                             if r['sample_id'] == e['sample_id'] and r['start'] == e['start'] and r['end'] == e['end']), e['evidence_id'])
                            for e in graph['evidence']}
        graph = replace_references(graph, maps)
        if role == 'extraction':
            block = request['body']
            evidence = [dict(evidence_id=e['evidence_id'], sample_id=e['sample_id'], quote=e['quote'], start=e['start'], end=e['end'])
                        for e in graph['evidence'] if e['sample_id'] == block['sample_id'] and block['start'] <= e['start'] and e['end'] <= block['end']]
            ev_ids = {e['evidence_id'] for e in evidence}
            actions = []
            for action in graph['actions']:
                support = [s for s in action['support'] if s['target'] != '/phase_id']
                if support and all(set(s['evidence_ids']) <= ev_ids for s in support):
                    action.update(phase_id=None, support=support)
                    action.pop('delta_context_refs', None)
                    action.pop('baseline_context_exclusions', None)
                    actions.append(action)
            return dict(entities=graph['entities'], actions=actions, contexts=[], relation_candidates=[], evidence=evidence,
                        pending=[], note='Synthetic continuous body processed.')
        if role == 'consolidation':
            return dict(decisions=[dict(operation='keep', input_refs=[r], outputs=[], reason='Distinct documented action.', evidence_ids=[])
                                   for r in request['assigned']], evidence=[], pending=[])
        if role == 'organization':
            assignments = []
            for action in graph['actions']:
                assignments.append(dict(action_id=action['action_id'], phase_id=action['phase_id'],
                    support=[s for s in action['support'] if s['target'] == '/phase_id']))
            for phase in graph['phases']:
                phase['baseline_context_refs'] = []
            return dict(stages=graph['stages'], phases=graph['phases'], assignments=assignments, split_proposals=[],
                        event_overview={k: graph['event'][k] for k in ('time', 'summary', 'support')}, evidence=[], pending=[])
        if role == 'relations':
            return dict(contexts=graph['contexts'], relations=graph['relations'],
                phase_context_updates=[dict(phase_id=p['phase_id'], baseline_context_refs=p['baseline_context_refs'])
                                       for p in graph['phases'] if p['phase_id'] in request['assigned_phase_ids']],
                action_context_updates=[dict(action_id=a['action_id'], delta_context_refs=a.get('delta_context_refs', []),
                                             baseline_context_exclusions=a.get('baseline_context_exclusions', []))
                                        for a in graph['actions'] if a['action_id'] in request['assigned_action_ids']], evidence=[], pending=[])
        raise AssertionError(role)


def test_complete_new_protocol_pipeline(tmp_path, payload):
    model = SyntheticEventModel()
    state = run_event(payload, tmp_path, model=model)
    assert state['execution_status'] == 'finished', state
    assert state['result_status'] == 'draft', json.loads((tmp_path / state['checks']).read_text())
    graph_path = tmp_path / state['output']
    graph = json.loads(graph_path.read_text())
    assert graph['schema_version'] == 'person-event-1.0'
    assert check_graph(graph, payload)['valid']
    assert sha256(graph_path.read_bytes()) == state['graph_sha256']
    assert len(graph['actions']) == 3 and len(graph['phases']) == 2
    assert len(model.calls) == 5
    assert all(r['status'] == 'processed' for r in state['coverage'])
    assert json.loads((tmp_path / state['checks']).read_text())['review_required']


def test_budget_resume_does_not_repeat_body_or_change_ids(tmp_path, payload):
    model = SyntheticEventModel()
    first = run_event(payload, tmp_path, {'max_calls': 1}, model=model)
    assert first['execution_status'] == 'limit' and len(first['calls']) == 1
    old_actions = json.loads((tmp_path / first['facts']).read_text())['actions']
    second = run_event(payload, tmp_path, {'max_calls': 10}, model=model, resume=True)
    assert second['result_status'] == 'draft', json.loads((tmp_path / second['checks']).read_text())
    assert model.calls.count('extract.0') == 1
    graph = json.loads((tmp_path / second['output']).read_text())
    assert old_actions[0]['action_id'] in {a['action_id'] for a in graph['actions']}
    assert len(second['calls']) == 5


def test_body_ranges_cover_all_text_without_hidden_truncation(payload):
    config = EventBuildConfig(extraction_chars=40, extraction_overlap=7)
    blocks = list(body_ranges(payload, config))
    for sample in payload['samples']:
        covered = set()
        for block in blocks:
            if block['sample_id'] == sample['sample_id']:
                covered.update(range(block['start'], block['end']))
        assert covered == set(range(len(sample['content'])))


def test_bad_neighbor_is_not_adopted_or_allowed_to_delete_good_action(payload, graph):
    facts = seed_facts(payload)
    good = deepcopy(graph['actions'][0])
    good['phase_id'] = None
    good['support'] = [s for s in good['support'] if s['target'] != '/phase_id']
    good.pop('delta_context_refs', None)
    bad = deepcopy(good)
    bad.update(action_id='BAD', name='Unsupported neighbor')
    bad['actor']['entity_id'] = 'MISSING'
    response = dict(entities=graph['entities'], actions=[good, bad], contexts=[], relation_candidates=[],
        evidence=[{k: e[k] for k in ('evidence_id', 'sample_id', 'quote', 'start', 'end')} for e in graph['evidence']], pending=[])
    result, report = Receiver(facts, payload, IdMap(), 'test').extract(response)
    assert len(result['actions']) == 1 and report['rejected']
    assert result['actions'][0]['name'] == good['name']
    assert result['pending']


def test_no_permission_does_not_create_run(tmp_path, payload):
    target = tmp_path / 'not-created'
    with pytest.raises(PermissionError):
        run_event(payload, target)
    assert not target.exists()


def test_final_repair_round_is_not_replenished(tmp_path, payload):
    base = SyntheticEventModel()

    def omit_assignments(system, user, name):
        value = base(system, user, name)
        if name in ('organize', 'repair.organization'):
            value['assignments'] = []
        return value
    first = run_event(payload, tmp_path, model=omit_assignments)
    assert first['final_repair_used'] and first['result_status'] == 'partial'
    count = len(base.calls)
    second = run_event(payload, tmp_path, model=omit_assignments, resume=True)
    assert second['result_status'] == 'partial' and len(base.calls) == count


def test_unrelated_pending_survives_local_relation_repair(tmp_path, payload):
    base = SyntheticEventModel()
    unresolved_reason = 'A further focal action is evidenced but has not been extracted or assigned.'
    def model(system, user, name):
        req = json.loads(user)['task']
        if name == 'repair.relations':
            # Complete the requested association fields, without resolving the missing action.
            return dict(contexts=[], relations=[], phase_context_updates=[],
                action_context_updates=[dict(action_id=aid, delta_context_refs=[], baseline_context_exclusions=[])
                                        for aid in req['assigned_action_ids']], evidence=[], pending=[])
        value = base(system, user, name)
        if name == 'relate.0':
            aid = req['assigned_action_ids'][0]
            value['pending'].append(dict(refs=[reference('actions', aid)], reason=unresolved_reason, evidence_ids=[]))
            value['relations'].append(dict(relation_id='INVALID-NEIGHBOR', from_action_id=aid,
                to_action_id='ABSENT-ACTION', type='responds_to', basis='asserted',
                support=deepcopy(value['relations'][-1]['support'])))
        return value
    state = run_event(payload, tmp_path / 'repair', model=model)
    adoption = json.loads((tmp_path / 'repair' / 'attempts/0001/adoption.json').read_text())
    before = next(r for r in adoption if r['task_id']=='relate.0')
    assert any(p['reason'] == unresolved_reason for p in before['report']['pending'])
    assert state['final_repair_used']
    assert state['result_status'] == 'partial', {'status':state['result_status'], 'pending_marked_resolved_by':before.get('resolved_by')}
    checks = json.loads((tmp_path / 'repair' / state['checks']).read_text())
    assert any(p['reason'] == unresolved_reason for r in checks['unresolved_tasks'] for p in r['report']['pending'])


@pytest.mark.parametrize('explicit_pending', [False, True])
def test_repair_resolves_only_its_verified_work(tmp_path, payload, explicit_pending):
    base = SyntheticEventModel()
    reason = 'An additional focal action still needs extraction and assignment.'
    def model(system, user, name):
        value = base(system, user, name)
        if name == 'relate.0':
            omitted = value['action_context_updates'].pop()
            if explicit_pending:
                value['pending'].append(dict(refs=[reference('actions', omitted['action_id'])],
                    reason=reason, evidence_ids=[]))
        if name == 'repair.relations':
            request = json.loads(user)['task']
            return dict(contexts=[], relations=[], phase_context_updates=[],
                action_context_updates=[dict(action_id=aid, delta_context_refs=[], baseline_context_exclusions=[])
                    for aid in request['assigned_action_ids']], evidence=[], pending=[])
        return value
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == ('partial' if explicit_pending else 'draft')
    checks = json.loads((tmp_path / state['checks']).read_text())
    pending = [p for r in checks['unresolved_tasks'] for p in r['report']['pending']]
    assert any(p['reason'] == reason for p in pending) == explicit_pending
    assert not any(r['report']['rejected'] for r in checks['unresolved_tasks'])
    count = len(base.calls)
    resumed = run_event(payload, tmp_path, model=model, resume=True)
    assert resumed['result_status'] == state['result_status']
    assert len(base.calls) == count


def test_missing_action_field_support_is_rejected_before_completion(tmp_path, payload):
    base = SyntheticEventModel()
    def model(system, user, name):
        value = base(system, user, name)
        if name.startswith('extract.'):
            for action in value['actions']:
                action['support'] = [s for s in action['support'] if s['target'] not in ('/actor','/time')]
        return value
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == 'partial'
    checks = json.loads((tmp_path / state['checks']).read_text())
    assert any('FIELD_SUPPORT_OR_GAP_REQUIRED' in issue['reason'] for r in checks['unresolved_tasks'] for issue in r['report']['rejected'])
    assert not state['final_repair_used']


def test_valid_information_gap_completes_without_a_repair_round(tmp_path, payload):
    model = SyntheticEventModel()
    model.graph['actions'][0].setdefault('gaps', []).append(dict(
        target='/action_type', reason='No narrower action category is established.'))
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == 'draft'
    assert len(model.calls) == 5 and not state['final_repair_used']
