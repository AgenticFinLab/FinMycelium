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
        assert saved['stages']['test']['metrics']['succeeded'] == 1
        assert saved['stages']['test']['metrics']['requests'] == 2
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
    assert '有效完成' in output.err and '平均就绪排队' in output.err
    assert 'PRIVATE REASONING' not in output.err + json.dumps(run.state)
    assert len(run.state['calls']) == 2  # Heartbeats never submit model requests.
    assert config.timeout == 900 and config.max_read_rounds == 2


def test_fast_completion_has_no_heartbeat(tmp_path, payload, capsys):
    run = Execution(tmp_path, payload, EventBuildConfig(), lambda *a: {'ok': True})
    assert run.infer('fast', 'system', {}, seed_facts(payload), lambda v: None) == {'ok': True}
    assert capsys.readouterr().err == ''
    assert 'progress_updated_at' not in run.state


class TerminalBuffer:
    """Keep frames separately so cursor-control output can be inspected offline."""
    def __init__(self):
        self.frames = []
    def isatty(self):
        return True
    def write(self, text):
        self.frames.append(text)
    def flush(self):
        pass


def test_stage_boxes_count_tasks_not_calls_and_fit_terminal(monkeypatch):
    from copy import deepcopy
    import os
    stream = TerminalBuffer()
    monkeypatch.setattr(scheduling.sys, 'stderr', stream)
    monkeypatch.setattr(scheduling.shutil, 'get_terminal_size', lambda fallback: os.terminal_size((80, 24)))
    state = dict(attempts=2, calls=[{}] * 30, task_states={
        str(i): dict(stage='extraction', attempt=2, status=status)
        for i, status in enumerate(['succeeded', 'failed', 'running', 'queued'])})
    state['old'] = dict(stage='extraction', attempt=1, status='succeeded')
    before = deepcopy(state)
    display = scheduling.TerminalProgress(SimpleNamespace(state=state, config=EventBuildConfig(full_corpus_supplement=False)))
    display.update('extraction', 'running')
    frame = stream.frames[-1]
    assert '抽取 2/4' in frame and '1 运行 · 1 排队 · 1 失败/限额' in frame
    assert '补充 跳过' in frame and '████████░░░░░░░░' in frame
    assert all(scheduling.terminal_text(line, 79).rstrip() == line for line in frame.splitlines())
    display.update('organization', 'blocked')
    assert '组织 受阻' in stream.frames[-1]
    assert any('\x1b[' in text for text in stream.frames)
    assert state == before


def test_tty_parallel_refresh_does_not_add_calls_or_persist_heartbeat(tmp_path, payload, monkeypatch):
    import os
    stream = TerminalBuffer()
    release = Event()
    monkeypatch.setattr(scheduling.sys, 'stderr', stream)
    monkeypatch.setattr(scheduling.shutil, 'get_terminal_size', lambda fallback: os.terminal_size((120, 24)))
    monkeypatch.setattr(scheduling, 'TTY_INTERVAL_SECONDS', 0.01)
    write = stream.write
    def capture(text):
        write(text)
        if 'extract.0 ·' in text and 'extract.1 ·' in text:
            release.set()
    stream.write = capture
    def model(*args):
        assert release.wait(3), 'Both active requests must be displayed while blocked'
        return {'ok': True}
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2), model)
    facts = seed_facts(payload)
    result = run.execute_tasks('extraction', [Task(name, run.infer_steps(name, 'system', {}, facts, lambda v: None))
                                            for name in ('extract.0', 'extract.1')])
    assert all(t.result == {'ok': True} for t in result.values())
    assert len(run.state['calls']) == 2 and 'progress_updated_at' not in run.state
    assert '抽取 2/2 完成' in stream.frames[-1]
    assert '成功 2' in stream.frames[-1] and '重试 0/2' in stream.frames[-1]
    assert run._terminal_progress.lines == 0


def test_tty_pipeline_finishes_all_boxes_and_resumes_without_model_calls(tmp_path, payload, monkeypatch):
    from finmy.person_epg.event.build import run_event
    from test_person_event_pipeline import SyntheticEventModel
    stream = TerminalBuffer()
    monkeypatch.setattr(scheduling.sys, 'stderr', stream)
    model = SyntheticEventModel()
    first = run_event(payload, tmp_path, model=model)
    assert first['result_status'] == 'draft'
    assert '校验' in stream.frames[-1] and '待开始' not in stream.frames[-1]
    assert '░' not in stream.frames[-1]
    calls = len(model.calls)
    second = run_event(payload, tmp_path, model=model, resume=True)
    assert second['result_status'] == 'draft' and len(model.calls) == calls
    assert '░' not in stream.frames[-1]
