"""Stable error records for CLI, state and scheduler; never persist raw SDK messages."""
import traceback
import re

from ..building.model_transport import error_metadata


def account_unavailable(info):
    """Only explicit credential/billing failures pause the whole model service."""
    return (info.get('http_status') == 401 or info.get('error_type') == 'AuthenticationError'
            or info.get('error_code') in {'AccountOverdueError', 'InsufficientBalance',
                'InsufficientQuota', 'insufficient_quota', 'invalid_api_key'})


def failure_details(error=None, transport=None, *, task_id=None, call_id=None):
    original = getattr(error, 'original', error)
    info = dict(error_metadata(original)) if original is not None else {}
    supplied = transport or getattr(original, 'diagnostics', {}) or {}
    for key in ('error_type', 'error_chain', 'http_status', 'request_id', 'error_code', 'retry_after_seconds', 'traceback'):
        if supplied.get(key) is not None:
            info[key] = supplied[key]
    remote = getattr(original, 'remote_error_type', None)
    if remote:
        info['error_type'] = remote
    if original is not None:
        info['wrapper_type'] = type(original).__name__
        if type(original) in (ValueError, TypeError, KeyError):
            message = re.sub(r'https?://\S+|\b(?:sk-|ark-)[A-Za-z0-9_-]+', '[redacted]', str(original))
            message = re.sub(r'(?i)(authorization|api[_-]?key|token|password)(\s*[=:]\s*)\S+',
                             r'\1\2[redacted]', message)
            info['message'] = message[:1600]
    kind = info.get('error_type') or 'UnknownError'
    status = info.get('http_status')
    retryable = supplied.get('retryable', getattr(original, 'retryable', None))
    if retryable is None:
        retryable = status == 429 or isinstance(status, int) and status >= 500 or kind in {
            'StreamStalled', 'RequestDeadlineExceeded', 'ReadTimeout', 'APITimeoutError', 'APIConnectionError'}
    info.update(task_id=task_id, call_id=call_id, retryable=bool(retryable))
    info['summary'] = ' | '.join(str(value) for value in (
        task_id, kind, 'HTTP ' + str(status) if status else None, info.get('error_code'), info.get('message'),
        'request_id=' + info['request_id'] if info.get('request_id') else None) if value)
    if original is not None:
        # Stack locations are sufficient to debug code; source lines and locals may contain secrets.
        info.setdefault('traceback', [dict(file=f.filename, line=f.lineno, function=f.name)
                                     for f in traceback.extract_tb(original.__traceback__)])
    return info


def record_failure(run, error, *, task_id=None, call=None, transport=None):
    details = failure_details(error, transport or (call or {}).get('transport'),
        task_id=task_id or (call or {}).get('task_id'), call_id=(call or {}).get('call_id'))
    path, digest = run.save((call['call_id'] if call else 'execution') + '-error.json', details)
    details.update(path=path, sha256=digest)
    run.state['last_error'] = details
    if call is not None:
        call['failure'] = details
    return details
