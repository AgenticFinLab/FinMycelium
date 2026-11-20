"""Offline output-limit recovery preserves accepted work and spent budgets."""
from copy import deepcopy
import json
import socket

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.building.completion_errors import IncompleteCompletionError
from finmy.person_epg.event import recovery, runtime
from finmy.person_epg.event.build import run_event


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No network'))


class TruncateOrganization(SyntheticEventModel):
    def __init__(self):
        super().__init__()
        self.organization_calls = 0
        self.last_diagnostics = None

    def __call__(self, system, user, name):
        self.last_diagnostics = None
        if name != 'organize':
            return super().__call__(system, user, name)
        self.organization_calls += 1
        if self.organization_calls == 1:
            return 'invalid json'
        if self.organization_calls == 2:
            return {'read_requests': [{'tool': 'read_sample', 'sample_id': 'SAMPLE-1', 'start': 0, 'end': 10}]}
        self.last_diagnostics = {'finish_reason': 'length', 'stream_exhausted': True}
        raise IncompleteCompletionError(name, finish_reason='length', output_limit=32768)


def stopped_run(directory, payload, monkeypatch):
    current = runtime.code_identity
    monkeypatch.setattr(runtime, 'code_identity', lambda: recovery.OUTPUT_ORIGIN)
    from finmy.person_epg.event.build import Construction
    with monkeypatch.context() as legacy:
        legacy.setattr(Construction, 'stage', lambda self, name, operation: (operation(), True)[1])
        state = run_event(payload, directory, {'max_new_tokens': 32768}, model=TruncateOrganization())
    assert state['execution_status'] == 'failed' and state['reason'] == 'IncompleteCompletionError'
    monkeypatch.setattr(runtime, 'code_identity', current)
    monkeypatch.setattr(recovery, 'compatible_output_code', lambda: True)
    return state


def test_recovery_reuses_upstream_reads_attempts_and_preserves_originals(tmp_path, payload, monkeypatch):
    old = stopped_run(tmp_path, payload, monkeypatch)
    original_files = {p:p.read_bytes() for name in ('attempts', 'checkpoints')
                      for p in (tmp_path/name).rglob('*') if p.is_file()}
    entry = recovery.prepare_output_recovery(tmp_path, max_new_tokens=65536)
    assert recovery.prepare_output_recovery(tmp_path, max_new_tokens=65536) == entry
    state = json.loads((tmp_path/'state.json').read_text())
    assert state['config'] == dict(old['config'], max_new_tokens=65536)
    for key in ('calls', 'reads', 'attempts', 'final_repair_used', 'id_map'):
        assert state[key] == old[key]
    model = SyntheticEventModel()
    def resume(system, user, name):
        if name == 'organize':
            assert len(json.loads(user)['read_results']) == 1
        return model(system, user, name)
    resumed = run_event(payload, tmp_path, state['config'], model=resume, resume=True)
    assert resumed['result_status'] == 'draft'
    assert model.calls == ['organize', 'relate.0']
    assert resumed['calls'][:len(old['calls'])] == old['calls']
    assert resumed['reads'] == old['reads']
    groups = [v for k,v in resumed['validation_attempts'].items() if k.startswith('organize-')]
    assert len(groups) == 2 and all(len(v) == 1 for v in groups)
    assert all(p.read_bytes() == data for p,data in original_files.items())
    assert json.loads((tmp_path/'config.json').read_text())['max_new_tokens'] == 65536


@pytest.mark.parametrize('limit', [32768, 16384, True, '65536'])
def test_recovery_requires_an_explicit_increase(tmp_path, payload, monkeypatch, limit):
    old = stopped_run(tmp_path, payload, monkeypatch)
    with pytest.raises(ValueError, match='must increase'):
        recovery.prepare_output_recovery(tmp_path, max_new_tokens=limit)
    assert json.loads((tmp_path/'state.json').read_text()) == old
    assert not (tmp_path/recovery.OUTPUT_RECORD).exists()


@pytest.mark.parametrize('target', ['input', 'checkpoint', 'request', 'settings', 'code', 'manifest'])
def test_recovery_rejects_dependency_changes(tmp_path, payload, monkeypatch, target):
    stopped_run(tmp_path, payload, monkeypatch)
    recovery.prepare_output_recovery(tmp_path, max_new_tokens=65536)
    state = json.loads((tmp_path/'state.json').read_text())
    if target == 'input': (tmp_path/'input.json').write_text('{}')
    elif target == 'checkpoint': next((tmp_path/'checkpoints').glob('*.json')).write_text('{}')
    elif target == 'request': next((tmp_path/'attempts').glob('*/steps/*/request.json')).write_text('{}')
    elif target == 'settings': state['config']['max_context_chars'] += 1
    elif target == 'code': monkeypatch.setattr(recovery, 'compatible_output_code', lambda: False)
    else: (tmp_path/recovery.OUTPUT_RECORD).write_text('{}')
    with pytest.raises(ValueError): recovery.validate_recovery(tmp_path, state)


def test_recovery_can_retry_interrupted_preparation(tmp_path, payload, monkeypatch):
    old = stopped_run(tmp_path, payload, monkeypatch)
    write = recovery.write_json
    def interrupted(path, value):
        if path == tmp_path/'state.json':
            raise OSError('Interrupted before state publication')
        return write(path, value)
    monkeypatch.setattr(recovery, 'write_json', interrupted)
    with pytest.raises(OSError): recovery.prepare_output_recovery(tmp_path, max_new_tokens=65536)
    saved = (tmp_path/recovery.OUTPUT_RECORD).read_bytes()
    assert json.loads((tmp_path/'state.json').read_text()) == old
    monkeypatch.setattr(recovery, 'write_json', write)
    recovery.prepare_output_recovery(tmp_path, max_new_tokens=65536)
    assert (tmp_path/recovery.OUTPUT_RECORD).read_bytes() == saved


def test_controller_prepares_but_does_not_start(tmp_path, payload, monkeypatch):
    from finmy.workbench.build_tasks import BuildController, check_person_code
    from finmy.workbench.store import Store
    from finmy.workbench.domain import digest, encoded
    payload = json.loads(encoded(payload))  # Match the workbench's saved key ordering.
    directory = tmp_path/'run'
    old = stopped_run(directory, payload, monkeypatch)
    monkeypatch.setattr(recovery, 'compatible_output_workbench', lambda _: True)
    store = Store(tmp_path/'workspace'); controller = BuildController(store)
    body = dict(kind='person_event', artifact_directory=str(directory),
        code={'commit':'old', 'python_sources_sha256':'old'}, person_code='old',
        input=deepcopy(payload), input_hash=digest(payload),
        scope_hash=digest(payload['user_query']['extras']['person_event']['scope']),
        person_config=old['config'])
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)', ('PBUILD-test','event',encoded(body),'failed','now'))
    first = controller.prepare_person_output_recovery('PBUILD-test', max_new_tokens=65536)
    assert first['model_started'] is False
    assert first == controller.prepare_person_output_recovery('PBUILD-test', max_new_tokens=65536)
    row = controller.inspect('PBUILD-test')
    assert row['status'] == 'failed' and len(row['body']['code_history']) == 1
    assert row['body']['person_config']['max_new_tokens'] == 65536
    check_person_code(row['body'])
    controller.prepare_person_resume('PBUILD-test')
    assert controller.inspect('PBUILD-test')['status'] == 'ready'
    assert json.loads((directory/'state.json').read_text())['calls'] == old['calls']
