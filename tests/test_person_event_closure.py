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


@pytest.fixture
def support_run(partial):
    """Two rejections of a retained Context, one model note and an incompatible Action citation."""
    r = load_review(partial)
    facts, checks, state = r['facts'], r['checks'], r['state']
    context = next(c for c in facts['contexts'] if c['context_id'] == r['graph']['contexts'][0]['context_id'])
    action = next(a for a in facts['actions'] if any(s['mode'] in ('O', 'A') and s['evidence_ids'] for s in a['support']))
    support = next(s for s in action['support'] if s['mode'] in ('O', 'A') and s['evidence_ids'])
    ev = next(e for e in facts['evidence'] if e['evidence_id'] == support['evidence_ids'][0])

    def rejected(collection, oid, reason, item, proposal, issues):
        return dict(refs=[dict(collection=collection, object_id=oid, field='')], evidence_ids=[], reason=reason,
                    item=item, proposal=proposal, issues=issues)

    resubmission = rejected('contexts', context['context_id'], 'Extraction cannot overwrite an existing candidate',
        'candidates:0', [dict(collection='contexts', record=deepcopy(context))], [])
    addition = dict(collection='actions', object_id=action['action_id'], target=support['target'],
                    mode='A' if support['mode'] == 'O' else 'O', reason='Additional citation in a different mode.',
                    sample_id=ev['sample_id'], quote=ev['quote'])
    mixed = rejected('actions', action['action_id'], 'Separate record-content and world-assertion claims.',
        'additional_support.0', addition, [dict(code='SUPPORT_MODE_MIXED', severity='error', object_type='actions',
                                                object_id=action['action_id'])])
    def pending_for(issue):
        return {k: deepcopy(issue[k]) for k in ('refs', 'reason', 'evidence_ids')}

    note = pending_for(resubmission)
    note.update(reason='Check whether the proposed citation belongs on this record.',
                evidence_ids=next(s['evidence_ids'] for s in context['support'] if s['evidence_ids']))
    def task(tid, issue=None):
        return dict(task_id=tid, role='extraction', body_processed=True,
            report=dict(accepted=[], accepted_items=[], rejected=[deepcopy(issue)] if issue else [],
                        pending=[pending_for(issue) if issue else note], reported_pending=[] if issue else [note]))

    facts['pending'] = [pending_for(resubmission), note, pending_for(mixed)]
    checks['unresolved_tasks'] = [task('extract.0', resubmission), task('extract.0.correct.1', resubmission),
                                  task('extract.0.correct.2'), task('whole-corpus.supplement', mixed)]
    state['facts_sha256'] = write_json(partial/state['facts'], facts)
    checks['artifact_hashes']['facts'] = state['facts_sha256']
    state['checks_sha256'] = write_json(partial/state['checks'], checks)
    write_json(partial/'state.json', state)
    return partial


def groups(review):
    from finmy.person_epg.event.closure_support import support_groups
    return support_groups(review, pending_items(review))


def decline(group):
    return dict(key=group['key'], outcome='decline_support_change', reason='Keep the existing attribution and evidence.',
                acknowledged_pending=[m['item']['key'] for m in group['members'] if m.get('reported')])


def test_support_decisions_require_acknowledgement_and_preserve_graph(support_run):
    root = support_run
    old = load_review(root)
    context, action = groups(old)
    assert [len(context['members']), len(action['members'])] == [3, 1]
    assert action['changes'][0]['quote']['location_status'] == 'matched'
    chosen = decline(context)
    with pytest.raises(ValueError, match='逐条确认'):
        close_pending(root, [dict(chosen, acknowledged_pending=[])], expected_state_sha256=old['state_sha256'], reviewer='Test')
    assert load_review(root)['state_sha256'] == old['state_sha256']
    first = close_pending(root, [chosen], expected_state_sha256=old['state_sha256'], reviewer='Test')
    assert first['result_status'] == 'partial'
    next_review = load_review(root)
    assert [i['task_id'] for i in pending_items(next_review)] == ['whole-corpus.supplement']
    with pytest.raises(ValueError, match='更新'):
        close_pending(root, [decline(action)], expected_state_sha256=old['state_sha256'], reviewer='Test')
    result = close_pending(root, [decline(groups(next_review)[0])], expected_state_sha256=next_review['state_sha256'], reviewer='Test')
    assert result['result_status'] == 'draft' and result['review_required']
    assert (root/result['output']).read_bytes() == (root/old['state']['output']).read_bytes()
    assert result['calls'] == old['state']['calls']
    audits = [json.loads((root/a['path']).read_text()) for a in result['offline_revisions']]
    receipts = audits[0]['dispositions'][0]['receipts']
    assert len(receipts) == 3 and receipts[-1]['model_reported']
    assert all(r['rejection_sha256'] for r in receipts[:-1])
    assert audits[0]['parent_state_sha256'] == old['state_sha256']
    assert audits[1]['dispositions'][0]['reviewer'] == 'Test'


@pytest.mark.parametrize('change', ['substantive_edit', 'lost_quote', 'different_mode_error', 'unread', 'unrelated_note'])
def test_unverified_or_unrelated_proposals_stay_pending(support_run, change):
    r = load_review(support_run)
    tasks = r['checks']['unresolved_tasks']
    if change == 'substantive_edit':
        for t in tasks[:2]:
            t['report']['rejected'][0]['proposal'][0]['record']['description'] = 'A different fact.'
    elif change == 'lost_quote':
        tasks[-1]['report']['rejected'][0]['proposal']['quote'] = 'Missing from this input.'
    elif change == 'different_mode_error':
        tasks[-1]['report']['rejected'][0]['issues'][0]['code'] = 'OTHER_VALIDATION_ERROR'
    elif change == 'unread':
        r['state']['coverage'][0]['body_status'] = 'failed'
    elif change == 'unrelated_note':
        for p in (r['facts']['pending'][1], tasks[2]['report']['pending'][0], tasks[2]['report']['reported_pending'][0]):
            p['evidence_ids'] = ['unrelated']
    available = {g['kind']: len(g['members']) for g in groups(r)}
    if change in ('lost_quote', 'different_mode_error'):
        assert available == {'repeated_candidate': 3}
    elif change == 'unrelated_note':
        assert available == {'repeated_candidate': 2, 'mixed_support': 1}
    else:
        assert available == {'mixed_support': 1}
    assert len(pending_items(r)) == 4


def test_review_form_saves_successive_decisions(support_run, tmp_path):
    from streamlit.testing.v1 import AppTest
    from finmy.workbench.store import Store
    from finmy.workbench.build_tasks import BuildController

    workspace = tmp_path/'workspace'
    store = Store(workspace)
    tid = 'PBUILD-ui'
    controller = BuildController(store)
    (controller.root/tid).mkdir(parents=True)
    body = dict(kind='person_event', artifact_directory=str(support_run),
                run_state=load_review(support_run)['state'])
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)', (tid, 'test', json.dumps(body), 'partial', 'now'))

    app = AppTest.from_string(
        'from finmy.workbench.store import Store\nfrom finmy.workbench.build_tasks import BuildController\n'
        'from finmy.workbench.closure_page import closure_panel\n'
        f'controller = BuildController(Store({str(workspace)!r}))\nclosure_panel(controller, controller.inspect({tid!r}))'
    ).run(timeout=20)
    assert not app.exception and len(app.selectbox[0].options) == 2
    assert len(app.get('download_button')) == 1
    for remaining in (1, 0):
        assert len(app.checkbox) == remaining + 1
        for widget in app.checkbox:
            widget.check()
        app.text_area[0].set_value('Retain the existing evidence.')
        app.text_input[0].set_value('Test')
        next(b for b in app.button if b.label == '保存处置并重新检查').click().run(timeout=20)
        assert not app.exception
        assert controller.inspect(tid)['status'] == ('partial' if remaining else 'completed')
    assert any('结构收尾已完成' in message.value for message in app.success)
