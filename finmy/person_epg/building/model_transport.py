"""Bounded streaming transport shared by person builders; never retry implicitly."""
import re
import time
import traceback
from datetime import datetime, timezone
from threading import Lock

from finmy.model_config import person_build_request_effort
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
    result['traceback'] = [dict(file=f.filename, line=f.lineno, function=f.name)
                           for f in traceback.extract_tb(exc.__traceback__)]
    result.update(response_metadata(getattr(exc, 'response', None)))
    request_id = identifier(getattr(exc, 'request_id', None))
    if request_id:
        result['request_id'] = request_id
    body = getattr(exc, 'body', None)
    if isinstance(body, dict):
        body = body.get('error', body)
        if isinstance(body, dict):
            code = identifier(body.get('code'))
            if code:
                result['error_code'] = code
    return result


class StreamingModel:
    def __init__(self, config):
        self.config = config
        self.adapter = None
        self.last_usage = None
        self.last_diagnostics = None
        self._progress_lock = Lock()
        self._progress = None
        self._progress_started = None

    def _publish_progress(self, info, started):
        # Publish counters only; never expose prompts or generated text.
        with self._progress_lock:
            self._progress = dict(info)
            self._progress_started = started

    def _publish_content(self, content, info):
        """Private transport hook; generated text never enters progress logs."""
        pass

    def progress_snapshot(self):
        """Readable while the SDK is blocked waiting for headers or a chunk."""
        with self._progress_lock:
            if self._progress is None:
                return None
            value = dict(self._progress)
            elapsed = time.monotonic() - self._progress_started
        value['elapsed_seconds'] = round(elapsed, 3)
        last = value.get('last_chunk_seconds')
        value['idle_seconds'] = round(max(0, elapsed - last), 3) if last is not None else None
        return value

    def __call__(self, system, user, name):
        effort = person_build_request_effort(getattr(self.config, 'reasoning_effort', None), name)
        return self.call_with_effort(system, user, name, reasoning_effort=effort)

    def call_with_effort(self, system, user, name, *, reasoning_effort):
        self.last_usage = None
        api_json_mode = getattr(self.config, 'api_json_mode', False)
        started = time.monotonic()
        info = self.last_diagnostics = dict(mode='stream', api_json_mode=api_json_mode, reasoning_effort=reasoning_effort,
            phase='initializing', chunks=0,
            content_chars=0, reasoning_chars=0, first_chunk_seconds=None,
            finish_reason=None, stream_exhausted=False,
            request_started_at=datetime.now(timezone.utc).isoformat(),
            response_received_at=None, first_response_seconds=None,
            first_chunk_at=None, last_chunk_at=None, last_chunk_seconds=None)
        self._publish_progress(info, started)
        try:
            if self.adapter is None:
                from finmy.model_api import ModelAPIInference
                adapter = ModelAPIInference(lm_name=self.config.lm_name, generation_config={})
                adapter.client = adapter.client.with_options(max_retries=0, timeout=self.config.timeout)
                self.adapter = adapter
            requested = dict(max_tokens=self.config.max_new_tokens)
            if reasoning_effort is not None:
                requested['reasoning_effort'] = reasoning_effort
            if api_json_mode:
                requested['response_format'] = {'type': 'json_object'}
            parameters = self.adapter.request_parameters(requested)
            info['phase'] = 'connecting'
            self._publish_progress(info, started)
            stream = self.adapter.client.chat.completions.create(model=self.adapter.model_name,
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                stream=True, stream_options={'include_usage': True}, **parameters)
            info.update(response_received_at=datetime.now(timezone.utc).isoformat(),
                        first_response_seconds=round(time.monotonic() - started, 3))
            parts, refused, tools = [], False, False
            with stream:
                info.update(response_metadata(stream.response))
                info['phase'] = 'receiving'
                self._publish_progress(info, started)
                for chunk in stream:
                    content_parts = []
                    info['chunks'] += 1
                    info['last_chunk_at'] = datetime.now(timezone.utc).isoformat()
                    info['last_chunk_seconds'] = round(time.monotonic() - started, 3)
                    if info['first_chunk_seconds'] is None:
                        info['first_chunk_seconds'] = info['last_chunk_seconds']
                        info['first_chunk_at'] = info['last_chunk_at']
                    response_id = identifier(getattr(chunk, 'id', None))
                    if response_id:
                        info['response_id'] = response_id
                    if chunk.usage is not None:
                        # Providers may repeat cumulative usage; do not sum chunks.
                        self.last_usage = chunk.usage.model_dump()
                    for choice in chunk.choices:
                        if choice.index != 0:
                            info['multiple_choices'] = True
                            raise IncompleteCompletionError(name, finish_reason='multiple_choices',
                                output_limit=self.config.max_new_tokens)
                        delta = choice.delta
                        reasoning = getattr(delta, 'reasoning_content', None)
                        if isinstance(reasoning, str):
                            info['reasoning_chars'] += len(reasoning)
                        refused = refused or bool(getattr(delta, 'refusal', None))
                        tools = tools or bool(getattr(delta, 'tool_calls', None) or getattr(delta, 'function_call', None))
                        info.update(refusal=refused, tool_calls=tools)
                        if delta.content:
                            parts.append(delta.content)
                            content_parts.append(delta.content)
                            info['content_chars'] += len(delta.content)
                        if choice.finish_reason is not None and info['finish_reason'] in {None, 'stop'}:
                            info['finish_reason'] = (choice.finish_reason if choice.finish_reason in FINISH_REASONS else 'unknown')
                    if content_parts:
                        self._publish_content(''.join(content_parts), dict(info))
                    self._publish_progress(info, started)
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
            self._publish_progress(info, started)
