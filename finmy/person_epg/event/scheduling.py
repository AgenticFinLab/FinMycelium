"""One state owner, a FIFO ready queue, and transport-only workers."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from heapq import heappop, heappush
from queue import Queue, Empty
from threading import Lock
import random
import sys
import shutil
import unicodedata
import time


PROGRESS_INTERVAL_SECONDS = 60

TTY_INTERVAL_SECONDS = 1
DISPLAY_STAGES = (('extraction', '抽取'), ('corpus_supplement', '补充'),
                  ('consolidation', '整理'), ('organization', '组织'),
                  ('relations', '关系'), ('validation', '校验'))


def retry_delay(call, calls):
    """Bounded exponential backoff with jitter; honor the provider's minimum wait."""
    previous = calls.get(call.get('retry_of'))
    if previous is None:
        return 0
    attempt, ancestor = 1, previous
    while ancestor.get('retry_of') in calls:
        attempt += 1
        ancestor = calls[ancestor['retry_of']]
    ceiling = min(30, 2 ** min(attempt, 5))
    minimum = (previous.get('failure') or previous.get('transport') or {}).get('retry_after_seconds', 0)
    return minimum + random.uniform(ceiling / 2, ceiling)


def metrics_text(metrics):
    return (f"成功 {metrics['succeeded']} · 有效完成 {metrics['tasks_per_minute']:.1f}/分钟 · "
            f"重试 {metrics['retry_requests']}/{metrics['requests']} ({metrics['retry_fraction']:.0%})\n"
            f"平均就绪排队 {metrics['mean_queue_seconds']:.1f}s · 退避等待 {metrics['backoff_tasks']}")


def terminal_text(text, width):
    """Clip by terminal cells, including Chinese labels; never emit control text."""
    result, used = '', 0
    for char in str(text):
        if unicodedata.category(char).startswith('C'):
            continue
        cells = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in 'WF' else 1
        if used + cells > width:
            break
        result += char
        used += cells
    return result + ' ' * (width - used)


class TerminalProgress:
    """Ephemeral terminal view; does not change execution state or call budgets."""
    def __init__(self, run):
        self.run, self.stream = run, sys.stderr
        self.enabled = bool(getattr(self.stream, 'isatty', lambda: False)())
        self.lines, self.frame, self.current = 0, 0, None
        self.stages, self.requests, self.outer = {}, [], None
        self.metrics = None
        if not run.config.full_corpus_supplement:
            self.stages['corpus_supplement'] = 'skipped'

    @staticmethod
    def key(stage):
        return {'hierarchy_repair': 'organization', 'repair': 'validation'}.get(stage, stage)

    def update(self, stage, status):
        stage = self.key(stage)
        self.current = stage
        self.stages[stage] = status
        self.requests = []
        if status == 'running':
            self.metrics = None
        self.draw()

    def clear(self):
        if self.enabled and self.lines:
            try:
                self.stream.write(f'\x1b[{self.lines}A' + '\r\x1b[2K\n' * self.lines + f'\x1b[{self.lines}A')
                self.stream.flush()
            except (OSError, ValueError):
                self.enabled = False
            self.lines = 0

    def draw(self, requests=None):
        if not self.enabled:
            return
        if requests is not None:
            self.requests = requests
        size = shutil.get_terminal_size((110, 24))
        width = max(1, size.columns - 1)
        cell = min(18, width)
        columns = next(n for n in (6, 3, 2, 1) if n * (cell + 1) - 1 <= width)
        spin = '◐◓◑◒'[self.frame % 4]
        self.frame += 1
        boxes, summaries = [], []
        for stage, label in DISPLAY_STAGES:
            status = self.stages.get(stage, 'pending')
            tasks = [t for t in self.run.state.get('task_states', {}).values()
                     if t.get('attempt') == self.run.state['attempts'] and self.key(t['stage']) == stage]
            total = len(tasks)
            done = sum(t['status'] in ('succeeded', 'failed', 'limited') for t in tasks)
            failed = sum(t['status'] in ('failed', 'limited') for t in tasks)
            count = f' {done}/{total}' if total else ''
            tag = {'completed': '完成', 'partial': '有异常', 'failed': '失败', 'blocked': '受阻',
                   'paused': '暂停', 'interrupted': '中断', 'skipped': '跳过', 'pending': '待开始'}.get(status, spin)
            if self.current == stage and status == 'running':
                running = sum(t['status'] in ('running', 'processing') for t in tasks)
                queued = sum(t['status'] in ('queued', 'retrying', 'waiting_read') for t in tasks)
                summaries.append(f'{label}{count} 已结束 · {running} 运行 · {queued} 排队 · {failed} 失败/限额')
            elif failed:
                summaries.append(f'{label}：{failed} 失败/限额')
            inner = max(0, cell - 2)
            fill = inner if status in ('completed', 'partial') else (
                min(max(0, inner - 1), int(inner * done / total)) if total and status == 'running' else 0)
            border = '━' if self.current == stage and status == 'running' else '─'
            boxes.append(['┌' + border * inner + '┐',
                          '│' + terminal_text(label + count + ' ' + tag, inner) + '│',
                          '│' + '█' * fill + '░' * (inner - fill) + '│',
                          '└' + border * inner + '┘'])
        lines = []
        for start in range(0, len(boxes), columns):
            lines.extend(' '.join(box[row] for box in boxes[start:start + columns]) for row in range(4))
        lines += summaries
        if self.metrics is not None:
            lines.extend(metrics_text(self.metrics).splitlines())
        slots = max(0, size.lines - len(lines) - 3)
        shown = self.requests[:slots]
        if len(self.requests) > slots and slots:
            shown = self.requests[:slots - 1] + [f'另有 {len(self.requests) - slots + 1} 个任务（终端高度不足）']
        lines += [spin + ' ' + line.strip() for line in shown]
        lines = [terminal_text(line, width).rstrip() for line in lines]
        self.clear()
        try:
            self.stream.write('\n'.join(lines) + '\n')
            self.stream.flush()
            self.lines = len(lines)
        except (OSError, ValueError):
            self.enabled = False

    def finish(self, status):
        for stage, value in list(self.stages.items()):
            if value == 'running':
                self.stages[stage] = status
        self.requests = []
        self.draw()
        self.lines = 0  # Leave the final frame above subsequent command output.


def terminal_progress(run):
    if not hasattr(run, '_terminal_progress'):
        run._terminal_progress = TerminalProgress(run)
    return run._terminal_progress


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
    from .diagnostics import account_unavailable, record_failure
    tasks = list(tasks)
    ready, events, active = deque(tasks), Queue(), {}
    delayed, submitted = [], []
    sequence = 0
    started = time.monotonic()
    ready_since = {task.task_id: started for task in tasks}
    live_models, live_lock = {}, Lock()
    display = terminal_progress(run)
    next_progress = time.monotonic() + PROGRESS_INTERVAL_SECONDS
    next_frame = time.monotonic()
    results = {t.task_id: t for t in tasks}
    stop = None
    stage_record = dict(status='running', task_ids=[t.task_id for t in tasks], started_at=now())
    run.state.setdefault('stages', {})[stage] = stage_record
    for task in tasks:
        emit(run, stage, task.task_id, 'TaskQueued')
    if display.outer is None:
        display.update(stage, 'running')

    def metrics_snapshot():
        elapsed = max(0, time.monotonic() - started)
        succeeded = sum(run.state['task_states'][stage + ':' + t.task_id]['status'] == 'succeeded'
                        for t in tasks)
        retries = sum(bool(call.get('retry_of') or call.get('retry_kind')) for call in submitted)
        waits = [call['queue_wait_seconds'] for call in submitted]
        return dict(elapsed_seconds=round(elapsed, 3), succeeded=succeeded, requests=len(submitted),
            retry_requests=retries, retry_fraction=retries / len(submitted) if submitted else 0,
            tasks_per_minute=round(succeeded * 60 / elapsed, 2) if elapsed else 0,
            mean_queue_seconds=round(sum(waits) / len(waits), 3) if waits else 0,
            backoff_tasks=len(delayed), ready_tasks=len(ready), running_tasks=len(active))

    def enqueue(task):
        nonlocal sequence
        call = task.request.call
        delay = retry_delay(call, {c['call_id']: c for c in run.state['calls']})
        if delay:
            sequence += 1
            call.update(retry_delay_seconds=round(delay, 3),
                        retry_not_before=(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat())
            heappush(delayed, (time.monotonic() + delay, sequence, task))
            emit(run, stage, task.task_id, 'RetryRequested', call_id=call['call_id'],
                 retry_not_before=call['retry_not_before'], delay_seconds=call['retry_delay_seconds'])
        else:
            ready_since[task.task_id] = time.monotonic()
            ready.append(task)

    def report_progress(persist=True):
        """Refresh TTY locally; persist and append non-TTY logs only once a minute."""
        nonlocal next_progress, next_frame
        stamp = now()
        display.metrics = metrics_snapshot()
        lines = [f'[{stamp}] {stage} | running={len(active)} queued={len(ready)} backoff={len(delayed)}',
                 '  ' + metrics_text(display.metrics)]
        request_lines = []
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
            call = task.request.call
            retry, prior = 0, call.get('retry_of')
            calls = {c['call_id']: c for c in run.state['calls']}
            while prior in calls:
                retry += 1
                prior = calls[prior].get('retry_of')
            retry_label = f' · 重试 {retry}/{run.config.max_transport_retries}' if retry else ''
            request_lines.append(f"{call['task_id']} · {label}{retry_label} · {progress['elapsed_seconds']:.0f}s · "
                                 f"正文 {progress.get('content_chars', 0):,} 字符{output_idle}")
            if persist:
                task.request.call['progress'] = progress
            lines.append(f"  {call_id} {task.request.call['task_id']} | {label} | "
                         f"耗时 {progress['elapsed_seconds']:.0f}s | 首响应 {response} | "
                         f"正文 {progress.get('content_chars', 0)} 字符 | "
                         f"推理 {progress.get('reasoning_chars', 0)} 字符 | 最近数据块 {idle}{output_idle}")
        if persist:
            stage_record['metrics'] = display.metrics
            run.state['progress_updated_at'] = stamp
            run.persist()
            if not display.enabled:
                try:
                    print('\n'.join(lines), file=sys.stderr, flush=True)
                except OSError:
                    pass
            next_progress = time.monotonic() + PROGRESS_INTERVAL_SECONDS
        stamp_mono = time.monotonic()
        request_lines.extend(f'{task.task_id} · 等待重试 {max(0, due - stamp_mono):.0f}s'
                             for due, _, task in sorted(delayed))
        request_lines.extend(f'{task.task_id} · 排队 {stamp_mono - ready_since[task.task_id]:.0f}s'
                             for task in ready)
        display.draw(request_lines)
        next_frame = time.monotonic() + TTY_INTERVAL_SECONDS

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
            if isinstance(exc, ModelCallFailed):
                call = next((c for c in reversed(run.state['calls']) if c['task_id'] == task.task_id), None)
                if call and call.get('failure'):
                    run.state['task_states'][stage + ':' + task.task_id]['failure'] = call['failure']
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
        while ready or active or delayed:
            if stop is None:
                try:
                    run.check_pause()
                except BaseException as exc:
                    stop = exc
            while delayed and delayed[0][0] <= time.monotonic() and stop is None:
                _, _, task = heappop(delayed)
                ready_since[task.task_id] = time.monotonic()
                ready.append(task)
            while ready and len(active) < run.config.extraction_workers and stop is None:
                task = ready.popleft()
                if task.request is None:
                    if not advance(task):
                        continue
                    if task.request.call.get('retry_of'):
                        enqueue(task)  # A resumed partial response can itself request a retry.
                        continue
                try:
                    run.check_pause()
                except BaseException as exc:
                    stop = exc
                    ready.appendleft(task)
                    break
                active[task.task_id] = task
                task.request.call['queue_wait_seconds'] = round(time.monotonic() - ready_since.pop(task.task_id), 3)
                submitted.append(task.request.call)
                pool.submit(worker, task.task_id, task.request)
            if not active and (stop is not None or not delayed):
                break
            if time.monotonic() >= next_progress:
                report_progress()
            elif display.enabled and time.monotonic() >= next_frame:
                report_progress(persist=False)
            deadline = min(next_progress, next_frame) if display.enabled else next_progress
            if delayed and stop is None:
                # Waiting retries consume neither workers nor the coordinator; check pause at least once a second.
                deadline = min(deadline, delayed[0][0], time.monotonic() + 1)
            try:
                kind, task_id, value = events.get(timeout=max(0, deadline - time.monotonic()))
            except Empty:
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
                details = record_failure(run, error, call=call, transport=transport)
                display.clear()
                try:
                    print(details['summary'] + ' | retryable=' + str(details['retryable']), file=sys.stderr, flush=True)
                except OSError:
                    pass
                emit(run, stage, task_id, 'ModelFailed', call_id=call['call_id'], reason=type(error).__name__)
                if stop is None and account_unavailable(details):
                    run.state['service_pause'] = dict(model=run.config.lm_name, attempt=run.state['attempts'],
                        at=now(), failure=details)
                    stop = PauseRequested('Model service unavailable: ' + details['summary'] +
                                          '; fix the account or credentials, then resume this run')
                    run.state['task_states'][stage + ':' + task_id]['failure'] = details
                    emit(run, stage, task_id, 'ModelServicePaused', call_id=call['call_id'])
                    try:
                        print('已暂停新请求；正在收存已在途的响应。修复账户或凭据后可 resume。',
                              file=sys.stderr, flush=True)
                    except OSError:
                        pass
            task.request = None
            if stop is None:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    stop = error
                elif advance(task, raw, error if isinstance(error, (LimitReached, PauseRequested))
                             else ModelCallFailed(error) if error else None):
                    enqueue(task)
            if stop is not None:
                state = run.state['task_states'][stage + ':' + task_id]
                if state['status'] not in TERMINAL:
                    emit(run, stage, task_id, 'TaskPaused' if isinstance(stop, PauseRequested)
                         else 'TaskInterrupted', reason=type(stop).__name__)
        for task in list(ready) + [entry[2] for entry in delayed]:
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
    # Final counters exclude paused queues; each per-call wait remains available in state.json.
    ready.clear()
    delayed.clear()
    stage_record['metrics'] = display.metrics = metrics_snapshot()
    run.persist()
    if display.outer is None:
        display.update(stage, stage_record['status'])
        display.finish(stage_record['status'])
    if stop is not None:
        raise stop
    return results
