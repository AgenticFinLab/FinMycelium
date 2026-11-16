"""Saved-window replay remains compatible; new handoffs use whole-block allocation."""
from copy import deepcopy
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search.budget import BUDGET_POLICY, SAVED_WINDOW_POLICY
from finmy.search.evidence import record_passages
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, SearchConfig, digest
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('No network'))


def materials(tmp_path):
    state=SearchState(tmp_path,'case',task=dict(target_type='person',target_name='Ada',
        query_text='Trace Ada public education commitments.',research_scope={'include':'Education commitment'}),
        config=SearchConfig(max_read_chars=6000))
    text = ('Routine storage inventory and maintenance are reported here.\n'*180 +
        'Ada accepted the community invitation to sponsor the library.\n'
        'This commitment required written consent from the local council.\n'
        'The exact decision day was not recorded.\n' +
        'Another unrelated department reported routine inventory counts.\n'*180)
    tools=SearchTools(state);sid=tools.sources.register('https://example.org/report')
    document=tools.sources.save_raw(sid,text.encode(),'txt')
    assert len(document['blocks']) == 1
    query='Ada accepted community invitation sponsor library written consent'
    tools.read_source(sid,query=query)
    start=text.index('Ada accepted');end=text.index('The exact decision')
    record_passages(state,[dict(source_id=sid,block=0,start=start,end=end,reason='Commitment with qualification')])
    _,complete=prepare_complete_sources(state,[sid])
    complete['budget_policy']=SAVED_WINDOW_POLICY
    complete.pop('complete_id');complete['complete_id']=digest(complete)
    return state,sid,document,complete


def test_long_merged_block_uses_exact_ranges_and_preserves_qualifications(tmp_path):
    state,sid,document,complete=materials(tmp_path)
    before=deepcopy(complete);original=deepcopy(document)
    payload,record=derive_input(state,complete,max_chars=6500)
    text=payload['samples'][0]['content']
    for phrase in ('Ada accepted the community invitation','required written consent','exact decision day was not recorded'):
        assert phrase in text
    assert record['material_chars'] <= 6500 < complete['material_chars']/2
    assert record['allocation']['priority_decisions'][0]['status']=='with_context'
    sample=payload['samples'][0];entry=record['selected'][0]
    expected=[]
    for span in entry['ranges']:
        raw=document['blocks'][span['block']]['text'][span['start']:span['end']]
        expected.append(f"[original block {span['block']} chars {span['start']}:{span['end']}]\n{raw}")
    assert sample['content']==complete['selected'][0]['header']+'\n\n'.join(expected)
    assert SourceStore(state).document(sid)==original and complete==before
    assert state.data['usage']=={'search':0,'model':0}
    UserQueryInput(**payload['user_query']);DataSample(**sample)
    previous=[]
    for stage in record['allocation']['threshold_stages']:
        current=stage['selected_ranges'][sid]
        assert all(any(b['block']==a['block'] and b['start']<=a['start'] and b['end']>=a['end']
                       for b in current) for a in previous)
        previous=current


def test_source_question_is_stable_against_unrelated_scope_and_old_policy_replays(tmp_path):
    state,sid,document,complete=materials(tmp_path)
    first=derive_input(state,complete,max_chars=6500)
    alternate=deepcopy(complete)
    alternate['scope_queries']=['Routine storage inventory in all departments']
    alternate.pop('complete_id');alternate['complete_id']=digest(alternate)
    second=derive_input(state,alternate,max_chars=6500)
    assert first[0]==second[0]
    assert first[1]['allocation']['query_plan'][sid]['basis']=='source_reading'
    legacy=deepcopy(complete);legacy['budget_policy']=BUDGET_POLICY
    legacy.pop('complete_id');legacy['complete_id']=digest(legacy)
    old=derive_input(state,legacy,max_chars=6500)
    explicit=derive_input(state,complete,max_chars=6500,allocation_policy=BUDGET_POLICY)
    assert old[0]==explicit[0]
    assert 'windowing' not in old[1]['allocation']
    assert 'windowing' in first[1]['allocation']
    assert all('ranges' not in e for e in old[1]['selected'])


def test_small_budget_reports_priority_omission_and_full_fit_remains_exact(tmp_path):
    state,sid,document,complete=materials(tmp_path)
    payload,record=derive_input(state,complete,max_chars=50)
    assert not payload['samples']
    assert record['allocation']['priority_decisions'][0]['status']=='material_limit'
    full,record=derive_input(state,complete,max_chars=complete['material_chars'])
    assert full['samples'][0]['content']==complete['selected'][0]['header']+document['blocks'][0]['text']
    assert record['allocation']['full_material_retained']
    assert not (state.run_dir/'builder_input.json').exists()


def test_identified_table_row_is_indivisible_even_when_it_contains_sentences(tmp_path):
    state=SearchState(tmp_path,'table',task=dict(target_type='event',target_name='Commitment',
        query_text='Trace the commitment and its conditions.'),config=SearchConfig(max_read_chars=16000))
    row=' '.join(f'Condition {i} remains subject to consent.' for i in range(140))
    raw=f'<article><p>The public commitment is conditional.</p><table><tr><td>{row}</td></tr></table></article>'
    tools=SearchTools(state);sid=tools.sources.register('https://example.org/table')
    doc=tools.sources.save_raw(sid,raw.encode(),'html')
    index=next(i for i,b in enumerate(doc['blocks']) if b.get('row'))
    tools.read_source(sid,query='commitment condition consent')
    record_passages(state,[dict(source_id=sid,block=index,start=0,end=40)])
    _,complete=prepare_complete_sources(state,[sid])
    complete['budget_policy']=SAVED_WINDOW_POLICY
    complete.pop('complete_id');complete['complete_id']=digest(complete)
    payload,record=derive_input(state,complete,max_chars=1500)
    assert record['allocation']['priority_decisions'][0]['status']=='material_limit'
    assert all(index not in e['blocks'] for e in record['selected'])
    assert all(row not in sample['content'] and 'Condition 0' not in sample['content']
               for sample in payload['samples'])
    assert SourceStore(state).document(sid)['blocks'][index]['text']==row


def test_new_handoff_uses_whole_blocks_and_scope_with_source_questions(tmp_path):
    state,sid,document,_=materials(tmp_path)
    _,complete=prepare_complete_sources(state,[sid])
    assert BUDGET_POLICY=='evidence_priority_windows_v4'
    assert complete['budget_policy']==BUDGET_POLICY
    payload,record=derive_input(state,complete,max_chars=6500)
    assert 'windowing' not in record['allocation']
    assert all('ranges' not in e for e in record['selected'])
    plan=record['allocation']['query_plan'][sid]
    assert plan['core_queries']==list(dict.fromkeys(plan['queries']+complete['scope_queries']))
    # Same frozen material can still replay the saved policy without changing the new default.
    saved,_=derive_input(state,complete,max_chars=6500,allocation_policy=SAVED_WINDOW_POLICY)
    assert 'Ada accepted the community invitation' in saved['samples'][0]['content']
    assert complete['budget_policy']==BUDGET_POLICY
