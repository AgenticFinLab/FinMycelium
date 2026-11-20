"""Isolated relation replay uses frozen facts, real adoption and no network."""
from copy import deepcopy
import json
import socket

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.relation_experiment import load_snapshot, run_relations
from finmy.person_epg.event.records import fingerprint


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No network'))


@pytest.fixture
def baseline(tmp_path, payload):
    model = SyntheticEventModel()
    root = tmp_path / 'baseline'
    state = run_event(payload, root, model=model, stop_after_organization=True)
    assert state['execution_status'] == 'paused'
    assert not any(x.startswith('relate.') for x in model.calls)
    return root, root / state['organization_snapshot']


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_stage_replay_preserves_source_and_calls_relations_then_evidence(tmp_path, baseline):
    source, snapshot = baseline
    before = files(source)
    envelope = load_snapshot(snapshot)
    model = SyntheticEventModel()
    output = tmp_path / 'experiment'
    state = run_relations(snapshot, output, model=model)
    assert state['execution_status'] == 'finished' and state['result_status'] == 'draft'
    assert model.calls == ['relate.0', 'evidence_merge.0']
    graph = json.loads((output / state['output']).read_text())
    assert len(graph['relations']) > 0
    assert [a['action_id'] for a in graph['actions']] == [a['action_id'] for a in envelope['snapshot']['graph']['actions']]
    assert files(source) == before
    report = json.loads((output / 'relation-summary.json').read_text())
    assert report['stage_calls'] == 2 and report['upstream_calls'] > 1
    assert report['usage'][0]['total_tokens'] == 20
    assert report['config']['api_json_mode'] is False
    assert report['semantic_review_required']


@pytest.mark.parametrize('change', ['digest', 'quote', 'incomplete'])
def test_invalid_snapshot_fails_before_model_or_output(tmp_path, baseline, change):
    _, snapshot = baseline
    envelope = json.loads(snapshot.read_text())
    if change == 'digest':
        envelope['snapshot']['config']['max_calls'] += 1
    else:
        if change == 'quote':
            envelope['snapshot']['graph']['evidence'][0]['quote'] = 'Unfounded quotation'
        else:
            envelope['snapshot']['coverage'][0]['proposal_status'] = 'unresolved'
        envelope['fingerprint'] = fingerprint(envelope['snapshot'])
    tampered = tmp_path / 'bad.json'
    tampered.write_text(json.dumps(envelope))
    model = SyntheticEventModel()
    output = tmp_path / 'invalid-output'
    with pytest.raises(ValueError):
        run_relations(tampered, output, model=model)
    assert not model.calls and not output.exists()


def test_resume_keeps_budget_and_reuses_only_own_checkpoints(tmp_path, baseline):
    _, snapshot = baseline
    root = tmp_path / 'experiment'
    first = run_relations(snapshot, root, model=SyntheticEventModel())
    before = files(root)
    with pytest.raises(ValueError):
        run_relations(snapshot, root, config={'api_json_mode': True},
                      model=SyntheticEventModel(), resume=True)
    assert files(root) == before
    model = SyntheticEventModel()
    second = run_relations(snapshot, root, model=model, resume=True)
    assert not model.calls and second['calls'] == first['calls']
    with pytest.raises(FileExistsError):
        run_relations(snapshot, root, model=model)


def test_permission_and_failure_are_not_zero_relation_success(tmp_path, baseline):
    _, snapshot = baseline
    with pytest.raises(PermissionError):
        run_relations(snapshot, tmp_path / 'denied')
    class Broken:
        def __call__(self, *args):
            raise RuntimeError('transport failure')
    output = tmp_path / 'failed'
    state = run_relations(snapshot, output, model=Broken())
    report = json.loads((output / 'relation-summary.json').read_text())
    assert state['execution_status'] == 'finished' and state['result_status'] == 'partial'
    assert state['task_states']['relations:relate.0']['status'] == 'failed'
    assert report['calls_without_usage'] == 2
    assert report['execution_status'] == 'finished'


def test_read_budget_limit_resumes_without_repeating_paid_read(tmp_path, baseline):
    _, snapshot = baseline
    class Reading(SyntheticEventModel):
        def __call__(self, system, user, name):
            request = json.loads(user)
            if request['task']['role'] == 'evidence_consolidation':
                return super().__call__(system, user, name)
            if not request['read_results']:
                self.calls.append(name)
                return {'read_requests': [{'tool': 'read_records', 'refs': [{
                    'collection': 'actions',
                    'object_id': request['task']['assigned_action_ids'][0], 'field': '/name'}]}]}
            return super().__call__(system, user, name)
    model = Reading()
    root = tmp_path / 'limited'
    first = run_relations(snapshot, root, config={'max_calls': 1}, model=model)
    assert first['execution_status'] == 'limit'
    assert len(first['calls']) == 1 and len(first['reads']) == 1
    second = run_relations(snapshot, root, config={'max_calls': 3}, model=model, resume=True)
    assert second['execution_status'] == 'finished'
    assert len(second['calls']) == 3 and len(second['reads']) == 1
    assert second['calls'][0] == first['calls'][0]
