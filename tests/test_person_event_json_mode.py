"""Opt-in JSON requests, comparable task inputs and immutable recovery identity."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

from openai import BadRequestError
import pytest

from test_model_api import offline, transport
from test_person_event_contract import payload
from test_person_event_runtime import Model as OfflineModel, valid
from test_person_event_workbench import setup as search_setup
from finmy.model_config import person_build_json_mode_supported
from finmy.person_epg.build import Model
from finmy.person_epg.building.completion_errors import IncompleteCompletionError
from finmy.person_epg.event.prompts import system_prompt
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, semantic_config, write_json
from finmy.workbench.build_tasks import BuildController


@pytest.mark.parametrize('value', [None, 0, 1, 'true', 'false'])
def test_mode_is_an_explicit_boolean(value):
    with pytest.raises(ValueError, match='api_json_mode'):
        EventBuildConfig(api_json_mode=value)


@pytest.mark.parametrize('name', ['tokenhub/kimi-k3.1-pro', 'ark/doubao-seed-evolving',
                                  'ark/custom-model', '', None])
def test_unverified_modes_fail_before_transport(name, transport):
    assert not person_build_json_mode_supported(name)
    with pytest.raises(ValueError):
        EventBuildConfig(lm_name=name, api_json_mode=True)
    assert not transport['clients']


def test_bare_ark_id_and_missing_mode_are_compatible():
    assert person_build_json_mode_supported('kimi-k3-1-pro-261024')
    assert EventBuildConfig(lm_name='kimi-k3-1-pro-261024', api_json_mode=True).api_json_mode
    old = asdict(EventBuildConfig())
    old.pop('api_json_mode')
    old.pop('full_corpus_supplement')
    assert not EventBuildConfig(**old).api_json_mode
    old.pop('max_calls')
    assert semantic_config(EventBuildConfig()) == old


@pytest.mark.parametrize('role', ['extraction', 'consolidation', 'organization', 'relations'])
def test_role_requests_differ_only_in_response_format(transport, role):
    models = [Model(EventBuildConfig(api_json_mode=flag, max_new_tokens=65536))
              for flag in (False, True)]
    prompt = system_prompt(role)
    assert 'json' in prompt.lower()
    for flag, model in zip((False, True), models):
        assert model(prompt, '{}', role) == '{"ok":true}'
        assert model.last_diagnostics['api_json_mode'] is flag
        assert model.last_usage['total_tokens'] == 35
        assert model.adapter.client.max_retries == 0
    ordinary, constrained = [deepcopy(body) for _, body in transport['requests']]
    assert 'response_format' not in ordinary
    assert constrained.pop('response_format') == {'type': 'json_object'}
    assert ordinary == constrained
    assert ordinary['max_tokens'] == 65536 and ordinary['stream'] is True
    assert ordinary['stream_options'] == {'include_usage': True}
    assert ordinary['reasoning_effort'] == 'low'
    assert not {'temperature', 'top_p', 'thinking'} & ordinary.keys()


@pytest.mark.parametrize('failure', ['unsupported_format', 'truncation'])
def test_json_request_failure_never_falls_back(transport, failure):
    model = Model(EventBuildConfig(api_json_mode=True))
    if failure == 'unsupported_format':
        transport['status'] = 400
        error = BadRequestError
    else:
        transport['finish'] = 'length'
        error = IncompleteCompletionError
    with pytest.raises(error):
        model('Return JSON', '{}', 'extract')
    assert len(transport['requests']) == 1
    assert transport['requests'][0][1]['response_format'] == {'type': 'json_object'}


def test_json_mode_keeps_local_reading_and_result_validation(tmp_path, payload, transport):
    read = dict(tool='read_sample', sample_id='SAMPLE-1', start=0, end=30)
    transport['contents'] = iter([json.dumps({'read_requests': [read]}), '{"wrong":true}', '{"ok":true}'])
    config = EventBuildConfig(api_json_mode=True)
    run = Execution(tmp_path, payload, config, Model(config))
    assert run.infer('relations', 'Return JSON', {}, seed_facts(payload), valid) == {'ok': True}
    assert [call['status'] for call in run.state['calls']] == ['read_requested', 'invalid_output', 'accepted']
    assert all(call['api_json_mode'] is True for call in run.state['calls'])
    assert all(call['reasoning_effort'] == 'low' for call in run.state['calls'])
    assert len(run.state['reads']) == 1
    assert all(body['response_format'] == {'type': 'json_object'} for _, body in transport['requests'])
    requests = list((tmp_path/'attempts/0001/steps').glob('*/request.json'))
    assert len(requests) == 3
    assert all(json.loads(path.read_text())['api_json_mode'] is True for path in requests)
    resumed = Execution(tmp_path, payload, config, OfflineModel([]), resume=True)
    assert resumed.infer('relations', 'Return JSON', {}, seed_facts(payload), valid) == {'ok': True}
    assert not resumed.model.calls and len(resumed.state['calls']) == 3


@pytest.mark.parametrize('original', [False, True])
def test_resume_cannot_change_mode_or_write_state(tmp_path, payload, original):
    run = Execution(tmp_path, payload, EventBuildConfig(api_json_mode=original), OfflineModel([{'ok': True}]))
    run.infer('extract', 'Return JSON', {}, seed_facts(payload), valid)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='semantic settings'):
        Execution(tmp_path, payload, EventBuildConfig(api_json_mode=not original), OfflineModel([]), resume=True)
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_new_modes_have_distinct_dependencies(tmp_path, payload):
    runs = []
    for flag in (False, True):
        run = Execution(tmp_path/str(flag), payload, EventBuildConfig(api_json_mode=flag), OfflineModel([{'ok': True}]))
        run.infer('extract', 'Return JSON', {}, seed_facts(payload), valid)
        runs.append(run)
    a, b = runs
    assert a.state['input_sha256'] == b.state['input_sha256']
    assert a.state['code_sha256'] == b.state['code_sha256']
    assert a.state['calls'][0]['request_fingerprint'] == b.state['calls'][0]['request_fingerprint']
    assert a.state['calls'][0]['dependency'] != b.state['calls'][0]['dependency']
    fingerprints = [json.loads((run.directory/'provenance.json').read_text())['config_fingerprint'] for run in runs]
    assert fingerprints[0] != fingerprints[1]


def test_ordinary_checkpoint_keeps_identity_when_field_was_absent(tmp_path, payload):
    # A same-code legacy configuration fixture, not a code-mismatch exemption.
    run = Execution(tmp_path, payload, EventBuildConfig(), OfflineModel([{'ok': True}]))
    run.infer('extract', 'Return JSON', {}, seed_facts(payload), valid)
    old = deepcopy(run.state)
    old['config'].pop('api_json_mode')
    write_json(tmp_path/'state.json', old)
    write_json(tmp_path/'config.json', old['config'])
    resumed = Execution(tmp_path, payload, EventBuildConfig(max_calls=60), OfflineModel([]), resume=True)
    assert resumed.infer('extract', 'Return JSON', {}, seed_facts(payload), valid) == {'ok': True}
    assert not resumed.model.calls


def test_prepare_two_workbench_tasks_changes_only_mode(search_setup, tmp_path):
    store, search, tid, requests = search_setup
    builds = BuildController(store)
    before = deepcopy(search.inspect(tid))
    previous_requests = list(requests)
    params = dict(lm_name='ark/kimi-k3-1-pro-261024', max_calls=60, max_new_tokens=65536,
                  max_context_chars=240000, extraction_chars=12000,
                  max_read_calls=60, max_read_chars=160000, final_repair_rounds=1)
    rows = [builds.inspect(builds.create_person(search, tid, dict(params, api_json_mode=flag),
            confirmed=True, artifact_root=tmp_path/'runs')) for flag in (False, True)]
    assert all(row['status'] == 'ready' for row in rows)
    assert rows[0]['id'] != rows[1]['id']
    a, b = [row['body'] for row in rows]
    for field in ('input', 'input_hash', 'provenance', 'scope_hash', 'code', 'person_code'):
        assert a[field] == b[field]
    ordinary, constrained = [deepcopy(body['person_config']) for body in (a, b)]
    assert ordinary.pop('api_json_mode') is False
    assert constrained.pop('api_json_mode') is True
    assert ordinary == constrained
    assert ordinary['reasoning_effort'] == 'by_stage'
    assert all(not Path(body['artifact_directory']).exists() for body in (a, b))
    assert search.inspect(tid) == before and requests == previous_requests
