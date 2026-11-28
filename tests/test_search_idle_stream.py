"""Real OpenAI SDK streaming with synthetic HTTP; no lmbase service needed."""
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
from openai import OpenAI
import pytest

from finmy.search.agent import LmbaseModel, run_agent
from finmy.search.eval import search_usage
from finmy.search.inspection import pending_passages
from finmy.search.model_transport import streaming_timeout
from test_search_candidate_review import setup, saved, finish, offline


def sdk_model(state, plans):
    requests, closed = [], []
    def handler(request):
        requests.append(request)
        plan = plans[len(requests) - 1]
        class Events(httpx.SyncByteStream):
            def __iter__(self):
                for event in plan:
                    if event == 'timeout':
                        raise httpx.ReadTimeout('synthetic timeout', request=request)
                    yield ('data: ' + json.dumps(event) + '\n\n').encode()
                yield b'data: [DONE]\n\n'
            def close(self):
                closed.append(True)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Events())
    client = OpenAI(api_key='synthetic', max_retries=0, timeout=streaming_timeout(),
                    http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    model = LmbaseModel(state.config)
    state.config.allow_network = True
    model.adapter = SimpleNamespace(client=client, model_name='synthetic', request_parameters=lambda p:p)
    return model, client, requests, closed


def delta(text=None, reasoning=None, finish_reason=None, usage=None):
    return dict(id='synthetic', object='chat.completion.chunk', created=1, model='synthetic',
        choices=[dict(index=0, delta=dict(content=text, reasoning_content=reasoning), finish_reason=finish_reason)],
        **({'usage': usage} if usage else {}))


USAGE = dict(prompt_tokens=100, completion_tokens=20, total_tokens=120,
             completion_tokens_details=dict(reasoning_tokens=10))


def successful(action):
    return [delta(reasoning='thinking'), delta(json.dumps(action), finish_reason='stop', usage=USAGE)]


def test_timeout_retries_same_context_and_commits_only_completed_response(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=8)
    sid, _ = saved(tools, 'notice', 'Ada Vale approved Orion.', read=True)
    original = deepcopy(state.data['sources'])
    partial = delta('{"action":"search","query":"must never execute"')
    model, client, requests, closed = sdk_model(state, [[partial, 'timeout'], successful(finish([sid]))])
    try:
        run_agent(state, tools, model)
        assert state.data['usage'] == {'model': 2, 'search': 0}
        assert state.data['status'] == 'finished'
        assert state.data['sources'] == original
        assert len(closed) == 2
        bodies = [json.loads(r.content) for r in requests]
        assert bodies[0] == bodies[1] and bodies[0]['stream']
        assert bodies[0]['stream_options'] == {'include_usage': True}
        assert all(r.extensions['timeout']['read'] == 30 for r in requests)
        rows = [json.loads(l) for l in (state.run_dir/'trace.jsonl').read_text().splitlines()]
        attempts = [r for r in rows if r['action'] == 'model_attempt']
        assert [r['status'] for r in attempts] == ['idle_timeout', 'success']
        assert attempts[0]['stream']['content_chars'] > 0 and attempts[0]['attempt_usage'] is None
        assert attempts[1]['stream']['reasoning_chars'] == len('thinking')
        usage = search_usage(state)
        assert usage['calls'] == 2 and usage['reported_usage_calls'] == 1
        assert usage['input_tokens'] == 100 and usage['total_tokens'] == 120
        assert usage['transport_retries'] == 1 and usage['idle_timeout_attempts'] == 1
    finally:
        client.close()


def test_two_retries_then_pause_without_committing_shown_evidence(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=8)
    sid, _ = saved(tools, 'condition', 'Ada Vale required local consent for Orion.')
    before = deepcopy(state.data['sources'])
    model, client, requests, closed = sdk_model(state, [[delta(reasoning='partial'), 'timeout']] * 3)
    try:
        run_agent(state, tools, model)
        assert len(requests) == len(closed) == 3
        assert state.data['usage']['model'] == 3
        assert state.data['status'] == 'paused' and state.data['stop_reason'] == 'model_idle_timeout'
        assert state.data['sources'] == before and not state.data.get('passage_reviews')
        assert not state.data.get('priority_passages') and not pending_passages(state)
        assert not (state.run_dir/'builder_input.json').exists()
    finally:
        client.close()


def test_retry_cannot_exceed_total_model_budget(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=2)
    model, client, requests, _ = sdk_model(state, [['timeout']] * 2)
    try:
        run_agent(state, tools, model)
        assert len(requests) == 2 and state.data['usage']['model'] == 2
        assert state.data['status'] == 'limit'
    finally:
        client.close()


def test_reasoning_stream_can_exceed_total_30_seconds_without_idle_retry(tmp_path, monkeypatch):
    state, tools = setup(tmp_path, max_model_calls=8)
    sid, _ = saved(tools, 'notice', 'Ada Vale approved Orion.', read=True)
    # Emulate a long-lived stream: HTTP read timeout, not wall time, controls it.
    clock = iter(range(0, 10000, 20))
    monkeypatch.setattr('finmy.search.model_transport.time.monotonic', lambda: next(clock))
    plan = [delta(reasoning='thinking') for _ in range(8)] + successful(finish([sid]))
    model, client, requests, _ = sdk_model(state, [plan])
    try:
        run_agent(state, tools, model)
        assert len(requests) == 1 and state.data['status'] == 'finished'
        assert model.last_stream_metrics['reasoning_chars'] == 9 * len('thinking')
    finally:
        client.close()


def test_truncated_completion_is_not_a_silence_retry(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=8)
    model, client, requests, _ = sdk_model(state, [[delta(reasoning='thinking', finish_reason='length', usage=USAGE)]])
    try:
        run_agent(state, tools, model, max_steps=1)
        assert len(requests) == 1 and not state.data.get('passage_reviews')
        assert search_usage(state)['total_tokens'] == 120
    finally:
        client.close()
