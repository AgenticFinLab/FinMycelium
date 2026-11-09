"""Provider failures are local to one task; transient errors remain resumable."""
from contextlib import contextmanager
from datetime import timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import math
import re
import time

from .state import digest, write_json


class ProviderRequestError(ValueError):
    def __init__(self, details):
        self.details = details
        super().__init__('Search provider request failed: ' + details['category'])


def _body_fields(body):
    if not isinstance(body, dict):
        return None, ''
    nested = body.get('error')
    nested = nested if isinstance(nested, dict) else {}
    code = body.get('error_code', nested.get('code', body.get('code')))
    message = ' '.join(str(value)[:2000] for value in (
        body.get('message', ''), body.get('msg', ''), body.get('error_msg', ''),
        nested.get('message', ''), nested.get('type', ''), code or ''))
    return code, message.lower()


def _safe_code(code):
    if type(code) is int:
        return code
    if not isinstance(code, str):
        return None
    if re.fullmatch(r'[0-9]{1,12}', code):
        return code
    # Preserve useful symbolic error codes, not arbitrary echoed request values.
    # Unknown values get a stable fingerprint so different errors stay distinguishable.
    if (re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,63}', code)
            and not any(term in code.lower() for term in ('secret', 'password', 'bearer', 'sk-', 'api-key:'))
            and any(term in code.lower() for term in ('limit', 'quota', 'balance', 'auth',
                'forbidden', 'permission', 'denied', 'invalid', 'expired', 'timeout', 'unavailable'))):
        return code
    return 'unrecognized:' + digest(code)[:12]


def _retry_seconds(value, now):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = when.timestamp() - now
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0, math.ceil(seconds)) if math.isfinite(seconds) else None


def failure_details(exc=None, *, status=None, body=None, retry_after=None, now=None):
    if isinstance(exc, ProviderRequestError):
        return dict(exc.details)
    response = getattr(exc, 'response', None)
    if response is not None:
        status = getattr(response, 'status_code', None)
        try:
            body = response.json()
        except Exception:
            body = None
        retry_after = getattr(response, 'headers', {}).get('Retry-After')
    code, message = _body_fields(body)
    if any(term in message for term in ('insufficient balance', 'insufficient_balance',
            'insufficientbalance', '余额不足', 'insufficient_quota', 'insufficient quota')) or status == 402:
        category = 'balance_or_quota'
    elif status == 401 or any(term in message for term in (
            'invalid_api_key', 'invalid api key', 'invalidapikey', 'authentication_error',
            'unauthorized', 'access token invalid', 'invalid access token',
            'token expired', 'invalid token', '鉴权失败')):
        category = 'authentication'
    elif status == 403 or any(term in message for term in ('permission denied', 'permission_denied', 'forbidden')):
        category = 'permission'
    elif status == 429 or any(term in message for term in ('rate limit', 'rate_limit', 'ratelimit', '限流')):
        category = 'rate_limit'
    elif status is not None and status >= 500:
        category = 'server'
    elif type(exc).__name__ in {'Timeout', 'TimeoutError', 'ReadTimeout', 'ConnectTimeout', 'ConnectionError'}:
        category = 'network'
    elif status is not None and 400 <= status < 500:
        category = 'invalid_request'
    elif body is not None:
        category = 'provider_error'
    else:
        category = 'unknown'
    retryable = category not in {'balance_or_quota', 'authentication', 'permission'}
    result = {'category': category, 'http_status': status if type(status) is int else None,
              'provider_code': _safe_code(code), 'retryable': retryable,
              'scope': 'task_provider',
              'next_action': 'retry_after_cooldown' if retryable else 'check_service_access_then_resume'}
    seconds = _retry_seconds(retry_after, time.time() if now is None else now)
    if seconds is not None:
        result['retry_after_seconds'] = seconds
    return result


def check_response(provider, body):
    if not isinstance(body, dict):
        return
    error = body.get('error') or body.get('error_code')
    if provider == 'bocha' and body.get('code', 200) not in (200, '200'):
        error = True
    if error:
        raise ProviderRequestError(failure_details(body=body))


class ProviderHealth:
    """Persist task-local deadlines; retry bounds apply only to this invocation.

    The old phase-wide health file is intentionally not consulted: one event's
    failure is not evidence that another event has failed. Saved request quotas
    remain authoritative across manual resume and configuration revisions.
    """
    MAX_TRANSIENT_FAILURES = 3

    def __init__(self, state, clock=None):
        self.state = state
        self.clock = clock or time.time
        self.root = state.run_dir
        self.generation = len(state.data.get('config_history', []))
        self.key = digest({'providers': sorted(state.config.providers), 'generation': self.generation})
        self.invocation_failures = {}

    @contextmanager
    def _records(self):
        path = self.root / 'provider_health.json'
        with (self.root / '.provider_health.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                data = self._read_state(path)
                records = data['scopes'].setdefault(self.key, {})
                yield records
                write_json(path, data)
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _read_state(self, path):
        empty = {'version': 2, 'scope': 'task_provider', 'scopes': {}}
        if not path.exists():
            return empty
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('scopes'), dict):
                raise ValueError('Invalid provider health state')
            for records in data['scopes'].values():
                if not isinstance(records, dict):
                    raise ValueError('Invalid provider records')
                for row in records.values():
                    if not isinstance(row, dict):
                        raise ValueError('Invalid provider record')
                    deadline = row.get('retry_at', 0)
                    count = row.get('consecutive_failures', 0)
                    if (type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline < 0
                            or type(count) is not int or count < 0
                            or type(row.get('blocked', False)) is not bool
                            or not isinstance(row.get('last_error', {}), dict)):
                        raise ValueError('Invalid provider health fields')
            return data
        except (ValueError, UnicodeError):
            # This optional cache never owns request usage or source evidence.
            # Preserve corrupt bytes for diagnosis, and only reset its health.
            archive = path.with_name(f'provider_health.corrupt-{time.time_ns()}.json')
            path.replace(archive)
            self.state.trace({'action': 'provider_health_recovered',
                'reason': 'invalid_health_state', 'archive': archive.name,
                'scope': 'task_provider', 'usage_preserved': True})
            return empty

    def begin_invocation(self):
        """An explicit resume permits probing corrected access once per provider."""
        self.invocation_failures.clear()
        with self._records() as records:
            for row in records.values():
                if row.get('blocked'):
                    row['blocked'] = False
                    row['retry_at'] = 0

    def status(self, provider):
        with self._records() as records:
            row = records.get(provider, {})
            error = row.get('last_error')
            if row.get('blocked'):
                return {'status': 'blocked', 'error_details': error,
                        'resumable': True, 'requires_action': True,
                        'hint': 'This task received an access refusal. Check this provider account or credential and explicitly resume; other tasks are independent.'}
            if self.invocation_failures.get(provider, 0) >= self.MAX_TRANSIENT_FAILURES:
                return {'status': 'retry_exhausted', 'error_details': error,
                        'resumable': True, 'retry_at': row.get('retry_at', 0),
                        'hint': 'Automatic retries for this invocation are exhausted. Pause this task and resume later without resetting its quota.'}
            remaining = row.get('retry_at', 0) - self.clock()
            if remaining > 0:
                return {'status': 'cooldown', 'retry_after_seconds': math.ceil(remaining),
                        'retry_at': row['retry_at'], 'resumable': True,
                        'error_details': error,
                        'hint': 'Temporary provider cooldown. Wait until retry_at or pause for resume; this is not a completed search.'}
            return {'status': 'available'}

    def failure(self, provider, details):
        self.invocation_failures[provider] = self.invocation_failures.get(provider, 0) + 1
        with self._records() as records:
            row = records.setdefault(provider, {})
            failures = row.get('consecutive_failures', 0) + 1
            cooldown = details.get('retry_after_seconds', min(30, 2 ** min(failures, 5)))
            row.update(consecutive_failures=failures, blocked=not details['retryable'],
                       retry_at=self.clock() + cooldown if details['retryable'] else 0,
                       last_error=details)
        return self.status(provider)

    def success(self, provider):
        self.invocation_failures.pop(provider, None)
        with self._records() as records:
            records[provider] = {'consecutive_failures': 0, 'blocked': False, 'retry_at': 0}

    def availability(self):
        states = {p: self.status(p) for p in self.state.config.providers}
        available = [p for p, value in states.items() if value['status'] == 'available']
        retryable = [p for p, value in states.items() if value['status'] in {'cooldown', 'retry_exhausted'}]
        deadlines = [value['retry_at'] for value in states.values() if value['status'] == 'cooldown']
        return {'providers_available': available, 'all_providers_unavailable': not available,
                'retryable_providers': retryable,
                'blocked_providers': [p for p, value in states.items() if value['status'] == 'blocked'],
                'next_retry_at': min(deadlines) if deadlines else None,
                'provider_health': states}
