"""One state owner, a FIFO ready queue, and transport-only workers."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from queue import Queue, Empty
from threading import Lock
import sys
import time


PROGRESS_INTERVAL_SECONDS = 60


class ModelCallFailed(Exception):
    def __init__(self, original):
        self.original = original
        super().__init__(type(original).__name__)


@dataclass
class ModelRequest:
    call: dict
    system: str
    user: str


@dataclass
class Task:
    task_id: str
    steps: object
    on_failure: object = None
    request: object = None
    result: object = None
    error: object = None


STATES = {
    'TaskQueued': 'queued', 'ModelQueued': 'queued', 'ModelStarted': 'running',
    'ModelCompleted': 'processing', 'ModelFailed': 'processing',
    'ReadRequested': 'waiting_read', 'RetryRequested': 'retrying',
    'TaskSucceeded': 'succeeded', 'TaskFailed': 'failed', 'TaskLimited': 'limited',
    'TaskBlocked': 'blocked', 'TaskPaused': 'paused', 'TaskInterrupted': 'interrupted',
}
TERMINAL = {'succeeded', 'failed', 'limited', 'blocked', 'paused', 'interrupted'}


def emit(run, stage, task_id, kind, **details):
    from .runtime import now
    events = run.state.setdefault('events', [])
    event = dict(seq=len(events) + 1, at=now(), attempt=run.state['attempts'],
                 stage=stage, task_id=task_id, type=kind, **details)
    key = stage + ':' + task_id
    state = run.state.setdefault('task_states', {}).setdefault(key, {})
    if kind in STATES:
        if state.get('status') in TERMINAL and kind != 'TaskQueued':
            raise RuntimeError('Terminal task needs TaskQueued before another transition')
        state.update(task_id=task_id, stage=stage, status=STATES[kind],
                     updated_at=event['at'], attempt=run.state['attempts'])
        if kind == 'TaskQueued':
            state.pop('reason', None)
        if 'reason' in details:
            state['reason'] = details['reason']
    events.append(event)
    run.persist()


def execute(run, stage, tasks):
    """Advance task continuations only on the coordinator thread.

    Each continuation yields one model call. Reads and protocol/semantic retries
    return to the same queue, so a slow continuation cannot occupy the coordinator.
    Expected task failures terminate that task; storage/program errors stop the run.
    """
    from .runtime import (InvalidResponse, LimitReached, PauseRequested, now,
                          write_json, sha256, json_bytes)
    from ..building.model_transport import error_metadata
    tasks = list(tasks)
    ready, events, active = deque(tasks), Queue(), {}
    live_models, live_lock = {}, Lock()
    next_progress = time.monotonic() + PROGRESS_INTERVAL_SECONDS
    results = {t.task_id: t for t in tasks}
    stop = None
    stage_record = dict(status='running', task_ids=[t.task_id for t in tasks], started_at=now())
    run.state.setdefault('stages', {})[stage] = stage_record
    for task in tasks:
        emit(run, stage, task.task_id, 'TaskQueued')

    def report_progress():
        """One batch per minute, even if every request is waiting on the SDK."""
        nonlocal next_progress
        stamp = now()
        lines = [f'[{stamp}] {stage} | running={len(active)} queued={len(ready)}']
        with live_lock:
            live = dict(live_models)
        for task_id, task in active.items():
            entry = live.get(task_id)
            if entry is None:
                continue
            model, started, call_id = entry
            if call_id != task.request.call['call_id']:
                continue
            snapshot = getattr(model, 'progress_snapshot', None)
            progress = snapshot() if callable(snapshot) else None
            progress = dict(progress or {}, updated_at=stamp)
            progress.setdefault('elapsed_seconds', round(time.monotonic() - started, 3))
            phase = progress.get('phase', 'initializing')
            label = {'initializing': '初始化', 'connecting': '等待响应',
                     'receiving': '接收中', 'completed': '响应已完成',
                     'incomplete': '响应不完整'}.get(phase, phase)
            if phase == 'receiving' and not progress.get('chunks'):
                label = '已响应，等待首块'
            last = progress.get('idle_seconds')
            idle = f'{last:.0f}s前' if last is not None else '尚无数据块'
            first = progress.get('first_response_seconds')
            response = f'{first:.1f}s' if first is not None else '尚无'
            stalled = progress.get('no_output_seconds')
            output_idle = f' | 无输出增量 {stalled:.0f}s' if stalled is not None else ''
            task.request.call['progress'] = progress
            lines.append(f"  {call_id} {task.request.call['task_id']} | {label} | "
                         f"耗时 {progress['elapsed_seconds']:.0f}s | 首响应 {response} | "
                         f"正文 {progress.get('content_chars', 0)} 字符 | "
                         f"推理 {progress.get('reasoning_chars', 0)} 字符 | 最近数据块 {idle}{output_idle}")
        run.state['progress_updated_at'] = stamp
        run.persist()
        try:
            print('\n'.join(lines), file=sys.stderr, flush=True)
        except OSError:
            pass  # A closed log pipe must not interrupt model work.
        next_progress = time.monotonic() + PROGRESS_INTERVAL_SECONDS

    def advance(task, reply=None, error=None):
        nonlocal stop
        previous = getattr(run, 'current_task', None)
        run.current_task = (stage, task.task_id)
        try:
            task.request = task.steps.throw(error) if error else task.steps.send(reply)
            if not isinstance(task.request, ModelRequest):
                raise TypeError('Task continuation must yield ModelRequest')
            emit(run, stage, task.task_id, 'ModelQueued', call_id=task.request.call['call_id'])
            return True
        except StopIteration as done:
            task.result = done.value
            emit(run, stage, task.task_id, 'TaskSucceeded')
        except (ModelCallFailed, InvalidResponse, LimitReached) as exc:
            task.error = exc
            reason = str(exc) if isinstance(exc, LimitReached) else type(
                exc.original if isinstance(exc, ModelCallFailed) else exc).__name__
            emit(run, stage, task.task_id,
                 'TaskLimited' if isinstance(exc, LimitReached) else 'TaskFailed', reason=reason)
            if task.on_failure:
                task.on_failure(task.task_id, reason)
        except BaseException as exc:
            task.error = exc
            stop = exc
            emit(run, stage, task.task_id,
                 'TaskPaused' if isinstance(exc, PauseRequested) else 'TaskInterrupted',
                 reason=type(exc).__name__)
        finally:
            run.current_task = previous
        return False

    def worker(task_id, request):
        started = time.monotonic()
        events.put(('started', task_id, now()))
        model = None
        with live_lock:
            live_models[task_id] = (None, started, request.call['call_id'])
        try:
            model = run.model_factory() if run.model_factory is not None else run.model
            with live_lock:
                live_models[task_id] = (model, started, request.call['call_id'])
            method = getattr(model, 'call_with_effort', None)
            raw = (method(request.system, request.user, request.call['task_id'],
                          reasoning_effort=request.call['reasoning_effort'])
                   if method else model(request.system, request.user, request.call['task_id']))
            error = None
        except BaseException as exc:
            raw, error = None, exc
        events.put(('completed', task_id, (raw, error,
            deepcopy(getattr(model, 'last_diagnostics', None)),
            deepcopy(getattr(model, 'last_usage', None)), round(time.monotonic() - started, 3))))

    with ThreadPoolExecutor(max_workers=run.config.extraction_workers) as pool:
        while ready or active:
            while ready and len(active) < run.config.extraction_workers and stop is None:
                task = ready.popleft()
                if task.request is None and not advance(task):
                    continue
                try:
                    run.check_pause()
                except BaseException as exc:
                    stop = exc
                    ready.appendleft(task)
                    break
                active[task.task_id] = task
                pool.submit(worker, task.task_id, task.request)
            if not active:
                break
            if time.monotonic() >= next_progress:
                report_progress()
            try:
                kind, task_id, value = events.get(timeout=max(0, next_progress - time.monotonic()))
            except Empty:
                report_progress()
                continue
            except BaseException as exc:
                stop = exc
                continue
            task = active[task_id]
            call = task.request.call
            if kind == 'started':
                call.update(status='submitted', started_at=value)
                emit(run, stage, task_id, 'ModelStarted', call_id=call['call_id'])
                continue
            del active[task_id]
            with live_lock:
                live_models.pop(task_id, None)
            call.pop('progress', None)  # Completed calls have final transport diagnostics.
            raw, error, transport, usage, duration = value
            call.update(duration_seconds=duration, usage=usage,
                        usage_status='reported' if usage is not None else 'unknown')
            if transport is not None:
                call['transport'] = transport
            if error is None:
                path = run.directory / call['response_path']
                write_json(path, dict(raw=raw))
                call.update(status='prefetched', prefetched_response=call['response_path'],
                            prefetched_sha256=sha256(json_bytes(raw)))
                emit(run, stage, task_id, 'ModelCompleted', call_id=call['call_id'])
            else:
                call.update(status='incomplete' if type(error).__name__ == 'IncompleteCompletionError'
                            else 'transport_error', **error_metadata(error))
                emit(run, stage, task_id, 'ModelFailed', call_id=call['call_id'], reason=type(error).__name__)
            task.request = None
            if stop is None:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    stop = error
                elif advance(task, raw, error if isinstance(error, (LimitReached, PauseRequested))
                             else ModelCallFailed(error) if error else None):
                    ready.append(task)
            if stop is not None:
                state = run.state['task_states'][stage + ':' + task_id]
                if state['status'] not in TERMINAL:
                    emit(run, stage, task_id, 'TaskPaused' if isinstance(stop, PauseRequested)
                         else 'TaskInterrupted', reason=type(stop).__name__)
        for task in ready:
            emit(run, stage, task.task_id, 'TaskPaused' if isinstance(stop, PauseRequested)
                 else 'TaskInterrupted', reason=type(stop).__name__)
        if stop is not None:
            for task in tasks:
                task.steps.close()
    counts = {status: sum(run.state['task_states'][stage + ':' + t.task_id]['status'] == status
                         for t in tasks) for status in TERMINAL}
    stage_record.update(status='paused' if isinstance(stop, PauseRequested) else 'failed' if stop else
                        'partial' if counts['failed'] or counts['limited'] else 'completed',
                        counts=counts, finished_at=now())
    run.persist()
    if stop is not None:
        raise stop
    return results
