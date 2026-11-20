"""Operational changes preserve paid responses and domain outputs."""
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from test_person_event_contract import payload, graph
from test_person_event_runtime import Model, valid
from finmy.person_epg.event import runtime
from finmy.person_epg.event.config import EventBuildConfig, effective_read_limits, resume_settings
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.diagnostics import failure_details
from finmy.person_epg.event.guarded_transport import ModelTransportError
from finmy.person_epg.event.scheduling import Task
from finmy.person_epg.event.artifacts import artifact_summary
from finmy.person_epg.event.status import inspect_run


def test_http_failure_reaches_state_and_cli_without_sdk_message(tmp_path, payload):
    info = dict(error_type='PermissionDeniedError', http_status=403, request_id='request-123',
                error_code='AccountOverdueError')
    error = ModelTransportError('PermissionDeniedError', diagnostics=info)
    run = runtime.Execution(tmp_path, payload, EventBuildConfig(), Model([error]))
    run.execute_tasks('extraction', [Task('extract.0', run.infer_steps(
        'extract.0', 'system', {}, seed_facts(payload), valid))])
    failure = run.state['calls'][0]['failure']
    assert failure['error_type'] == 'PermissionDeniedError'
    assert failure['http_status'] == 403 and not failure['retryable']
    assert 'AccountOverdueError' in failure['summary']
    assert run.state['task_states']['extraction:extract.0']['failure'] == failure
    summary = inspect_run(tmp_path)
    assert summary['errors'][0]['request_id'] == 'request-123'
    assert (tmp_path / failure['path']).is_file()


def test_config_extensions_preserve_semantic_fingerprint():
    old = EventBuildConfig(max_read_calls=40, max_read_rounds=2)
    state = dict(config=asdict(old), calls=[{}]*50, reads=[{}]*40)
    settings = resume_settings(state, extra_calls=60, extra_read_calls=40, max_read_rounds=4)
    new = EventBuildConfig.from_saved({**state['config'], **settings})
    assert new.max_calls == 110 and effective_read_limits(new)['read_calls'] == 80
    assert effective_read_limits(new)['read_rounds'] == 4
    assert runtime.semantic_config(new) == runtime.semantic_config(old)
    assert EventBuildConfig.from_saved({**asdict(new), **resume_settings(
        {**state, 'config': asdict(new)}, max_read_rounds=2)}).read_round_extension == 2


def test_explicit_transport_upgrade_reuses_paid_response(tmp_path, payload, monkeypatch):
    original = runtime.code_identity()
    monkeypatch.setattr(runtime, 'code_identity', lambda: 'prior-transport-implementation')
    run = runtime.Execution(tmp_path, payload, EventBuildConfig(), Model([{'ok': True}]))
    facts = seed_facts(payload)
    run.infer('extract.0', 'system', {}, facts, valid)
    model = Model([])
    monkeypatch.setattr(runtime, 'code_identity', lambda: original)
    resumed = runtime.Execution(tmp_path, payload, run.config, model, resume=True, resume_transport_upgrade=True)
    assert resumed.infer('extract.0', 'system', {}, facts, valid) == {'ok': True}
    assert not model.calls and len(resumed.state['calls']) == 1
    assert resumed.state['execution_upgrades'][-1]['kind'] == 'transport-guard'


def test_renderer_and_smoke_files_are_not_execution_dependencies():
    manifest = runtime.code_manifest()
    assert 'person_epg/event/config.py' in manifest
    for name in ('graph_html.py', 'graph_layout.py', 'graph_view.py', 'graph_labels.py', 'rendering.py', 'state_machine_smoke.py'):
        assert 'person_epg/event/' + name not in manifest


def test_old_rendered_hierarchy_survives_new_partial_attempt(tmp_path, graph):
    from finmy.person_epg.event.graph_html import render_graph_html
    from finmy.person_epg.event.records import sha256
    for number, hierarchy in [(1, True), (2, False)]:
        attempt = tmp_path / 'attempts' / str(number).zfill(4)
        attempt.mkdir(parents=True)
        package = json.loads(json.dumps(graph))
        if not hierarchy:
            package['stages'], package['phases'] = [], []
        raw = json.dumps(package).encode()
        (attempt / 'epg.json').write_bytes(raw)
        (attempt / 'gantt.html').write_text(render_graph_html(package, graph_sha256=sha256(raw)))
        (attempt / 'checks.json').write_text(json.dumps(dict(graph_sha256=sha256(raw), result_status='partial')))
    summary = artifact_summary(tmp_path)
    assert summary['latest_rendered_artifact']['attempt'] == '0002'
    assert summary['latest_hierarchy_artifact']['attempt'] == '0001'


def test_sdk_messages_and_secrets_are_not_in_error_summary():
    error = RuntimeError('Authorization=secret sk-private https://provider.example/key')
    assert 'secret' not in json.dumps(failure_details(error))
    detail = failure_details(ValueError('Bad api_key=secret sk-private https://provider.example/key'))
    assert 'secret' not in json.dumps(detail) and 'sk-private' not in json.dumps(detail)


def test_workbench_resume_uses_execution_identity_instead_of_renderer_digest(monkeypatch):
    from finmy.workbench import build_tasks
    from finmy.person_epg.event.schema import GRAPH_VERSION
    body = dict(kind='person_event', graph_schema_version=GRAPH_VERSION,
        person_execution_code=build_tasks.person_execution_version())
    monkeypatch.setattr(build_tasks, 'code_version', lambda: {'commit':'renderer-only-commit'})
    build_tasks.check_person_code(body)
    monkeypatch.setattr(build_tasks, 'person_execution_version', lambda: 'changed-execution')
    with pytest.raises(ValueError):
        build_tasks.check_person_code(body)
