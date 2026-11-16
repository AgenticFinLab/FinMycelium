"""Explicit offline migrations for verified execution repairs and output headroom."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile

from .records import fingerprint, json_bytes, sha256
from .runtime import EventBuildConfig, PauseRequested, code_identity, code_manifest, now, semantic_config, write_json

ORIGIN = 'dbb94aa9865364a89f298661ffb591856c1ae68817000f66f5f6132dfd4107b4'
OLD_RUNTIME = '561b13e65e0f5c147d67315dee2a28fe5819da29cadd3dde64a0c1171a8a8c84'
OLD_WORKBENCH = '33ad90098f9fc49a0a70f14eb60c700474ad83d3c83e8788e9957faacb2ba5e4'
RECORD = 'recoveries/record-read-v1/manifest.json'

RELATION_ORIGIN = '42d5788aef8f0785be56423bb022464b0409f60fd96fc4a09c2433b9b5079928'
RELATION_RECORD = 'recoveries/relation-context-v1/manifest.json'
RELATION_PREVIOUS = {'person_epg/event/build.py': '4b025b6cb62b11b7866a4c1c7962ceeda2afd428a25e35b9db39e8728386fc53', 'person_epg/event/context.py': '986a12074495a36d9509ba4b4c29eae438e589ab049f95249e5c284060b36b53', 'person_epg/event/prompts.py': 'b0bb75d42cb9854053fe3cfc82132cd79b70f85c210e2b5098688f9ef8f5db05', 'person_epg/event/runtime.py': '6f72667dd342e22b88d7a6a356f01af7efe8620b1a76e049b75fa3f65450a825', 'person_epg/event/recovery.py': 'a2fab62d1115d11400006bd2158e23e30842ab323561b741d858deb43ff18082'}
RELATION_WORKBENCH = '412cf4537185c6b34c249818e6eca4ce8704d13c2cd428b6a236856da8797946'

OUTPUT_ORIGIN = '80568a42cfa08d50e5b41990aef056b55467bebabb72f09f43ad75e6bf103aad'
OUTPUT_RECORD = 'recoveries/output-limit-v1/manifest.json'
OUTPUT_PREVIOUS = 'b576a336b391fc937a02649590d778bc3845c28cf1c8e0bd898ffeb9a0d219f5'
OUTPUT_WORKBENCH = '2b85bb66b273ae12d5c08959cb07e894a1bbdad9d7fe776506238eebbf136b3f'


def compatible_code():
    manifest = code_manifest()
    manifest.update({k: v for k, v in RELATION_PREVIOUS.items() if k not in ('person_epg/event/recovery.py', 'person_epg/event/runtime.py')})
    manifest.pop('person_epg/event/recovery.py', None)
    manifest['person_epg/event/runtime.py'] = OLD_RUNTIME
    return fingerprint(manifest) == ORIGIN


def compatible_workbench(old):
    """Only these repair files may differ; a commit label alone proves nothing."""
    from finmy.workbench.build_tasks import ROOT
    from finmy.workbench.domain import digest
    files = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sorted((ROOT/'finmy').rglob('*.py'))}
    files.update({'finmy/'+k: v for k, v in RELATION_PREVIOUS.items() if k not in ('person_epg/event/recovery.py', 'person_epg/event/runtime.py')})
    files.pop('finmy/person_epg/event/recovery.py', None)
    files['finmy/person_epg/event/runtime.py'] = OLD_RUNTIME
    files['finmy/workbench/build_tasks.py'] = OLD_WORKBENCH
    return digest(files) == old['python_sources_sha256'] and compatible_code()


def validate_recovery(directory, state):
    from finmy.dataset import within
    directory = Path(directory)
    entry = state['compatible_recovery']
    if entry['record'] == OUTPUT_RECORD:
        return validate_output_recovery(directory, state)
    if entry['record'] == RELATION_RECORD:
        return validate_relation_recovery(directory, state)
    path = within(directory, entry['record'])
    if entry['record'] != RECORD or sha256(path.read_bytes()) != entry['sha256']:
        raise ValueError('Recovery record integrity mismatch')
    record = json.loads(path.read_text())
    if record['from_code'] != ORIGIN or record['to_code'] != code_identity() or not compatible_code():
        raise ValueError('Unsupported recovery implementation')
    if state['input_sha256'] != record['input_sha256'] or semantic_config(EventBuildConfig(**state['config'])) != record['semantic_config']:
        raise ValueError('Recovery input or settings changed')
    for name, digest in record['files'].items():
        if sha256(within(directory, name).read_bytes()) != digest:
            raise ValueError('Recovery source changed: '+name)
    return record


def import_checkpoint(execution, task_id, system, request, package, dependency, target, validator, *, attempt_group=None):
    if execution.state['compatible_recovery']['record'] == OUTPUT_RECORD:
        return import_output_checkpoint(execution, task_id, system, request, package, dependency, target, validator, attempt_group)
    if execution.state['compatible_recovery']['record'] == RELATION_RECORD:
        return import_relation_checkpoint(execution, task_id, system, request, package, dependency, target, validator, attempt_group)
    if not task_id.startswith('extract.'):
        return
    record = validate_recovery(execution.directory, execution.state)
    old_dependency = fingerprint(dict(system=system, request=request, package=package,
        config=semantic_config(execution.config), code=record['from_code']))
    name = 'checkpoints/' + task_id + '-' + old_dependency[:16] + '.json'
    if name not in record['files']:
        raise ValueError('No verified matching extraction checkpoint: '+task_id)
    cached = json.loads((execution.directory/name).read_text())
    if cached['dependency'] != old_dependency or cached['response_sha256'] != sha256(json_bytes(cached['response'])):
        raise ValueError('Imported checkpoint response mismatch')
    if not any(c['call_id'] == cached['call_id'] and c['status'] == 'accepted' and c['dependency'] == old_dependency
               for c in execution.state['calls']):
        raise ValueError('Imported checkpoint lacks an accepted original call')
    validator(cached['response'])
    write_json(target, dict(cached, dependency=dependency, imported_from=dict(path=name,
        sha256=record['files'][name], recovery=RECORD)))


def prepare_record_recovery(directory):
    """Caller holds task/worker/run locks. Never invokes a real model or network."""
    from .build import run_event
    from finmy.dataset import within
    directory = Path(directory)
    state = json.loads((directory/'state.json').read_text())
    if state.get('compatible_recovery'):
        validate_recovery(directory, state)
        return state['compatible_recovery']
    if not compatible_code() or state['code_sha256'] != ORIGIN:
        raise ValueError('Only the verified pre-repair implementation can migrate')
    if state['execution_status'] != 'failed' or state.get('offline_revisions'):
        raise ValueError('Recovery requires an unedited failed run')
    if not state['calls'] or state['calls'][-1]['task_id'] != 'organize':
        raise ValueError('This migration only resumes failed organization after extraction')
    if not state.get('coverage') or any(x.get('status') != 'processed' or x.get('proposal_status') != 'resolved' for x in state['coverage']):
        raise ValueError('All extraction batches must already be resolved')
    payload = json.loads((directory/'input.json').read_text())
    if sha256((directory/'input.json').read_bytes()) != state['input_sha256']:
        raise ValueError('Frozen input changed')
    files = {'input.json':state['input_sha256'], 'provenance.json':state['provenance_sha256']}
    for field in ('facts','checks','output'):
        files[state[field]] = state[{'facts':'facts_sha256','checks':'checks_sha256','output':'graph_sha256'}[field]]
    checkpoints = list((directory/'checkpoints').glob('*.json'))
    if len(checkpoints) != len(state['coverage']) or any(not p.name.startswith('extract.') for p in checkpoints):
        raise ValueError('Recovery expects one completed checkpoint per extraction batch')
    files.update({str(p.relative_to(directory)):sha256(p.read_bytes()) for p in checkpoints})
    for name,digest in files.items():
        if sha256(within(directory,name).read_bytes()) != digest:
            raise ValueError('Frozen artifact changed: '+name)
    before = (directory/'state.json').read_bytes()
    backup = 'recoveries/record-read-v1/state-before.json'
    files[backup] = sha256(before)
    record = dict(kind='record-read-v1', created_at=now(), from_code=ORIGIN, to_code=code_identity(),
        input_sha256=state['input_sha256'], semantic_config=semantic_config(EventBuildConfig(**state['config'])),
        files=files, stage='organize', original_calls=len(state['calls']), original_reads=len(state['reads']),
        extraction_checkpoints=len(checkpoints), reason='Batch whole record refs within unchanged read quotas.')
    # Reuse a fully published preparation after interruption before the state switch.
    if (directory/RECORD).exists():
        existing = json.loads((directory/RECORD).read_text())
        if {k:v for k,v in existing.items() if k != 'created_at'} != {k:v for k,v in record.items() if k != 'created_at'}:
            raise ValueError('Existing recovery record differs; inspect before retrying')
        record = existing
    entry = dict(record=RECORD, sha256=sha256(json_bytes(record)))
    migrated = deepcopy(state)
    migrated.update(code_sha256=code_identity(), compatible_recovery=entry)
    # Dry replay verifies current adoption/IDs and prohibits even a single paid extraction.
    with tempfile.TemporaryDirectory(prefix='finmy-read-recovery-') as temp:
        clone = Path(temp)/directory.name
        for name in files:
            destination = clone/name; destination.parent.mkdir(parents=True,exist_ok=True)
            if name == backup: destination.write_bytes(before)
            else: shutil.copyfile(directory/name,destination)
        write_json(clone/RECORD, record); write_json(clone/'state.json', migrated)
        seen = []
        def stop_at_organization(system,user,task):
            seen.append(task)
            raise PauseRequested('Offline recovery validation; no model invoked')
        checked = run_event(payload, clone, state['config'], model=stop_at_organization, resume=True)
        if seen != ['organize'] or checked['execution_status'] != 'paused':
            raise ValueError('Offline replay did not reach organization without re-extraction: '+str(seen))
        if checked['facts_sha256'] != state['facts_sha256']:
            raise ValueError('Offline replay changed adopted facts; migration refused')
    publish_immutable(directory, {backup: before, RECORD: json_bytes(record)})
    write_json(directory/'state.json',migrated)
    return entry


def publish_immutable(directory, records):
    """Publish exact bytes before the mutable pointer; an interrupted write is retryable."""
    import os
    for name, data in records.items():
        path = Path(directory)/name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('Existing recovery record differs: '+name)
            continue
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)


def compatible_relation_code():
    manifest = code_manifest()
    manifest.update(RELATION_PREVIOUS)
    return fingerprint(manifest) == RELATION_ORIGIN


def compatible_relation_workbench(old):
    from finmy.workbench.build_tasks import ROOT
    from finmy.workbench.domain import digest
    files = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sorted((ROOT/'finmy').rglob('*.py'))}
    files.update({'finmy/'+name: digest for name, digest in RELATION_PREVIOUS.items()})
    files['finmy/workbench/build_tasks.py'] = RELATION_WORKBENCH
    return digest(files) == old['python_sources_sha256'] and compatible_relation_code()


def validate_relation_recovery(directory, state):
    from finmy.dataset import within
    directory = Path(directory); entry = state['compatible_recovery']
    path = within(directory, entry['record'])
    if entry['record'] != RELATION_RECORD or sha256(path.read_bytes()) != entry['sha256']:
        raise ValueError('Relation recovery record integrity mismatch')
    record = json.loads(path.read_text())
    if (record['from_code'] != RELATION_ORIGIN or record['to_code'] != code_identity()
            or not compatible_relation_code()):
        raise ValueError('Unsupported relation recovery implementation')
    if state['input_sha256'] != record['input_sha256'] or semantic_config(EventBuildConfig(**state['config'])) != semantic_config(EventBuildConfig(**record['config'])):
        raise ValueError('Relation recovery input or settings changed')
    for name, digest in record['files'].items():
        if sha256(within(directory, name).read_bytes()) != digest:
            raise ValueError('Relation recovery source changed: '+name)
    return record


def upstream_request(execution, task_id, system, request, package):
    """Replay the original request as well as its response to preserve stable IDs."""
    if execution.state.get('compatible_recovery', {}).get('record') != RELATION_RECORD:
        return request
    record = validate_relation_recovery(execution.directory, execution.state)
    previous = record['upstream'].get(task_id)
    if previous is None:
        return request
    original = json.loads((execution.directory/previous['request']).read_text())
    cached = json.loads((execution.directory/previous['checkpoint']).read_text())
    optional = {'facts_index', 'related_records', 'context_selection'}
    core = lambda value: {k:v for k,v in value.items() if k not in optional}
    if system != original['system'] or core(request) != core(original['user']['task']):
        raise ValueError('Upstream task semantics changed: '+task_id)
    old_dependency = fingerprint(dict(system=system, request=original['user']['task'], package=package,
        config=semantic_config(EventBuildConfig(**record['previous_config'])), code=previous['code']))
    if old_dependency != cached['dependency']:
        raise ValueError('Upstream package changed: '+task_id)
    return deepcopy(original['user']['task'])


def import_relation_checkpoint(execution, task_id, system, request, package, dependency, target, validator, group):
    record = validate_relation_recovery(execution.directory, execution.state)
    if task_id == 'relate.0':
        # Failed protocol attempts are retained even though this task is repacked.
        budget = execution.state['validation_attempts'].setdefault(group, {})
        for old in record['relation_validation'].values():
            for key, value in old.items():
                budget.setdefault(key, deepcopy(value))
        execution.persist()
    previous = record['upstream'].get(task_id)
    if previous is None:
        if task_id.startswith(('extract.', 'consolidate.')) or task_id == 'organize':
            raise ValueError('Missing verified upstream checkpoint: '+task_id)
        return
    root = execution.directory
    original = json.loads((root/previous['request']).read_text())
    cached = json.loads((root/previous['checkpoint']).read_text())
    # Only optional context packing can differ upstream; bodies, identity, role
    # instructions, correction scope and package dependencies must match exactly.
    optional = {'facts_index', 'related_records', 'context_selection'}
    core = lambda value: {k:v for k,v in value.items() if k not in optional}
    if system != original['system'] or core(request) != core(original['user']['task']):
        raise ValueError('Upstream task semantics changed: '+task_id)
    old_dependency = fingerprint(dict(system=system, request=original['user']['task'], package=package,
        config=semantic_config(EventBuildConfig(**record['previous_config'])), code=previous['code']))
    if old_dependency != cached['dependency'] or cached['response_sha256'] != sha256(json_bytes(cached['response'])):
        raise ValueError('Upstream checkpoint dependency mismatch: '+task_id)
    if not any(c['call_id'] == cached['call_id'] and c['dependency'] == old_dependency and c['status'] == 'accepted'
               for c in execution.state['calls']):
        raise ValueError('Upstream checkpoint lacks an accepted call')
    validator(cached['response'])
    write_json(target, dict(cached, dependency=dependency, imported_from=dict(path=previous['checkpoint'],
        sha256=record['files'][previous['checkpoint']], recovery=RELATION_RECORD)))


def prepare_relation_recovery(directory, *, max_context_chars, max_read_calls, max_read_chars):
    """Repack only unfinished relations; replay completed work without paid calls."""
    from .build import run_event
    directory = Path(directory)
    state = json.loads((directory/'state.json').read_text())
    requested = dict(max_context_chars=max_context_chars, max_read_calls=max_read_calls, max_read_chars=max_read_chars)
    if state.get('compatible_recovery', {}).get('record') == RELATION_RECORD:
        record = validate_relation_recovery(directory, state)
        if any(record['config'][k] != v for k,v in requested.items()):
            raise ValueError('An existing recovery has different approved limits')
        write_json(directory/'config.json', state['config'])
        return state['compatible_recovery']
    if not compatible_relation_code() or state['code_sha256'] != RELATION_ORIGIN:
        raise ValueError('Relation recovery only supports the verified preceding implementation')
    if state['execution_status'] != 'limit' or state.get('reason') != 'model_context_chars' or state.get('offline_revisions'):
        raise ValueError('Choose an unedited run stopped by the context limit')
    if not state['calls'] or state['calls'][-1]['task_id'] != 'relate.0' or any(c['status']=='accepted' and c['task_id'].startswith('relate.') for c in state['calls']):
        raise ValueError('Recovery requires unfinished first relation work')
    if not state.get('coverage') or any(x.get('status') != 'processed' or x.get('proposal_status') != 'resolved' for x in state['coverage']):
        raise ValueError('Extraction must already be resolved')
    if not any(c['status']=='accepted' and c['task_id']=='organize' for c in state['calls']):
        raise ValueError('Organization checkpoint is required')
    if any(type(v) is not int or v < state['config'][k] for k,v in requested.items()):
        raise ValueError('Recovery limits must not decrease')
    config = dict(state['config'], **requested); EventBuildConfig(**config)
    before = (directory/'state.json').read_bytes()
    files = {str(f.relative_to(directory)):sha256(f.read_bytes())
        for name in ('attempts', 'checkpoints', 'recoveries') for f in (directory/name).rglob('*')
        if f.is_file() and not f.is_relative_to(directory/Path(RELATION_RECORD).parent)}
    for name,key in [('input.json','input_sha256'),('provenance.json','provenance_sha256')]:
        if sha256((directory/name).read_bytes()) != state[key]:
            raise ValueError('Frozen artifact changed: '+name)
        files[name]=state[key]
    for name,key in [('facts','facts_sha256'),('output','graph_sha256'),('checks','checks_sha256')]:
        if files[state[name]] != state[key]:
            raise ValueError('Saved artifact changed: '+name)
    codes = [RELATION_ORIGIN]
    prior = state.get('compatible_recovery')
    if prior:
        if prior['record'] != RECORD or files.get(RECORD) != prior['sha256']:
            raise ValueError('Previous recovery record mismatch')
        parent=json.loads((directory/RECORD).read_text())
        if (parent['from_code'] != ORIGIN or parent['to_code'] != RELATION_ORIGIN
                or parent['input_sha256'] != state['input_sha256']
                or parent['semantic_config'] != semantic_config(EventBuildConfig(**state['config']))
                or any(files.get(n) != h for n,h in parent['files'].items())):
            raise ValueError('Previous recovery chain mismatch')
        codes.append(ORIGIN)
    upstream={}
    for call in state['calls']:
        task=call['task_id']
        if call['status']!='accepted' or not (task.startswith(('extract.','consolidate.')) or task=='organize'):
            continue
        checkpoint='checkpoints/'+task+'-'+call['dependency'][:16]+'.json'
        matches=list((directory/'attempts').glob('*/steps/'+call['call_id']+'/request.json'))
        if checkpoint not in files or len(matches)!=1:
            raise ValueError('Missing original checkpoint/request: '+task)
        original=json.loads(matches[0].read_text()); cached=json.loads((directory/checkpoint).read_text())
        if (original['dependency'] != call['dependency'] or original['task_id'] != task
                or fingerprint(dict(system=original['system'],user=original['user'])) != call['request_fingerprint']
                or cached['call_id'] != call['call_id']):
            raise ValueError('Original call binding mismatch: '+task)
        # The source code is recorded by the attempt's initial provenance and
        # any prior verified recovery; dependency equality is checked on replay.
        code = codes[-1] if task.startswith('extract.') and prior else RELATION_ORIGIN
        upstream[task]=dict(checkpoint=checkpoint,request=str(matches[0].relative_to(directory)),code=code)
    backup_dir=Path(RELATION_RECORD).parent
    backups={str(backup_dir/'state-before.json'):before,
             str(backup_dir/'config-before.json'):(directory/'config.json').read_bytes()}
    if (directory/'snapshot.json').exists():
        backups[str(backup_dir/'snapshot-before.json')]=(directory/'snapshot.json').read_bytes()
    files.update({name:sha256(data) for name,data in backups.items()})
    record=dict(kind='relation-context-v1',created_at=now(),from_code=RELATION_ORIGIN,to_code=code_identity(),
        input_sha256=state['input_sha256'], previous_config=state['config'], config=config, files=files,
        previous_recovery=prior,upstream=upstream,
        relation_validation={k:v for k,v in state['validation_attempts'].items() if k.startswith('relate.')},
        original_calls=len(state['calls']),original_reads=len(state['reads']),
        reason='Reuse completed extraction/organization; repack unfinished relation tasks with approved headroom. Unfulfilled old read requests remain in the prior state; reads are selected again under the revised task.')
    if (directory/RELATION_RECORD).exists():
        existing=json.loads((directory/RELATION_RECORD).read_text())
        if {k:v for k,v in existing.items() if k!='created_at'} != {k:v for k,v in record.items() if k!='created_at'}:
            raise ValueError('Existing relation preparation differs')
        record=existing
    entry=dict(record=RELATION_RECORD,sha256=sha256(json_bytes(record)))
    migrated=deepcopy(state); migrated.update(code_sha256=code_identity(),config=config,compatible_recovery=entry)
    with tempfile.TemporaryDirectory(prefix='finmy-relation-replay-') as temp:
        clone=Path(temp)/directory.name
        for name in files:
            q=clone/name; q.parent.mkdir(parents=True,exist_ok=True)
            if name in backups:q.write_bytes(backups[name])
            else:shutil.copyfile(directory/name,q)
        write_json(clone/RELATION_RECORD,record);write_json(clone/'state.json',migrated)
        seen=[]
        def stop_at_relations(system,user,task):
            seen.append(task)
            raise PauseRequested('Offline relation recovery verification; no model invoked')
        checked=run_event(json.loads((clone/'input.json').read_text()),clone,config,model=stop_at_relations,resume=True)
        if seen!=['relate.0'] or checked['execution_status']!='paused':
            raise ValueError('Replay did not reach relations without upstream calls: '+str(seen))
        if checked['facts_sha256']!=state['facts_sha256'] or checked['graph_sha256']!=state['graph_sha256']:
            raise ValueError('Recovery replay changed adopted facts/organization')
    publish_immutable(directory, {**backups, RELATION_RECORD: json_bytes(record)})
    write_json(directory/'state.json',migrated)
    write_json(directory/'config.json',config)
    return entry



def compatible_output_code():
    manifest = code_manifest()
    manifest['person_epg/event/recovery.py'] = OUTPUT_PREVIOUS
    return fingerprint(manifest) == OUTPUT_ORIGIN


def compatible_output_workbench(old):
    from finmy.workbench.build_tasks import ROOT
    from finmy.workbench.domain import digest
    files = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sorted((ROOT/'finmy').rglob('*.py'))}
    files['finmy/person_epg/event/recovery.py'] = OUTPUT_PREVIOUS
    files['finmy/workbench/build_tasks.py'] = OUTPUT_WORKBENCH
    return digest(files) == old['python_sources_sha256'] and compatible_output_code()


def validate_output_recovery(directory, state):
    from finmy.dataset import within
    directory = Path(directory)
    entry = state['compatible_recovery']
    path = within(directory, entry['record'])
    if entry['record'] != OUTPUT_RECORD or sha256(path.read_bytes()) != entry['sha256']:
        raise ValueError('Output recovery record integrity mismatch')
    record = json.loads(path.read_text())
    if (record['from_code'] != OUTPUT_ORIGIN or record['to_code'] != code_identity()
            or not compatible_output_code()):
        raise ValueError('Unsupported output recovery implementation')
    if (state['input_sha256'] != record['input_sha256']
            or semantic_config(EventBuildConfig(**state['config'])) != semantic_config(EventBuildConfig(**record['config']))):
        raise ValueError('Output recovery input or settings changed')
    for name, digest in record['files'].items():
        if sha256(within(directory, name).read_bytes()) != digest:
            raise ValueError('Output recovery source changed: '+name)
    return record


def import_output_checkpoint(execution, task_id, system, request, package, dependency, target, validator, group):
    record = validate_output_recovery(execution.directory, execution.state)
    previous = json.loads((execution.directory/record['state_before']).read_text())
    old_dependency = fingerprint(dict(system=system, request=request, package=package,
        config=semantic_config(EventBuildConfig(**record['previous_config'])), code=record['from_code']))
    old_key = task_id + '-' + old_dependency[:16]
    new_key = task_id + '-' + dependency[:16]
    # An output-cap increase does not erase delivered reads or per-task attempts.
    if old_key in previous['tasks'] and new_key not in execution.state['tasks']:
        execution.state['tasks'][new_key] = deepcopy(previous['tasks'][old_key])
    group_name = (group or new_key).rsplit('-', 1)[0]
    budget = execution.state['validation_attempts'].setdefault(group or new_key, {})
    for name, spent in previous.get('validation_attempts', {}).items():
        if name.rsplit('-', 1)[0] == group_name:
            for key, value in spent.items():
                budget.setdefault(key, deepcopy(value))
    saved = record['upstream'].get(task_id)
    if saved is None:
        if task_id == record['resume_task'] and old_dependency != previous['calls'][-1]['dependency']:
            raise ValueError('Unfinished task dependencies changed')
        return
    cached = json.loads((execution.directory/saved['checkpoint']).read_text())
    original = json.loads((execution.directory/saved['request']).read_text())
    if (system != original['system'] or request != original['user']['task']
            or old_dependency != cached['dependency']
            or cached['response_sha256'] != sha256(json_bytes(cached['response']))):
        raise ValueError('Output recovery checkpoint dependencies changed: '+task_id)
    if not any(c['call_id'] == cached['call_id'] and c['dependency'] == old_dependency and c['status'] == 'accepted'
               for c in execution.state['calls']):
        raise ValueError('Output recovery checkpoint lacks an accepted call')
    validator(cached['response'])
    write_json(target, dict(cached, dependency=dependency, imported_from=dict(path=saved['checkpoint'],
        sha256=record['files'][saved['checkpoint']], recovery=OUTPUT_RECORD)))


def prepare_output_recovery(directory, *, max_new_tokens):
    """Raise only a truncated run's output cap after exact, offline upstream replay."""
    from .build import run_event
    directory = Path(directory)
    state = json.loads((directory/'state.json').read_text())
    if state.get('compatible_recovery', {}).get('record') == OUTPUT_RECORD:
        record = validate_output_recovery(directory, state)
        if record['config']['max_new_tokens'] != max_new_tokens:
            raise ValueError('An existing output recovery has a different approved limit')
        write_json(directory/'config.json', state['config'])
        return state['compatible_recovery']
    if state.get('compatible_recovery') or not compatible_output_code() or state['code_sha256'] != OUTPUT_ORIGIN:
        raise ValueError('Output recovery requires the verified preceding implementation without another migration')
    last = state['calls'][-1] if state['calls'] else {}
    if (state['execution_status'] != 'failed' or state.get('offline_revisions')
            or last.get('status') != 'incomplete' or last.get('transport', {}).get('finish_reason') != 'length'):
        raise ValueError('Choose an unedited run stopped by output truncation')
    if type(max_new_tokens) is not int or max_new_tokens <= state['config']['max_new_tokens']:
        raise ValueError('The approved output limit must increase')
    config = dict(state['config'], max_new_tokens=max_new_tokens)
    EventBuildConfig(**config)
    before = (directory/'state.json').read_bytes()
    files = {str(f.relative_to(directory)):sha256(f.read_bytes())
        for name in ('attempts', 'checkpoints') for f in (directory/name).rglob('*') if f.is_file()}
    for name, key in [('input.json','input_sha256'), ('provenance.json','provenance_sha256')]:
        if sha256((directory/name).read_bytes()) != state[key]:
            raise ValueError('Frozen artifact changed: '+name)
        files[name] = state[key]
    for name, key in [('facts','facts_sha256'), ('output','graph_sha256'), ('checks','checks_sha256')]:
        if state.get(name) and files.get(state[name]) != state.get(key):
            raise ValueError('Saved artifact changed: '+name)
    upstream = {}
    for call in state['calls']:
        if call['status'] != 'accepted':
            continue
        task = call['task_id']
        checkpoint = 'checkpoints/'+task+'-'+call['dependency'][:16]+'.json'
        requests = list((directory/'attempts').glob('*/steps/'+call['call_id']+'/request.json'))
        if task in upstream or checkpoint not in files or len(requests) != 1:
            raise ValueError('Missing or ambiguous accepted checkpoint: '+task)
        original = json.loads(requests[0].read_text())
        cached = json.loads((directory/checkpoint).read_text())
        if (original['dependency'] != call['dependency'] or original['task_id'] != task
                or fingerprint(dict(system=original['system'], user=original['user'])) != call['request_fingerprint']
                or cached['task_id'] != task or cached['dependency'] != call['dependency']
                or cached['call_id'] != call['call_id']
                or cached['response_sha256'] != sha256(json_bytes(cached['response']))):
            raise ValueError('Original call/checkpoint binding mismatch: '+task)
        upstream[task] = dict(checkpoint=checkpoint, request=str(requests[0].relative_to(directory)))
    base = Path(OUTPUT_RECORD).parent
    backups = {str(base/'state-before.json'):before,
               str(base/'config-before.json'):(directory/'config.json').read_bytes()}
    if (directory/'snapshot.json').exists():
        backups[str(base/'snapshot-before.json')] = (directory/'snapshot.json').read_bytes()
    files.update({name:sha256(data) for name,data in backups.items()})
    record = dict(kind='output-limit-v1', created_at=now(), from_code=OUTPUT_ORIGIN, to_code=code_identity(),
        input_sha256=state['input_sha256'], previous_config=state['config'], config=config, files=files,
        state_before=str(base/'state-before.json'), upstream=upstream, resume_task=last['task_id'],
        original_calls=len(state['calls']), original_reads=len(state['reads']),
        reason='Raise approved output ceiling; reuse complete accepted work and retain truncated attempts.')
    if (directory/OUTPUT_RECORD).exists():
        existing = json.loads((directory/OUTPUT_RECORD).read_text())
        if {k:v for k,v in existing.items() if k!='created_at'} != {k:v for k,v in record.items() if k!='created_at'}:
            raise ValueError('Existing output preparation differs')
        record = existing
    entry = dict(record=OUTPUT_RECORD, sha256=sha256(json_bytes(record)))
    migrated = deepcopy(state)
    migrated.update(config=config, code_sha256=code_identity(), compatible_recovery=entry)
    with tempfile.TemporaryDirectory(prefix='finmy-output-replay-') as temp:
        clone = Path(temp)/directory.name
        for name in files:
            path = clone/name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name in backups:
                path.write_bytes(backups[name])
            else:
                shutil.copyfile(directory/name, path)
        write_json(clone/OUTPUT_RECORD, record)
        write_json(clone/'state.json', migrated)
        seen = []
        def stop_at_unfinished(system, user, task):
            seen.append(task)
            raise PauseRequested('Offline output recovery verification; no model invoked')
        checked = run_event(json.loads((clone/'input.json').read_text()), clone, config,
                            model=stop_at_unfinished, resume=True)
        if seen != [record['resume_task']] or checked['execution_status'] != 'paused':
            raise ValueError('Replay did not reach the unfinished task without upstream calls: '+str(seen))
        if any(checked.get(k) != state.get(k) for k in ('facts_sha256', 'graph_sha256')):
            raise ValueError('Output recovery changed adopted facts or organization')
    publish_immutable(directory, {**backups, OUTPUT_RECORD:json_bytes(record)})
    write_json(directory/'state.json', migrated)
    write_json(directory/'config.json', config)
    return entry


def main():
    import argparse
    from finmy.workbench.store import Store
    from finmy.workbench.build_tasks import BuildController
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbench-root',required=True)
    parser.add_argument('--task',required=True)
    args=parser.parse_args()
    result=BuildController(Store(args.workbench_root)).prepare_person_read_recovery(args.task)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
