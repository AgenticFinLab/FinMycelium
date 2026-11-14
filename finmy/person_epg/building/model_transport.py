"""Bounded streaming transport shared by person builders; never retry implicitly."""
import re
import time

from .completion_errors import IncompleteCompletionError


REQUEST_HEADERS = ('x-request-id', 'x-tt-logid', 'x-tc-requestid', 'apigw-requestid')
FINISH_REASONS = {'stop', 'length', 'content_filter', 'tool_calls', 'function_call'}


def identifier(value):
    # Only opaque identifiers, never URLs, exception messages or header dumps.
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        return value
    return None


def response_metadata(response):
    result = {}
    status = getattr(response, 'status_code', None)
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    headers = getattr(response, 'headers', {})
    for key in REQUEST_HEADERS:
        request_id = identifier(headers.get(key))
        if request_id:
            result['request_id'] = request_id
            break
    return result


def error_metadata(exc):
    """Allowlisted diagnostics: no exception text, request body, URL or credentials."""
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen and len(chain) < 5:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    result = {'error_type': type(exc).__name__, 'error_chain': chain}
    result.update(response_metadata(getattr(exc, 'response', None)))
    request_id = identifier(getattr(exc, 'request_id', None))
    if request_id:
        result['request_id'] = request_id
    return result


class StreamingModel:
    def __init__(self, config):
        self.config = config
        self.adapter = None
        self.last_usage = None
        self.last_diagnostics = None

    def __call__(self, system, user, name):
        self.last_usage = None
        started = time.monotonic()
        info = self.last_diagnostics = dict(mode='stream', phase='initializing', chunks=0,
            content_chars=0, reasoning_chars=0, first_chunk_seconds=None,
            finish_reason=None, stream_exhausted=False)
        try:
            if self.adapter is None:
                from finmy.model_api import ModelAPIInference
                adapter = ModelAPIInference(lm_name=self.config.lm_name, generation_config={})
                adapter.client = adapter.client.with_options(max_retries=0, timeout=self.config.timeout)
                self.adapter = adapter
            parameters = self.adapter.request_parameters(dict(max_tokens=self.config.max_new_tokens))
            info['phase'] = 'connecting'
            stream = self.adapter.client.chat.completions.create(model=self.adapter.model_name,
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                stream=True, stream_options={'include_usage': True}, **parameters)
            parts, refused, tools = [], False, False
            with stream:
                info.update(response_metadata(stream.response))
                info['phase'] = 'receiving'
                for chunk in stream:
                    info['chunks'] += 1
                    if info['first_chunk_seconds'] is None:
                        info['first_chunk_seconds'] = round(time.monotonic() - started, 3)
                    response_id = identifier(getattr(chunk, 'id', None))
                    if response_id:
                        info['response_id'] = response_id
                    if chunk.usage is not None:
                        # Providers may repeat cumulative usage; do not sum chunks.
                        self.last_usage = chunk.usage.model_dump()
                    for choice in chunk.choices:
                        if choice.index != 0:
                            raise IncompleteCompletionError(name, finish_reason='multiple_choices',
                                output_limit=self.config.max_new_tokens)
                        delta = choice.delta
                        reasoning = getattr(delta, 'reasoning_content', None)
                        if isinstance(reasoning, str):
                            info['reasoning_chars'] += len(reasoning)
                        refused = refused or bool(getattr(delta, 'refusal', None))
                        tools = tools or bool(getattr(delta, 'tool_calls', None) or getattr(delta, 'function_call', None))
                        if delta.content:
                            parts.append(delta.content)
                            info['content_chars'] += len(delta.content)
                        if choice.finish_reason is not None and info['finish_reason'] in {None, 'stop'}:
                            info['finish_reason'] = (choice.finish_reason if choice.finish_reason in FINISH_REASONS else 'unknown')
                info['stream_exhausted'] = True
            if info['finish_reason'] != 'stop' or refused or tools or not ''.join(parts).strip():
                info['phase'] = 'incomplete'
                raise IncompleteCompletionError(name, finish_reason=info['finish_reason'],
                    refusal=refused, tool_calls=tools,
                    completion_tokens=(self.last_usage or {}).get('completion_tokens'),
                    output_limit=self.config.max_new_tokens)
            info['phase'] = 'completed'
            return ''.join(parts)
        except BaseException as exc:
            info.update(error_metadata(exc))
            raise
        finally:
            info['duration_seconds'] = round(time.monotonic() - started, 3)
