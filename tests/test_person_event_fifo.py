"""A stalled first request must not prevent queued work or adoption."""
import threading
from copy import deepcopy

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import Execution, EventBuildConfig


def test_fifo_refills_slot_and_adopts_before_slowest_returns(tmp_path, payload):
    third_adopted = threading.Event()

    class SlowFirst(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'extract.0':
                assert third_adopted.wait(5), 'third task could not finish while first task was running'
            return super().__call__(system, user, name)

    config = EventBuildConfig(extraction_workers=2)
    model = SlowFirst()
    run = Execution(tmp_path, payload, config, model)
    build = Construction(run)
    save = build.save_facts

    def save_and_release():
        save()
        if len(build.coverage) > 2 and build.coverage[2]['status'] == 'processed':
            third_adopted.set()

    build.save_facts = save_and_release
    build.stage('extraction', build.extract)
    assert third_adopted.is_set()
    assert [c['task_id'] for c in run.state['calls']] == ['extract.0', 'extract.1', 'extract.2']
    assert [r['task_id'] for r in build.reports] == ['extract.1', 'extract.2', 'extract.0']
    assert all(c['status'] == 'accepted' for c in run.state['calls'])
    facts = deepcopy(build.facts)
    replay_model = SyntheticEventModel()
    replay = Construction(Execution(tmp_path, payload, config, replay_model, resume=True))
    replay.stage('extraction', replay.extract)
    assert not replay_model.calls
    assert replay.facts == facts


def test_adoption_failure_retains_remaining_responses(tmp_path, payload):
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2),
                    lambda *args: {'ok': True})
    facts = seed_facts(payload)
    jobs = [('extract.' + str(i), 'system', {'role': 'extraction'}, facts) for i in range(4)]

    def fail(task_id):
        raise ValueError('adoption failed')

    with pytest.raises(ValueError, match='adoption failed'):
        run.prefetch_tasks(jobs, on_ready=fail)
    assert len(run.state['calls']) == 2  # A fatal adoption error stops dispatch; in-flight replies survive.
    assert all(c['status'] == 'prefetched' for c in run.state['calls'])
    assert all((tmp_path / c['prefetched_response']).is_file() for c in run.state['calls'])


def test_retry_backoff_yields_slot_and_reports_useful_work(tmp_path, payload, monkeypatch):
    import time
    from finmy.person_epg.event import scheduling
    from finmy.person_epg.event.guarded_transport import StreamStalled, ModelTransportError
    monkeypatch.setattr(scheduling, 'retry_delay', lambda call, calls: .15 if call.get('retry_of') else 0)
    calls, times = [], []
    def model(system, user, name):
        calls.append(name)
        times.append(time.monotonic())
        if name == 'retry' and calls.count(name) == 1:
            raise StreamStalled()
        if name == 'broken':
            raise ModelTransportError('NotFoundError', diagnostics={'http_status': 404})
        return {'ok': True}
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=1), model)
    facts = seed_facts(payload)
    result = run.execute_tasks('test', [scheduling.Task(name,
        run.infer_steps(name, 'system', {}, facts, lambda value: None)) for name in ('retry', 'fresh', 'broken')])
    assert calls == ['retry', 'fresh', 'broken', 'retry']
    assert times[-1] - times[0] >= .15
    assert result['fresh'].result == result['retry'].result == {'ok': True}
    assert result['broken'].error
    retry = next(call for call in run.state['calls'] if call.get('retry_of'))
    assert retry['retry_delay_seconds'] == .15 and retry['retry_not_before']
    metrics = run.state['stages']['test']['metrics']
    assert metrics['succeeded'] == 2 and metrics['requests'] == 4
    assert metrics['retry_requests'] == 1 and metrics['retry_fraction'] == .25
    assert metrics['tasks_per_minute'] == pytest.approx(120 / metrics['elapsed_seconds'], rel=.02)
    assert metrics['mean_queue_seconds'] == pytest.approx(
        sum(c['queue_wait_seconds'] for c in run.state['calls']) / 4, abs=.001)
    assert metrics['running_tasks'] == metrics['backoff_tasks'] == metrics['ready_tasks'] == 0


def test_retry_policy_is_bounded_jittered_and_respects_retry_after(monkeypatch):
    from finmy.person_epg.event import scheduling
    bounds = []
    def jitter(lo, hi):
        bounds.append((lo, hi))
        return hi
    monkeypatch.setattr(scheduling.random, 'uniform', jitter)
    calls = {'first': {'call_id': 'first'}}
    previous, delays = 'first', []
    for i in range(6):
        call = {'call_id': str(i), 'retry_of': previous}
        delays.append(scheduling.retry_delay(call, calls))
        calls[str(i)] = call
        previous = str(i)
    assert delays == [2, 4, 8, 16, 30, 30]
    assert bounds[0] == (1, 2) and bounds[-1] == (15, 30)
    calls['first']['failure'] = {'retry_after_seconds': 45}
    assert scheduling.retry_delay(calls['0'], calls) == 47


def test_pause_while_only_retry_is_waiting(tmp_path, payload, monkeypatch):
    from finmy.person_epg.event import scheduling
    from finmy.person_epg.event.guarded_transport import StreamStalled
    from finmy.person_epg.event.runtime import PauseRequested
    monkeypatch.setattr(scheduling, 'retry_delay', lambda *args: 30)
    calls = []
    def model(*args):
        calls.append(1)
        raise StreamStalled()
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    persist = run.persist
    def pause_at_backoff():
        persist()
        if any(c.get('retry_not_before') for c in run.state['calls']):
            (tmp_path / 'pause_requested').touch()
    monkeypatch.setattr(run, 'persist', pause_at_backoff)
    with pytest.raises(PauseRequested):
        run.infer('a', 'system', {}, seed_facts(payload), lambda value: None)
    assert calls == [1]
    assert run.state['task_states']['a:a']['status'] == 'paused'
