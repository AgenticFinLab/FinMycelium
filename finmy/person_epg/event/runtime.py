"""Durable, bounded execution over one immutable, local evidence corpus."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

from finmy.model_config import (person_build_effort_options, person_build_json_mode_supported,
                                person_build_request_effort)

from .records import fingerprint, index_records, json_bytes, pointer, sha256, prompt_json
from .schema import FACTS_VERSION, GRAPH_VERSION
from ..building.model_transport import error_metadata
from ..building.completion_errors import IncompleteCompletionError


@dataclass
class EventBuildConfig:
    lm_name: str = 'ark/kimi-k3-1-pro-261024'
    max_calls: int = 40
    max_json_attempts: int = 3
    max_new_tokens: int = 12288
    max_context_chars: int = 160000
    timeout: int = 900
    extraction_chars: int = 12000
    extraction_overlap: int = 400
    max_read_calls: int = 24
    max_read_chars: int = 48000
    read_chars: int = 4000
    retrieval_top_k: int = 4
    final_repair_rounds: int = 1
    graph_schema_version: str = GRAPH_VERSION
    api_json_mode: bool = False
    full_corpus_supplement: bool = True
    automatic_search: bool = False
    reasoning_effort: str | None = 'auto'

    @classmethod
    def from_saved(cls, values):
        """Restore the defaults in effect before each setting was recorded."""
        return cls(**{'reasoning_effort': None, 'full_corpus_supplement': False, **values})

    def __post_init__(self):
        if not isinstance(self.lm_name, str) or not self.lm_name.strip():
            raise ValueError('Choose an independent build model')
        if type(self.full_corpus_supplement) is not bool:
            raise ValueError('full_corpus_supplement must be a boolean')
        if type(self.automatic_search) is not bool:
            raise ValueError('automatic_search must be a boolean')
        if type(self.api_json_mode) is not bool:
            raise ValueError('api_json_mode must be a boolean')
        if self.api_json_mode and not person_build_json_mode_supported(self.lm_name):
            raise ValueError('API JSON mode is currently supported for Ark Kimi K3.1 Pro only')
        effort_options = person_build_effort_options(self.lm_name)
        if self.reasoning_effort == 'auto':
            self.reasoning_effort = effort_options[0]
        elif self.reasoning_effort not in effort_options:
            raise ValueError('reasoning_effort accepts by_stage, low, high or max for Kimi K3.1 Pro, or None for the service default')
        for key, value in asdict(self).items():
            if key in ('lm_name', 'graph_schema_version', 'api_json_mode', 'full_corpus_supplement', 'automatic_search', 'reasoning_effort'):
                continue
            minimum = 0 if key in ('extraction_overlap', 'final_repair_rounds', 'max_read_calls') else 1
            if type(value) is not int or value < minimum:
                raise ValueError(key + ' is outside its supported range')
        if self.graph_schema_version != GRAPH_VERSION:
            raise ValueError('This executor only writes ' + GRAPH_VERSION)
        if self.extraction_overlap >= self.extraction_chars:
            raise ValueError('Extraction overlap must be smaller than the batch')
        if self.final_repair_rounds > 1:
            raise ValueError('At most one final targeted repair round is supported')


def kimi_workbench_config(*, automatic_search=False):
    return EventBuildConfig(max_calls=120 if automatic_search else 60, max_new_tokens=65536,
                            max_context_chars=240000, max_read_calls=80 if automatic_search else 60,
                            max_read_chars=200000 if automatic_search else 160000, automatic_search=automatic_search)


class LimitReached(Exception):
    pass


class PauseRequested(Exception):
    pass


class InvalidResponse(ValueError):
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
    files = {p for p in event.glob('*.py') if p.name != 'rendering.py'}
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
    value = {k: v for k, v in asdict(config).items() if k != 'max_calls'}
    # Missing in historical ordinary-mode configurations. Preserve their hashes;
    # explicit JSON mode still changes all request/checkpoint dependencies.
    if not config.automatic_search:
        value.pop('automatic_search')
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
    def __init__(self, directory, payload, config, model, *, resume=False, provenance=None):
        self.directory, self.payload, self.config, self.model = Path(directory), payload, config, model
        self.directory.mkdir(parents=True, exist_ok=True)
        state_path = self.directory / 'state.json'
        input_hash = sha256(json_bytes(payload))
        if state_path.exists():
            if not resume:
                raise ValueError('Existing run requires explicit resume or a new directory')
            self.state = json.loads(state_path.read_text())
            if self.state.get('graph_schema_version') != GRAPH_VERSION:
                raise ValueError('Cannot resume a different graph protocol')
            if (self.state['input_sha256'] != input_hash
                    or sha256((self.directory / 'input.json').read_bytes()) != input_hash):
                raise ValueError('Frozen input changed; create a new run')
            if self.state.get('compatible_recovery'):
                from .recovery import validate_recovery
                validate_recovery(self.directory, self.state)
            if self.state['code_sha256'] != code_identity():
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
            for call in self.state['calls']:
                if call['status'] == 'submitted':
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

    def infer(self, task_id, system, request, package, validator, *, attempt_group=None, single_response=False):
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
        corpus = Corpus(self.payload, package, self.config)
        effort = person_build_request_effort(self.config.reasoning_effort, request.get('role') or task_id)
        while len(budget) < self.config.max_json_attempts:
            self.check_pause()
            user = dict(task=request, read_results=task['read_results'])
            if task.get('validation_error'):
                user['validation_error'] = task['validation_error']
            user_text = prompt_json(user)
            if len(system) + len(user_text) > self.config.max_context_chars:
                raise LimitReached('model_context_chars')
            if len(self.state['calls']) >= self.config.max_calls:
                raise LimitReached('model_calls')
            call_id = f"CALL-{len(self.state['calls']) + 1:06d}"
            call = dict(call_id=call_id, task_id=task_id, dependency=dependency,
                        request_fingerprint=fingerprint(dict(system=system, user=user)), status='submitted',
                        api_json_mode=self.config.api_json_mode, reasoning_effort=effort,
                        context_chars=len(system) + len(user_text), started_at=now(), usage=None, usage_status='unknown')
            step_path = self.attempt / 'steps' / call_id
            write_json(step_path / 'request.json', dict(system=system, user=user, task_id=task_id,
                dependency=dependency, api_json_mode=self.config.api_json_mode, reasoning_effort=effort))
            self.state['calls'].append(call)
            self.persist()  # Durable reservation before the transport is invoked.
            started = time.monotonic()
            received = False
            try:
                send = getattr(self.model, 'call_with_effort', None)
                if send is None:
                    raw = self.model(system, user_text, task_id)
                else:
                    raw = send(system, user_text, task_id, reasoning_effort=effort)
                received = True
                write_json(step_path / 'response.json', dict(raw=raw))
                value = parse(raw)
                if 'read_requests' in value:
                    if request.get('role') == 'gap_review':
                        raise InvalidResponse('Evaluate the supplied evidence and return the requested decision')
                    if single_response:
                        raise InvalidResponse('The complete handoff is already present; this pass has no local reads')
                    if set(value) != {'read_requests'} or not isinstance(value['read_requests'], list) or not value['read_requests']:
                        raise InvalidResponse('Return either read_requests or the role result, never both')
                    pages = []
                    for read in value['read_requests']:
                        if request.get('role') == 'extraction' and read.get('tool') == 'search':
                            raise InvalidResponse('Initial extraction reads its continuous body ranges; local search is for later roles')
                        pages.extend((read, part, result) for part, result in corpus.pages(read))
                    # Each delivered page spends existing read quotas. Save progress before stopping.
                    for number, (original, read, result) in enumerate(pages):
                        chars = len(json_bytes(result).decode('utf-8'))
                        reason = ('read_calls' if len(self.state['reads']) >= self.config.max_read_calls else
                                  'read_chars' if sum(r['chars'] for r in self.state['reads']) + chars > self.config.max_read_chars else None)
                        next_results = task['read_results'] + [dict(request=read, result=result)]
                        next_user = dict(task=request, read_results=next_results)
                        if not reason and len(system) + len(prompt_json(next_user)) > self.config.max_context_chars:
                            reason = 'model_context_chars'
                        if reason:
                            task['read_delivery'] = dict(status='limited', reason=reason,
                                delivered_pages=number, remaining_requests=[p[1] for p in pages[number:]])
                            self.persist()
                            raise LimitReached(reason)
                        record = dict(call_id=call_id, task_id=task_id, request=read, original_request=original,
                                      result=result, chars=chars, result_fingerprint=fingerprint(result))
                        self.state['reads'].append(record)
                        task['read_results'].append(dict(request=read, result=result))
                        task['read_requests'].append(read)
                        task['read_delivery'] = dict(status='completed' if number == len(pages)-1 else 'delivering',
                            delivered_pages=number+1, remaining_requests=[p[1] for p in pages[number+1:]])
                        self.persist()
                    call['status'] = 'read_requested'
                    task.pop('validation_error', None)
                    continue
                validator(value)
                call['status'] = 'accepted'
                write_json(checkpoint, dict(task_id=task_id, dependency=dependency, call_id=call_id,
                    response=value, response_sha256=sha256(json_bytes(value)), reads=task['read_requests']))
                return value
            except LimitReached:
                call['status'] = 'limit'
                raise
            except IncompleteCompletionError as exc:
                call.update(status='incomplete', **error_metadata(exc))
                raise
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                if not received:
                    call.update(status='transport_error', **error_metadata(exc))
                    raise
                call['status'] = 'invalid_output'
                task['invalid_attempts'] += 1
                task['validation_error'] = str(exc)[:1600]
                budget['format:' + call_id] = dict(kind='protocol', message=task['validation_error'])
                if single_response or len(budget) >= self.config.max_json_attempts:
                    raise InvalidResponse(task['validation_error']) from exc
            except BaseException as exc:
                call.update(status='interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'transport_error',
                            **error_metadata(exc))
                raise
            finally:
                transport = deepcopy(getattr(self.model, 'last_diagnostics', None))
                if transport is not None:
                    call['transport'] = transport
                usage = deepcopy(getattr(self.model, 'last_usage', None))
                call.update(duration_seconds=round(time.monotonic() - started, 3), usage=usage,
                            usage_status='reported' if usage is not None else 'unknown')
                self.persist()
        raise InvalidResponse('JSON attempts exhausted for this semantic task; inspect the saved responses')
