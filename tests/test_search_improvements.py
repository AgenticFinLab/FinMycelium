"""Case-independent retrieval and finish controls, with no network/model calls."""
from copy import deepcopy
import pytest
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, query_units
from finmy.search.topic import plan_for, select
from finmy.search.topic_reading import read_topic
from finmy.search.review import finish_review
from finmy.search.sources import SourceStore


def task(entity='Orion Works',person='Mira Vale'):
    return dict(target_type='event', target_name=entity+' commitment',
        query_text='Trace the commitment and confirmed delivery.', key_words=[entity,'commitment','delivery'],
        research_scope=dict(include='commitment, delivery'),
        catalog=dict(kind='person_event',person_name=person,event_name=entity+' commitment'))


def document(*texts):
    return dict(version='v',blocks=[dict(text=t) for t in texts])


def test_oversize_provider_does_not_block_other_providers(tmp_path):
    state=SearchState(tmp_path,'x',task=task(),config=SearchConfig(providers=['baidu','bocha','exa']))
    calls=[]
    def transport(provider,payload,config):
        calls.append((provider,payload['query']))
        return {'data':{'webPages':{'value':[]}}} if provider=='bocha' else {'results':[]}
    query='Aster Quay '+('未完成交付' * 12)
    result=SearchTools(state,transport=transport).search(query)
    assert calls==[('bocha',query),('exa',query)]
    assert result['providers'][0]['status']=='skipped_length'
    assert state.data['usage']['search']==2
    assert not any('action_error' in l for l in (state.run_dir/'trace.jsonl').read_text().splitlines())


@pytest.mark.parametrize('entity,person',[('Orion Works','Mira Vale'),('Juniper Labs','Noah Reed')])
def test_person_speech_preserved_for_renamed_tasks(entity,person):
    d=document(entity+' commitment was announced.',
        '“The terms protect our independence,” said '+person+'.',
        'Unrelated municipal sports attendance increased.')
    plan=plan_for(task(entity,person))
    items,groups=select(d,plan,[entity+' delivery'])
    picked={items[i]['block'] for group,_ in groups for i in group}
    assert 1 in picked and 2 not in picked


def test_contract_role_and_terms_located_in_one_read():
    d=document('Agreement between Orion Works (the “Company”) and a purchaser.',
        'The Company shall deliver 300 units after approval.',
        'A different manufacturer reported unrelated sales.')
    original=deepcopy(d)
    spans,meta=read_topic(d,'Orion Works delivery approval',1000,[],plan_for(task()))
    assert any('300 units' in x['text'] for x in spans)
    assert d==original
    for span in spans: assert span['text']==d['blocks'][span['block']]['text'][span['start']:span['end']]


def test_large_match_returns_text_and_exact_continuation():
    d=document('Orion Works commitment '+('delivery conditions '*200))
    spans,meta=read_topic(d,'Orion Works delivery',100,[],plan_for(task()))
    assert sum(len(s['text']) for s in spans)==100
    assert meta['candidate_locations'][0]['offset']==100


def test_no_match_returns_location_without_calling_it_evidence():
    d=document('Other Works delivery happened yesterday.')
    spans,meta=read_topic(d,'Orion Works delivery',500,[],plan_for(task()))
    assert not spans and meta['match_status']=='no_match'
    assert meta['candidate_locations'][0]['block']==0


def test_finish_retains_unread_lead_and_planned_completion(tmp_path):
    t=task(); t['seed_urls']=['https://example.org/letter']
    s=SearchState(tmp_path,'x',task=t);store=SourceStore(s)
    sid=store.register('https://example.org/notice');store.save_raw(sid,b'Orion Works will deliver tomorrow.','txt');store.read(sid)
    action=dict(reason='supported',gaps=[],fact_checks=[dict(question='Was delivery completed?',
        status='planned',source_ids=[sid],detail='The announcement only schedules delivery.')])
    finish_review(s,action)
    assert action['reason']=='low_gain' and len(action['gaps'])==2
    assert s.data['source_lead_review'][0]['status']=='unresolved'
    action=dict(reason='supported',gaps=[],source_lead_decisions={t['seed_urls'][0]:'Duplicate edition of the inspected source.'})
    finish_review(s,action)
    assert s.data['source_lead_review'][0]['status']=='skipped'


def test_v1_does_not_adopt_new_person_protection():
    d=document('Orion Works commitment was announced.', '“A fair arrangement,” said Mira Vale.')
    plan=dict(plan_for(task()),policy='entity_attribute_windows_v1')
    items,groups=select(d,plan,['unmatched_attribute'])
    assert not groups


def test_pronouns_and_distant_contract_alias_do_not_link_unrelated_text():
    from finmy.search.topic import windows
    from finmy.search.topic_context import enrich
    d=document('Agreement with Orion Works (the “Company”).',
        'The Company shall deliver 300 units after approval.',
        'We completed the staff picnic and this improved morale.',
        'Unrelated operations',
        'The Company completed a different delivery for another customer.')
    items=windows(d);enrich(d,items,plan_for(task()))
    assert next(w for w in items if w['block']==1)['entity_context']
    assert not any(w['entity_context'] for w in items if w['block'] in {2,4})


def test_delivery_uses_exact_marks_and_does_not_fill_spare_budget(tmp_path):
    from finmy.search.evidence import record_passages
    from finmy.search.handoff import prepare_complete_sources, derive_input
    s=SearchState(tmp_path,'x',task=task());store=SourceStore(s)
    sid=store.register('https://example.org/annual-report')
    evidence='Mira Vale said: we will deliver on Friday, subject to approval.'
    body='Orion Works annual report.\n\n'+evidence+' Unrelated staff expenses increased.\n\nOrion Works completed another delivery for a different customer.'
    d=store.save_raw(sid,body.encode(),'txt');store.read(sid)
    record_passages(s,[dict(source_id=sid,block=1,start=0,end=len(evidence),reason='speaker, date and condition')])
    _,c=prepare_complete_sources(s,[sid])
    small,a=derive_input(s,c,max_chars=2000)
    large,b=derive_input(s,c,max_chars=200000)
    assert small==large
    assert evidence in small['samples'][0]['content']
    assert 'expenses' not in small['samples'][0]['content']
    assert 'another delivery' not in small['samples'][0]['content']
    assert a['selected'][0]['ranges']==[dict(block=1,start=0,end=len(evidence))]
    assert b['allocation']['unused_chars']>190000
    assert b['allocation']['priority_decisions'][0]['status']=='retained'
    limited,limit_report=derive_input(s,c,max_chars=1)
    assert not limited['samples']
    assert limit_report['allocation']['priority_decisions'][0]['status']=='material_limit'


def test_unmarked_sources_stay_in_pool_without_silent_lexical_fallback(tmp_path):
    from finmy.search.handoff import prepare_complete_sources, derive_input
    s=SearchState(tmp_path,'x',task=task());store=SourceStore(s)
    sid=store.register('https://example.org/notice')
    store.save_raw(sid,b'Orion Works completed the delivery.','txt');store.read(sid)
    _,c=prepare_complete_sources(s,[sid])
    p,a=derive_input(s,c)
    assert c['selected'] and not p['samples']
    assert any('No marked evidence' in gap for gap in a['gaps'])
