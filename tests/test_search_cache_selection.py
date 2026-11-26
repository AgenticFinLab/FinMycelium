"""Cache evidence reaches decisions without extra requests or uninspected marks."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import SYSTEM_PROMPT, context_for, execute_action, model_context, run_agent
from finmy.search.evidence import record_passages, validate_passage
from finmy.search.inspection import commit_evidence, context_passages
from finmy.search.reading import record_presented
from finmy.search.retrieval import cached_candidates
from finmy.search.review import finish_review, record_checks
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_evidence_routing import check
from test_search_integrated_review import mark


def test_cached_original_can_be_marked_and_delivered_on_the_same_call(tmp_path):
    state,tools=setup(tmp_path)
    text='Ada Vale stipulated that the Orion program required local consent.'
    sid,doc=saved(tools,'opaque.pdf',text+'\n\nUnrelated travel advice.')
    state.data['sources'][sid]['title']='document.pdf'
    before=deepcopy(state.data)
    context=context_for(state)
    assert state.data==before and not state.data['sources'][sid].get('read_ranges')
    assert context['cached_evidence'][0]['spans'][0]['text']==text
    with pytest.raises(ValueError,match='not inspected'):
        validate_passage(state,mark(sid,0,text))
    calls=[]
    def decide(context):
        calls.append(context)
        candidates=context['cached_evidence']
        refs=[dict(source_id=c['source_id'],version=c['version'],**{k:s[k] for k in ('block','start','end')})
              for c in candidates for s in c['spans']]
        return finish([sid],priority_passages=refs)
    run_agent(state,tools,decide)
    assert state.data['status']=='finished' and len(calls)==1
    assert state.data['usage']=={'model':1,'search':0}
    assert len(state.data['sources'][sid]['read_ranges'])==1
    with pytest.raises(ValueError,match='not inspected'):
        validate_passage(state,dict(source_id=sid,block=1,start=0,end=10))
    body=json.loads((state.run_dir/'builder_input.json').read_text())['samples'][0]['content']
    assert text in body and 'Unrelated travel' not in body
    assert tools.sources.document(sid)==doc


def test_failed_request_or_context_inspection_does_not_create_read_ranges(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'interview','Ada Vale stipulated local consent before funding Orion.')
    assert context_for(state)['cached_evidence']
    assert not state.data['sources'][sid].get('read_ranges')
    def fail(_): raise RuntimeError('Synthetic model failure')
    run_agent(state,tools,fail,max_steps=1)
    assert not state.data['sources'][sid].get('read_ranges')
    assert sid not in state.data['read_sources']
    assert state.data['usage']['model']==1


def test_presented_cache_counts_as_reading_progress_once(tmp_path):
    state,tools=setup(tmp_path)
    text='Ada Vale stipulated local consent before funding the Orion program.'
    sid,_=saved(tools,'interview',text)
    tools.sources.can_complete_partial=False
    state.data['research_progress']={'consecutive_no_gain':3}
    contexts=[]
    def decide(context):
        contexts.append(context)
        return dict(action='read_source',source=sid,query='Orion local consent')
    run_agent(state,tools,decide,max_steps=1)
    assert state.data['feedback']['operation_deferred']  # Shown cache needs a decision, not another read.
    assert state.data['research_progress']['new_chars']==len(text)
    assert state.data['research_progress']['consecutive_no_gain']==0
    assert record_presented(state,contexts[0]['cached_evidence'])==0


def test_display_is_bounded_and_discarded_finalization_context_is_not_read(tmp_path):
    state,tools=setup(tmp_path)
    for i in range(6):
        saved(tools,str(i),f'Ada Vale stipulated that the Orion program required consent from district {i}.')
    c=context_for(state)
    assert len(json.dumps(c['cached_evidence'],ensure_ascii=False))+32<=3200
    assert len(SYSTEM_PROMPT)+len(json.dumps(c,ensure_ascii=False))<=state.config.max_model_context_chars
    assert not context_for(state,finalize=True).get('cached_evidence')
    assert state.data['read_sources']==[]


def test_stale_question_does_not_hide_conditions_or_duplicate_its_rendered_gap(tmp_path):
    state,tools=setup(tmp_path)
    announcement,_=saved(tools,'notice','The Orion program will open in June.',read=True)
    sid,_=saved(tools,'history','Ada Vale stipulated local approval before opening Orion.')
    q='Has the Orion program opened?'
    fact=check(q,announcement,status='planned',detail='Only an announcement is known.')
    record_checks(state,[fact])
    candidates=cached_candidates(state,dict(fact_checks=[fact],gaps=[q+': planned; Only an announcement is known.']))
    assert any(c['source_id']==sid for c in candidates)
    assert not any(c['query'].startswith(q+':') for c in candidates)


def test_late_same_paragraph_abbreviation_is_visible_but_report_wide_alias_is_not(tmp_path):
    state,tools=setup(tmp_path)
    lead='The Orion education program (OP) received a commitment from Ada Vale. '
    middle=('The agreement had several administrative provisions. '*30)
    ending='The commitment was completed and we received 7,321 units of OP funding.'
    sid=tools.sources.register('https://example.org/report',title='report.pdf')
    doc=tools.sources.save_raw(sid,(lead+middle+ending).encode(),'txt',partial=True,
        parsed=dict(status='success',blocks=[dict(text=lead+middle+ending),
            dict(text='We received 9,876 unrelated units in another business.')]))
    candidates=cached_candidates(state,dict(query='received 7,321 units completed',fact_checks=[]),unread_only=True)
    spans=[s for c in candidates if c['source_id']==sid for s in c['spans']]
    assert any(ending in s['text'] for s in spans)
    assert any(lead.strip() in s['text'] for s in spans)
    assert all(s['block']==0 for s in spans)
    assert all(doc['blocks'][s['block']]['text'][s['start']:s['end']]==s['text'] for s in spans)


def test_presented_copy_is_not_offered_as_an_unread_new_origin(tmp_path):
    state,tools=setup(tmp_path)
    text='Ada Vale stipulated local consent before funding the Orion program.'
    first,_=saved(tools,'original',text)
    second,_=saved(tools,'repost',text)
    candidates=context_for(state)['cached_evidence']
    record_presented(state,candidates)
    assert first in state.data['read_sources'] and second not in state.data['read_sources']
    assert not context_for(state).get('cached_evidence')


def test_explicit_question_merge_closes_old_gap_and_preserves_unrelated_question(tmp_path):
    state,tools=setup(tmp_path)
    text='The Orion program opened after local consent.'
    sid,_=saved(tools,'completion',text,read=True)
    old=check('What did the Orion opening notice promise?',sid,status='planned',detail='A June opening was planned.')
    missing=check('Who initiated Orion?',status='missing',detail='The initiator is unknown.')
    record_checks(state,[old,missing]);state.save()
    resumed=SearchState(tmp_path,'case')
    current=check('Did Orion open?',sid,mark(sid,0,text))
    current['replaces']=[old['question']]
    action=finish([sid])
    action.update(fact_checks=[current],gaps=[old['question']+': planned; A June opening was planned.'])
    commit_evidence(resumed,action)
    finish_review(resumed,action)
    assert {c['question'] for c in resumed.data['fact_checks']}=={current['question'],missing['question']}
    assert not any(old['question'] in g for g in action['gaps'])
    assert any(missing['question'] in g for g in action['gaps'])
    before=deepcopy(resumed.data['fact_checks'])
    record_checks(resumed,[current])
    assert resumed.data['fact_checks']==before
    assert action['reason']=='low_gain'  # The unrelated initiation question remains unresolved.
    renamed=dict(current,question='Was the Orion opening completed?',replaces=[current['question']])
    action.update(fact_checks=[renamed],gaps=[old['question']+': planned; old announcement'])
    commit_evidence(resumed,action)
    finish_review(resumed,action)
    assert not any(old['question'] in g for g in action['gaps'])
    assert {c['question'] for c in resumed.data['fact_checks']}=={renamed['question'],missing['question']}


def test_invalid_question_merge_is_atomic(tmp_path):
    state,tools=setup(tmp_path)
    record_checks(state,[check('Who initiated Orion?',status='missing',detail='Unknown.')])
    before=deepcopy(state.data)
    bad=check('Did Orion open?',status='missing',detail='Unknown.');bad['replaces']=['Invented old question']
    record_checks(state,[bad])
    assert state.data['fact_checks']==before['fact_checks']
    assert 'saved question' in state.data['evidence_feedback']['fact_checks']['rejected'][0]['reason']


def test_cursor_read_does_not_reset_same_question_no_gain_guard(tmp_path):
    state,tools=setup(tmp_path,max_read_chars=90)
    text='\n\n'.join(f'Orion approval involved local families from district {i}.' for i in range(20))
    sid,_=saved(tools,'report',text);tools.sources.can_complete_partial=False
    q='Did Orion receive local approval?'
    first=tools.read_source(sid,query='Orion approval local families',question=q,agent_feedback=True)
    second=tools.read_source(sid,location={'block':4},question=q,agent_feedback=True)
    assert first['spans'] and second['spans']
    resumed=SearchState(tmp_path,'case');other=SearchTools(resumed);other.sources.can_complete_partial=False
    blocked=other.read_source(sid,query='district participation authorization',question=q,agent_feedback=True)
    assert blocked['reading']['match_status']=='no_evidence_gain'
    span=second['spans'][0]
    record_passages(resumed,[dict(source_id=sid,**{k:span[k] for k in ('block','start','end')})])
    assert other.read_source(sid,query='district participation authorization',question=q,agent_feedback=True).get('reading',{}).get('match_status')!='no_evidence_gain'
    # A new explicit location is still available; a fresh question is not blocked.
    assert other.read_source(sid,location={'block':9},question=q,agent_feedback=True)['spans']
    assert other.read_source(sid,query='Orion education funding',question='Who funded Orion?',agent_feedback=True).get('reading',{}).get('match_status')!='no_evidence_gain'


def test_numeric_abbreviation_can_reach_the_model_without_a_full_name(tmp_path):
    state,tools=setup(tmp_path)
    state.data['task']['retrieval_constraints']={'event_id':'target'}
    text='In October, the OP units were transferred and we received 7,321 shares.'
    bad,_=saved(tools,'wrong-event',text,scope={'event_id':'other'})
    sid,doc=saved(tools,'report',text)
    state.data['sources'][sid]['title']='Quarterly report'
    state.data['actions']=[dict(action='read_source',source=sid,query='received 7,321 shares')]
    candidates=context_for(state)['cached_evidence']
    assert sid in {c['source_id'] for c in candidates} and bad not in {c['source_id'] for c in candidates}
    assert any(s['text']==text for c in candidates if c['source_id']==sid for s in c['spans'])
    assert not state.data.get('priority_passages') and tools.sources.document(sid)==doc


def test_source_language_query_ranks_long_chinese_cache_without_name_translation(tmp_path):
    state,tools=setup(tmp_path)
    lead='这里记录其他社区的日常会议安排。'*130
    answer='晨星计划规定，在资金到账以前，负责人不得出售超过百分之十的股份。'
    text=lead+answer
    sid=tools.sources.register('https://example.org/chinese',title='晨星计划报道')
    doc=tools.sources.save_raw(sid,text.encode(),'txt',partial=True,
                              parsed=dict(status='success',blocks=[dict(text=text)]))
    state.data['actions']=[dict(action='search',query='Orion executive share sale restrictions',
                               provider_queries={'baidu':'晨星计划 负责人 股份 出售 限制'})]
    candidates=context_for(state)['cached_evidence']
    spans=[s for c in candidates if c['source_id']==sid for s in c['spans']]
    assert any(answer in s['text'] for s in spans)
    assert all(doc['blocks'][s['block']]['text'][s['start']:s['end']]==s['text'] for s in spans)
    assert not state.data.get('priority_passages')


def test_shared_preview_budget_keeps_latest_read_without_replaying_old_marks(tmp_path):
    state,tools=setup(tmp_path,max_read_chars=4000)
    for i in range(12):
        sid,_=saved(tools,str(i),f'Orion MARKED_{i} announced funding.\n\n'+
                    (f'Orion district {i} asked about consent before opening. '*20),read=True)
    state.data['priority_passages']=[m for m in state.data['priority_passages'] if m['block']==0]
    state.data['feedback']=tools.read_source(sid,location={'block':1})
    before=deepcopy(state.data)
    context=context_for(state)
    previews=[s for source in context['sources'] for s in source.get('read_evidence',[])]
    assert 0<sum(len(json.dumps(s,ensure_ascii=False))+32 for s in previews)<=4000
    assert 'spans' not in (context.get('feedback') or {})
    assert any('district 11' in s['text'] for s in previews)
    assert all('MARKED_0 ' not in s['text'] for s in previews)
    assert state.data==before


def test_request_prefix_does_not_change_when_reading_state_changes(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'report','Ada Vale stipulated local consent for Orion.')
    first=context_for(state);record_presented(state,first['cached_evidence'])
    text=first['cached_evidence'][0]['spans'][0]['text']
    record_passages(state,[mark(sid,0,text)])
    state.data['usage']['model']+=1
    second=context_for(state)
    a,b=map(model_context,(first,second))
    assert a!=b and a.split('"source_leads":')[0]==b.split('"source_leads":')[0]
    request=json.loads(b)
    assert request['source_catalog'][0]['title']==state.data['sources'][sid]['title']
    assert 'title' not in request['sources'][0]
    assert not second['sources'][0].get('read_evidence')


def test_presented_but_rejected_condition_never_becomes_automatic_support(tmp_path):
    state,tools=setup(tmp_path)
    kept,_=saved(tools,'notice','Orion opened in June.',read=True)
    candidate,_=saved(tools,'condition','Ada Vale stipulated local consent before opening Orion.')
    calls=[]
    def decide(context):
        calls.append(context)
        if len(calls)==1:
            assert candidate in {c['source_id'] for c in context['cached_evidence']}
        return finish([kept],fact_checks=[check('What additional conditions applied?',
                      status='missing',detail='The offered condition has not been accepted as support.')],
                      passage_exclusions={r['passage_id']:'This condition does not concern the requested program phase.'
                                          for r in context_passages(context)})
    run_agent(state,tools,decide)
    assert len(calls)<=2 and state.data['status']=='finished' and state.data['stop_reason']=='low_gain'
    assert all(m['source_id']!=candidate for m in state.data['priority_passages'])
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert {s['raw_data_id'] for s in payload['samples']}=={kept}


def test_title_and_first_person_footer_do_not_trigger_finish_review(tmp_path):
    state,tools=setup(tmp_path)
    kept,_=saved(tools,'notice','Orion opened in June.',read=True)
    title='# Ada Vale on the Orion program'
    footer='I agree to receive marketing messages. I will not receive updates unless I opt in.'
    sid,_=saved(tools,'article',title+'\n\n'+footer)
    state.data['sources'][sid]['title']='Ada Vale on the Orion program | News'
    feedback=execute_action(state,tools,finish([kept]))
    assert 'candidates' not in feedback and not state.data.get('finish_candidate_review')
    assert not state.data['sources'][sid].get('read_ranges')
