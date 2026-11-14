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

from .records import fingerprint, index_records, json_bytes, pointer, sha256
from .schema import FACTS_VERSION, GRAPH_VERSION
from ..building.model_transport import error_metadata
from ..building.completion_errors import IncompleteCompletionError


@dataclass
class EventBuildConfig:
    lm_name: str = 'ark/doubao-seed-2-0-pro-260215'
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

    def __post_init__(self):
        if not isinstance(self.lm_name, str) or not self.lm_name.strip():
            raise ValueError('Choose an independent build model')
        for key, value in asdict(self).items():
            if key in ('lm_name', 'graph_schema_version'):
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


def code_identity():
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
    return fingerprint({p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in sorted(files)})


def semantic_config(config):
    return {k: v for k, v in asdict(config).items() if k != 'max_calls'}


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
                raise ValueError('Requested records exceed read_chars; select narrower fields')
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
            if any(previous[k] != v for k, v in semantic_config(config).items()) or config.max_calls < previous['max_calls']:
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

    def infer(self, task_id, system, request, package, validator):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', task_id):
            raise ValueError('Invalid task ID')
        dependency = fingerprint(dict(system=system, request=request, package=package,
                                      config=semantic_config(self.config), code=self.state['code_sha256']))
        key = task_id + '-' + dependency[:16]
        checkpoint = self.directory / 'checkpoints' / (key + '.json')
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
        task = self.state['tasks'].setdefault(key, dict(invalid_attempts=0, read_results=[], read_requests=[]))
        corpus = Corpus(self.payload, package, self.config)
        while task['invalid_attempts'] < self.config.max_json_attempts:
            self.check_pause()
            user = dict(task=request, read_results=task['read_results'])
            if task.get('validation_error'):
                user['validation_error'] = task['validation_error']
            user_text = json_bytes(user).decode('utf-8')
            if len(system) + len(user_text) > self.config.max_context_chars:
                raise LimitReached('model_context_chars')
            if len(self.state['calls']) >= self.config.max_calls:
                raise LimitReached('model_calls')
            call_id = f"CALL-{len(self.state['calls']) + 1:06d}"
            call = dict(call_id=call_id, task_id=task_id, dependency=dependency,
                        request_fingerprint=fingerprint(dict(system=system, user=user)), status='submitted',
                        started_at=now(), usage=None, usage_status='unknown')
            step_path = self.attempt / 'steps' / call_id
            write_json(step_path / 'request.json', dict(system=system, user=user, task_id=task_id, dependency=dependency))
            self.state['calls'].append(call)
            self.persist()  # Durable reservation before the transport is invoked.
            started = time.monotonic()
            received = False
            try:
                raw = self.model(system, user_text, task_id)
                received = True
                write_json(step_path / 'response.json', dict(raw=raw))
                value = parse(raw)
                if 'read_requests' in value:
                    if set(value) != {'read_requests'} or not isinstance(value['read_requests'], list) or not value['read_requests']:
                        raise InvalidResponse('Return either read_requests or the role result, never both')
                    for read in value['read_requests']:
                        if request.get('role') == 'extraction' and read.get('tool') == 'search':
                            raise InvalidResponse('Initial extraction reads its continuous body ranges; local search is for later roles')
                        if len(self.state['reads']) >= self.config.max_read_calls:
                            raise LimitReached('read_calls')
                        result = corpus.read(read)
                        chars = len(json_bytes(result).decode('utf-8'))
                        if sum(r['chars'] for r in self.state['reads']) + chars > self.config.max_read_chars:
                            raise LimitReached('read_chars')
                        record = dict(call_id=call_id, task_id=task_id, request=read, result=result,
                                      chars=chars, result_fingerprint=fingerprint(result))
                        self.state['reads'].append(record)
                        task['read_results'].append(dict(request=read, result=result))
                        task['read_requests'].append(read)
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
                if task['invalid_attempts'] >= self.config.max_json_attempts:
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
