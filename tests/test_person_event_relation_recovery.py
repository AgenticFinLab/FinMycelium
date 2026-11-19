"""Relation headroom, complete ownership and audited offline checkpoint recovery."""
from copy import deepcopy
import json
import socket
from types import SimpleNamespace
import pytest

from test_person_event_contract import payload, graph
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event import recovery, runtime
from finmy.person_epg.event.build import Construction, run_event
from finmy.person_epg.event.context import sized_request
from finmy.person_epg.event.prompts import system_prompt
from finmy.person_epg.event.records import prompt_json, json_bytes
from finmy.person_epg.event.runtime import EventBuildConfig, LimitReached


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No network'))


def test_relation_index_does_not_repeat_full_assigned_records(graph):
    assigned = dict(actions=graph['actions'][:1], phases=graph['phases'][:1])
    request = sized_request(dict(role='relations', assigned_records=assigned), graph, 100000, 25000)
    assert request['assigned_records'] == assigned
    assert {a['action_id'] for a in request['facts_index']['actions']} == {a['action_id'] for a in graph['actions']}
    owned = next(a for a in request['facts_index']['actions'] if a['action_id']==assigned['actions'][0]['action_id'])
    assert set(owned) <= {'action_id', 'name', 'phase_id'}
    assert len(prompt_json(owned)) < len(prompt_json(assigned['actions'][0]))


def test_relation_batches_use_characters_and_keep_cross_batch_targets(payload, graph):
    graph=deepcopy(graph)
    original=graph['actions'][0]
    graph['actions']=[]
    for i in range(12):
        a=deepcopy(original);a.update(action_id='A'+str(i), name='Action '+str(i), description='evidence-backed detail '*350)
        graph['actions'].append(a)
    execution=SimpleNamespace(payload=payload,config=EventBuildConfig(max_context_chars=60000),state={'id_map':{}})
    builder=Construction(execution);builder.graph=graph
    seen=[]
    def receive(task,role,package,request,**scope):
        size=len(system_prompt(role))+len(prompt_json(dict(task=request,read_results=[])))
        assert size <= 45000
        assert {a['action_id'] for a in request['facts_index']['actions']} == {a['action_id'] for a in graph['actions']}
        seen.append((request,scope))
        return package, []
    def receive_steps(*args, **kwargs):
        if False:
            yield
        return receive(*args, **kwargs)
    builder.receive_steps=receive_steps
    def execute_tasks(stage, tasks):
        for task in tasks:
            try:
                next(task.steps)
            except StopIteration:
                pass
    execution.execute_tasks=execute_tasks
    before=deepcopy(graph)
    builder.relate()
    assert len(seen)>1
    ids=[i for request,_ in seen for i in request['assigned_action_ids']]
    phases=[i for request,_ in seen for i in request['assigned_phase_ids']]
    assert ids == [a['action_id'] for a in graph['actions']]
    assert len(phases)==len(set(phases))==len(graph['phases'])
    assert builder.graph==before
    # A relation from a batch-owned source may point outside that batch.
    assert any(set(r['assigned_action_ids']) < {a['action_id'] for a in r['facts_index']['actions']} for r,_ in seen)


class LimitRelations(SyntheticEventModel):
    def __init__(self):
        super().__init__();self.failed=False
    def __call__(self,system,user,name):
        if name=='relate.0':
            if not self.failed:
                self.failed=True
                return 'invalid json'
            raise LimitReached('model_context_chars')
        return super().__call__(system,user,name)


def stopped_run(path,payload,monkeypatch):
    current=runtime.code_identity
    monkeypatch.setattr(runtime,'code_identity',lambda:recovery.RELATION_ORIGIN)
    with monkeypatch.context() as legacy:
        legacy.setattr(Construction, 'stage', lambda self, name, operation: (operation(), True)[1])
        execute = runtime.Execution.execute_tasks
        def legacy_execute(run, stage, tasks):
            tasks = list(tasks)
            for task in tasks:
                task.on_failure = None
            outcomes = execute(run, stage, tasks)
            for outcome in outcomes.values():
                if outcome.error:
                    raise outcome.error
            return outcomes
        legacy.setattr(runtime.Execution, 'execute_tasks', legacy_execute)
        state=run_event(payload,path,model=LimitRelations())
    assert state['execution_status']=='limit' and state['reason']=='model_context_chars'
    monkeypatch.setattr(runtime,'code_identity',current)
    monkeypatch.setattr(recovery,'compatible_relation_code',lambda:True)
    return state


LIMITS=dict(max_context_chars=240000,max_read_calls=40,max_read_chars=96000)


def test_relation_recovery_replays_upstream_and_preserves_attempts(tmp_path,payload,monkeypatch):
    original=stopped_run(tmp_path,payload,monkeypatch)
    files={p:p.read_bytes() for p in (tmp_path/'attempts').rglob('*') if p.is_file()}
    entry=recovery.prepare_relation_recovery(tmp_path,**LIMITS)
    assert recovery.prepare_relation_recovery(tmp_path,**LIMITS)==entry
    state=json.loads((tmp_path/'state.json').read_text())
    assert state['calls']==original['calls'] and state['reads']==original['reads']
    assert state['final_repair_used']==original['final_repair_used']
    assert state['attempts']==original['attempts']
    model=SyntheticEventModel()
    resumed=run_event(payload,tmp_path,state['config'],model=model,resume=True)
    assert resumed['result_status']=='draft'
    assert model.calls==['relate.0']
    assert resumed['calls'][:len(original['calls'])]==original['calls']
    new_key=next(k for k in resumed['tasks'] if k.startswith('relate.') and k not in original['tasks'])
    assert any(k.startswith('format:') for k in resumed['validation_attempts'][new_key])
    assert all(p.read_bytes()==content for p,content in files.items())


@pytest.mark.parametrize('target',['input','response','request','source_code','settings'])
def test_relation_recovery_refuses_changed_dependencies(tmp_path,payload,monkeypatch,target):
    stopped_run(tmp_path,payload,monkeypatch)
    entry=recovery.prepare_relation_recovery(tmp_path,**LIMITS)
    state=json.loads((tmp_path/'state.json').read_text())
    if target=='input':(tmp_path/'input.json').write_text('{}')
    elif target in ('response','request'):
        next((tmp_path/'attempts').glob('*/steps/*/'+target+'.json')).write_text('{}')
    elif target=='source_code':monkeypatch.setattr(recovery,'compatible_relation_code',lambda:False)
    else:state['config']['extraction_chars']+=1
    with pytest.raises(ValueError):recovery.validate_recovery(tmp_path,state)


def test_workbench_relation_recovery_prepares_without_starting(tmp_path,payload,monkeypatch):
    from finmy.workbench.build_tasks import BuildController, check_person_code
    from finmy.workbench.store import Store
    from finmy.workbench.domain import digest, encoded
    payload=json.loads(encoded(payload))
    directory=tmp_path/'run';original=stopped_run(directory,payload,monkeypatch)
    monkeypatch.setattr(recovery,'compatible_relation_workbench',lambda _:True)
    store=Store(tmp_path/'workspace');controller=BuildController(store)
    body=dict(kind='person_event',artifact_directory=str(directory),code={'commit':'old','python_sources_sha256':'old'},
        person_code='old',input=payload,input_hash=digest(payload),scope_hash=digest(payload['user_query']['extras']['person_event']['scope']),
            person_config=original['config'],graph_schema_version='person-event-2.0')
    with store.connection() as db:db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)',('PBUILD-test','event',encoded(body),'limit','now'))
    first=controller.prepare_person_relation_recovery('PBUILD-test',**LIMITS)
    assert first['model_started'] is False
    assert first==controller.prepare_person_relation_recovery('PBUILD-test',**LIMITS)
    row=controller.inspect('PBUILD-test');assert row['status']=='limit'
    assert len(row['body']['code_history'])==1
    check_person_code(row['body'])
    controller.prepare_person_resume('PBUILD-test')
    row=controller.inspect('PBUILD-test');assert row['status']=='ready'
    controller.save('PBUILD-test','queued',row['body'])
    model=SyntheticEventModel()
    def executor(body,path):
        state=run_event(body['input'],path,body['person_config'],model=model,resume=True)
        return dict(state=state,graph=json.loads((path/state['output']).read_text()))
    controller.run('PBUILD-test',executor=executor)
    assert controller.inspect('PBUILD-test')['status']=='completed'
    assert model.calls==['relate.0']
