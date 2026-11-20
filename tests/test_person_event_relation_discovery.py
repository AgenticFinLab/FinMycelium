"""Offline discovery receipts and the reproduced nested ContextRef target failure."""
from copy import deepcopy
import json

import pytest

from test_person_event_contract import graph, payload
from test_person_event_pipeline import SyntheticEventModel, no_network
from test_person_event_relation_experiment import baseline
from finmy.person_epg.event.feedback import validate_correction
from finmy.person_epg.event.proposals import FIELDS
from finmy.person_epg.event.relation_experiment import load_snapshot, run_relations
from finmy.person_epg.event.relation_review import validate_review
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.runtime import EventBuildConfig
from types import SimpleNamespace


def empty_response():
    return {k: [] for k in (*FIELDS['relations'], 'evidence', 'pending')}


def complete_review(graph):
    pairs = {}
    for r in graph['relations']:
        pair = pairs.setdefault((r['from_action_id'], r['to_action_id']), dict(
            from_action_id=r['from_action_id'], to_action_id=r['to_action_id'], status='linked',
            relation_ids=[], evidence_ids=[], reason='Authored relationship.'))
        pair['relation_ids'].append(r['relation_id'])
    return dict(actions=[dict(action_id=a['action_id'], status='complete', within_phase='Checked local actions.',
                             cross_phase='Checked actions in other phases.') for a in graph['actions']],
                candidates=[], pairs=list(pairs.values()))


@pytest.mark.parametrize('fault', ['missing_action', 'duplicate_action', 'pending_action', 'missing_pair',
                                   'bad_endpoint', 'unknown_evidence', 'unaccepted_relation', 'missing_candidate'])
def test_incomplete_or_invalid_receipt_cannot_complete(graph, fault):
    review = complete_review(graph)
    scope = dict(action_ids=[a['action_id'] for a in graph['actions']], candidate_ids=[])
    if fault == 'missing_action': review['actions'].pop()
    elif fault == 'duplicate_action': review['actions'].append(deepcopy(review['actions'][0]))
    elif fault == 'pending_action': review['actions'][0]['status'] = 'pending'
    elif fault == 'missing_pair': review['pairs'] = []
    elif fault == 'bad_endpoint': review['pairs'][0]['to_action_id'] = review['pairs'][0]['from_action_id']
    elif fault == 'unknown_evidence': review['pairs'][0]['evidence_ids'] = ['ABSENT']
    elif fault == 'unaccepted_relation': review['pairs'][0]['relation_ids'] = ['ABSENT']
    elif fault == 'missing_candidate': scope['candidate_ids'] = ['CANDIDATE']
    with pytest.raises(ValueError):
        validate_review(review, scope, graph)


def test_discovery_accepts_cross_batch_targets_and_zero_edges(graph):
    relation = next(r for r in graph['relations'] if
        next(a['phase_id'] for a in graph['actions'] if a['action_id'] == r['from_action_id']) !=
        next(a['phase_id'] for a in graph['actions'] if a['action_id'] == r['to_action_id']))
    source = relation['from_action_id']
    review = complete_review(graph)
    review['actions'] = [a for a in review['actions'] if a['action_id'] == source]
    review['pairs'] = [p for p in review['pairs'] if p['from_action_id'] == source]
    validate_review(review, dict(action_ids=[source], candidate_ids=[]), graph)
    graph['relations'] = []
    review['pairs'] = []
    validate_review(review, dict(action_ids=[source], candidate_ids=[]), graph)


def test_missing_review_is_partial_and_retry_budget_survives_resume(tmp_path, baseline):
    _, snapshot = baseline
    base = SyntheticEventModel()
    def model(system, user, name):
        value = base(system, user, name)
        value.pop('relation_review', None)
        return value
    root = tmp_path / 'missing'
    state = run_relations(snapshot, root, config={'max_json_attempts': 3}, model=model)
    assert state['execution_status'] == 'finished' and state['result_status'] == 'partial'
    assert len(base.calls) == 4
    report = json.loads((root / state['relation_discovery']).read_text())
    assert report['incomplete_action_ids'] and not report['completed_action_ids']
    before = deepcopy(state['calls'])
    resumed = run_relations(snapshot, root, model=model, resume=True)
    assert resumed['calls'] == before and len(base.calls) == 4
    assert resumed['result_status'] == 'partial'


def test_missing_review_can_be_completed_without_regenerating_edges(tmp_path, baseline):
    _, snapshot = baseline
    base, corrections = SyntheticEventModel(), []
    def model(system, user, name):
        value = base(system, user, name)
        if name.startswith('evidence_merge.'):
            return value
        if name == 'relate.0':
            value.pop('relation_review')
        else:
            corrections.append(json.loads(user)['task'])
            assert not any(value[k] for k in FIELDS['relations'])
        return value
    root = tmp_path / 'review-corrected'
    state = run_relations(snapshot, root, model=model)
    assert state['result_status'] == 'draft'
    assert len(corrections) == 1 and corrections[0]['accepted_relations']
    assert not corrections[0]['assigned_action_ids']
    assert corrections[0]['relation_discovery']['action_ids']
    assert len(json.loads((root / state['output']).read_text())['relations']) == len(base.graph['relations'])


def test_candidates_have_one_owner_even_across_batches(payload, graph):
    builder = Construction(SimpleNamespace(payload=payload, config=EventBuildConfig(), state={'id_map': {}}))
    builder.graph = graph
    a, b = graph['actions'][:2]
    builder.facts['relation_candidates'] = [
        dict(candidate_id='KNOWN', from_action_id=a['action_id'], to_action_id=b['action_id']),
        dict(candidate_id='TARGET', from_action_id=None, to_action_id=b['action_id']),
        dict(candidate_id='UNKNOWN', from_action_id=None, to_action_id=None)]
    owners = [builder.relation_request([x['action_id']], [])['relation_discovery']['candidate_ids']
              for x in graph['actions']]
    assert sorted(cid for ids in owners for cid in ids) == ['KNOWN', 'TARGET', 'UNKNOWN']
    assert 'KNOWN' in owners[0] and 'TARGET' in owners[1]


def context_model(base, requests, *, fix=True, pause_path=None):
    def model(system, user, name):
        request = json.loads(user)['task']
        if name.startswith('evidence_merge.'):
            return base(system, user, name)
        requests.append(request)
        if 'correction' not in request:
            value = base(system, user, name)
            update = next(p for p in value['phase_context_updates'] if p['baseline_context_refs'])
            update['baseline_context_refs'][0]['support'][0]['target'] = '/phase_id'
            if pause_path:
                pause_path.write_text('pause')
            return value
        value = empty_response()
        for issue in request['correction']['issues']:
            if not issue['item'].startswith('context_updates:'):
                continue
            for field, items in issue['proposal'].items():
                for item in items:
                    if item not in value[field]:
                        value[field].append(deepcopy(item))
        if fix:
            for update in value['phase_context_updates']:
                for ref in update['baseline_context_refs']:
                    for support in ref['support']:
                        if support['target'] == '/phase_id':
                            support['target'] = ''  # Authored fixture supports the whole association.
        return value
    return model


@pytest.mark.parametrize('pause', [False, True])
def test_bad_context_target_is_locally_corrected_with_edges_and_upstream_retained(tmp_path, baseline, pause):
    _, snapshot = baseline
    frozen = load_snapshot(snapshot)['snapshot']['graph']
    base, requests = SyntheticEventModel(), []
    root = tmp_path / 'corrected'
    model = context_model(base, requests, pause_path=(root / 'pause_requested') if pause else None)
    state = run_relations(snapshot, root, model=model)
    if pause:
        assert state['execution_status'] == 'paused'
        before = json.loads((root / state['output']).read_text())
        assert before['relations']  # Adopted edges survive interruption before correction.
        state = run_relations(snapshot, root, model=model, resume=True)
    assert state['result_status'] == 'draft', json.loads((root / state['checks']).read_text())
    assert len(requests) == 2 and len(state['calls']) == 3
    correction = requests[1]
    # Both Phase updates share a new Context and were rejected atomically.
    assert not correction['assigned_action_ids'] and len(correction['assigned_phase_ids']) == 2
    assert 'relation_discovery' not in correction  # The first receipt was already accepted.
    final = json.loads((root / state['output']).read_text())
    assert len(final['relations']) == len(base.graph['relations'])
    assert final['stages'] == frozen['stages']
    for c, removable in [('actions', {'delta_context_refs', 'baseline_context_exclusions'}),
                          ('phases', {'baseline_context_refs'})]:
        assert [{k: v for k, v in r.items() if k not in removable} for r in final[c]] == [
            {k: v for k, v in r.items() if k not in removable} for r in frozen[c]]
    adoption = json.loads((root / state['output']).with_name('adoption.json').read_text())
    first = next(r for r in adoption if r['task_id'] == 'relate.0')
    assert any('/phase_id' in i['reason'] for i in first['report']['rejected'])
    assert first['resolutions'] and all(r['resolved_by'] == 'relate.0.correct.1' for r in first['resolutions'])
    receipt = json.loads((root / state['relation_discovery']).read_text())
    assert not receipt['incomplete_action_ids'] and receipt['semantic_review_required']
    calls = deepcopy(state['calls'])
    resumed = run_relations(snapshot, root, model=model, resume=True)
    assert resumed['calls'] == calls and len(requests) == 2


def test_unfixed_context_remains_partial_after_bounded_attempts(tmp_path, baseline):
    _, snapshot = baseline
    requests = []
    model = context_model(SyntheticEventModel(), requests, fix=False)
    root = tmp_path / 'uncorrected'
    state = run_relations(snapshot, root, model=model)
    assert state['result_status'] == 'partial' and len(requests) == 3
    assert json.loads((root / state['output']).read_text())['relations']
    resumed = run_relations(snapshot, root, model=model, resume=True)
    assert resumed['result_status'] == 'partial' and len(requests) == 3


def test_local_correction_cannot_rewrite_valid_neighbors():
    value = empty_response()
    value['action_context_updates'] = [dict(action_id='GOOD', delta_context_refs=[], baseline_context_exclusions=[])]
    with pytest.raises(ValueError, match='rejected Context'):
        validate_correction('relations', value, {'actions': ['BAD']})
    value = empty_response()
    value['relations'] = [{'relation_id': 'GOOD-EDGE'}]
    with pytest.raises(ValueError, match='rewrite relations'):
        validate_correction('relations', value, {'phases': ['BAD']})
