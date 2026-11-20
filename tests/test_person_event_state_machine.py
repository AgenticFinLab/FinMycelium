"""Failures are task outcomes; only global faults stop the coordinator."""
import json
import socket
import threading

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import Execution, EventBuildConfig
from finmy.person_epg.event.scheduling import Task


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No model network calls'))


@pytest.mark.parametrize('workers', [1, 3])
def test_timeout_is_local_and_resume_reuses_successes(tmp_path, payload, workers):
    class OneTimeout(SyntheticEventModel):
        failed = False
        def __call__(self, system, user, name):
            if name == 'extract.0' and not self.failed:
                self.failed = True
                self.calls.append(name)
                raise TimeoutError('private endpoint or credential must not enter events')
            return super().__call__(system, user, name)
    model = OneTimeout()
    first = run_event(payload, tmp_path, {'extraction_workers': workers}, model=model)
    assert first['execution_status'] == 'finished' and first['result_status'] == 'partial'
    assert first['task_states']['extraction:extract.0']['status'] == 'failed'
    assert all(first['coverage'][i]['body_status'] == 'processed' for i in (1, 2))
    assert any(name == 'organize' for name in model.calls)
    assert 'private endpoint' not in json.dumps(first)
    assert json.loads((tmp_path / first['checks']).read_text())['task_failures']
    second = run_event(payload, tmp_path, model=model, resume=True)
    assert second['result_status'] == 'draft'
    assert model.calls.count('extract.0') == 2
    assert model.calls.count('extract.1') == model.calls.count('extract.2') == 1


def test_organization_timeout_blocks_dependents_without_losing_facts(tmp_path, payload):
    class NoOrganization(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'organize':
                self.calls.append(name)
                raise TimeoutError()
            return super().__call__(system, user, name)
    model = NoOrganization()
    state = run_event(payload, tmp_path, {'extraction_workers': 3}, model=model)
    assert state['execution_status'] == 'finished' and state['result_status'] == 'partial'
    assert state['stages']['relations']['status'] == 'blocked'
    assert not any(n.startswith('relate.') for n in model.calls)
    assert json.loads((tmp_path / state['facts']).read_text())['actions']


def test_one_relation_failure_does_not_stop_other_scopes(tmp_path, payload):
    class OneRelationTimeout(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'relate.0':
                self.calls.append(name)
                raise TimeoutError()
            return super().__call__(system, user, name)
    state = run_event(payload, tmp_path, {'extraction_workers': 3}, model=OneRelationTimeout())
    assert state['execution_status'] == 'finished' and state['result_status'] == 'partial'
    assert state['task_states']['relations:relate.0']['status'] == 'failed'
    assert any(t['stage'] == 'relations' and t['status'] == 'succeeded' for t in state['task_states'].values())


@pytest.mark.parametrize('continuation', ['read', 'retry'])
def test_slow_continuation_does_not_block_other_task(tmp_path, payload, continuation):
    second_completed = threading.Event()
    counts = {}
    active = 0
    peak = 0
    lock = threading.Lock()
    def model(system, user, name):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            counts[name] = counts.get(name, 0) + 1
        try:
            if name == 'a' and counts[name] == 1:
                if continuation == 'retry':
                    return 'bad json'
                return {'read_requests': [dict(tool='read_sample',
                    sample_id=payload['samples'][0]['sample_id'], start=0, end=10)]}
            if name == 'a':
                assert second_completed.wait(5), 'coordinator blocked on continuation'
            return {'ok': True}
        finally:
            with lock:
                active -= 1
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2), model)
    facts = seed_facts(payload)
    def steps(name):
        result = yield from run.infer_steps(name, 'system', {}, facts, lambda value: None)
        if name == 'b':
            second_completed.set()
        return result
    results = run.execute_tasks('test', [Task(name, steps(name)) for name in ('a', 'b')])
    assert all(t.error is None and t.result == {'ok': True} for t in results.values())
    assert peak <= 2 and counts == {'a': 2, 'b': 1}
    metrics = run.state['stages']['test']['metrics']
    assert metrics['requests'] == 3 and metrics['succeeded'] == 2
    assert metrics['retry_requests'] == (1 if continuation == 'retry' else 0)
    assert any(e['type'] == ('ReadRequested' if continuation == 'read' else 'RetryRequested')
               for e in run.state['events'])


def test_all_extractions_fail_but_summary_is_written(tmp_path, payload):
    def model(*args):
        raise TimeoutError()
    state = run_event(payload, tmp_path, {'extraction_workers': 3}, model=model)
    assert state['execution_status'] == 'finished' and state['result_status'] == 'partial'
    assert len(state['calls']) == len(payload['samples']) + 1
    assert state['calls'][-1]['task_id'] == 'whole-corpus.supplement'
    assert state['stages']['organization']['status'] == 'blocked'
    assert (tmp_path / state['checks']).is_file()


def test_pause_drains_inflight_and_resume_uses_saved_response(tmp_path, payload):
    config = EventBuildConfig(extraction_workers=2)
    run = Execution(tmp_path, payload, config, lambda *args: {'ok': True})
    facts = seed_facts(payload)
    def steps(name):
        value = yield from run.infer_steps(name, 'system', {}, facts, lambda value: None)
        (tmp_path / 'pause_requested').touch()
        return value
    from finmy.person_epg.event.runtime import PauseRequested
    with pytest.raises(PauseRequested):
        run.execute_tasks('test', [Task(name, steps(name)) for name in ('a', 'b', 'c')])
    assert len(run.state['calls']) == 2
    assert all((tmp_path / c['response_path']).is_file() for c in run.state['calls'])
    (tmp_path / 'pause_requested').unlink()
    resumed = Execution(tmp_path, payload, config, lambda *args: pytest.fail('Repeat request'), resume=True)
    for name in ('a', 'b'):
        assert resumed.infer(name, 'system', {}, facts, lambda value: None) == {'ok': True}


@pytest.mark.parametrize('info', [
    dict(error_type='AuthenticationError', http_status=401),
    dict(error_type='PermissionDeniedError', http_status=403, error_code='AccountOverdueError'),
])
def test_account_failure_pauses_dispatch_and_resume_reuses_inflight(tmp_path, payload, info):
    from finmy.person_epg.event.guarded_transport import ModelTransportError
    from finmy.person_epg.event.runtime import PauseRequested
    released = threading.Event()
    calls = []
    def model(system, user, name):
        calls.append(name)
        if name == 'bad':
            raise ModelTransportError(info['error_type'], diagnostics=info)
        assert released.wait(3), 'Coordinator did not pause service while collecting in-flight work'
        return {'ok': True}
    config = EventBuildConfig(extraction_workers=2)
    run = Execution(tmp_path, payload, config, model)
    persist = run.persist
    def capture():
        persist()
        if run.state.get('service_pause'):
            released.set()
    run.persist = capture
    facts = seed_facts(payload)
    with pytest.raises(PauseRequested):
        run.execute_tasks('test', [Task(name, run.infer_steps(name, 'system', {}, facts, lambda v: None))
                                   for name in ('bad', 'inflight', 'queued')])
    assert set(calls) == {'bad', 'inflight'}
    assert run.state['stages']['test']['status'] == 'paused'
    assert all(t['status'] == 'paused' for t in run.state['task_states'].values())
    kept = next(c for c in run.state['calls'] if c['task_id'] == 'inflight')
    assert kept['status'] == 'prefetched' and (tmp_path / kept['response_path']).is_file()
    recovered_calls = []
    def recovered(system, user, name):
        recovered_calls.append(name)
        return {'ok': True}
    resumed = Execution(tmp_path, payload, config, recovered, resume=True)
    result = resumed.execute_tasks('test', [Task(name, resumed.infer_steps(name, 'system', {}, facts, lambda v: None))
                                          for name in ('bad', 'inflight', 'queued')])
    assert all(t.result == {'ok': True} for t in result.values())
    assert set(recovered_calls) == {'bad', 'queued'} and 'service_pause' not in resumed.state


def test_account_pause_stops_later_stages_and_preserves_finished_extraction(tmp_path, payload):
    from finmy.person_epg.event.guarded_transport import ModelTransportError
    class Overdue(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'extract.1':
                self.calls.append(name)
                raise ModelTransportError('PermissionDeniedError', diagnostics=dict(
                    http_status=403, error_code='AccountOverdueError'))
            return super().__call__(system, user, name)
    model = Overdue()
    state = run_event(payload, tmp_path, {'extraction_workers': 1}, model=model)
    assert state['execution_status'] == 'paused' and model.calls == ['extract.0', 'extract.1']
    assert state['coverage'][0]['body_status'] == 'processed'
    assert 'AccountOverdueError' in state['reason']
    good = SyntheticEventModel()
    resumed = run_event(payload, tmp_path, model=good, resume=True)
    assert resumed['execution_status'] == 'finished' and resumed['result_status'] == 'draft'
    assert 'extract.0' not in good.calls


def test_resource_specific_403_remains_local(tmp_path, payload):
    from finmy.person_epg.event.guarded_transport import ModelTransportError
    def model(system, user, name):
        if name == 'bad':
            raise ModelTransportError('PermissionDeniedError', diagnostics=dict(
                http_status=403, error_code='ContentPolicyViolation'))
        return {'ok': True}
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    facts = seed_facts(payload)
    tasks = run.execute_tasks('test', [Task(name, run.infer_steps(name, 'system', {}, facts, lambda v: None))
                                     for name in ('bad', 'good')])
    assert tasks['bad'].error and tasks['good'].result == {'ok': True}
    assert 'service_pause' not in run.state
