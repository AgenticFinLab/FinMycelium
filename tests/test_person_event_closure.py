"""Offline artifact and controller tests; all fixtures stay in pytest tmp_path."""
from copy import deepcopy
import json
import socket

import pytest
from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.closure import load_review, pending_items, close_pending
from finmy.person_epg.event.runtime import write_json
from finmy.person_epg.rendering import read_gantt


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network prohibited'))


@pytest.fixture
def partial(tmp_path, payload):
    root=tmp_path/'run'; state=run_event(payload, root, model=SyntheticEventModel())
    graph=json.loads((root/state['output']).read_text()); facts=json.loads((root/state['facts']).read_text())
    checks=json.loads((root/state['checks']).read_text())
    context=next(c for c in graph['contexts'] if any(s['evidence_ids'] for s in c['support']))
    facts['contexts'].append(deepcopy(context))
    for evidence in graph['evidence']:
        if evidence['evidence_id'] not in {e['evidence_id'] for e in facts['evidence']}:
            facts['evidence'].append(deepcopy(evidence))
    pending=dict(refs=[dict(collection='event',object_id=graph['event']['event_id'],field='/actions')],
        reason='Corporate conduct is documented but the focal person participation is unknown.',
        evidence_ids=next(s['evidence_ids'] for s in context['support'] if s['evidence_ids']))
    facts['pending']=[pending]
    report=dict(accepted=['candidates:0'],accepted_items=[dict(item='candidates:0',refs=[dict(
        collection='contexts',object_id=context['context_id'],field='')])],rejected=[],pending=[pending],reported_pending=[pending])
    checks['unresolved_tasks']=[dict(task_id='extract.0',role='extraction',body_processed=True,report=report)]
    checks['result_status']='partial';state['result_status']='partial'
    state['coverage'][0].update(status='partial',proposal_status='unresolved')
    checks['coverage']=deepcopy(state['coverage'])
    state['facts_sha256']=write_json(root/state['facts'],facts)
    checks['artifact_hashes']['facts']=state['facts_sha256']
    state['checks_sha256']=write_json(root/state['checks'],checks)
    write_json(root/'state.json',state)
    return root


def decision(review):
    item=pending_items(review)[0]
    return dict(key=item['key'],context_id=item['context_ids'][0],
                reason='Retain the supported corporate conduct. Individual participation is unknown in this corpus, not disproved.')


def test_offline_successor_preserves_history_and_evidence(partial):
    review=load_review(partial);before=deepcopy(review['state'])
    original={p:p.read_bytes() for p in partial.rglob('*') if p.is_file()}
    state=close_pending(partial,[decision(review)],expected_state_sha256=review['state_sha256'],reviewer='Reviewer')
    assert state['result_status']=='draft'
    for k in ('calls','reads','attempts','code_sha256','finished_at','config'):
        assert state[k]==before[k]
    after=load_review(partial)
    for k in ('actions','sources','evidence','stages','phases','relations'):
        assert after['graph'][k]==review['graph'][k]
    assert not after['facts']['pending'] and not after['checks']['unresolved_tasks']
    assert after['checks']['review_required']
    assert after['checks']['summary']['errors']==0
    for path,data in original.items():
        if path.name!='state.json': assert path.read_bytes()==data
    assert (partial/state['offline_revisions'][-1]['parent_state']).read_bytes()==original[partial/'state.json']
    assert 'Draft' in read_gantt(partial,state)
    with pytest.raises(ValueError,match='更新'):
        close_pending(partial,[decision(review)],expected_state_sha256=review['state_sha256'],reviewer='Reviewer')


def test_disposing_upstream_pending_preserves_independent_uncertainty(partial, tmp_path):
    from finmy.person_epg.event.semantic_review import review_relations

    original = load_review(partial)
    graph = original['graph']
    def review_model(system, user, task):
        if task == 'review.discover':
            return {'pairs': []}
        return dict(existing=[dict(relation_id=r['relation_id'], decision='uncertain',
            evidence_ids=[graph['evidence'][0]['evidence_id']], reason='The link needs content review.')
            for r in graph['relations']], additions=[], context_findings=[])

    output = tmp_path / 'review'
    review_relations(partial, output, model=review_model)
    reviewed = load_review(output)
    assert reviewed['facts']['pending'] == original['facts']['pending']
    assert not reviewed['semantic_review']['complete']
    state = close_pending(output, [decision(reviewed)], expected_state_sha256=reviewed['state_sha256'],
                          reviewer='Reviewer')
    assert state['result_status'] == 'partial'
    after = load_review(output)
    assert not after['facts']['pending'] and not after['checks']['unresolved_tasks']
    assert after['semantic_review'] == reviewed['semantic_review']


@pytest.mark.parametrize('kind',['rejected','unprocessed','action_assignment','no_evidence','wrong_context'])
def test_cannot_clear_unfinished_or_unrelated_work(partial,kind):
    review=load_review(partial);chosen=decision(review);state=review['state'];checks=review['checks']
    task=checks['unresolved_tasks'][0]
    if kind=='rejected': task['report']['rejected']=[dict(reason='Invalid proposal')]
    if kind=='unprocessed': task['body_processed']=False
    if kind=='action_assignment':
        task['report']['pending'][0]['refs']=[dict(collection='actions',object_id=review['graph']['actions'][0]['action_id'],field='/phase_id')]
    if kind=='no_evidence': task['report']['pending'][0]['evidence_ids']=[]
    if kind=='wrong_context': chosen['context_id']='NONEXISTENT'
    state['checks_sha256']=write_json(partial/state['checks'],checks);write_json(partial/'state.json',state)
    current=load_review(partial)
    with pytest.raises(ValueError):
        close_pending(partial,[chosen],expected_state_sha256=current['state_sha256'],reviewer='Reviewer')
    assert not (partial/'revisions').exists()


@pytest.mark.parametrize('kind',['unread_body','another_pending','invalid_graph','incomplete_relation_review'])
def test_remaining_problems_keep_partial(partial,kind):
    r=load_review(partial);s=r['state'];checks=r['checks'];facts=r['facts']
    if kind=='unread_body': s['coverage'][-1]['body_status']='failed'
    if kind=='another_pending': facts['pending'].append(dict(refs=[],reason='Unprocessed independent work',evidence_ids=[]))
    if kind=='incomplete_relation_review':
        discovery=r['discovery']
        discovery['incomplete_action_ids'].append(discovery['completed_action_ids'].pop())
        s['relation_discovery_sha256']=write_json(partial/s['relation_discovery'],discovery)
    if kind=='invalid_graph':
        r['graph']['actions'][0]['phase_id']='MISSING'
        s['graph_sha256']=write_json(partial/s['output'],r['graph'])
    s['facts_sha256']=write_json(partial/s['facts'],facts)
    checks['artifact_hashes']['facts']=s['facts_sha256'];checks['graph_sha256']=s['graph_sha256']
    s['checks_sha256']=write_json(partial/s['checks'],checks);write_json(partial/'state.json',s)
    r=load_review(partial)
    result=close_pending(partial,[decision(r)],expected_state_sha256=r['state_sha256'],reviewer='Reviewer')
    assert result['result_status']=='partial'


def test_controller_persists_result_without_changing_usage(partial,tmp_path):
    from finmy.workbench.store import Store
    from finmy.workbench.build_tasks import BuildController
    store=Store(tmp_path/'workspace');controller=BuildController(store);tid='PBUILD-test'
    (controller.root/tid).mkdir(parents=True)
    r=load_review(partial)
    body=dict(kind='person_event',artifact_directory=str(partial),run_state=r['state'],usage=['keep'],finished='keep')
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)',(tid,'event',json.dumps(body),'partial','now'))
    controller.close_person_pending(tid,[decision(r)],expected_state_sha256=r['state_sha256'],reviewer='Reviewer')
    saved=controller.inspect(tid)
    assert saved['status']=='completed'
    assert saved['body']['usage']==['keep'] and saved['body']['finished']=='keep'
    assert saved['body']['run_state']==load_review(partial)['state']
    controller.save(tid, 'partial', saved['body'])
    with pytest.raises(ValueError, match='人工收尾修订'):
        controller.prepare_person_resume(tid)


def test_mismatched_check_binding_is_blocked(partial):
    r=load_review(partial); s=r['state'];checks=r['checks']
    checks['graph_sha256']='wrong'
    s['checks_sha256']=write_json(partial/s['checks'],checks);write_json(partial/'state.json',s)
    with pytest.raises(ValueError,match='不一致'):
        load_review(partial)
