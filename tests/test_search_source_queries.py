"""Source-bound questions retain event cores and original evidence without network calls."""
from copy import deepcopy
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search import budget
from finmy.search.evidence import record_passages
from finmy.search.handoff import prepare_complete_sources, derive_input
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('No external calls in source-query tests')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)


def setup(tmp_path, **task_options):
    task=dict(target_type='event',target_name='Cedar education program',
              query_text='Research the education program. Exclude astronomy and telescope history.',
              catalog=dict(kind='person_event',event_name='Cedar education program',person_name='Ada Example'),
              research_scope=dict(include='The commitment and implementation',exclude='Astronomy'))
    task.update(task_options)
    state=SearchState(tmp_path,'case',task=task,config=SearchConfig(max_read_chars=4000))
    return state,SourceStore(state),SearchTools(state)


def saved(store,name,paragraphs):
    sid=store.register('https://example.org/'+name,title=name)
    return sid,store.save_raw(sid,'\n\n'.join(paragraphs).encode(),'txt')


def sealed(value):
    value.pop('complete_id',None);value['complete_id']=digest(value)
    return value


def test_source_questions_keep_multiple_actions_core_and_qualifications(tmp_path):
    state,store,tools=setup(tmp_path)
    paragraphs=['Cedar education program was announced.',
                'The invitation arrived by letter.',
                'She declined the invitation pending local consent.',
                'No exact day was disclosed.',
                'Routine inventory. '*600,
                'The following notice describes the opening.',
                'The institution opened the library in April.',
                'Opening remained conditional on staffing.',
                'Routine maintenance. '*600]
    paragraphs += ['Stadium attendance and ticketing details. '*25+str(i) for i in range(15)]
    sid,doc=saved(store,'report',paragraphs)
    other,_=saved(store,'other',['Stadium ticketing details in another source.'])
    tools.read_source(sid,query='invitation local consent')
    tools.read_source(sid,query='library opened April')
    tools.read_source(other,query='stadium attendance ticketing')
    record_passages(state,[dict(source_id=sid,version=doc['version'],block=2,start=0,
                               end=len(paragraphs[2]),reason='Preserve the qualified personal response')])
    _,complete=prepare_complete_sources(state,[sid,other])
    payload,selection=derive_input(state,complete,max_chars=4000)
    body=next(x['content'] for x in payload['samples'] if x['raw_data_id']==sid)
    for i in [0,2,3,6,7]:assert paragraphs[i] in body
    assert 'Stadium attendance' not in body
    plan=selection['allocation']['query_plan'][sid]
    assert plan['basis']=='source_reading'
    assert plan['queries']==['invitation local consent','library opened April']
    assert all('stadium' not in q for q in plan['core_queries'])
    assert len(payload['samples'])==2 and selection['material_chars']<=4000
    assert any(o['omission_reason']=='relevance_selection' for o in selection['omitted'])
    assert selection['allocation']['priority_decisions'][0]['status']=='with_context'
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']:DataSample(**sample)
    assert state.data['usage']=={'search':0,'model':0}
    reverse=deepcopy(complete);reverse['selected'].reverse();sealed(reverse)
    _,reordered=derive_input(state,reverse,max_chars=4000)
    assert {e['source_id']:e['blocks'] for e in reordered['selected']}=={e['source_id']:e['blocks'] for e in selection['selected']}


@pytest.mark.parametrize('include',['The commitment and implementation',''])
def test_no_question_uses_frozen_scope_not_other_queries_or_exclusions(tmp_path, include):
    state,store,tools=setup(tmp_path,research_scope=dict(include=include,exclude='Astronomy'))
    sid,_=saved(store,'report',['Cedar education program commitment was conditional.',
                               'Staffing remains necessary.']+
                              ['Astronomy telescope operations. '*50+str(i) for i in range(30)])
    tools.read_source(sid,location={'block':0})
    state.trace(dict(action='provider_started',provider='bocha',query='astronomy telescope operations'))
    _,complete=prepare_complete_sources(state,[sid])
    payload,selection=derive_input(state,complete,max_chars=6000)
    plan=selection['allocation']['query_plan'][sid]
    assert plan['basis']=='research_scope' and plan['queries']==complete['scope_queries']
    assert all('Astronomy' not in q and 'telescope' not in q for q in plan['queries'])
    assert 'astronomy telescope operations' in complete['retrieval_queries']
    body=payload['samples'][0]['content']
    assert 'commitment was conditional' in body and 'Staffing remains necessary.' in body
    assert 'Astronomy telescope operations.' not in body
    frozen=deepcopy(complete)
    state.data['task']['research_scope']['include']='Astronomy telescope operations'
    state.trace(dict(action='provider_started',query='Later unrelated research'))
    assert derive_input(state,complete,max_chars=6000)==(payload,selection)
    assert complete==frozen


def test_only_matching_version_questions_apply_and_original_task_remains_available(tmp_path):
    state,store,tools=setup(tmp_path)
    sid,doc=saved(store,'letter',['She made a conditional commitment.','A public response followed.'])
    tools.read_source(sid,query='conditional commitment')
    _,complete=prepare_complete_sources(state,[sid])
    complete['reading_queries'].append(dict(source_id=sid,version='other-version',query='foreign question'))
    sealed(complete)
    payload,selection=derive_input(state,complete)
    assert selection['allocation']['query_plan'][sid]['queries']==['conditional commitment']
    assert selection['allocation']['full_material_retained']
    assert 'A public response followed.' in payload['samples'][0]['content']
    assert payload['user_query']['query_text']==state.data['task']['query_text']
    old=deepcopy(complete);old.pop('scope_queries');old['budget_policy']=budget.PRIORITY_POLICY;sealed(old)
    old['reading_queries']=[];sealed(old)
    _,upgraded=derive_input(state,old,allocation_policy=budget.BUDGET_POLICY)
    assert upgraded['allocation']['query_plan'][sid]['basis']=='research_scope'
    assert all('Astronomy' not in q for q in upgraded['allocation']['query_plan'][sid]['queries'])


@pytest.mark.parametrize('policy',[budget.LEGACY_POLICY,budget.FIXED_POLICY,budget.ADAPTIVE_POLICY,budget.PRIORITY_POLICY])
def test_saved_previous_policies_do_not_adopt_source_query_routing(tmp_path,policy):
    state,store,_=setup(tmp_path)
    sid,doc=saved(store,'report',['Cedar education program announcement.','Consent remained required.']+
                               ['Background operations. '*40+str(i) for i in range(20)])
    store.read(sid)
    _,complete=prepare_complete_sources(state,[sid]);complete['budget_policy']=policy;sealed(complete)
    payload,record=derive_input(state,complete,max_chars=3000)
    changed=deepcopy(complete)
    changed['scope_queries']=['unrelated replacement']
    changed['reading_queries']=[dict(source_id=sid,version=doc['version'],query='unrelated replacement')]
    sealed(changed)
    replay,replayed=derive_input(state,changed,max_chars=3000)
    assert replay==payload and replayed['selected']==record['selected']
    assert 'query_plan' not in replayed['allocation']


def test_plain_task_falls_back_to_original_requirement_and_keywords(tmp_path):
    state,store,_=setup(tmp_path,catalog={},research_scope={},target_type='company',
                       query_text='Trace the library opening and its conditions.',key_words=['staffing'])
    sid,_=saved(store,'notice',['The library opening required staffing.'])
    store.read(sid)
    _,complete=prepare_complete_sources(state,[sid]);_,selection=derive_input(state,complete)
    assert selection['allocation']['query_plan'][sid]['queries']==[state.data['task']['query_text'],'staffing']
