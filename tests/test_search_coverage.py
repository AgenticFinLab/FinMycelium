from copy import deepcopy
import json
import pytest
from finmy.search.agent import context_for, run_agent
from finmy.search.state import SearchState, SearchConfig
from finmy.search.sources import SourceStore
from finmy.search.evidence import record_passages
from finmy.search.handoff import prepare_complete_sources, derive_input
from finmy.search.tools import SearchTools
from test_search_improvements import task


def setup(tmp_path, rows):
    s=SearchState(tmp_path,'x',task=task());store=SourceStore(s);ids=[]
    for i,(text,fields) in enumerate(rows):
        sid=store.register('https://example.org/source-'+str(i));ids.append(sid)
        d=store.save_raw(sid,text.encode(),'txt');store.read(sid)
        report=record_passages(s,[dict(source_id=sid,block=0,start=0,end=len(d['blocks'][0]['text']),**fields)])
        assert report['accepted']==1
    _,complete=prepare_complete_sources(s,ids)
    return s,complete


def test_new_facts_conditions_personal_conflicts_and_independent_support(tmp_path):
    fields=dict(fact_ids=['payment'],claim_id='paid',evidence_role='outcome')
    s,c=setup(tmp_path,[
        ('The purchaser paid the full amount.',fields),
        ('Payment of the full amount was made by the purchaser.',fields),
        ('Mira Vale said she authorized the payment.',dict(fact_ids=['payment'],claim_id='authorized',evidence_role='personal')),
        ('Payment was conditional on approval.',dict(fact_ids=['payment'],claim_id='approval-condition',evidence_role='condition')),
        ('The purchaser denied making payment.',dict(fact_ids=['payment'],claim_id='denied',evidence_role='contradiction')),
        ('An independent receipt confirms payment.',dict(fact_ids=['payment'],claim_id='paid',evidence_role='corroboration',independence_key='receipt-original')),
        ('The same receipt verifies the payment.',dict(fact_ids=['payment'],claim_id='paid',evidence_role='corroboration',independence_key='receipt-original')),
        ('A separate ledger independently records payment.',dict(fact_ids=['payment'],claim_id='paid',evidence_role='corroboration',independence_key='ledger-original')),
        ('The organization sponsors a community festival.',dict(claim_id='festival',evidence_role='context'))])
    before=deepcopy(s.data)
    p,a=derive_input(s,c,max_chars=20000)
    text=' '.join(x['content'] for x in p['samples'])
    for needle in ['authorized','conditional','denied','ledger']:
        assert needle in text
    assert 'festival' not in text
    statuses=[x['status'] for x in a['allocation']['priority_decisions']]
    assert statuses.count('retained')==6 and statuses.count('redundant')==3
    assert a['allocation']['unused_chars']>0
    assert s.data==before
    assert derive_input(s,c,max_chars=200000)[0]==p


@pytest.mark.parametrize('text,facts,retained', [
    ('Their longstanding relationship led to the investment approach.', ['approach'], True),
    ('The transaction involved a payment by the purchaser.', ['payment'], False),
    ('The organization sponsors a community festival.', None, False),
    ('Payment was completed.\n\nReposted source footer.', ['approach'], False),
])
def test_context_delivery_requires_new_fact_and_keeps_duplicate_checks(tmp_path,text,facts,retained):
    fields=dict(claim_id='context-claim',evidence_role='context')
    if facts is not None:
        fields['fact_ids']=facts
    s,c=setup(tmp_path,[
        ('Payment was completed.',dict(fact_ids=['payment'],claim_id='paid',evidence_role='outcome')),
        (text,fields)])
    sid=c['source_ids'][1]
    before=deepcopy(s.data)
    payload,selection=derive_input(s,c)
    decision=next(d for d in selection['allocation']['priority_decisions'] if d['passage']['source_id']==sid)
    assert decision['status']==('retained' if retained else 'redundant')
    assert (sid in {sample['raw_data_id'] for sample in payload['samples']})==retained
    if retained:
        assert decision['new_facts']==['approach']
        assert text in next(sample['content'] for sample in payload['samples'] if sample['raw_data_id']==sid)
        original=next(e for e in selection['selected'] if e['source_id']!=sid)
        limited,report=derive_input(s,c,max_chars=original['material_chars'])
        assert len(limited['samples'])==1 and limited['samples'][0]['raw_data_id']!=sid
        assert any(d['passage']['source_id']==sid and d['status']=='material_limit'
                   for d in report['allocation']['priority_decisions'])
    assert s.data==before


def test_dates_amounts_and_negation_survive_same_claim_annotation(tmp_path):
    fields=dict(fact_ids=['settlement'],claim_id='settled',evidence_role='outcome')
    s,c=setup(tmp_path,[('Settlement was completed on 2013-10-01 for 5 million.',fields),
                      ('Settlement was not completed on 2013-10-04 for 6 million.',fields)])
    p,a=derive_input(s,c)
    assert len(p['samples'])==2


def test_exact_repost_not_independent_by_url_and_new_fact_wins_tight_budget(tmp_path):
    fields=dict(fact_ids=['payment'],claim_id='paid',evidence_role='outcome')
    s,c=setup(tmp_path,[('Payment was completed.',fields),('Payment was completed.',fields),
        ('Mira Vale authorized the transaction.',dict(fact_ids=['authorization'],claim_id='authorized',evidence_role='personal'))])
    p,a=derive_input(s,c)
    assert len(p['samples'])==2
    needed=max(e['material_chars'] for e in a['selected'])
    limited,report=derive_input(s,c,max_chars=needed)
    assert len(limited['samples'])==1
    assert any(x['status']=='material_limit' for x in report['allocation']['priority_decisions'])


def test_annotation_validation_and_updates(tmp_path):
    s,c=setup(tmp_path,[('Mira Vale approved the contract.',{})])
    sid=c['source_ids'][0];mark=c['priority_passages'][0]
    result=record_passages(s,[dict(mark,fact_ids=['approval'],claim_id='approved',evidence_role='personal')])
    assert result['accepted']==1 and len(s.data['priority_passages'])==1
    assert s.data['priority_passages'][0]['fact_ids']==['approval']
    result=record_passages(s,[dict(mark,evidence_role='invented')])
    assert result['rejected'] and result['accepted']==0


def test_original_ranges_and_unlabelled_mark_compatibility(tmp_path):
    s,c=setup(tmp_path,[('Mira Vale approved the contract.',{}),('Terms include a delivery guarantee.',{})])
    p,a=derive_input(s,c)
    assert len(p['samples'])==2
    store=SourceStore(s)
    for e in a['selected']:
        doc=store.document(e['source_id'],e['version'])
        for r in e['ranges']:
            assert doc['blocks'][r['block']]['text'][r['start']:r['end']] in next(x['content'] for x in p['samples'] if x['raw_data_id']==e['source_id'])


def test_identical_originals_cannot_gain_independence_from_labels(tmp_path):
    fields=dict(fact_ids=['payment'],claim_id='paid',evidence_role='corroboration')
    s,c=setup(tmp_path,[('Payment was completed.',dict(fields,independence_key='independent-ledger')),
                      ('Payment was completed.',dict(fields,independence_key='independent-receipt'))])
    p,a=derive_input(s,c)
    assert len(p['samples'])==1 and c['duplicates']


@pytest.mark.parametrize('fields,length', [
    ({'fact_id':'delivery'},302),
    ({'fact_ids':['delivery']},304),
    ({'fact_id':'delivery','fact_ids':['delivery','authorization']},302),
])
def test_coverage_alias_and_long_reason_survive_finish_and_resume(tmp_path,fields,length):
    s=SearchState(tmp_path,'x',task=task(),config=SearchConfig(max_model_calls=1))
    store=SourceStore(s);sid=store.register('https://example.org/delivery')
    text='Mira Vale confirmed that Orion Works delivered the units on April 3.'
    doc=store.save_raw(sid,('Unrelated preface.\n\n'+text+'\n\nUnrelated tail.').encode(),'txt')
    store.read(sid)
    mark=dict(source_id=sid,block=1,start=0,end=len(text),reason='r'*length,**fields)
    original=deepcopy(mark)
    run_agent(s,SearchTools(s),lambda _:dict(action='finish',source_ids=[sid],
        priority_passages=[mark],gaps=[],reason='supported'))
    assert mark==original
    assert s.data['status']=='finished' and s.data['usage']=={'search':0,'model':1}
    restored=SearchState(tmp_path,'x')
    accepted=restored.data['priority_passages'][0]
    assert accepted['fact_ids']==sorted(fields.get('fact_ids',['delivery']))
    assert 'fact_id' not in accepted and accepted['reason']=='r'*300
    assert (accepted['block'],accepted['start'],accepted['end'],accepted['version'])==(1,0,len(text),doc['version'])
    payload=json.loads((s.run_dir/'builder_input.json').read_text())
    assert len(payload['samples'])==1 and text in payload['samples'][0]['content']
    assert 'Unrelated' not in payload['samples'][0]['content']
    assert store.document(sid)==doc


@pytest.mark.parametrize('fields', [
    {'fact_id':None}, {'fact_id':[]}, {'fact_id':''}, {'fact_ids':'delivery'},
    {'fact_id':'different','fact_ids':['delivery']}, {'reason':None},
])
def test_coverage_compatibility_still_rejects_invalid_metadata(tmp_path,fields):
    s,c=setup(tmp_path,[('Mira Vale confirmed delivery.',{})])
    before=deepcopy(s.data['priority_passages'])
    result=record_passages(s,[dict(c['priority_passages'][0],**fields)])
    assert result['accepted']==0 and result['rejected']
    assert s.data['priority_passages']==before


def test_unknown_mark_field_is_named_in_model_feedback(tmp_path):
    s,c=setup(tmp_path,[('Mira Vale confirmed delivery.',{})])
    record_passages(s,[dict(c['priority_passages'][0],factz=['delivery'])])
    feedback=context_for(s)['evidence_feedback']['priority_passages']
    assert feedback['accepted']==0 and 'factz' in feedback['rejected'][0]['reason']
