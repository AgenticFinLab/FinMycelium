"""Sixty-second output-stall recovery with a shared two-retry ceiling."""
import json
import sys
from types import SimpleNamespace

import pytest

from test_person_event_contract import payload
from finmy.person_epg.event.guarded_transport import GuardedModel, StreamStalled
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, IncompleteStreamResponse
from finmy.person_epg.event.scheduling import PROGRESS_INTERVAL_SECONDS


def validate(value):
    if value != {'ok': True}:
        raise ValueError('Expected ok=true')


def test_defaults_and_semantic_checkpoint_compatibility():
    from finmy.person_epg.event.runtime import semantic_config
    new = EventBuildConfig()
    old = EventBuildConfig(stall_timeout=180, max_transport_retries=1)
    assert (new.stall_timeout, new.max_transport_retries, new.timeout) == (60, 2, 900)
    assert new.max_read_rounds == 2 and PROGRESS_INTERVAL_SECONDS == 60
    assert semantic_config(new) == semantic_config(old)


@pytest.mark.parametrize('raw', ['{"ok":true}', '```json\n{"ok":true}\n```'])
def test_real_child_is_killed_but_complete_json_is_accepted(tmp_path, payload, monkeypatch, raw):
    import finmy.person_epg.event.guarded_transport as transport
    model = GuardedModel(SimpleNamespace(timeout=2, stall_timeout=.15))
    message = dict(kind='content', text=raw, diagnostics=dict(phase='receiving', chunks=1,
        content_chars=len(raw), reasoning_chars=0, finish_reason=None))
    script = 'import time\nprint(' + repr(json.dumps(message)) + ',flush=True)\ntime.sleep(20)'
    monkeypatch.setattr(model, '_command', lambda: [sys.executable, '-u', '-c', script])
    processes = []
    popen = transport.subprocess.Popen
    def track(*a, **kw):
        p = popen(*a, **kw); processes.append(p); return p
    monkeypatch.setattr(transport.subprocess, 'Popen', track)
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    assert run.infer('organize', 'system', {}, seed_facts(payload), validate) == {'ok': True}
    call, = run.state['calls']
    assert call['status'] == 'accepted' and call['recovery_status'] == 'validated_complete'
    assert call['transport']['recovery_reason'] == 'StreamStalled'
    assert call['transport']['finish_reason'] is None
    assert all(p.poll() is not None for p in processes)
    assert json.loads((tmp_path / call['response_path']).read_text())['raw'] == raw


class Interrupted:
    last_usage = None
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []
    def __call__(self, system, user, name):
        self.calls.append(user)
        self.last_diagnostics = None
        outcome = self.outcomes[min(len(self.calls)-1, len(self.outcomes)-1)]
        if isinstance(outcome, Exception):
            raise outcome
        self.last_diagnostics = dict(output_recovered=True, finish_reason=None,
                                     recovery_reason='StreamStalled')
        return outcome


def test_two_incomplete_retries_then_success(tmp_path, payload):
    model = Interrupted(['{"ok":', '{"ok":t', '{"ok":true}'])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    assert run.infer('organize', 'system', {}, seed_facts(payload), validate) == {'ok': True}
    assert len(model.calls) == 3 and len(set(model.calls)) == 1
    calls = run.state['calls']
    assert [c['status'] for c in calls] == ['incomplete', 'incomplete', 'accepted']
    assert calls[1]['retry_of'] == calls[0]['call_id']
    assert calls[2]['retry_of'] == calls[1]['call_id']
    assert list(run.state['transport_retries'].values()) == [2]
    for call in calls:
        assert (tmp_path / call['response_path']).exists()


def test_exhausted_incomplete_budget_cannot_fall_through_to_format_retries(tmp_path, payload):
    model = Interrupted(['{"ok":'])
    run = Execution(tmp_path, payload, EventBuildConfig(max_json_attempts=8), model)
    with pytest.raises(IncompleteStreamResponse):
        run.infer('organize', 'system', {}, seed_facts(payload), validate)
    assert len(model.calls) == 3
    assert all(c['status'] == 'incomplete' for c in run.state['calls'])
    assert not list((tmp_path / 'checkpoints').glob('organize-*.json'))
    assert any(t['status'] == 'failed' for t in run.state['task_states'].values())
    # Explicit resume can make an initial attempt, but cannot replenish automatic retries.
    resumed = Execution(tmp_path, payload, run.config, model, resume=True)
    with pytest.raises(IncompleteStreamResponse):
        resumed.infer('organize', 'system', {}, seed_facts(payload), validate)
    assert len(model.calls) == 4
    assert list(resumed.state['transport_retries'].values()) == [2]


def test_empty_timeouts_and_partial_json_share_one_retry_budget(tmp_path, payload):
    model = Interrupted([StreamStalled(), '{"ok":', StreamStalled()])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    with pytest.raises(StreamStalled):
        run.infer('organize', 'system', {}, seed_facts(payload), validate)
    assert len(model.calls) == 3
    assert [c['status'] for c in run.state['calls']] == ['transport_error','incomplete','transport_error']


def test_complete_json_still_requires_role_validation(tmp_path, payload):
    model = Interrupted(['{"wrong":true}', '{"ok":true}'])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    assert run.infer('organize', 'system', {}, seed_facts(payload), validate) == {'ok': True}
    assert [c['status'] for c in run.state['calls']] == ['invalid_output', 'accepted']


def test_prefetched_partial_response_is_recovered_on_resume(tmp_path, payload):
    first = Interrupted(['{"ok":'])
    run = Execution(tmp_path, payload, EventBuildConfig(max_transport_retries=0), first)
    with pytest.raises(IncompleteStreamResponse):
        run.infer('organize', 'system', {}, seed_facts(payload), validate)
    run.state['calls'][0]['status'] = 'prefetched'
    run.persist()
    model = Interrupted(['{"ok":true}'])
    resumed = Execution(tmp_path, payload, EventBuildConfig(), model, resume=True)
    assert resumed.infer('organize', 'system', {}, seed_facts(payload), validate) == {'ok': True}
    assert len(model.calls) == 1 and len(resumed.state['calls']) == 2


def test_stream_content_hook_does_not_drop_last_fragment():
    from finmy.person_epg.building.model_transport import StreamingModel
    chunks = ['{"ok":', 'true}']
    class Stream:
        response = SimpleNamespace(status_code=200, headers={})
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def __iter__(self):
            for text in chunks:
                yield SimpleNamespace(id='test', usage=None, choices=[SimpleNamespace(index=0,
                    delta=SimpleNamespace(content=text), finish_reason=None)])
            raise TimeoutError()
    sent = []
    class Model(StreamingModel):
        def _publish_content(self, content, info): sent.append(content)
    m = Model(EventBuildConfig())
    m.adapter = SimpleNamespace(model_name='fixture', request_parameters=lambda x: x,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: Stream()))))
    with pytest.raises(TimeoutError): m('s', '{}', 'organize')
    assert sent == chunks
    assert 'true}' not in json.dumps(m.progress_snapshot())


def test_pipeline_resume_command_overrides_old_transport_settings(tmp_path, monkeypatch):
    from finmy.person_epg.event import resume_transport
    (tmp_path / 'state.json').write_text(json.dumps({'calls': [], 'config': {
        'timeout': 900, 'stall_timeout': 180, 'max_transport_retries': 1}}))
    (tmp_path / 'input.json').write_text('{}')
    invoked = []
    def run(payload, **kwargs):
        invoked.append(kwargs)
        return {'execution_status':'finished', 'stages':{}}
    monkeypatch.setattr(resume_transport, 'run_event', run)
    resume_transport.main([str(tmp_path), '--allow-model'])
    assert invoked[0]['config'] == {'timeout':900, 'stall_timeout':60, 'max_transport_retries':2, 'max_calls':60}
    assert invoked[0]['resume'] and invoked[0]['resume_transport_upgrade']
