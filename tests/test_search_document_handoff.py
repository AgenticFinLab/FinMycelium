"""Whole-source handoff, provenance, budget and legacy compatibility; entirely offline."""
import json
import socket
from pathlib import Path
import pytest
from finmy.search.state import SearchState, SearchConfig
from finmy.search.sources import SourceStore
from finmy.search.handoff import prepare_sources, assemble_sources
from finmy.search.agent import execute_action, context_for, run_agent, SYSTEM_PROMPT
from finmy.search.tools import SearchTools
from finmy.search.control import SearchController

TASK=dict(target_type='event',target_name='Deal',query_text='Trace proposal, approval and closing')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('Unexpected network'))


def document(state,name,text,read=True,kind='txt'):
    store=SourceStore(state);sid=store.register('https://example.org/'+name,title=name)
    doc=store.save_raw(sid,text.encode(),kind,partial=True)
    if read:store.read(sid)
    return sid,doc


def test_source_choice_keeps_saved_body_not_just_model_excerpt(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK,config=SearchConfig(max_read_chars=8))
    sid,doc=document(state,'announcement','Agreement proposed.\n\nApproval was conditional.\n\nThe deal closed later.')
    execute_action(state,SearchTools(state),dict(action='finish',source_ids=[sid],gaps=[],reason='supported'))
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert len(payload['samples'])==1
    assert all(b['text'] in payload['samples'][0]['content'] for b in doc['blocks'])
    assert set(payload)=={'user_query','samples'}
    from finmy.generic import DataSample,UserQueryInput
    UserQueryInput(**payload['user_query']);DataSample(**payload['samples'][0])
    selection=json.loads((state.run_dir/'selection.json').read_text())
    assert selection['mode']=='sources' and selection['source_versions'][sid]==doc['version']
    assert selection['selected'][0]['source_status']=='partial'
    assert state.data['usage']['model']==0  # Assembly itself needs no inference.


def test_uninspected_and_tampered_documents_rejected(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK)
    sid,doc=document(state,'a','Original body.',read=False)
    with pytest.raises(ValueError,match='Inspect'):prepare_sources(state,[sid])
    SourceStore(state).read(sid)
    (state.root/'sources'/sid/doc['version']/'raw').write_bytes(b'Modified')
    with pytest.raises(ValueError,match='integrity'):prepare_sources(state,[sid])


def test_budget_preserves_sources_and_complete_paragraphs(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK)
    a,da=document(state,'long','\n\n'.join('Approval clause '+str(i)+' '+('X'*180)+'.' for i in range(10)))
    b,db=document(state,'short','Approval not yet granted.')
    from finmy.search.handoff import prepare_complete_sources, derive_input
    _, complete = prepare_complete_sources(state, [b, a])
    payload,record=derive_input(state,complete,max_chars=1500)
    assert sum(len(s['content']) for s in payload['samples'])==record['material_chars']<=1500
    assert any('Approval not yet granted.' in s['content'] for s in payload['samples'])
    selected=next(s for s in record['selected'] if s['source_id']==a)
    omitted=next(s for s in record['omitted'] if s['source_id']==a)
    assert sorted(selected['blocks']+omitted['blocks'])==list(range(10))
    assert not set(selected['blocks']) & set(omitted['blocks'])
    assert [s['raw_data_id'] for s in payload['samples']] == [b, a]
    sample=next(s for s in payload['samples'] if s['raw_data_id']==a)
    assert all(da['blocks'][i]['text'] in sample['content'] for i in selected['blocks'])
    assert record['gaps'] and not (state.run_dir/'builder_input.json').exists()


def test_duplicates_and_conservative_cleanup_are_accounted_for(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK)
    text='Announcement remains subject to regulatory approval. '+('Important condition. '*8)
    a,_=document(state,'a','<nav>Home</nav><p>'+text+'</p><p>'+text+'</p>',kind='html')
    b,_=document(state,'b',text)
    payload,record=prepare_sources(state,[a,b])
    assert len(payload['samples'])==1
    assert payload['samples'][0]['content'].count(text.strip())==1
    assert record['duplicates']==[dict(source_id=b,version=state.data['sources'][b]['version'],duplicate_of=a)]
    assert {r['reason'] for r in record['cleanup']}=={'navigation_label','exact_repeated_paragraph'}


def test_reassembly_recovers_saved_version_and_omissions(tmp_path):
    controller=SearchController(tmp_path);tid=controller.create(TASK,{})
    state=SearchState(tmp_path,tid)
    sid,doc=document(state,'a','Original filing.\n\nClosing was not confirmed.')
    assemble_sources(state,[sid],max_chars=1)
    SourceStore(state).save_raw(sid,b'Later revised text.','txt')
    payload=controller.reassemble(tid,10000)
    assert payload['samples'][0]['content'].endswith('Closing was not confirmed.')
    assert 'Later revised' not in payload['samples'][0]['content']
    assert len(list((state.run_dir/'handoffs').iterdir()))==2


def test_context_pressure_enters_document_finalization_before_call(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK,config=SearchConfig(max_model_calls=30,max_model_context_chars=6000))
    sid,_=document(state,'a','Proposal and conditional approval.')
    state.data['feedback']={'spans':[{'text':'X'*9000}]};state.save()
    assert len(SYSTEM_PROMPT)+len(json.dumps(context_for(state),ensure_ascii=False))>6000
    def model(c):
        assert c['phase']=='finalize' and 'spans' not in c['feedback']
        return dict(action='finish',source_ids=[sid],gaps=[],reason='low_gain')
    run_agent(state,SearchTools(state),model)
    assert state.data['status']=='finished' and state.data['usage']['model']==1


def test_oversized_first_paragraph_does_not_block_other_sources(tmp_path):
    state=SearchState(tmp_path,'case',task=TASK)
    large,_=document(state,'large','Long indivisible block. '*1000)
    small,_=document(state,'small','A separate closing notice.')
    payload,record=prepare_sources(state,[large,small],max_chars=1000)
    assert len(payload['samples'])==1
    assert payload['samples'][0]['raw_data_id']==small
    assert record['omitted'][0]['source_id']==large


def test_complete_material_is_independent_of_input_budget(tmp_path):
    from finmy.search.handoff import prepare_complete_sources,derive_input,materialize_complete
    state=SearchState(tmp_path,'case',task=TASK)
    a,_=document(state,'a','First official announcement.')
    b,_=document(state,'b','Later closing confirmation.')
    full,complete=prepare_complete_sources(state,[a,b])
    small,limited=derive_input(state,complete,max_chars=1)
    large,unlimited=derive_input(state,complete,max_chars=10000)
    assert small['samples']==[] and len(full['samples'])==2
    assert large==full and limited['complete_id']==unlimited['complete_id']==complete['complete_id']
    assert limited['omitted'] and not unlimited['omitted']
    assert not (state.run_dir/'complete_material.json').exists()
    # A changed current title/version cannot silently alter the retained complete view.
    state.data['sources'][a]['title']='New title'
    SourceStore(state).save_raw(a,b'New unrelated version.','txt')
    assert materialize_complete(state,complete)==full


def test_reassembly_preserves_complete_manifest(tmp_path):
    controller=SearchController(tmp_path);tid=controller.create(TASK,{})
    state=SearchState(tmp_path,tid);sid,_=document(state,'a','Complete body with final outcome.')
    assemble_sources(state,[sid],max_chars=1)
    original=(state.run_dir/'complete_material.json').read_bytes()
    assert json.loads(original)['material_chars']>1
    assert controller.reassemble(tid,10000)['samples']
    assert (state.run_dir/'complete_material.json').read_bytes()==original
    assert len(list((state.run_dir/'handoffs').iterdir()))==2


def test_complete_manifest_tamper_rejected(tmp_path):
    from finmy.search.handoff import prepare_complete_sources,materialize_complete
    state=SearchState(tmp_path,'case',task=TASK);sid,_=document(state,'a','Original body.')
    _,complete=prepare_complete_sources(state,[sid])
    complete['selected'][0]['blocks']=[]
    with pytest.raises(ValueError,match='manifest integrity'):materialize_complete(state,complete)
