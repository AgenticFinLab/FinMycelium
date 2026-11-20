"""Actual child-process cancellation plus checkpoint-preserving transport upgrades."""
from dataclasses import asdict
import json
from types import SimpleNamespace
import time
import sys

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event import runtime
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.guarded_transport import (
    GuardedModel, StreamStalled, RequestDeadlineExceeded, ModelTransportError, retryable_failure)
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, write_json
from finmy.person_epg.event.scheduling import Task


@pytest.mark.parametrize('flowing,exception', [(False, StreamStalled), (True, RequestDeadlineExceeded)])
def test_watchdog_kills_real_process_even_with_heartbeats(monkeypatch, flowing, exception):
    import finmy.person_epg.event.guarded_transport as transport
    processes = []
    popen = transport.subprocess.Popen
    def track(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(transport.subprocess, 'Popen', track)
    model = GuardedModel(SimpleNamespace(timeout=0.4, stall_timeout=0.2))
    script = '''import json,time
i=0
while True:
 i+=1
 print(json.dumps({'kind':'progress','diagnostics':{'phase':'receiving',
 'chunks':i,'content_chars':i if FLOWING else 0,'reasoning_chars':0}}),flush=True)
 time.sleep(.01)
'''.replace('FLOWING', repr(flowing))
    monkeypatch.setattr(model, '_command', lambda: [sys.executable, '-u', '-c', script])
    started = time.monotonic()
    with pytest.raises(exception):
        model.call_with_effort('system', '{}', 'organize', reasoning_effort='low')
    assert time.monotonic() - started < 3
    assert len(processes) == 1 and processes[0].poll() is not None
    assert model.last_diagnostics['chunks'] > 0
    assert model.last_diagnostics['error_type'] == exception.__name__


def test_subprocess_success_retains_usage_and_result(monkeypatch):
    model = GuardedModel(SimpleNamespace(timeout=2, stall_timeout=1))
    message = dict(kind='completed', raw='{"ok":true}', usage={'total_tokens': 4},
                   diagnostics=dict(phase='completed', chunks=1, content_chars=11, reasoning_chars=3))
    monkeypatch.setattr(model, '_command', lambda: [sys.executable, '-c', 'print(' + repr(json.dumps(message)) + ')'])
    assert model.call_with_effort('system', '{}', 'organize', reasoning_effort='low') == '{"ok":true}'
    assert model.last_usage == {'total_tokens': 4}


@pytest.mark.parametrize('always_fail', [False, True])
def test_exactly_one_retry_other_tasks_continue(tmp_path, payload, always_fail):
    calls = []
    def model(system, user, name):
        calls.append(name)
        if name == 'slow' and (always_fail or calls.count(name) == 1):
            raise StreamStalled()
        return {'ok': True}
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2, max_transport_retries=1), model)
    facts = seed_facts(payload)
    result = run.execute_tasks('test', [Task(name,
        run.infer_steps(name, 'system', {}, facts, lambda value: None)) for name in ('slow', 'good')])
    assert calls.count('slow') == 2 and calls.count('good') == 1
    assert result['good'].result == {'ok': True}
    assert bool(result['slow'].error) == always_fail
    slow = [c for c in run.state['calls'] if c['task_id'] == 'slow']
    assert slow[0]['status'] == 'transport_error'
    assert slow[1]['retry_of'] == slow[0]['call_id']
    assert slow[1]['status'] == ('transport_error' if always_fail else 'accepted')
    if not always_fail:
        cp = json.loads(next((tmp_path / 'checkpoints').glob('slow-*.json')).read_text())
        assert cp['call_id'] == slow[1]['call_id']
    else:
        previous = len(calls)
        resumed = Execution(tmp_path, payload, run.config, model, resume=True)
        with pytest.raises(StreamStalled):
            resumed.infer('slow', 'system', {}, facts, lambda value: None)
        assert len(calls) == previous + 1  # An explicit resume does not reset auto-retry budget.


def test_nontransient_error_has_no_retry(tmp_path, payload):
    calls = []
    def model(*args):
        calls.append(1)
        raise ModelTransportError('AuthenticationError')
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    with pytest.raises(runtime.PauseRequested, match='AuthenticationError'):
        run.infer('organize', 'system', {}, seed_facts(payload), lambda value: None)
    assert len(calls) == 1
    assert not retryable_failure({'error_type': 'AuthenticationError', 'http_status': 401})
    assert retryable_failure({'error_chain': ['APITimeoutError', 'ReadTimeout']})


@pytest.mark.parametrize('header,expected', [('45', 45), ('1.5', 1.5), ('-1', None),
                                          ('nan', None), ('inf', None), ('broken', None)])
def test_retry_after_diagnostic_is_numeric_and_safe(header, expected):
    from finmy.person_epg.building.model_transport import error_metadata
    from finmy.person_epg.event.diagnostics import failure_details
    error = RuntimeError('private credentials')
    error.response = SimpleNamespace(status_code=429, headers={'retry-after': header,
                                                               'authorization': 'private credentials'})
    info = error_metadata(error)
    wrapped = ModelTransportError('RateLimitError', retryable=True, diagnostics=info)
    assert failure_details(wrapped).get('retry_after_seconds') == expected
    assert 'private credentials' not in json.dumps(info)


def test_retry_after_http_date(monkeypatch):
    import finmy.person_epg.building.model_transport as transport
    from datetime import datetime, timezone
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 20, 0, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(transport, 'datetime', Clock)
    info = transport.response_metadata(SimpleNamespace(status_code=429,
        headers={'retry-after': 'Fri, 20 Nov 2026 00:00:45 GMT'}))
    assert info['retry_after_seconds'] == 45


def test_upgrade_resumes_organization_without_reextracting(tmp_path, payload, monkeypatch):
    class BrokenOrganization(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'organize':
                self.calls.append(name)
                raise TimeoutError()
            return super().__call__(system, user, name)
    # Old code fingerprint and config shape, with completed upstream stage checkpoints.
    with monkeypatch.context() as m:
        m.setattr(runtime, 'code_identity', lambda: 'previous-implementation')
        first = run_event(payload, tmp_path, {'extraction_workers': 2}, model=BrokenOrganization())
    for key in ('stall_timeout', 'max_transport_retries'):
        first['config'].pop(key)
    write_json(tmp_path / 'state.json', first)
    before = (tmp_path / 'state.json').read_bytes()
    input_before = (tmp_path / 'input.json').read_bytes()
    class ResumeModel(SyntheticEventModel):
        def __call__(self, system, user, name):
            assert not name.startswith(('extract.', 'consolidate.')), 'Repeated paid upstream call'
            return super().__call__(system, user, name)
    model = ResumeModel()
    state = run_event(payload, tmp_path, model=model, resume=True, resume_transport_upgrade=True)
    assert model.calls and model.calls[0] == 'organize'
    assert state['result_status'] == 'draft'
    assert state['stages']['extraction']['reused'] and state['stages']['consolidation']['reused']
    assert state['code_sha256'] == 'previous-implementation'
    assert state['execution_code_sha256'] == runtime.code_identity()
    assert (tmp_path / state['execution_upgrades'][0]['backup']).read_bytes() == before
    assert (tmp_path / 'input.json').read_bytes() == input_before
    # Further ordinary resume works without repeating the explicit upgrade.
    model.calls.clear()
    run_event(payload, tmp_path, model=model, resume=True)
    assert not model.calls


def test_upgrade_reuses_response_saved_before_checkpoint(tmp_path, payload, monkeypatch):
    facts = seed_facts(payload)
    config = EventBuildConfig()
    with monkeypatch.context() as m:
        m.setattr(runtime, 'code_identity', lambda: 'old-code')
        run = Execution(tmp_path, payload, config, lambda *args: {'ok': True})
        run.infer('organize', 'system', {}, facts, lambda value: None)
    for p in (tmp_path / 'checkpoints').glob('organize-*.json'):
        p.unlink()
    run.state['calls'][0]['status'] = 'prefetched'
    run.persist()
    resumed = Execution(tmp_path, payload, config, lambda *a: pytest.fail('Response was already saved'),
                        resume=True, resume_transport_upgrade=True)
    assert resumed.infer('organize', 'system', {}, facts, lambda value: None) == {'ok': True}
    assert len(resumed.state['calls']) == 1


def test_transport_settings_do_not_change_semantic_dependencies():
    a = EventBuildConfig()
    b = EventBuildConfig(stall_timeout=240, max_transport_retries=0)
    assert runtime.semantic_config(a) == runtime.semantic_config(b)
