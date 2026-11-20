"""Bounded record delivery and explicit offline repair migration."""
import json
import socket
from copy import deepcopy
import pytest
from test_person_event_contract import payload
from test_person_event_runtime import Model, valid
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event import runtime, recovery
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.records import seed_facts, json_bytes
from finmy.person_epg.event.runtime import Corpus, Execution, EventBuildConfig, LimitReached

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('No network'))

def records(payload):
    p=seed_facts(payload)
    p['contexts']=[dict(context_id='C'+str(i),description='x'*100) for i in range(3)]
    refs=[dict(collection='contexts',object_id=x['context_id'],field='/description') for x in p['contexts']]
    return p,dict(tool='read_records',refs=refs)

def test_whole_refs_split_without_extra_model_turns(tmp_path,payload):
    p,read=records(payload); cfg=EventBuildConfig(read_chars=300)
    pages=Corpus(payload,p,cfg).pages(read)
    assert len(pages)==3
    assert [r for request,_ in pages for r in request['refs']]==read['refs']
    assert all(len(json_bytes(result).decode())<=300 for _,result in pages)
    model=Model([{'read_requests':[read]},{'ok':True}])
    run=Execution(tmp_path,payload,cfg,model)
    run.infer('organize','contract',{},p,valid)
    assert len(run.state['calls'])==2 and len(run.state['reads'])==3
    assert sum(x['chars'] for x in run.state['reads'])==sum(len(json_bytes(result).decode()) for _,result in pages)
    assert len(model.calls[-1]['read_results'])==3
    assert not any(run.state['validation_attempts'].values())

@pytest.mark.parametrize('limit',['calls','chars','context'])
def test_partial_delivery_keeps_budget_and_pending_refs(tmp_path,payload,limit):
    p,read=records(payload)
    cfg=EventBuildConfig(read_chars=300,max_read_calls=2 if limit=='calls' else 24,
        max_read_chars=550 if limit=='chars' else 48000,max_context_chars=700 if limit=='context' else 160000)
    run=Execution(tmp_path,payload,cfg,Model([{'read_requests':[read]}]))
    with pytest.raises(LimitReached):run.infer('organize','contract',{},p,valid)
    task=next(iter(run.state['tasks'].values()))
    assert task['read_delivery']['status']=='limited'
    assert task['read_delivery']['remaining_requests']
    assert len(run.state['reads'])<=cfg.max_read_calls
    assert sum(x['chars'] for x in run.state['reads'])<=cfg.max_read_chars
    assert not any(run.state['validation_attempts'].values())

def test_oversized_field_reports_exact_ref_and_children(payload):
    p,read=records(payload);p['contexts'][0]['support']=[{'reason':'x'*500}]
    read['refs']=[dict(collection='contexts',object_id='C0',field='/support')]
    with pytest.raises(ValueError) as e:Corpus(payload,p,EventBuildConfig(read_chars=300)).pages(read)
    for text in ('C0','/support','/support/0','requested_chars','300'):assert text in str(e.value)

class FailOrganization(SyntheticEventModel):
    def __call__(self,system,user,name):
        if name=='organize':return 'invalid'
        return super().__call__(system,user,name)

def old_run(tmp_path,payload,monkeypatch):
    actual=runtime.code_identity
    monkeypatch.setattr(runtime,'code_identity',lambda:recovery.ORIGIN)
    from finmy.person_epg.event.build import Construction
    with monkeypatch.context() as legacy:
        # Reproduce the legacy global-failure boundary, without new stage snapshots.
        legacy.setattr(Construction, 'stage', lambda self, name, operation: (operation(), True)[1])
        state=run_event(payload,tmp_path,{'full_corpus_supplement': False},model=FailOrganization())
    assert state['execution_status']=='failed'
    monkeypatch.setattr(runtime,'code_identity',actual)
    monkeypatch.setattr(recovery,'compatible_code',lambda:True)
    return state

def test_migration_reuses_extraction_preserves_failed_attempt_and_usage(tmp_path,payload,monkeypatch):
    old=old_run(tmp_path,payload,monkeypatch)
    originals={p:p.read_bytes() for p in (tmp_path/'attempts/0001').rglob('*') if p.is_file()}
    entry=recovery.prepare_record_recovery(tmp_path)
    assert recovery.prepare_record_recovery(tmp_path)==entry
    state=json.loads((tmp_path/'state.json').read_text())
    assert state['calls']==old['calls'] and state['reads']==old['reads']
    model=SyntheticEventModel()
    resumed=run_event(payload,tmp_path,model=model,resume=True)
    assert resumed['result_status']=='draft'
    assert not any(n.startswith('extract.') for n in model.calls)
    assert resumed['calls'][:len(old['calls'])]==old['calls']
    assert originals=={p:p.read_bytes() for p in originals}

@pytest.mark.parametrize('target',['input','checkpoint','record'])
def test_recovery_rejects_changed_sources(tmp_path,payload,monkeypatch,target):
    old_run(tmp_path,payload,monkeypatch)
    if target=='input':
        (tmp_path/'input.json').write_text('{}')
        with pytest.raises(ValueError):recovery.prepare_record_recovery(tmp_path)
    else:
        recovery.prepare_record_recovery(tmp_path)
        path=next((tmp_path/'checkpoints').glob('*.json')) if target=='checkpoint' else tmp_path/recovery.RECORD
        path.write_text('{}')
        with pytest.raises(ValueError):run_event(payload,tmp_path,model=Model([]),resume=True)


def test_interrupted_migration_can_retry_without_replacing_provenance(tmp_path, payload, monkeypatch):
    old = old_run(tmp_path, payload, monkeypatch)
    write = recovery.write_json
    def interrupted(path, value):
        if path == tmp_path/'state.json':
            raise OSError('Simulated interruption before state publication')
        return write(path, value)
    monkeypatch.setattr(recovery, 'write_json', interrupted)
    with pytest.raises(OSError):
        recovery.prepare_record_recovery(tmp_path)
    manifest = (tmp_path/recovery.RECORD).read_bytes()
    assert json.loads((tmp_path/'state.json').read_text()) == old
    monkeypatch.setattr(recovery, 'write_json', write)
    recovery.prepare_record_recovery(tmp_path)
    assert (tmp_path/recovery.RECORD).read_bytes() == manifest


def test_workbench_prepares_recovery_once_without_starting_worker(tmp_path, payload, monkeypatch):
    from finmy.workbench.build_tasks import BuildController, check_person_code
    from finmy.workbench.store import Store
    from finmy.workbench.domain import encoded, digest
    payload = json.loads(encoded(payload))  # Match the workbench's saved-input ordering.
    directory = tmp_path/'run'
    old = old_run(directory, payload, monkeypatch)
    monkeypatch.setattr(recovery, 'compatible_workbench', lambda code: True)
    store = Store(tmp_path/'workspace')
    controller = BuildController(store)
    body = dict(kind='person_event', artifact_directory=str(directory),
                code={'commit':'old', 'python_sources_sha256':'old'}, person_code=recovery.ORIGIN,
                input=payload, input_hash=digest(payload), scope_hash=digest(payload['user_query']['extras']['person_event']['scope']),
                person_config=old['config'])
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)', ('PBUILD-test','event',encoded(body),'failed','now'))
    first = controller.prepare_person_read_recovery('PBUILD-test')
    assert first == controller.prepare_person_read_recovery('PBUILD-test')
    row = controller.inspect('PBUILD-test')
    assert row['status'] == 'failed' and first['model_started'] is False
    assert len(row['body']['code_history']) == 1
    check_person_code(row['body'])
    changed = deepcopy(row['body'])
    changed['code']['python_sources_sha256'] = 'different'
    with pytest.raises(ValueError):
        check_person_code(changed)
    # A subsequent commit of identical Python bytes must not block this recorded migration.
    changed = deepcopy(row['body'])
    changed['code']['commit'] = 'different-commit-label'
    check_person_code(changed)

    # Exercise the worker's code check, not just the preparation entry point.
    controller.save('PBUILD-test', 'failed', changed)
    controller.prepare_person_resume('PBUILD-test')
    queued = controller.inspect('PBUILD-test')['body']
    controller.save('PBUILD-test', 'queued', queued)
    model = SyntheticEventModel()
    def execute(body, path):
        try:
            state = run_event(body['input'], path, body['person_config'], model=model, resume=True)
        except Exception as exc:
            pytest.fail(str(exc))
        return dict(state=state, graph=json.loads((path/state['output']).read_text()))
    controller.run('PBUILD-test', executor=execute)
    done = controller.inspect('PBUILD-test')
    assert done['status'] == 'completed', done['body'].get('error_type')
    assert not any(name.startswith('extract.') for name in model.calls)
    assert done['body']['run_state']['calls'][:len(old['calls'])] == old['calls']
