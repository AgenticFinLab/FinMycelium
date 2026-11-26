"""Semantic selection advice must remain grounded in immutable original evidence."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search.agent import SYSTEM_PROMPT, context_for, execute_action, run_agent
from finmy.search.budget import ADAPTIVE_POLICY, BUDGET_POLICY
from finmy.search.evidence import record_passages
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.reading import located_preview
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail('Offline evidence tests cannot use external services')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)


def setup(tmp_path, **options):
    task=dict(target_type='event',target_name='Cedar education program',
              query_text='Trace the education program and Ada Example participation.',
              catalog=dict(kind='person_event',event_name='Cedar education program',person_name='Ada Example'),
              research_scope=dict(include='Education program',exclude='Unrelated family history'))
    state=SearchState(tmp_path,'case',task=task,config=SearchConfig(**options))
    return state,SourceStore(state),SearchTools(state)


def saved(store,name,text):
    sid=store.register('https://example.org/'+name,title=name)
    return sid,store.save_raw(sid,text.encode(),'txt')


def marker(sid,doc,block,reason='Adds the personal response and its qualification'):
    return dict(source_id=sid,version=doc['version'],block=block,start=0,
                end=len(doc['blocks'][block]['text']),reason=reason)


@pytest.mark.parametrize(('reader', 'repeat_status'), [('topic', 'already_read'), ('bm25', 'no_evidence_gain')])
def test_repeated_reads_keep_original_facts_in_final_context(tmp_path, reader, repeat_status):
    state,store,tools=setup(tmp_path, retrieval={'mode': reader})
    sid,doc=saved(store,'Completion notice','Completion notice\n\nThe program opened on April 3.\n\nContact: Office 123.')
    first=tools.read_source(sid,query='program opened',agent_feedback=True)
    ranges=deepcopy(state.data['sources'][sid]['read_ranges'])
    second=tools.read_source(sid,query='program opened',agent_feedback=True)
    assert first['spans']==second['spans'] and second['reading']['replayed']
    assert state.data['sources'][sid]['read_ranges']==ranges
    state.data['feedback']=second
    final=context_for(state,finalize=True)
    assert 'spans' not in final['feedback']
    evidence=final['sources'][0]['read_evidence']
    assert 'April 3' in ' '.join(p['text'] for p in evidence)
    assert all(doc['blocks'][p['block']]['text'][p['start']:p['end']]==p['text'] for p in evidence)
    repeated=tools.read_source(sid,query='program opened',agent_feedback=True)
    assert repeated['spans']==[] and repeated['reading']['match_status']==repeat_status
    assert repeated['progress']['new_chars'] == 0
    state.data['feedback']=repeated
    retained=context_for(state,finalize=True)['sources'][0]['read_evidence']
    assert 'April 3' in ' '.join(p['text'] for p in retained)
    # The original location still resolves through the deterministic source reader.
    assert store.read(sid,**evidence[0]['read_location'])['spans']


def test_annotations_do_not_block_a_valid_tool_action(tmp_path):
    state,store,tools=setup(tmp_path)
    sid,doc=saved(store,'interview','She accepted the invitation.\n\nThe date was not disclosed.')
    other,_=saved(store,'unread','The institution issued a statement.')
    store.read(sid)
    good=marker(sid,doc,0)
    result=execute_action(state,tools,dict(action='read_source',source=sid,query='invitation',
        priority_passages=[good,{**good,'source_id':'invented'},
                           {**good,'source_id':other}, {**good,'end':99999}]))
    assert result['spans']
    assert state.data['priority_passages']==[good]
    assert len(state.data['priority_feedback']['rejected'])==3
    assert state.data['usage']=={'search':0,'model':0}


def test_priority_requires_contiguous_inspected_support_and_current_version(tmp_path):
    state,store,_=setup(tmp_path,max_read_chars=8)
    sid,doc=saved(store,'statement','She accepted the invitation and required written consent.')
    store.read(sid)
    full=marker(sid,doc,0)
    assert record_passages(state,[full])['rejected']
    assert record_passages(state,[{**full,'end':8}])['accepted']==1
    updated=store.save_raw(sid,b'A revised statement with different details.','txt')
    store.read(sid)
    assert updated['version']!=doc['version']
    assert record_passages(state,[{**full,'end':8}])['rejected']
    _,complete=prepare_complete_sources(state,[sid])
    assert complete['priority_passages']==[] and complete['priority_omissions']


def test_priorities_preserve_original_action_context_under_budget(tmp_path):
    state,store,_=setup(tmp_path,max_read_chars=100000)
    paragraphs=['Education program operations. '*100+str(i) for i in range(12)]
    paragraphs += ['The interviewer asked about her participation.',
                   'She declined the invitation pending written consent.',
                   'No precise day was disclosed.']
    paragraphs += ['Education program accounts. '*100+str(i) for i in range(10)]
    sid,doc=saved(store,'annual-report','\n\n'.join(paragraphs));store.read(sid)
    notice,_=saved(store,'notice','The education program was announced in April.');store.read(notice)
    _,before=prepare_complete_sources(state,[sid,notice])
    ordinary,_=derive_input(state,before,max_chars=2200)
    phrase=paragraphs[13]
    assert phrase not in ''.join(s['content'] for s in ordinary['samples'])
    hint=marker(sid,doc,13,reason='SEMANTIC_HINT_ONLY')
    record_passages(state,[hint])
    full,complete=prepare_complete_sources(state,[sid,notice])
    payload,selection=derive_input(state,complete,max_chars=2200)
    text='\n'.join(s['content'] for s in payload['samples'])
    assert phrase in text and paragraphs[14] in text and 'announced in April' in text
    assert 'SEMANTIC_HINT_ONLY' not in text
    assert selection['material_chars']<=2200 and complete['material_chars']>2200
    assert selection['allocation']['priority_decisions'][0]['status']=='with_context'
    assert len(full['samples'])==2 and derive_input(state,complete,max_chars=2200)==(payload,selection)
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']:DataSample(**sample)
    assert set(payload)=={'user_query','samples'}


def test_priority_omissions_are_recorded_and_old_policy_replay_is_unchanged(tmp_path):
    state,store,_=setup(tmp_path,max_read_chars=100000)
    sid,doc=saved(store,'report','Education program announcement.\n\n'+'She responded with qualifications. '*500)
    store.read(sid)
    _,old=prepare_complete_sources(state,[sid])
    old['budget_policy']=ADAPTIVE_POLICY
    old['complete_id']=digest({k:v for k,v in old.items() if k!='complete_id'})
    baseline=derive_input(state,old,max_chars=1000)
    record_passages(state,[marker(sid,doc,1)])
    _,current=prepare_complete_sources(state,[sid])
    _,selection=derive_input(state,current,max_chars=1000)
    assert selection['material_chars']<=1000
    assert selection['allocation']['priority_decisions'][0]['status']=='material_limit'
    assert derive_input(state,old,max_chars=1000)==baseline
    _,excluded=prepare_complete_sources(state,[])
    assert excluded['priority_omissions'][0]['reason']=='Source not retained by final selection'


def test_finish_records_person_assessment_without_inventing_builder_text(tmp_path):
    state,store,tools=setup(tmp_path,max_model_calls=1)
    sid,doc=saved(store,'notice','The institution announced a new school.');store.read(sid)
    review=dict(status='limited',detail='No evidence of her private discussions; only the institutional announcement was inspected.')
    run_agent(state,tools,lambda c:dict(action='finish',source_ids=[sid],gaps=['Personal response unattempted.'],
        reason='supported',reason_detail='Call limit; retain useful context.',person_evidence=review,
        priority_passages=[marker(sid,doc,0)]))
    assert state.data['status']=='finished' and state.data['usage']['model']==1
    complete=json.loads((state.run_dir/'complete_material.json').read_text())
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert complete['person_evidence']==review and complete['priority_passages']
    assert review['detail'] not in str(payload['samples'])
    from finmy.search.summary import render
    data=deepcopy(state.data)
    data['task']['catalog'].update(event_id='E1',person_id='P1',storyline_name='Education',storyline_id='S1')
    data['task']['research_scope']['period']='2000–2001'
    selection=json.loads((state.run_dir/'selection.json').read_text())
    summary,_=render(data,'case',selection,payload)
    assert 'Valid priority annotations: 1; retained in input: 1' in summary
    assert 'Search Agent assessment: limited' in summary
    assert review['detail'] not in summary
    assert selection['person_evidence']['detail'] in summary
    assert selection['person_evidence']['questions']==[]


def test_interrupted_response_usage_is_recorded_once(tmp_path):
    state,store,tools=setup(tmp_path,max_model_calls=2)
    sid,_=saved(store,'notice','The institution announced a new school.');store.read(sid)
    class Model:
        calls=0
        last_usage=None
        last_finish_reason=None
        def __call__(self,context):
            self.calls+=1
            self.last_usage=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15)
            self.last_finish_reason='length' if self.calls==1 else 'stop'
            if self.calls==1:raise ValueError('Model completion was interrupted or truncated')
            return dict(action='finish',source_ids=[sid],gaps=[],reason='supported')
    run_agent(state,tools,Model())
    trace=[json.loads(x) for x in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    records=[x for x in trace if x.get('usage')]
    assert len(records)==2 and sum(x['usage']['total_tokens'] for x in records)==30
    assert records[0]['action']=='action_error' and records[0]['finish_reason']=='length'


def test_context_bound_and_no_unread_text_leakage(tmp_path):
    state,store,_=setup(tmp_path,max_model_context_chars=20000,max_read_chars=100)
    for i in range(10):
        sid,doc=saved(store,str(i),'She accepted the invitation. '*20+' UNREAD_TAIL_MARKER')
        store.read(sid)
    c=context_for(state,finalize=True)
    assert len(SYSTEM_PROMPT)+len(json.dumps(c,ensure_ascii=False))<=20000
    assert 'UNREAD_TAIL_MARKER' not in json.dumps(c)
    previews=[s for source in c['sources'] for s in source.get('read_evidence',[])]
    assert previews and sum(len(json.dumps(s,ensure_ascii=False))+32 for s in previews)<=3200
    assert all(s['end']<=100 for s in previews)


@pytest.mark.parametrize('intervals,version,expected', [
    ([], 'v', 'unmarked'),
    ([(0, 10), (10, 20)], 'v', 'marked'),
    ([(0, 12), (8, 20)], 'v', 'marked'),
    ([(0, 8), (9, 20)], 'v', 'partial'),
    ([(0, 8)], 'v', 'partial'),
    ([(20, 30)], 'v', 'unmarked'),
    ([(0, 20)], 'old', 'unmarked'),
])
def test_preview_mark_status_uses_current_version_and_interval_union(intervals, version, expected):
    document = dict(version='v', blocks=[dict(text='Read evidence text. ' + 'UNREAD_TAIL')])
    ranges = [dict(version='v', block=0, start=0, end=20)]
    marks = [dict(version=version, block=0, start=a, end=b) for a,b in intervals]
    before = deepcopy((document, ranges, marks))
    spans = located_preview(document, ranges, ['evidence'], 500, marks)
    assert len(spans) == 1 and spans[0]['mark_status'] == expected
    assert spans[0]['text'] == document['blocks'][0]['text'][:20]
    assert 'UNREAD_TAIL' not in json.dumps(spans)
    assert (document, ranges, marks) == before


def test_preview_status_describes_displayed_text_and_fits_serialized_budget():
    text = 'Evidence includes "conditions" and 原文. ' * 100
    document = dict(version='v', blocks=[dict(text=text)])
    ranges = [dict(version='v', block=0, start=0, end=len(text))]
    # Only the prefix is marked. Spend the bounded preview on an unmarked
    # original instead of repeatedly displaying that saved prefix.
    marks = [dict(version='v', block=0, start=0, end=500)]
    spans = located_preview(document, ranges, ['Evidence'], 300, marks)
    assert len(spans) == 1 and spans[0]['mark_status'] == 'unmarked'
    assert spans[0]['start'] >= 500
    assert 500 < spans[0]['end'] <= len(text)
    assert spans[0]['text'] == text[spans[0]['start']:spans[0]['end']]
    assert len(json.dumps(spans, ensure_ascii=False)) <= 300


def test_existing_finish_can_add_missing_fact_and_sentence_tail_without_rereading(tmp_path):
    task = dict(target_type='event', target_name='Cedar education program',
                query_text='Trace the education program and Ada participation.',
                key_words=['Cedar', 'education program', 'participation'],
                catalog=dict(kind='person_event', person_name='Ada', event_name='Cedar education program'))
    state = SearchState(tmp_path, 'case', task=task, config=SearchConfig(max_model_calls=1))
    store = SourceStore(state)
    parts = ['Cedar approached Ada because of their longstanding working relationship.',
             'Ada accepted the invitation. Work would begin only after local consent.',
             'An unrelated community festival took place in summer.']
    sid, doc = saved(store, 'interview', '\n\n'.join(parts))
    store.read(sid)
    first = dict(marker(sid, doc, 1), end=len('Ada accepted the invitation.'),
                 fact_ids=['acceptance'], evidence_role='personal')
    record_passages(state, [first])
    before = deepcopy(state.data)
    context_for(state, finalize=True)
    assert state.data == before

    # A scripted decision checks the existing one-call route, not LLM behavior.
    def decide(context):
        spans = context['sources'][0]['read_evidence']
        assert {p['block']:p['mark_status'] for p in spans} == {0:'unmarked', 1:'unmarked', 2:'unmarked'}
        tail=next(p for p in spans if p['block']==1)
        assert tail['start']==first['end'] and 'only after local consent' in tail['text']
        assert context['sources'][0]['priority_passages']==[first]
        return dict(action='finish', source_ids=[sid], gaps=[], reason='supported',
                    priority_passages=[
                        dict(marker(sid, doc, 0), fact_ids=['approach'], evidence_role='context'),
                        dict(marker(sid, doc, 1), fact_ids=['consent'], evidence_role='condition')])

    run_agent(state, SearchTools(state), decide)
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    text = '\n'.join(s['content'] for s in payload['samples'])
    assert parts[0] in text and parts[1] in text and parts[2] not in text
    assert state.data['status'] == 'finished' and state.data['usage'] == {'search':0, 'model':1}
    assert state.data['sources'][sid]['read_ranges'] == before['sources'][sid]['read_ranges']
    assert first in state.data['priority_passages']


def test_read_locations_fail_clearly_before_source_registration(tmp_path):
    state,store,tools=setup(tmp_path)
    with pytest.raises(ValueError,match='read_location'):
        tools.read_source('https://example.org/new',location={'block':0,'start':0,'end':100})
    assert not state.data['sources'] and not state.data['read_sources']
