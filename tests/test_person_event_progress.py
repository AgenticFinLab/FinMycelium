"""Progress remains observable while the transport is blocked, without network."""
import json
from threading import Event
from types import SimpleNamespace

from test_person_event_contract import payload
from finmy.person_epg.building.model_transport import StreamingModel
from finmy.person_epg.event import scheduling
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution
from finmy.person_epg.event.scheduling import Task


def test_minute_default():
    assert scheduling.PROGRESS_INTERVAL_SECONDS == 60


def test_waiting_headers_chunks_and_stalled_stream_are_reported(tmp_path, payload, monkeypatch, capsys):
    # Accelerate only the test clock interval; production always uses 60 seconds.
    monkeypatch.setattr(scheduling, 'PROGRESS_INTERVAL_SECONDS', 0.03)
    headers, chunk, finish = Event(), Event(), Event()
    class Stream:
        response = SimpleNamespace(status_code=200, headers={})
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def __iter__(self):
            assert chunk.wait(3), 'No heartbeat while waiting for first chunk'
            yield SimpleNamespace(id='response-test', usage=None, choices=[SimpleNamespace(
                index=0, delta=SimpleNamespace(content='{"ok":true}', reasoning_content='PRIVATE REASONING'),
                finish_reason=None)])
            assert finish.wait(3), 'No heartbeat while stream is idle'
            yield SimpleNamespace(id='response-test', usage=None, choices=[SimpleNamespace(
                index=0, delta=SimpleNamespace(content=None), finish_reason='stop')])
    def create(**kwargs):
        assert headers.wait(3), 'No heartbeat while waiting for headers'
        return Stream()
    class Model(StreamingModel):
        def call_with_effort(self, system, user, name, *, reasoning_effort):
            if name == 'fast':
                return '{"ok":true}'
            return super().call_with_effort(system, user, name, reasoning_effort=reasoning_effort)
    config = EventBuildConfig(extraction_workers=2)
    def factory():
        m = Model(config)
        m.adapter = SimpleNamespace(model_name='fixture', request_parameters=lambda x: x,
            client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        return m
    run = Execution(tmp_path, payload, config, factory(), model_factory=factory)
    snapshots, stamps = [], set()
    persist = run.persist
    def capture():
        persist()
        stamp = run.state.get('progress_updated_at')
        if not stamp or stamp in stamps:
            return
        stamps.add(stamp)
        saved = json.loads((tmp_path / 'state.json').read_text())
        info = next(c['progress'] for c in saved['calls'] if c['task_id'] == 'slow')
        snapshots.append(info)
        assert saved['task_states']['test:fast']['status'] == 'succeeded'
        if info['phase'] == 'connecting':
            assert info['first_response_seconds'] is None and info['idle_seconds'] is None
            headers.set()
        elif not info['chunks']:
            assert info['first_response_seconds'] is not None
            chunk.set()
        elif sum(s['content_chars'] > 0 for s in snapshots) >= 2:
            finish.set()
    monkeypatch.setattr(run, 'persist', capture)
    facts = seed_facts(payload)
    results = run.execute_tasks('test', [Task(name, run.infer_steps(name, 'system', {}, facts, lambda v: None))
                                        for name in ('slow', 'fast')])
    assert all(t.result == {'ok': True} and t.error is None for t in results.values())
    received = [s for s in snapshots if s['content_chars']]
    assert len(received) >= 2 and received[-1]['idle_seconds'] > received[0]['idle_seconds']
    assert all(s['content_chars'] == 11 and s['reasoning_chars'] == 17 for s in received)
    assert received[0]['first_chunk_at'] and received[0]['last_chunk_at']
    output = capsys.readouterr()
    assert output.out == ''
    assert '等待响应' in output.err and '已响应，等待首块' in output.err and '接收中' in output.err
    assert 'PRIVATE REASONING' not in output.err + json.dumps(run.state)
    assert len(run.state['calls']) == 2  # Heartbeats never submit model requests.
    assert config.timeout == 900 and config.max_read_rounds == 2


def test_fast_completion_has_no_heartbeat(tmp_path, payload, capsys):
    run = Execution(tmp_path, payload, EventBuildConfig(), lambda *a: {'ok': True})
    assert run.infer('fast', 'system', {}, seed_facts(payload), lambda v: None) == {'ok': True}
    assert capsys.readouterr().err == ''
    assert 'progress_updated_at' not in run.state
