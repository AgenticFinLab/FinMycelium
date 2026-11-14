"""Progressive assembly preserves earlier evidence and immutable handoffs."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.search import budget
from finmy.search.control import SearchController
from finmy.search.handoff import prepare_complete_sources, derive_input, assemble_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network allowed'))


def materials(tmp_path):
    state=SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Aster acquisition',
                     query_text='Aster acquisition approval', key_words=['approval','closing']))
    store=SourceStore(state);ids=[]
    paragraphs=['Opening notice.', 'Aster acquisition approval was conditional.',
                'Conditions require divestment before closing.'] + [
                'Retail discounts and parking. '*50+str(i) for i in range(20)]
    for i,text in enumerate(['\n\n'.join(paragraphs), 'Closing awaits approval.']):
        sid=store.register('https://example.org/'+str(i));store.save_raw(sid,text.encode(),'txt');store.read(sid);ids.append(sid)
    _,complete=prepare_complete_sources(state,ids)
    return state,complete


@pytest.mark.parametrize('limit',[1,800,8000,60000])
def test_progressive_keeps_first_pass_and_original_blocks(tmp_path,limit):
    state,complete=materials(tmp_path)
    payload,record=derive_input(state,complete,max_chars=limit)
    assert record['material_chars']==sum(len(s['content']) for s in payload['samples'])<=limit
    allocation=record['allocation']
    assert allocation['thresholds']==[.5,.4,.3]
    if complete['material_chars']<=limit:
        assert allocation['full_material_retained'] and not record['omitted']
    else:
        stages=allocation['threshold_stages']
        _,fixed=derive_input(state,complete,max_chars=limit,allocation_policy=budget.FIXED_POLICY)
        first={e['source_id']:e['blocks'] for e in fixed['selected']}
        assert {sid:blocks for sid,blocks in stages[0]['selected_blocks'].items() if blocks}==first
        for before,after in zip(stages,stages[1:]):
            assert all(set(blocks)<=set(after['selected_blocks'][sid]) for sid,blocks in before['selected_blocks'].items())
        assert stages[-1]['material_chars']==record['material_chars']
        assert stages[-1]['threshold']==.3
    entries={e['source_id']:e for e in complete['selected']}
    for entry,sample in zip(record['selected'],payload['samples']):
        sid=entry['source_id'];doc=SourceStore(state).document(sid,entry['version'])
        assert entry['blocks']==sorted(set(entry['blocks']))
        assert sample['content']==budget.render(entries[sid],doc,entry['blocks'],markers=len(entry['blocks'])<len(entries[sid]['blocks']))
    assert derive_input(state,complete,max_chars=limit)==(payload,record)
    reverse=deepcopy(complete);reverse['selected'].reverse();reverse['source_ids'].reverse()
    reverse.pop('complete_id');reverse['complete_id']=digest(reverse)
    _,reordered=derive_input(state,reverse,max_chars=limit)
    assert {e['source_id']:e['blocks'] for e in reordered['selected']}=={e['source_id']:e['blocks'] for e in record['selected']}


def test_assembly_thresholds_do_not_change_reading(tmp_path,monkeypatch):
    state,complete=materials(tmp_path)
    import finmy.search.reading as reading
    # Reading's default stays independent of explicitly selected assembly thresholds.
    assert reading.MIN_RELATIVE_SCORE==budget.MIN_RELATIVE_SCORE==.4
    before=derive_input(state,complete,max_chars=8000)
    monkeypatch.setattr(budget,'MIN_RELATIVE_SCORE',.9)
    assert derive_input(state,complete,max_chars=8000)==before
    assert derive_input(state,complete,max_chars=8000,allocation_policy=budget.FIXED_POLICY)[1]['allocation']['min_relative_score']==.5


def test_reassemble_upgrades_policy_without_overwriting_sources_or_revision(tmp_path):
    state,complete=materials(tmp_path)
    complete['budget_policy']=budget.FIXED_POLICY
    complete.pop('complete_id');complete['complete_id']=digest(complete)
    old_payload=assemble_sources(state,complete['source_ids'],complete_manifest=complete,max_chars=8000)
    old_revision=state.data['handoff_revision'];old_folder=state.run_dir/'handoffs'/old_revision
    old_files={p:p.read_bytes() for base in [old_folder,state.root/'sources'] for p in base.rglob('*') if p.is_file()}
    state.data.update(status='finished');state.save()
    usage=deepcopy(state.data['usage'])
    controller=SearchController(tmp_path)
    payload=controller.reassemble('case',8000);data=controller.inspect('case')
    assert data['handoff_revision']!=old_revision
    assert data['usage']==usage
    assert data['complete_material']==complete
    assert data['selection']['budget_policy']==budget.BUDGET_POLICY
    assert len(data['selection']['assembly_code_sha256'])==64
    assert {p:p.read_bytes() for p in old_files}==old_files
    assert derive_input(state,complete,max_chars=8000)[0]==old_payload
    assert derive_input(state,complete,max_chars=8000,allocation_policy=budget.BUDGET_POLICY)[0]==payload
    trace=[json.loads(line) for line in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    assert trace[-1]['action']=='handoff_reassembled'
    assert trace[-1]['previous_revision']==old_revision
