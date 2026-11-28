"""Search streaming transport and budgeted retries of an unchanged decision."""
import time

import httpx
from openai import APITimeoutError

IDLE_SECONDS = 30
MAX_IDLE_RETRIES = 2


class ModelIdleTimeout(TimeoutError):
    pass


def stream_action(model, parameters, messages):
    # HTTP read timeouts measure inactivity between response bytes, not the total
    # generation time. Reasoning and SSE heartbeats keep an active stream alive.
    parameters = dict(parameters)
    parameters['extra_body'] = {k: v for k, v in parameters.get('extra_body', {}).items()
                                if k not in {'stream', 'stream_options'}}
    parameters.update(stream=True, stream_options={'include_usage': True}, timeout=streaming_timeout())
    stream, parts = None, []
    started = time.monotonic()
    model.last_stream_metrics = dict(first_response_seconds=None, chunks=0,
                                     content_chars=0, reasoning_chars=0)
    try:
        stream = model.adapter.client.chat.completions.create(
            model=model.adapter.model_name, messages=messages, **parameters)
        for chunk in stream:
            metrics = model.last_stream_metrics
            if metrics['first_response_seconds'] is None:
                metrics['first_response_seconds'] = round(time.monotonic() - started, 3)
            metrics['chunks'] += 1
            if chunk.usage is not None:
                model.last_usage = chunk.usage.model_dump()
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta.content:
                parts.append(delta.content)
                metrics['content_chars'] += len(delta.content)
            metrics['reasoning_chars'] += len(getattr(delta, 'reasoning_content', None) or '')
            if choice.finish_reason is not None:
                model.last_finish_reason = choice.finish_reason
    except (APITimeoutError, httpx.TimeoutException) as exc:
        raise ModelIdleTimeout(f'No response data for {IDLE_SECONDS} seconds') from exc
    finally:
        if stream is not None:
            stream.close()
    if model.last_finish_reason != 'stop':
        raise ValueError('Model completion was interrupted or truncated. Return one compact action; '
                         'keep evidence decisions concise and omit repeated chronology.')
    return ''.join(parts)


def call_model(state, model, context):
    """The caller has charged the first attempt; charge every retry before I/O."""
    decision_call = state.data['usage']['model']
    for attempt in range(MAX_IDLE_RETRIES + 1):
        if attempt:
            if (state.root / 'pause_requested').exists():
                raise ModelIdleTimeout('Retry paused by user')
            state.consume('model')
        number = state.data['usage']['model']
        state.trace(dict(action='model_started', model_call=number, decision_call=decision_call,
                         attempt=attempt + 1, phase=context['phase'],
                         finalization_reason=context['finalization_reason']))
        started = time.monotonic()
        status = 'error'
        try:
            result = model(context)
            status = 'success'
            return result
        except ModelIdleTimeout:
            status = 'idle_timeout'
            if attempt == MAX_IDLE_RETRIES:
                raise
            state.trace(dict(action='model_retry', model_call=number, decision_call=decision_call,
                             retry=attempt + 1, reason='idle_timeout', idle_seconds=IDLE_SECONDS))
        finally:
            state.trace(dict(action='model_attempt', model_call=number, decision_call=decision_call,
                attempt=attempt + 1, status=status, duration_seconds=round(time.monotonic()-started, 3),
                attempt_usage=getattr(model, 'last_usage', None),
                finish_reason=getattr(model, 'last_finish_reason', None),
                stream=getattr(model, 'last_stream_metrics', None)))


def streaming_timeout():
    return httpx.Timeout(IDLE_SECONDS)
