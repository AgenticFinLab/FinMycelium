"""Model-service routing through real SDK serialization with network blocked."""
import json
import socket
from pathlib import Path

import httpx
from openai import OpenAI, RateLimitError
import pytest

from finmy.model_api import ModelAPIInference
from finmy.model_config import generation_parameters, model_name, tokenhub_base_url
from finmy.person_epg.build import Model
from finmy.person_epg.building.completion_errors import IncompleteCompletionError
from finmy.person_epg.event.runtime import EventBuildConfig
from finmy.search.agent import LmbaseModel
from finmy.search.state import SearchConfig
from finmy.workbench.build_tasks import build_config
from finmy.workbench.store import Store
from finmy.workbench.domain import MODELS, TOKENHUB_MODELS

ROOT = Path(__file__).resolve().parents[1]

# Expected wire values, independent of the production policy registry.
PRESET_SAMPLING = {
    'doubao-seed-2-0-pro-260215': {'temperature': 1.0, 'top_p': 0.95},
    'doubao-seed-2-1-lite-260915': {'temperature': 1.0, 'top_p': 0.95},
    'glm-5-2-260617': {'temperature': 1.0, 'top_p': 0.95},
    'deepseek-v4-pro-ga-260813': {'temperature': 1.0, 'top_p': 0.95},
    'deepseek-v4-1-flash-261017': {'temperature': 1.0, 'top_p': 0.95},
    'glm-5.3': {'temperature': 1.0, 'top_p': 0.95},
    'glm-5.3-flash': {'temperature': 1.0, 'top_p': 0.95},
    'deepseek-v4-pro-202606': {'temperature': 1.0, 'top_p': 1.0},
    'deepseek/deepseek-flash': {'temperature': 1.0, 'top_p': 1.0},
    'hy4': {'temperature': 0.9, 'top_p': 1.0},
    'kimi-k3.1-pro': {},
}
PRESET_CASES = ([('ark', model) for model in MODELS.values()]
               + [('tokenhub', model) for models in TOKENHUB_MODELS.values() for model in models.values()])


def assert_sampling(body, remote_model):
    assert {k: body[k] for k in ('temperature', 'top_p') if k in body} == PRESET_SAMPLING[remote_model]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('External network is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setenv('HUNYUAN_API_KEY', 'synthetic-tokenhub-key')
    monkeypatch.setenv('HUNYUAN_BASE_URL', 'https://tokenhub.tencentmaas.com')
    monkeypatch.setenv('ARK_API_KEY', 'synthetic-ark-key')


@pytest.fixture
def transport(monkeypatch):
    state = {'requests': [], 'clients': [], 'finish': 'stop', 'status': 200,
             'content': '{"ok":true}'}

    def handle(request):
        body = json.loads(request.content)
        state['requests'].append((request, body))
        if 'connection_error' in state:
            raise state['connection_error']
        headers = state.get('headers', {'x-request-id': 'request-fixture-123'})
        if state['status'] != 200:
            return httpx.Response(state['status'], headers=headers,
                json={'error': {'message': state.get('error_message', 'synthetic error')}})
        content = next(state['contents']) if 'contents' in state else state['content']
        usage = {'prompt_tokens': 20, 'completion_tokens': 15, 'total_tokens': 35,
                 'completion_tokens_details': {'reasoning_tokens': 5}}
        if body.get('stream'):
            def delta(value, finish=None):
                return {'choices': [{'index': 0, 'delta': value, 'finish_reason': finish}]}
            chunks = state.get('stream_chunks', [
                delta({'role': 'assistant', 'reasoning_content': 'private reasoning'}),
                delta({'content': content[:4]}), delta({'content': content[4:]}),
                {**delta({}, state['finish']), 'usage': usage}, {'choices': [], 'usage': usage}])
            class Events(httpx.SyncByteStream):
                def __iter__(self):
                    yield b': heartbeat\n\n'
                    for chunk in chunks:
                        value = {'id': 'test-response', 'object': 'chat.completion.chunk',
                                 'created': 1, 'model': body['model'], **chunk}
                        yield ('data: ' + json.dumps(value) + '\n\n').encode()
                    if 'stream_error' in state:
                        raise state['stream_error']
                    if state.get('send_done', True):
                        yield b'data: [DONE]\n\n'
                def close(self):
                    state['closed_streams'] = state.get('closed_streams', 0) + 1
            return httpx.Response(200, headers={**headers, 'content-type': 'text/event-stream'}, stream=Events())
        return httpx.Response(200, json={
            'id': 'test-response', 'object': 'chat.completion', 'created': 1, 'model': body['model'],
            'choices': [{'index': 0, 'finish_reason': state['finish'],
                         'message': {'role': 'assistant', 'content': content}}],
            'usage': usage,
        })

    def client(**kwargs):
        result = OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        state['clients'].append(result)
        return result

    monkeypatch.setattr('lmbase.inference.api_call.OpenAI', client)
    yield state
    for client in state['clients']:
        client.close()


@pytest.mark.parametrize('name,expected', [
    ('old-ark-endpoint', 'ark/old-ark-endpoint'),
    ('ark/old-ark-endpoint', 'ark/old-ark-endpoint'),
    ('tokenhub/synthetic-hy', 'tokenhub/synthetic-hy'),
    ('tokenhub/deepseek/remote-model', 'tokenhub/deepseek/remote-model'),
])
def test_model_names_preserve_remote_namespaces(name, expected):
    assert model_name(name) == expected


@pytest.mark.parametrize('name', ['', None, 'tokenhub/', 'tokenhub/a b',
                                 'unknown/model', 'tokenhub//model', 'tokenhub/../model'])
def test_invalid_model_names_fail_before_client_creation(name, transport):
    with pytest.raises(ValueError):
        ModelAPIInference(name)
    assert transport['clients'] == []


def test_tokenhub_key_id_is_not_a_credential(monkeypatch, transport):
    monkeypatch.delenv('HUNYUAN_API_KEY')
    monkeypatch.setenv('HUNYUAN_TOKENHUB_KEY_ID', 'synthetic-display-id')
    with pytest.raises(ValueError, match='HUNYUAN_API_KEY'):
        ModelAPIInference('tokenhub/synthetic-hy')
    assert transport['clients'] == []


@pytest.mark.parametrize('base', ['https://tokenhub-intl.tencentmaas.com',
                                 'https://tokenhub-intl.tencentmaas.com/v1/'])
def test_sdk_base_normalization_preserves_region(monkeypatch, base):
    monkeypatch.setenv('HUNYUAN_BASE_URL', base)
    assert tokenhub_base_url() == 'https://tokenhub-intl.tencentmaas.com/v1'


@pytest.mark.parametrize('base', ['https://tokenhub.tencentmaas.com/v1/chat/completions',
    'https://tokenhub.tencentmaas.com/plan/v3', 'https://user:secret@example.org/v1',
    'https://example.org/v1?key=secret'])
def test_bad_base_is_rejected_without_echoing_secrets(monkeypatch, transport, base):
    monkeypatch.setenv('HUNYUAN_BASE_URL', base)
    with pytest.raises(ValueError, match='HUNYUAN_BASE_URL') as exc:
        ModelAPIInference('tokenhub/synthetic-hy')
    assert base not in str(exc.value)
    assert 'secret' not in str(exc.value)
    assert transport['clients'] == []


@pytest.mark.parametrize('search_name,build_name', [
    ('tokenhub/synthetic-search', 'ark/synthetic-build'),
    ('ark/synthetic-search', 'tokenhub/vendor/synthetic-build'),
])
def test_search_and_person_build_route_independently(transport, search_name, build_name):
    search = LmbaseModel(SearchConfig(lm_name=search_name, allow_network=True))
    build = Model(EventBuildConfig(lm_name=build_name))
    assert search({'task': 'synthetic scope'}) == '{"ok":true}'
    assert build('Return JSON', 'synthetic evidence', 'Extract') == '{"ok":true}'
    for call, name in zip(transport['requests'], (search_name, build_name)):
        request, body = call
        provider, identifier = name.split('/', 1)
        assert body['model'] == identifier
        assert request.headers['Authorization'] == 'Bearer synthetic-' + provider + '-key'
        assert str(request.url) == ('https://tokenhub.tencentmaas.com/v1/chat/completions'
            if provider == 'tokenhub' else 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        assert 'tools' not in body and 'web_search_options' not in body
    assert [body['max_tokens'] for _, body in transport['requests']] == [4096, 12288]
    for model in (search, build):
        assert model.adapter.client.max_retries == 0
        assert model.last_usage['completion_tokens_details']['reasoning_tokens'] == 5


def test_search_gate_does_not_initialize_transport(transport):
    with pytest.raises(PermissionError):
        LmbaseModel(SearchConfig(lm_name='tokenhub/synthetic-hy'))({})
    assert transport['clients'] == []


@pytest.mark.parametrize('kind', ['search', 'person'])
def test_tokenhub_truncation_and_errors_are_not_silently_retried(transport, kind):
    model = (LmbaseModel(SearchConfig(lm_name='tokenhub/synthetic-hy', allow_network=True))
             if kind == 'search' else Model(EventBuildConfig(lm_name='tokenhub/synthetic-hy')))
    invoke = (lambda: model({})) if kind == 'search' else (lambda: model('system', 'user', 'Extract'))
    transport['finish'] = 'length'
    with pytest.raises(ValueError if kind == 'search' else IncompleteCompletionError):
        invoke()
    assert model.last_usage['completion_tokens'] == 15
    assert len(transport['requests']) == 1
    transport['status'] = 429
    with pytest.raises(RateLimitError):
        invoke()
    assert len(transport['requests']) == 2
    assert model.last_usage is None


@pytest.mark.parametrize('kind', ['AgentEventBuilder', 'SparseRagBuilder'])
@pytest.mark.parametrize('provider,remote_model',
    [('ark', model) for model in MODELS.values()]
    + [('tokenhub', model) for model in ['vendor/synthetic-build', *TOKENHUB_MODELS['build'].values()]])
def test_workbench_and_bounded_event_builders_use_model_policy(tmp_path, transport, kind, provider, remote_model):
    from finmy.runner.build_only_runner import select_builder, replay
    from finmy.runner.sparse_build_runner import load_inputs, preflight
    from test_sparse_runtime_entry import responses

    settings = {'model': provider + '/' + remote_model, 'builder': kind, 'concurrency': 1}
    store = Store(tmp_path / 'workspace')
    store.save_settings(settings)
    config = build_config(store.settings(), tmp_path / 'build')
    assert config['lm_name'] == settings['model']
    cls, checked = select_builder(config)
    inputs, _ = load_inputs(ROOT / 'examples/sparse_input.json')
    report = preflight(checked, inputs)
    assert report['credential_present'] is True
    assert report['online_compatibility_verified'] is False
    assert transport['clients'] == []
    transport['contents'] = iter(json.dumps(r) for r in responses())
    builder = cls(build_config=config)
    result = builder.run(inputs)
    assert result.event_cascades
    assert replay(builder.save_dir)['status'] == 'replay_pass'
    assert len(transport['requests']) == 11
    assert all(body['model'] == remote_model for _, body in transport['requests'])
    for _, body in transport['requests']:
        if remote_model in PRESET_SAMPLING:
            assert_sampling(body, remote_model)
        if remote_model == 'kimi-k3.1-pro':
            assert body['max_completion_tokens'] == 12288
            assert not {'max_tokens', 'temperature', 'top_p'} & body.keys()
        else:
            assert body['max_tokens'] == 12288
    assert builder.agents_lm.client.max_retries == 0
    assert result.extras['usage']['prompt_tokens'] == 220
    assert 'synthetic-' + provider + '-key' not in (Path(builder.save_dir) / 'RunManifest.json').read_text()


def test_workbench_preserves_legacy_ark_settings(tmp_path):
    config = build_config({'model': 'legacy-endpoint', 'builder': 'SparseRagBuilder', 'concurrency': 1}, tmp_path)
    assert config['lm_name'] == 'ark/legacy-endpoint'


@pytest.mark.parametrize('provider', ['ark', 'tokenhub'])
def test_original_agent_transport_keeps_its_existing_workflow(tmp_path, transport, provider):
    from finmy.builder.agent_build.main_build import AgentEventBuilder
    from finmy.runner.sparse_build_runner import load_inputs
    from test_sparse_runtime_entry import responses

    config = build_config({'model': provider + '/synthetic-build', 'builder': 'AgentEventBuilder',
                           'concurrency': 1}, tmp_path)
    transport['contents'] = iter(json.dumps(r) for r in responses())
    inputs, _ = load_inputs(ROOT / 'examples/sparse_input.json')
    builder = AgentEventBuilder(build_config=config)
    output = builder.run(inputs)
    assert output.event_cascades
    assert len(transport['requests']) == 11
    assert all(body['model'] == 'synthetic-build' for _, body in transport['requests'])


def test_batch_api_remains_available_and_does_not_format_supplied_messages(transport):
    from lmbase.inference.base import InferInput
    adapter = ModelAPIInference('tokenhub/synthetic-model', {'max_tokens': 512})
    messages = [{'role': 'user', 'content': '{literal: braces}'}]
    result = adapter.run([InferInput('', '', messages=messages)])
    assert len(result.outputs) == 1
    assert transport['requests'][0][1]['messages'] == messages
    with pytest.raises(ValueError, match='not both'):
        adapter.run([], infer_input=InferInput('', ''))
    assert len(transport['requests']) == 1


@pytest.mark.parametrize('provider,purpose,remote_model',
    [('ark', purpose, model) for purpose in ('search', 'build') for model in MODELS.values()]
    + [('tokenhub', purpose, model) for purpose, models in TOKENHUB_MODELS.items() for model in models.values()])
def test_each_preset_reaches_its_role_transport_with_the_exact_model_id(transport, provider, purpose, remote_model):
    lm_name = provider + '/' + remote_model
    if purpose == 'search':
        model = LmbaseModel(SearchConfig(lm_name=lm_name, allow_network=True))
        result = model({'task': 'synthetic task'})
        cap = 4096
    else:
        model = Model(EventBuildConfig(lm_name=lm_name))
        result = model('Return JSON', 'Synthetic source text', 'Extract')
        cap = 12288
    assert result == '{"ok":true}'
    request, body = transport['requests'][0]
    assert str(request.url) == ('https://tokenhub.tencentmaas.com/v1/chat/completions'
        if provider == 'tokenhub' else 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
    assert body['model'] == remote_model
    assert request.headers['Authorization'] == 'Bearer synthetic-' + provider + '-key'
    if remote_model == 'kimi-k3.1-pro':
        assert body['max_completion_tokens'] == cap
        assert not {'max_tokens', 'temperature', 'top_p'} & body.keys()
    else:
        assert body['max_tokens'] == cap
    assert_sampling(body, remote_model)
    if purpose == 'build':
        assert body['stream'] is True and body['stream_options'] == {'include_usage': True}
    assert len(transport['requests']) == 1


@pytest.mark.parametrize('provider,remote_model', PRESET_CASES)
def test_preset_sampling_survives_inherited_and_extra_body_overrides(transport, provider, remote_model):
    from copy import deepcopy
    from lmbase.inference.base import InferInput
    original = {'max_new_tokens': 2222, 'temperature': 0.2, 'top_p': 0.8,
                'extra_body': {'temperature': 0.1, 'top_p': 0.7, 'reasoning_effort': 'high'}}
    before = deepcopy(original)
    adapter = ModelAPIInference(provider + '/' + remote_model, original)
    result = adapter.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    assert result.response == '{"ok":true}'
    body = transport['requests'][0][1]
    assert_sampling(body, remote_model)
    limit_key = 'max_completion_tokens' if remote_model == 'kimi-k3.1-pro' else 'max_tokens'
    assert body[limit_key] == 2222
    assert body['reasoning_effort'] == 'high'
    assert original == before


@pytest.mark.parametrize('provider,remote_model', PRESET_CASES)
@pytest.mark.parametrize('parameters', [None, {}])
def test_sampling_defaults_preserve_direct_adapter_output_cap(transport, provider, remote_model, parameters):
    from lmbase.inference.base import InferInput
    adapter = ModelAPIInference(provider + '/' + remote_model, parameters)
    adapter.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    body = transport['requests'][0][1]
    assert_sampling(body, remote_model)
    limit_key = 'max_completion_tokens' if remote_model == 'kimi-k3.1-pro' else 'max_tokens'
    assert body[limit_key] == 8192
    assert set(body) & {'max_tokens', 'max_completion_tokens', 'max_new_tokens'} == {limit_key}


@pytest.mark.parametrize('options,control', [
    ({'extra_body': {'thinking': {'type': 'disabled'}}}, {'thinking': {'type': 'disabled'}}),
    ({'reasoning_effort': 'none'}, {'reasoning_effort': 'none'}),
    ({'extra_body': {'reasoning_effort': 'none'}}, {'reasoning_effort': 'none'}),
    ({'reasoning_effort': 'high', 'extra_body': {'reasoning_effort': 'none'}}, {'reasoning_effort': 'none'}),
])
def test_ark_flash_nonthinking_sampling_preserves_mode_and_limit(transport, options, control):
    from copy import deepcopy
    from lmbase.inference.base import InferInput
    original = {'max_tokens': 1234, 'temperature': 0.2, 'top_p': 0.7}
    original.update(options)
    before = deepcopy(original)
    adapter = ModelAPIInference('ark/deepseek-v4-1-flash-261017', original)
    adapter.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    body = transport['requests'][0][1]
    assert body['temperature'] == 1.0 and body['top_p'] == 1.0
    assert body['max_tokens'] == 1234
    assert {key: body[key] for key in control} == control
    assert original == before


@pytest.mark.parametrize('remote_model', list(MODELS.values()))
def test_legacy_bare_ark_model_ids_use_the_same_sampling(transport, remote_model):
    from lmbase.inference.base import InferInput
    adapter = ModelAPIInference(remote_model, {'max_tokens': 1234, 'temperature': 0.2})
    adapter.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    assert_sampling(transport['requests'][0][1], remote_model)


@pytest.mark.parametrize('name', ['ark/glm-5.3', 'tokenhub/custom-model'])
def test_sampling_policy_preserves_other_services_and_custom_models(transport, name):
    from lmbase.inference.base import InferInput
    parameters = {'max_tokens': 1234, 'temperature': 0.2, 'top_p': 0.8}
    adapter = ModelAPIInference(name, parameters)
    adapter.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    body = transport['requests'][0][1]
    assert {key: body[key] for key in parameters} == parameters


@pytest.mark.parametrize('field', ['max_tokens', 'max_new_tokens', 'max_completion_tokens'])
def test_kimi_preserves_explicit_limits_and_does_not_mutate_configuration(field):
    from copy import deepcopy
    original = {field: 2222, 'temperature': 0.2, 'top_p': 0.95,
                'extra_body': {'temperature': 0.2}, 'reasoning_effort': 'high'}
    before = deepcopy(original)
    effective = generation_parameters('tokenhub/kimi-k3.1-pro', original)
    assert effective == {'max_completion_tokens': 2222, 'reasoning_effort': 'high', 'extra_body': {}}
    assert original == before
    assert generation_parameters('ark/kimi-k3.1-pro', original) == original


@pytest.mark.parametrize('parameters', [
    {'max_tokens': 10, 'max_completion_tokens': 20},
    {'extra_body': {'thinking': {'type': 'disabled'}}},
    {'reasoning_effort': 'medium'},
])
def test_invalid_kimi_options_fail_before_requests(parameters, transport):
    with pytest.raises(ValueError):
        ModelAPIInference('tokenhub/kimi-k3.1-pro', parameters)
    assert transport['clients'] == []


def test_kimi_direct_adapter_default_and_single_input_use_compatible_parameters(transport):
    from lmbase.inference.base import InferInput
    model = ModelAPIInference('tokenhub/kimi-k3.1-pro')
    result = model.run(infer_input=InferInput('Return JSON', 'Synthetic source'))
    assert result.response == '{"ok":true}'
    body = transport['requests'][0][1]
    assert body['max_completion_tokens'] == 8192
    assert 'max_tokens' not in body
