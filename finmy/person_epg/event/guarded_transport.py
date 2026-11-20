"""Killable model requests with output-stall and wall-clock deadlines."""
from contextlib import redirect_stdout
from dataclasses import asdict
import json
from queue import Empty, Queue
import subprocess
import sys
import tempfile
from threading import Lock, Thread
import time
from types import SimpleNamespace

from finmy.model_config import person_build_request_effort


class RequestDeadlineExceeded(TimeoutError):
    retryable = True


class StreamStalled(TimeoutError):
    retryable = True


class ModelTransportError(RuntimeError):
    def __init__(self, error_type, *, retryable=False):
        self.remote_error_type = error_type
        self.retryable = retryable
        super().__init__(error_type)


def retryable_failure(info):
    names = set(info.get('error_chain', [])) | {info.get('error_type')}
    if names & {'APITimeoutError', 'APIConnectionError', 'TimeoutError', 'ReadTimeout',
                'ConnectTimeout', 'ConnectError', 'ReadError', 'WriteError',
                'RemoteProtocolError', 'ConnectionResetError', 'BrokenPipeError'}:
        return True
    status = info.get('http_status')
    return (status == 429 or isinstance(status, int) and 500 <= status <= 599
            or 'IncompleteCompletionError' in names and info.get('finish_reason') is None)


class GuardedModel:
    """Each invocation owns its subprocess; a timed-out invocation cannot write back."""
    def __init__(self, config):
        self.config = config
        self.last_usage = None
        self.last_diagnostics = None
        self._lock = Lock()
        self._progress = None
        self._started = None
        self._last_growth = None
        self._last_chunk = None

    def __call__(self, system, user, name):
        return self.call_with_effort(system, user, name, reasoning_effort=
            person_build_request_effort(getattr(self.config, 'reasoning_effort', None), name))

    def progress_snapshot(self):
        with self._lock:
            if self._progress is None:
                return None
            stamp = time.monotonic()
            return dict(self._progress, elapsed_seconds=round(stamp - self._started, 3),
                        no_output_seconds=round(stamp - self._last_growth, 3),
                        idle_seconds=round(stamp - self._last_chunk, 3) if self._last_chunk else None)

    def _command(self):
        return [sys.executable, '-u', '-m', 'finmy.person_epg.event.guarded_transport']

    def call_with_effort(self, system, user, name, *, reasoning_effort):
        started = time.monotonic()
        self.last_usage = None
        with self._lock:
            self._started = self._last_growth = started
            self._last_chunk = None
            self._progress = dict(phase='initializing', chunks=0, content_chars=0,
                                  reasoning_chars=0, first_response_seconds=None)
        process, reader = None, None
        messages = Queue()
        parts = []
        try:
            # A file-backed stdin avoids blocking the deadline monitor on pipe writes.
            with tempfile.TemporaryFile(mode='w+b') as request_file:
                config = asdict(self.config) if hasattr(self.config, '__dataclass_fields__') else vars(self.config)
                request_file.write(json.dumps(dict(config=config, system=system, user=user,
                    name=name, reasoning_effort=reasoning_effort)).encode('utf-8'))
                request_file.seek(0)
                process = subprocess.Popen(self._command(), stdin=request_file,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')

                def receive():
                    try:
                        for line in process.stdout:
                            messages.put(json.loads(line))
                    except (ValueError, OSError):
                        messages.put(dict(kind='reader_error'))
                    finally:
                        messages.put(dict(kind='eof'))
                reader = Thread(target=receive, daemon=True)
                reader.start()
                while True:
                    stamp = time.monotonic()
                    total_left = self.config.timeout - (stamp - started)
                    stall_left = self.config.stall_timeout - (stamp - self._last_growth)
                    if total_left <= 0:
                        raise RequestDeadlineExceeded('request_deadline')
                    if stall_left <= 0:
                        raise StreamStalled('output_stalled')
                    try:
                        item = messages.get(timeout=min(total_left, stall_left))
                    except Empty:
                        continue
                    info = item.get('diagnostics')
                    if item['kind'] == 'content':
                        parts.append(item['text'])
                    if info is not None:
                        with self._lock:
                            old = self._progress
                            if (info.get('content_chars', 0) > old.get('content_chars', 0)
                                    or info.get('reasoning_chars', 0) > old.get('reasoning_chars', 0)):
                                self._last_growth = time.monotonic()
                            if info.get('chunks', 0) > old.get('chunks', 0):
                                self._last_chunk = time.monotonic()
                            self._progress = info
                        self.last_diagnostics = info
                    if item['kind'] == 'completed':
                        self.last_usage = item.get('usage')
                        return item['raw']
                    if item['kind'] == 'failed':
                        self.last_usage = item.get('usage')
                        info = info or {}
                        raise ModelTransportError(info.get('error_type', 'WorkerError'),
                                                  retryable=retryable_failure(info))
                    if item['kind'] in ('eof', 'reader_error'):
                        raise ModelTransportError('WorkerExited', retryable=True)
        except BaseException as exc:
            self.last_diagnostics = dict(self.progress_snapshot() or {},
                error_type=getattr(exc, 'remote_error_type', type(exc).__name__),
                duration_seconds=round(time.monotonic() - started, 3))
            info = self.last_diagnostics
            recoverable = (isinstance(exc, (StreamStalled, RequestDeadlineExceeded)) or
                           isinstance(exc, ModelTransportError) and exc.retryable)
            if (recoverable and ''.join(parts).strip()
                    and info.get('finish_reason') in (None, 'stop')
                    and not any(info.get(k) for k in ('refusal', 'tool_calls', 'multiple_choices'))):
                # This is a candidate only: runtime still parses and validates it.
                info.update(output_recovered=True, recovery_reason=info['error_type'])
                return ''.join(parts)
            raise
        finally:
            # No abandoned executor thread or SDK request survives a retry.
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.wait()
                if reader is not None:
                    reader.join(timeout=1)
                process.stdout.close()


def worker():
    """Private line-delimited protocol; imported provider logging stays off stdout."""
    output = sys.stdout
    def send(kind, **fields):
        print(json.dumps(dict(kind=kind, **fields), ensure_ascii=False), file=output, flush=True)
    with redirect_stdout(sys.stderr):
        from ..building.model_transport import StreamingModel, error_metadata
        request = json.load(sys.stdin)
        class ReportingModel(StreamingModel):
            last_report = 0
            last_phase = None
            def _publish_content(self, content, info):
                send('content', text=content, diagnostics=info)

            def _publish_progress(self, info, started):
                super()._publish_progress(info, started)
                stamp = time.monotonic()
                if stamp - self.last_report >= 0.25 or info['phase'] != self.last_phase:
                    send('progress', diagnostics=dict(info))
                    self.last_report, self.last_phase = stamp, info['phase']
        model = ReportingModel(SimpleNamespace(**request['config']))
        try:
            raw = model.call_with_effort(request['system'], request['user'], request['name'],
                                        reasoning_effort=request['reasoning_effort'])
            send('completed', raw=raw, diagnostics=model.last_diagnostics, usage=model.last_usage)
        except Exception as exc:
            send('failed', diagnostics=dict(model.last_diagnostics or {}, **error_metadata(exc)),
                 usage=model.last_usage)


if __name__ == '__main__':
    worker()
