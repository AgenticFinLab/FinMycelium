import json
from copy import deepcopy
import pytest
from finmy.search.topic import plan_for, select, windows, POLICY
from finmy.search.state import SearchState
from finmy.search.sources import SourceStore
from finmy.search.handoff import prepare_complete_sources, derive_input

TASK=dict(target_type='event',target_name='Atlas Bank crisis investment',
          query_text='Find the investment, repayment and personal approval.',
          key_words=['Atlas Bank','preferred shares','redemption'],
          research_scope=dict(include='Preferred shares, redemption',exclude='Exclude Beacon Bank.'),
          catalog=dict(kind='person_event',person_name='Ada Example',event_name='Atlas Bank crisis investment'))


def doc(*texts):
    return dict(version='v',kind='txt',blocks=[dict(text=t) for t in texts])


def picked(document,query):
    items,groups=select(document,plan_for(TASK),[query])
    return [w for i,w in enumerate(items) if any(i in g for g,_ in groups)]


def test_positive_scope_and_exclusions_are_separate():
    p=plan_for(TASK)
    assert p['entities']==['Atlas Bank']
    assert 'Beacon Bank' in p['excluded_entities']
    assert all('Beacon' not in f for f in p['facets'])
    assert not p['publication_filter']


def test_entity_attribute_both_required_numbers_do_not_qualify():
    d=doc('A joke: XYZ stock at 5 is now 18.',
          'Atlas Bank has an office in London.',
          'Beacon Bank redeemed preferred shares for 5 billion.',
          'Atlas Bank redeemed its preferred shares for 5 billion.')
    result=picked(d,'Atlas Bank preferred stock redemption 5 billion')
    assert {w['block'] for w in result}=={3}


def test_pronoun_alone_does_not_expand_event_context():
    d=doc('Atlas Bank redeemed preferred shares.', 'It paid the agreed premium.',
          'Insurance Operations','Beacon Bank announced a price increase.')
    result=picked(d,'Atlas Bank redemption')
    assert {w['block'] for w in result}=={0}
    for w in result:assert w['text']==d['blocks'][w['block']]['text'][w['start']:w['end']]


def test_mixed_issuer_evidence_kept_and_page_numbers_removed():
    d=doc('12','Atlas Bank and Beacon Bank received preferred investments together.')
    assert {w['block'] for w in picked(d,'Atlas Bank preferred investments')}=={1}


def test_table_row_has_attribute_from_original_header():
    d=doc('Room | Floor','Executive Suite | 12','Deluxe Suite | 3')
    d['blocks'][0].update(table=1,cells=[dict(header=True)])
    for b in d['blocks'][1:]:b.update(table=1,cells=[dict(header=False)])
    plan=dict(plan_for(TASK),entities=['Executive Suite'],facets=['floor'],excluded_entities=[])
    items,groups=select(d,plan,['Executive Suite floor'])
    chosen={items[i]['block'] for g,_ in groups for i in g}
    assert chosen=={0,1}


def test_virtual_windows_do_not_modify_document():
    d=doc(('Atlas Bank issued preferred shares. '*100),'19')
    original=deepcopy(d);items=windows(d)
    assert len(items)>1 and d==original
    assert ''.join(w['text'] for w in items)==d['blocks'][0]['text']


def test_reading_no_match_is_not_falsely_already_read():
    from finmy.search.topic_reading import read_topic
    spans,meta=read_topic(doc('Beacon Bank paid a premium.'),'Atlas Bank redemption',1000,[],plan_for(TASK))
    assert not spans and meta['match_status']=='no_match'


def test_new_plan_persisted_old_checkpoint_not_upgraded(tmp_path):
    s=SearchState(tmp_path,'t',task=TASK);assert s.data['retrieval_plan']['policy']==POLICY
    del s.data['retrieval_plan'];s.save()
    assert 'retrieval_plan' not in SearchState(tmp_path,'t').data


def test_handoff_ranges_priority_and_legacy_replay(tmp_path):
    s=SearchState(tmp_path,'t',task=TASK);store=SourceStore(s)
    sid=store.register('https://example.org/notice')
    text='Atlas Bank redeemed preferred shares.\n\nAda personally approved the commitment.\n\nUnrelated insurance costs increased.'
    d=store.save_raw(sid,text.encode(),'txt');store.read(sid)
    s.data['priority_passages']=[dict(source_id=sid,version=d['version'],block=1,start=0,end=len(d['blocks'][1]['text']),reason='personal action')]
    _,c=prepare_complete_sources(s,[sid]);assert c['budget_policy']==POLICY
    original=deepcopy(s.data)
    p,a=derive_input(s,c)
    assert s.data==original
    assert 'Ada personally' in p['samples'][0]['content'] and 'insurance' not in p['samples'][0]['content']
    assert a['selected'][0]['ranges']
    p2,a2=derive_input(s,c);assert p2==p and a2==a
    legacy,_=derive_input(s,c,allocation_policy='evidence_priority_windows_v3')
    assert 'insurance' in legacy['samples'][0]['content']
