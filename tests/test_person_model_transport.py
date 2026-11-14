"""Exercise streaming through the real SDK and a network-blocked SSE transport."""
import json

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError, APITimeoutError

from test_model_api import offline, transport
from test_person_event_contract import payload
from finmy.person_epg.build import Model
from finmy.person_epg.building.completion_errors import IncompleteCompletionError
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution


def chunk(content=None, finish=None, **extra):
    return {'choices': [{'index': 0, 'delta': {'content': content, **extra}, 'finish_reason': finish}]}


def model():
    return Model(EventBuildConfig(lm_name='tokenhub/kimi-k3.1-pro', max_new_tokens=32768))


def test_stream_joins_only_answer_and_keeps_usage_once(transport):
    m = model()
    assert m('system', 'source', 'extract') == '{"ok":true}'
    body = transport['requests'][0][1]
    assert body['stream'] is True and body['stream_options'] == {'include_usage': True}
    assert body['max_completion_tokens'] == 32768 and 'max_tokens' not in body
    assert m.adapter.client.max_retries == 0 and m.adapter.client.timeout == 900
    assert m.last_usage['total_tokens'] == 35  # repeated cumulative usage is not doubled
    assert m.last_diagnostics['reasoning_chars'] == len('private reasoning')
    assert m.last_diagnostics['request_id'] == 'request-fixture-123'
    assert m.last_diagnostics['first_chunk_seconds'] is not None
    assert m.last_diagnostics['phase'] == 'completed'
    assert 'private reasoning' not in json.dumps(m.last_diagnostics)
    assert transport['closed_streams'] == 1


@pytest.mark.parametrize('finish,delta', [
    (None, {}), ('length', {}), ('content_filter', {}),
    ('stop', {'refusal': 'private refusal'}),
    ('stop', {'tool_calls': [{'index': 0, 'id': 't1', 'type': 'function',
                            'function': {'name': 'not_allowed', 'arguments': '{}'}}]}),
    ('stop', {'function_call': {'name': 'not_allowed', 'arguments': '{}'}}),
])
def test_even_parseable_json_needs_clean_text_completion(transport, finish, delta):
    transport['stream_chunks'] = [chunk('{"ok":true}', finish, **delta)]
    m = model()
    with pytest.raises(IncompleteCompletionError):
        m('system', 'source', 'extract')
    assert len(transport['requests']) == 1 and transport['closed_streams'] == 1
    assert m.last_usage is None
    assert m.last_diagnostics['phase'] == 'incomplete'


@pytest.mark.parametrize('chunks', [[], [chunk(None, 'stop')], [chunk(None, 'stop', reasoning_content='private')]])
def test_empty_and_reasoning_only_streams_are_incomplete(transport, chunks):
    transport['stream_chunks'] = chunks
    with pytest.raises(IncompleteCompletionError):
        model()('system', 'source', 'extract')


def test_usage_is_optional_but_not_invented_or_reused(transport):
    m = model()
    m('system', 'source', 'extract')
    assert m.last_usage is not None
    transport['stream_chunks'] = [chunk('{"ok":true}', 'stop')]
    assert m('system', 'source', 'extract') == '{"ok":true}'
    assert m.last_usage is None


@pytest.mark.parametrize('finish', [None, 'stop'])
def test_disconnect_does_not_accept_partial_or_complete_looking_json(tmp_path, payload, transport, finish):
    transport['stream_chunks'] = [chunk('{"ok":true}', finish)]
    transport['stream_error'] = httpx.RemoteProtocolError('Bearer synthetic-secret https://private/?key=secret')
    m = model()
    run = Execution(tmp_path/'run', payload, m.config, m)
    with pytest.raises(httpx.RemoteProtocolError):
        run.infer('extract', 'contract', {}, seed_facts(payload), lambda value: None)
    call = run.state['calls'][0]
    assert call['status'] == 'transport_error' and call['usage_status'] == 'unknown'
    assert call['error_chain'] == ['RemoteProtocolError']
    assert call['transport']['content_chars'] > 0 and not call['transport']['stream_exhausted']
    assert not list((tmp_path/'run/checkpoints').glob('*.json'))
    assert not list((tmp_path/'run/attempts').rglob('response.json'))
    assert len(transport['requests']) == 1 and transport['closed_streams'] == 1
    assert 'synthetic-secret' not in (tmp_path/'run/state.json').read_text()
    assert 'private/' not in (tmp_path/'run/state.json').read_text()
    # An explicit same-code resume preserves the failed call and starts a new one.
    del transport['stream_error']
    transport['stream_chunks'] = [chunk('{"ok":true}', 'stop')]
    resumed = Execution(tmp_path/'run', payload, m.config, m, resume=True)
    assert resumed.infer('extract', 'contract', {}, seed_facts(payload), lambda value: None) == {'ok': True}
    assert len(resumed.state['calls']) == 2
    assert resumed.state['calls'][0] == call and len(transport['requests']) == 2


@pytest.mark.parametrize('failure,expected', [
    (httpx.ConnectError, APIConnectionError), (httpx.ReadTimeout, APITimeoutError),
])
def test_connection_error_retains_safe_cause_chain(transport, failure, expected):
    transport['connection_error'] = failure('Bearer synthetic-secret https://private/?key=secret')
    m = model()
    with pytest.raises(expected):
        m('system', 'source', 'extract')
    info = m.last_diagnostics
    assert info['phase'] == 'connecting' and info['chunks'] == 0
    assert info['error_chain'][:2] == [expected.__name__, failure.__name__]
    assert len(transport['requests']) == 1
    assert 'synthetic-secret' not in json.dumps(info) and 'private/' not in json.dumps(info)


def test_http_failure_records_status_and_request_id_without_headers_or_body(transport):
    transport['status'] = 401
    transport['error_message'] = 'Bearer synthetic-secret https://private/?key=secret'
    transport['headers'] = {'x-request-id': 'req-401', 'set-cookie': 'private-cookie'}
    m = model()
    with pytest.raises(AuthenticationError):
        m('system', 'source', 'extract')
    info = m.last_diagnostics
    assert info['http_status'] == 401 and info['request_id'] == 'req-401'
    assert info['error_type'] == 'AuthenticationError'
    assert not any(s in json.dumps(info) for s in ('synthetic-secret', 'private-cookie', 'private/'))
    assert len(transport['requests']) == 1


@pytest.mark.parametrize('finish', ['length', None])
def test_incomplete_stream_is_recorded_without_format_retry(tmp_path, payload, transport, finish):
    transport['finish'] = finish
    m = model()
    run = Execution(tmp_path/'run', payload, m.config, m)
    with pytest.raises(IncompleteCompletionError):
        run.infer('extract', 'contract', {}, seed_facts(payload), lambda value: None)
    call = run.state['calls'][0]
    assert call['status'] == 'incomplete'
    assert call['usage']['total_tokens'] == 35
    assert call['transport']['finish_reason'] == finish
    assert len(transport['requests']) == 1
    assert not list((tmp_path/'run/checkpoints').glob('*.json'))
    assert not list((tmp_path/'run/attempts').rglob('response.json'))
    from finmy.workbench.records import build_usage
    portable = build_usage(run.state['calls'])
    assert portable['calls'][0]['transport']['finish_reason'] == finish
    assert portable['calls'][0]['error_type'] == 'IncompleteCompletionError'
    assert portable['total_tokens'] == 35


def test_stream_error_event_is_not_accepted_or_retried(transport):
    from openai import APIError
    transport['stream_chunks'] = [chunk('{"ok":true}'),
        {'error': {'message': 'Bearer synthetic-secret', 'type': 'server_error'}}]
    m = model()
    with pytest.raises(APIError):
        m('system', 'source', 'extract')
    assert len(transport['requests']) == 1
    assert 'synthetic-secret' not in json.dumps(m.last_diagnostics)
    assert not m.last_diagnostics['stream_exhausted']
