"""Offline call-boundary pause/resume; all run files belong to tmp_path."""
import json
from pathlib import Path
import socket

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from test_event_collection import setup, finish
from test_person_event_workbench import setup as native_setup
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, PauseRequested, write_json
from finmy.workbench.build_tasks import BuildController


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No real API calls'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a, **k: pytest.fail('No real API calls'))


@pytest.mark.parametrize('pause_after', [1, 2, 3, 4])
def test_pause_finishes_current_call_then_resumes_without_repeating(tmp_path, payload, pause_after):
    model = SyntheticEventModel()
    def request_pause(system, user, name):
        result = model(system, user, name)
        if len(model.calls) == pause_after:
            write_json(tmp_path/'pause_requested', {'requested_at': 'test'})
        return result
    first = run_event(payload, tmp_path, model=request_pause)
    assert first['execution_status'] == 'paused', first
    assert len(model.calls) == len(first['calls']) == pause_after
    assert all(c['status'] == 'accepted' for c in first['calls'])
    assert len(list((tmp_path/'checkpoints').glob('*.json'))) == pause_after
    assert not (tmp_path/'pause_requested').exists()
    assert (tmp_path/first['facts']).is_file()
    second = run_event(payload, tmp_path, model=request_pause, resume=True)
    assert second['execution_status'] == 'finished' and second['result_status'] == 'draft', second
    assert second['attempts'] == 2 and len(second['calls']) == len(model.calls) == 5
    assert second['calls'][:pause_after] == first['calls']


def test_pause_before_first_call_spends_nothing(tmp_path, payload):
    model = SyntheticEventModel()
    write_json(tmp_path/'pause_requested', {})
    state = run_event(payload, tmp_path, model=model)
    assert state['execution_status'] == 'paused' and not model.calls
    assert not state['calls']


@pytest.mark.parametrize('answer,expected', [
    ('invalid JSON', 'invalid_output'),
    ({'read_requests': [{'tool': 'read_sample', 'sample_id': 'SAMPLE-1', 'start': 0, 'end': 30}]}, 'read_requested'),
])
def test_pause_blocks_format_retry_and_tool_followup(tmp_path, payload, answer, expected):
    calls = []
    def model(*args):
        calls.append(args)
        write_json(tmp_path/'pause_requested', {})
        return answer
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    with pytest.raises(PauseRequested):
        run.infer('test', 'contract', {}, seed_facts(payload), lambda value: None)
    assert len(calls) == 1 and run.state['calls'][0]['status'] == expected
    assert (tmp_path/'attempts/0001/steps/CALL-000001/response.json').is_file()


def test_last_call_can_finish_normally_and_transport_errors_are_not_hidden(tmp_path, payload):
    model = SyntheticEventModel()
    def last_pause(system, user, name):
        result = model(system, user, name)
        if len(model.calls) == 5:
            write_json(tmp_path/'done/pause_requested', {})
        return result
    assert run_event(payload, tmp_path/'done', model=last_pause)['execution_status'] == 'finished'
    def failed(*args):
        write_json(tmp_path/'failed/pause_requested', {})
        raise TimeoutError('synthetic')
    state = run_event(payload, tmp_path/'failed', model=failed)
    assert state['execution_status'] == 'failed' and state['reason'] == 'TimeoutError'


def test_controller_pause_and_resume_keep_task_identity_and_usage(native_setup):
    store, search, tid, _ = native_setup
    builds = BuildController(store)
    bid = builds.create_person(search, tid, confirmed=True)
    before = builds.inspect(bid)
    with pytest.raises(ValueError, match='运行中'):
        builds.pause_person(bid)
    assert not Path(before['body']['artifact_directory']).exists()
    model = SyntheticEventModel()
    body = before['body']
    def execute(saved, directory):
        model.bind(saved['input'])
        def pause_once(system, user, name):
            result = model(system, user, name)
            if len(model.calls) == 1:
                builds.pause_person(bid)
            return result
        state = run_event(saved['input'], directory, saved['person_config'], model=pause_once,
                          resume=saved.get('resume', False), provenance=saved['provenance'])
        graph = json.loads((directory/state['output']).read_text()) if state.get('output') else None
        return {'state': state, 'graph': graph}
    builds.save(bid, 'queued', body)
    builds.run(bid, executor=execute)
    row = builds.inspect(bid)
    assert row['status'] == 'paused' and len(row['body']['usage']) == 1
    frozen = (row['body']['input_hash'], row['body']['artifact_directory'])
    calls = list(model.calls)
    builds.prepare_person_resume(bid)
    assert model.calls == calls and builds.inspect(bid)['status'] == 'ready'
    builds.save(bid, 'queued', builds.inspect(bid)['body'])
    builds.run(bid, executor=execute)
    row = builds.inspect(bid)
    assert row['status'] == 'completed' and model.calls.count('extract.0') == 1
    assert len(row['body']['usage']) == len(model.calls)
    assert frozen == (row['body']['input_hash'], row['body']['artifact_directory'])


def test_failed_resume_clears_stale_pause_only_after_code_validation(setup, monkeypatch):
    from finmy.workbench import build_tasks
    _, store, search, _ = setup
    tid, _ = finish(setup)
    builds = BuildController(store); bid = builds.create_person(search, tid, confirmed=True)
    body = builds.inspect(bid)['body']
    marker = Path(body['artifact_directory'])/'pause_requested'
    write_json(marker, {})
    builds.save(bid, 'failed', body)
    with monkeypatch.context() as m:
        m.setattr(build_tasks, 'code_version', lambda: {})
        with pytest.raises(ValueError, match='代码已变化'):
            builds.prepare_person_resume(bid)
    assert marker.exists()
    builds.prepare_person_resume(bid)
    assert not marker.exists()
