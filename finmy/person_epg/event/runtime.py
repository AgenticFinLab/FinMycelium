"""Durable, bounded execution over one immutable, local evidence corpus."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

from finmy.model_config import person_build_request_effort

from .records import fingerprint, index_records, json_bytes, pointer, sha256, prompt_json
from .schema import FACTS_VERSION, GRAPH_VERSION
from .read_dedup import compact_read_results, next_read_charge
from ..building.model_transport import error_metadata
from ..building.completion_errors import IncompleteCompletionError


from .config import EventBuildConfig, effective_read_limits


class LimitReached(Exception):
    pass


class PauseRequested(Exception):
    pass


class InvalidResponse(ValueError):
    pass


class IncompleteStreamResponse(InvalidResponse):
    """A truncated stream spent its retry budget; do not start format retries."""
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    """Hash and atomically publish exactly the same bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json_bytes(value)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(data)


def code_manifest():
    """Repository-owned execution dependencies, excluding independent rendering.

    Keep this list alongside the direct runner's imports. Workbench creation also
    records its broader entry-point fingerprint; neither path may bypass this one.
    """
    event = Path(__file__).resolve().parent
    root = event.parents[1]
    files = {p for p in event.glob('*.py') if p.name not in {
        'rendering.py', 'graph_html.py', 'graph_layout.py', 'graph_view.py', 'graph_labels.py',
        'state_machine_smoke.py', 'status.py'}}
    files.update(root / name for name in (
        'person_epg/build.py',                    # Model entry point.
        'person_epg/building/model_transport.py', # Streaming transport and diagnostics.
        'model_api.py',                          # Shared model-service transport.
        'model_config.py',                       # Provider and endpoint resolution.
        'person_epg/input.py',                    # Confirmed identity validation.
        'person_epg/building/completion_errors.py',
        'generic.py',                            # Input dataclasses.
        'dataset.py',                            # Resume artifact path validation.
        'search/summary.py',                     # Shared run-directory lock.
    ))
    return {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in sorted(files)}


def code_identity():
    return fingerprint(code_manifest())


def semantic_config(config):
    value = {k: v for k, v in asdict(config).items()
             if k not in ('max_calls', 'stall_timeout', 'max_transport_retries',
                          'read_call_extension', 'read_round_extension', 'read_char_extension')}
    # Missing in historical ordinary-mode configurations. Preserve their hashes;
    # explicit JSON mode still changes all request/checkpoint dependencies.
    if not config.full_corpus_supplement:
        value.pop('full_corpus_supplement')
    if not config.api_json_mode:
        value.pop('api_json_mode')
    if config.reasoning_effort is None:
        value.pop('reasoning_effort')
    return value


def parse(raw):
    if isinstance(raw, dict):
        return deepcopy(raw)
    if not isinstance(raw, str):
        raise InvalidResponse('Expected a JSON object')
    value = raw.strip()
    if value.startswith('```') and value.endswith('```'):
        value = re.sub(r'^```(?:json)?\s*', '', value, flags=re.I)[:-3].strip()
    result = json.loads(value)
    if not isinstance(result, dict):
        raise InvalidResponse('Expected a JSON object')
    return result


class Corpus:
    """Allowlisted read tools. No filesystem paths, URLs or network requests."""
    def __init__(self, payload, package, config):
        self.samples = {s['sample_id']: s for s in payload['samples']}
        self.package, self.config = deepcopy(package), config

    def read(self, request):
        if not isinstance(request, dict):
            raise ValueError('Read requests must be objects')
        tool = request.get('tool')
        if tool == 'read_sample':
            if set(request) != {'tool', 'sample_id', 'start', 'end'}:
                raise ValueError('read_sample needs sample_id, start and end only')
            sample = self.samples[request['sample_id']]
            start, end = request['start'], request['end']
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(sample['content'])
                    or end - start > self.config.read_chars):
                raise ValueError('Read range is outside the frozen sample or per-read bound')
            return dict(sample_id=sample['sample_id'], source_id=sample['raw_data_id'], start=start, end=end,
                        text=sample['content'][start:end])
        if tool == 'read_records':
            if set(request) != {'tool', 'refs'} or not isinstance(request['refs'], list) or not 1 <= len(request['refs']) <= 20:
                raise ValueError('read_records needs between 1 and 20 refs')
            indexes, values = index_records(self.package), []
            for reference in request['refs']:
                if not isinstance(reference, dict) or set(reference) != {'collection', 'object_id', 'field'}:
                    raise ValueError('Each ref needs collection, object_id and field')
                # Only the package supplied to this task is readable.
                value = pointer(indexes[reference['collection']][reference['object_id']], reference['field'])
                values.append(dict(ref=reference, value=value))
            if len(json_bytes(values).decode('utf-8')) > self.config.read_chars:
                detail = []
                for value in values:
                    size = len(json_bytes([value]).decode('utf-8'))
                    if size <= self.config.read_chars:
                        continue
                    content = value['value']
                    keys = range(len(content)) if isinstance(content, list) else content if isinstance(content, dict) else []
                    paths = [value['ref']['field'] + '/' + str(k).replace('~', '~0').replace('/', '~1') for k in keys][:8]
                    detail.append(dict(ref=value['ref'], characters=size, child_paths=paths))
                raise ValueError('Record read exceeds limit: ' + prompt_json(dict(
                    requested_chars=len(json_bytes(values).decode('utf-8')), limit=self.config.read_chars,
                    oversized_fields=detail, hint='Select fewer refs or indexed child fields; no values were truncated.')))
            return values
        if tool == 'search':
            if set(request) != {'tool', 'query'} or not isinstance(request['query'], str) or not request['query'].strip():
                raise ValueError('search needs a nonempty text query only')
            if len(request['query']) > 1000:
                raise ValueError('Query exceeds the local search limit')
            tokens = set(re.findall(r'\w+', request['query'].casefold()))
            matches = []
            width = max(1, self.config.read_chars // self.config.retrieval_top_k)
            for sample in self.samples.values():
                for start in range(0, len(sample['content']), width):
                    text = sample['content'][start:start + width]
                    score = sum(text.casefold().count(token) for token in tokens)
                    if score:
                        matches.append((score, sample['sample_id'], start, text))
            matches.sort(key=lambda x: (-x[0], x[1], x[2]))
            return [dict(sample_id=sid, source_id=self.samples[sid]['raw_data_id'], start=start,
                         end=start + len(text), text=text) for _, sid, start, text in matches[:self.config.retrieval_top_k]]
        raise ValueError('Unknown read tool; allowed: read_sample, read_records, search')


    def pages(self, request):
        """Partition complete refs before delivery; no model-assisted splitting."""
        if request.get('tool') != 'read_records':
            return [(request, self.read(request))]
        if set(request) != {'tool', 'refs'} or not isinstance(request['refs'], list) or not 1 <= len(request['refs']) <= 20:
            raise ValueError('read_records needs between 1 and 20 refs')
        pages, refs, values = [], [], []
        for ref in request['refs']:
            item = self.read(dict(tool='read_records', refs=[ref]))[0]
            if values and len(json_bytes(values + [item]).decode('utf-8')) > self.config.read_chars:
                pages.append((dict(tool='read_records', refs=refs), values))
                refs, values = [], []
            refs.append(deepcopy(ref)); values.append(item)
        pages.append((dict(tool='read_records', refs=refs), values))
        return pages


class Execution:
    """The caller holds the run directory lock throughout execution.

    Responses are cached independently of adoption, so a crash between response and
    checkpoint publication can be replayed without another paid request. Adoption is
    deterministic and uses the same task-scoped ID map on every replay.
    """
    def __init__(self, directory, payload, config, model, *, resume=False, provenance=None, model_factory=None,
                 resume_transport_upgrade=False):
        self.directory, self.payload, self.config, self.model = Path(directory), payload, config, model
        self.model_factory = model_factory
        self.directory.mkdir(parents=True, exist_ok=True)
        state_path = self.directory / 'state.json'
        input_hash = sha256(json_bytes(payload))
        if state_path.exists():
            if not resume:
                raise ValueError('Existing run requires explicit resume or a new directory')
            self.state = json.loads(state_path.read_text())
            original_state = deepcopy(self.state)
            self.state.pop('last_error', None)
            if self.state.get('graph_schema_version') != GRAPH_VERSION:
                raise ValueError('Cannot resume a different graph protocol')
            if (self.state['input_sha256'] != input_hash
                    or sha256((self.directory / 'input.json').read_bytes()) != input_hash):
                raise ValueError('Frozen input changed; create a new run')
            if self.state.get('compatible_recovery'):
                from .recovery import validate_recovery
                validate_recovery(self.directory, self.state)
            previous_code = self.state.get('execution_code_sha256', self.state['code_sha256'])
            changed_code = previous_code != code_identity()
            if changed_code and not resume_transport_upgrade:
                raise ValueError('Implementation changed; create a new run')
            retained = self.directory / 'provenance.json'
            if sha256(retained.read_bytes()) != self.state['provenance_sha256']:
                raise ValueError('Frozen provenance changed; create a new run')
            if provenance is not None and json.loads(retained.read_text()).get('search_handoff') != provenance:
                raise ValueError('Search handoff provenance changed; create a new run')
            from finmy.dataset import within
            for field, hash_field in [('output', 'graph_sha256'), ('facts', 'facts_sha256'), ('checks', 'checks_sha256')]:
                if not self.state.get(field):
                    continue
                artifact = within(self.directory, self.state[field])
                actual = sha256(artifact.read_bytes()) if artifact.is_file() else None
                if actual != self.state.get(hash_field):
                    self.state.setdefault('invalid_artifacts', []).append(dict(path=self.state[field],
                        expected=self.state.get(hash_field), actual=actual, at=now(),
                        action='Retain previous attempt; rebuild from independently validated upstream checkpoints.'))
            previous = self.state['config']
            if (semantic_config(EventBuildConfig.from_saved(previous)) != semantic_config(config)
                    or config.max_calls < previous['max_calls']):
                raise ValueError('Resume retains semantic settings and cannot reduce the cumulative limit')
            if changed_code:
                # Explicit transport-only upgrade: retain semantic IDs/dependencies so
                # completed stages and responses replay without new paid calls.
                backup = 'recoveries/transport-guard-' + uuid.uuid4().hex + '/state-before.json'
                backup_hash = write_json(self.directory / backup, original_state)
                self.state.setdefault('execution_upgrades', []).append(dict(
                    kind='transport-guard', at=now(), from_code=previous_code,
                    to_code=code_identity(), backup=backup, backup_sha256=backup_hash))
                self.state['execution_code_sha256'] = code_identity()
            for call in self.state['calls']:
                if call['status'] in ('submitted', 'queued'):
                    call.update(status='interrupted', usage_status='unknown')
        else:
            if resume:
                raise ValueError('No run exists to resume')
            write_json(self.directory / 'input.json', payload)
            self.state = dict(run_id=self.directory.name, graph_schema_version=GRAPH_VERSION,
                facts_schema_version=FACTS_VERSION, input_sha256=input_hash, code_sha256=code_identity(),
                fingerprint_format='json-canonical-v1', created_at=now(), calls=[], reads=[], tasks={},
                attempts=0, final_repair_used=False, id_map={}, invalid_checkpoints=[],
                execution_status='ready', result_status='none', render_status='not_started')
        self.state.update(config=asdict(config), attempts=self.state['attempts'] + 1, execution_status='running')
        self.state.pop('service_pause', None)  # An explicit resume retries the repaired account.
        self.attempt = self.directory / 'attempts' / f"{self.state['attempts']:04d}"
        self.attempt.mkdir(parents=True, exist_ok=False)
        self.persist()
        write_json(self.directory / 'config.json', asdict(config))
        if not resume:
            self.state['provenance_sha256'] = write_json(self.directory / 'provenance.json', dict(graph_schema_version=GRAPH_VERSION,
                facts_schema_version=FACTS_VERSION, input_sha256=input_hash, code_sha256=self.state['code_sha256'],
                fingerprint_format='json-canonical-v1', config_fingerprint=fingerprint(semantic_config(config)),
                search_handoff=deepcopy(provenance),
                sample_sha256={s['sample_id']: sha256(s['content'].encode('utf-8')) for s in payload['samples']}))
            self.persist()

    def persist(self):
        self.state['updated_at'] = now()
        write_json(self.directory / 'state.json', self.state)

    def save(self, name, value):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise ValueError('Invalid artifact name')
        path = self.attempt / name
        digest = write_json(path, value)
        return str(path.relative_to(self.directory)), digest

    def check_pause(self):
        # Never interrupt transport or checkpoint publication. The controller
        # clears this request only when the user explicitly prepares a resume.
        if (self.directory / 'pause_requested').is_file():
            raise PauseRequested('Paused between model calls; checkpoints and cumulative usage are retained')

    def task_request(self, task_id, system, request, package):
        if self.state.get('compatible_recovery'):
            from .recovery import upstream_request
            return upstream_request(self, task_id, system, request, package)
        return request

    def attempt_group(self, task_id, system, request, package):
        return task_id + '-' + fingerprint(dict(system=system, request=request, package=package,
            config=semantic_config(self.config), code=self.state['code_sha256']))[:16]

    def reject_proposals(self, group, response_key, issues):
        """Adoption failures spend the same persisted allowance as invalid JSON.

        Replay of a cached response does not spend a second attempt.
        """
        budget = self.state.setdefault('validation_attempts', {}).setdefault(group, {})
        budget.setdefault('adoption:' + response_key, dict(kind='adoption', issues=deepcopy(issues)))
        self.persist()

    def task_event(self, kind, **details):
        from .scheduling import emit
        if getattr(self, 'current_task', None):
            emit(self, *self.current_task, kind, **details)

    def execute_tasks(self, stage, tasks):
        from .scheduling import execute
        return execute(self, stage, tasks)

    def drive(self, task_id, steps, *, stage=None, unwrap=False):
        from .scheduling import Task, ModelCallFailed
        task = self.execute_tasks(stage or task_id.split('.')[0], [Task(task_id, steps)])[task_id]
        if task.error:
            if unwrap and isinstance(task.error, ModelCallFailed):
                raise task.error.original
            raise task.error
        return task.result

    def reserve_call(self, task_id, system, user, dependency, effort):
        if len(self.state['calls']) >= self.config.max_calls:
            raise LimitReached('model_calls')
        call_id = f"CALL-{len(self.state['calls']) + 1:06d}"
        path = self.attempt / 'steps' / call_id
        call = dict(call_id=call_id, task_id=task_id, dependency=dependency,
                    request_fingerprint=fingerprint(dict(system=system, user=user)), status='queued',
                    api_json_mode=self.config.api_json_mode, reasoning_effort=effort,
                    queued_at=now(), usage=None, usage_status='unknown',
                    response_path=str((path / 'response.json').relative_to(self.directory)))
        write_json(path / 'request.json', dict(system=system, user=user, task_id=task_id,
                   dependency=dependency, api_json_mode=self.config.api_json_mode, reasoning_effort=effort))
        self.state['calls'].append(call)
        self.persist()
        return call

    def prefetch_tasks(self, jobs, on_ready=None):
        """Compatibility entry point; production stages schedule full continuations."""
        from .scheduling import Task, ModelRequest
        def steps(task_id, system, request, package):
            dependency = fingerprint(dict(system=system, request=request, package=package,
                config=semantic_config(self.config), code=self.state['code_sha256']))
            key = task_id + '-' + dependency[:16]
            if not (self.directory / 'checkpoints' / (key + '.json')).is_file() and not any(
                    c['task_id'] == task_id and c['dependency'] == dependency and c['status'] == 'prefetched'
                    for c in self.state['calls']):
                user = dict(task=request, read_results=[])
                text = prompt_json(user)
                if len(system) + len(text) > self.config.max_context_chars:
                    raise LimitReached('model_context_chars')
                call = self.reserve_call(task_id, system, user, dependency,
                    person_build_request_effort(self.config.reasoning_effort, request.get('role') or task_id))
                yield ModelRequest(call, system, text)
            if on_ready:
                on_ready(task_id)
        results = self.execute_tasks('prefetch', [Task(job[0], steps(*job)) for job in jobs])
        for task in results.values():
            if task.error:
                raise task.error

    def infer(self, task_id, system, request, package, validator, *, attempt_group=None, single_response=False):
        return self.drive(task_id, self.infer_steps(task_id, system, request, package, validator,
            attempt_group=attempt_group, single_response=single_response), unwrap=True)

    def infer_steps(self, task_id, system, request, package, validator, *, attempt_group=None, single_response=False,
                    allow_reads=True):
        from .scheduling import ModelRequest, ModelCallFailed
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', task_id):
            raise ValueError('Invalid task ID')
        dependency = fingerprint(dict(system=system, request=request, package=package,
                                      config=semantic_config(self.config), code=self.state['code_sha256']))
        key = task_id + '-' + dependency[:16]
        group = attempt_group or key
        budget = self.state.setdefault('validation_attempts', {}).setdefault(group, {})
        checkpoint = self.directory / 'checkpoints' / (key + '.json')
        if not checkpoint.is_file() and self.state.get('compatible_recovery'):
            from .recovery import import_checkpoint
            import_checkpoint(self, task_id, system, request, package, dependency, checkpoint, validator, attempt_group=group)
        if checkpoint.is_file():
            try:
                cached = json.loads(checkpoint.read_text())
                if cached['dependency'] != dependency or cached['response_sha256'] != sha256(json_bytes(cached['response'])):
                    raise ValueError('Checkpoint fingerprint mismatch')
                validator(cached['response'])
                self.save(task_id + '-reused.json', dict(checkpoint=checkpoint.name, dependency=dependency))
                return deepcopy(cached['response'])
            except (ValueError, KeyError, TypeError) as exc:
                self.state['invalid_checkpoints'].append(dict(task_id=task_id, reason=type(exc).__name__, at=now()))
                self.persist()
        if single_response and any(call['task_id'] == task_id for call in self.state['calls']):
            raise InvalidResponse('The one-call supplement has already been attempted without a valid checkpoint')
        task = self.state['tasks'].setdefault(key, dict(invalid_attempts=0, read_results=[], read_requests=[]))
        read_rounds = self.state.setdefault('read_rounds', {}).setdefault(group, [])
        limits = effective_read_limits(self.config)
        round_limit, call_limit, char_limit = limits['read_rounds'], limits['read_calls'], limits['read_chars']
        if task.get('read_round_limit_reached') and len(read_rounds) >= round_limit:
            raise LimitReached('read_rounds')
        # Older versions saved the response but not an explicit pending delivery.
        if not task.get('pending_read_response') and (task.get('read_round_limit_reached')
                or task.get('read_delivery', {}).get('status') == 'limited'):
            blocked = next((c for c in reversed(self.state['calls']) if c['task_id'] == task_id
                and c['dependency'] == dependency and c['status'] == 'limit'), None)
            if blocked:
                from finmy.dataset import within
                saved = json.loads(within(self.directory, blocked['response_path']).read_text())
                value = parse(saved['raw'])
                if set(value) == {'read_requests'}:
                    task['pending_read_response'] = dict(call_id=blocked['call_id'], value=value,
                        next_page=0 if task.get('read_round_limit_reached') else
                        task.get('read_delivery', {}).get('delivered_pages', 0))
        task.pop('read_round_limit_reached', None)
        corpus = Corpus(self.payload, package, self.config)
        effort = person_build_request_effort(self.config.reasoning_effort, request.get('role') or task_id)
        while len(budget) < self.config.max_json_attempts:
            self.check_pause()
            user = dict(task=request, read_results=compact_read_results(request, task['read_results'], corpus.samples))
            if task.get('validation_error'):
                user['validation_error'] = task['validation_error']
            prefetched = next((c for c in self.state['calls'] if c['task_id'] == task_id
                               and c['dependency'] == dependency and c['status'] == 'prefetched'), None)
            if prefetched and prefetched['request_fingerprint'] != fingerprint(dict(system=system, user=user)):
                # Reuse paid responses saved before this prompt-only compaction upgrade.
                legacy = dict(user, read_results=task['read_results'])
                if prefetched['request_fingerprint'] == fingerprint(dict(system=system, user=legacy)):
                    user = legacy
            user_text = prompt_json(user)
            if len(system) + len(user_text) > self.config.max_context_chars:
                raise LimitReached('model_context_chars')
            pending = task.get('pending_read_response')
            if pending:
                call = next(c for c in self.state['calls'] if c['call_id'] == pending['call_id'])
                call_id = call['call_id']
                step_path = (self.directory / call['response_path']).parent
            elif prefetched is None:
                call = self.reserve_call(task_id, system, user, dependency, effort)
                if task.get('validation_error'):
                    call['retry_kind'] = 'format'
                elif request.get('correction'):
                    call['retry_kind'] = 'adoption'
                call_id = call['call_id']
                step_path = self.attempt / 'steps' / call_id
            else:
                call = prefetched
                call_id = call['call_id']
                step_path = self.directory / call['prefetched_response']
                if call['request_fingerprint'] != fingerprint(dict(system=system, user=user)):
                    raise RuntimeError('Prefetched request changed')
            started = time.monotonic()
            received = False
            try:
                retry_key = fingerprint(dict(task_id=task_id, dependency=dependency, user=user))
                retries = self.state.setdefault('transport_retries', {})
                while True:
                    try:
                        if pending:
                            raw = pending['value']
                        elif prefetched is not None:
                            from finmy.dataset import within
                            raw = json.loads(within(self.directory, call['prefetched_response']).read_text())['raw']
                            if sha256(json_bytes(raw)) != call['prefetched_sha256']:
                                raise RuntimeError('Prefetched response changed')
                        else:
                            raw = yield ModelRequest(call, system, user_text)
                    except ModelCallFailed as exc:
                        if (single_response or not getattr(exc.original, 'retryable', False)
                                or retries.get(retry_key, 0) >= self.config.max_transport_retries):
                            raise
                        retry_reason = type(exc.original).__name__
                    else:
                        received = True
                        try:
                            value = parse(raw)
                        except json.JSONDecodeError as exc:
                            if not call.get('transport', {}).get('output_recovered'):
                                raise  # Ordinary completed-but-invalid output uses its format budget.
                            call.update(status='incomplete', recovery_status='invalid_json')
                            if single_response or retries.get(retry_key, 0) >= self.config.max_transport_retries:
                                raise IncompleteStreamResponse(
                                    'Interrupted JSON is incomplete; automatic retry budget exhausted') from exc
                            retry_reason = 'incomplete_json'
                        else:
                            break
                    self.check_pause()
                    prior_call_id = call_id
                    call = self.reserve_call(task_id, system, user, dependency, effort)
                    call_id = call['call_id']
                    call['retry_of'] = prior_call_id
                    call['retry_kind'] = 'transport'
                    step_path = self.attempt / 'steps' / call_id
                    retries[retry_key] = retries.get(retry_key, 0) + 1
                    prefetched = None
                    received = False
                    self.task_event('RetryRequested', call_id=call_id, retry_of=prior_call_id,
                                    reason=retry_reason)
                    self.persist()
                if 'read_requests' in value:
                    if not allow_reads:
                        raise InvalidResponse('This task does not allow reads; return the requested role result')
                    if single_response:
                        raise InvalidResponse('The complete handoff is already present; this pass has no local reads')
                    if set(value) != {'read_requests'} or not isinstance(value['read_requests'], list) or not value['read_requests']:
                        raise InvalidResponse('Return either read_requests or the role result, never both')
                    task.setdefault('pending_read_response', dict(call_id=call_id, value=value, next_page=0))
                    if call_id not in read_rounds and len(read_rounds) >= round_limit:
                        task['read_round_limit_reached'] = True
                        raise LimitReached('read_rounds')
                    self.task_event('ReadRequested', call_id=call_id)
                    pages = []
                    for read in value['read_requests']:
                        if request.get('role') == 'extraction' and read.get('tool') == 'search':
                            raise InvalidResponse('Initial extraction reads its continuous body ranges; local search is for later roles')
                        pages.extend((read, part, result) for part, result in corpus.pages(read))
                    # One response can request many pages; count it as one round.
                    # The semantic group shares this budget with corrections and resume.
                    if call_id not in read_rounds:
                        read_rounds.append(call_id)
                        self.persist()
                    # Keep every delivery, but charge source characters only once across tasks.
                    for number, (original, read, result) in enumerate(pages):
                        if number < task['pending_read_response']['next_page']:
                            continue
                        chars = len(json_bytes(result).decode('utf-8'))
                        spent, budget_chars = next_read_charge(corpus.samples, self.state['reads'], read, result)
                        reason = ('read_calls' if len(self.state['reads']) >= call_limit else
                                  'read_chars' if spent + budget_chars > char_limit else None)
                        next_results = task['read_results'] + [dict(request=read, result=result)]
                        next_user = dict(task=request, read_results=compact_read_results(request, next_results, corpus.samples))
                        if task.get('validation_error'):
                            next_user['validation_error'] = task['validation_error']
                        if not reason and len(system) + len(prompt_json(next_user)) > self.config.max_context_chars:
                            reason = 'model_context_chars'
                        if reason:
                            task['read_delivery'] = dict(status='limited', reason=reason,
                                delivered_pages=number, remaining_requests=[p[1] for p in pages[number:]])
                            self.persist()
                            raise LimitReached(reason)
                        record = dict(call_id=call_id, task_id=task_id, request=read, original_request=original,
                                      result=result, chars=chars, budget_chars=budget_chars,
                                      result_fingerprint=fingerprint(result))
                        if read.get('tool') in ('read_sample', 'search'):
                            items = result if isinstance(result, list) else [result]
                            record['sample_versions'] = {item['sample_id']:
                                sha256(corpus.samples[item['sample_id']]['content'].encode('utf-8')) for item in items}
                        self.state['reads'].append(record)
                        self.state['read_budget'] = dict(accounting='unique-source-ranges-v1',
                            charged_chars=spent + budget_chars, max_chars=char_limit)
                        task['read_results'].append(dict(request=read, result=result))
                        task['read_requests'].append(read)
                        task['read_delivery'] = dict(status='completed' if number == len(pages)-1 else 'delivering',
                            delivered_pages=number+1, remaining_requests=[p[1] for p in pages[number+1:]])
                        task['pending_read_response']['next_page'] = number + 1
                        self.persist()
                    task.pop('pending_read_response', None)
                    call['status'] = 'read_requested'
                    if call.get('transport', {}).get('output_recovered'):
                        call['recovery_status'] = 'validated_read_requests'
                    task.pop('validation_error', None)
                    continue
                validator(value)
                if call.get('transport', {}).get('output_recovered'):
                    call['recovery_status'] = 'validated_complete'
                call['status'] = 'accepted'
                write_json(checkpoint, dict(task_id=task_id, dependency=dependency, call_id=call_id,
                    response=value, response_sha256=sha256(json_bytes(value)), reads=task['read_requests']))
                return value
            except LimitReached:
                call['status'] = 'limit'
                raise
            except ModelCallFailed:
                # The coordinator has persisted transport diagnostics and response status.
                raise
            except IncompleteCompletionError as exc:
                call.update(status='incomplete', **error_metadata(exc))
                raise
            except IncompleteStreamResponse:
                raise
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                if not received:
                    call.update(status='transport_error', **error_metadata(exc))
                    raise
                call['status'] = 'invalid_output'
                task['invalid_attempts'] += 1
                task['validation_error'] = str(exc)[:1600]
                budget['format:' + call_id] = dict(kind='protocol', message=task['validation_error'])
                self.task_event('RetryRequested', call_id=call_id, reason='invalid_output')
                if single_response or len(budget) >= self.config.max_json_attempts:
                    raise InvalidResponse(task['validation_error']) from exc
            except GeneratorExit:
                raise  # Keep drained prefetched responses reusable after pause.
            except BaseException as exc:
                call.update(status='interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'transport_error',
                            **error_metadata(exc))
                raise
            finally:
                self.persist()
        raise InvalidResponse('JSON attempts exhausted for this semantic task; inspect the saved responses')
