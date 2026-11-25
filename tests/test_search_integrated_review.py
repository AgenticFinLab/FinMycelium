"""Evidence survives the read/mark/deliver boundary without paid services."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.evidence import record_passages
from finmy.search.handoff import prepare_complete_sources, derive_input
from finmy.search.review import delivered_checks
from finmy.search.retrieval import cached_candidates
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline


def mark(sid, block, text, **fields):
    return dict(source_id=sid,block=block,start=0,end=len(text),**fields)


def test_partially_read_or_excluded_source_still_offers_distinct_passage(tmp_path):
    state,tools = setup(tmp_path)
    known = 'Ada Vale announced the Orion education program.'
    kept,_ = saved(tools,'release',known,read=True)
    response = 'Ada Vale told the committee that she would support Orion only if local families approved.'
    sid,doc = saved(tools,'interview',known+'\n\n'+response)
    # A saved checkpoint with only the repeated announcement inspected.
    state.data['sources'][sid]['read_ranges'] = [dict(version=doc['version'],block=0,start=0,end=len(known))]
    state.data['read_sources'].append(sid)
    candidates = cached_candidates(state,finish([kept],source_exclusions={sid:'The announcement is repeated.'}))
    chosen = next(c for c in candidates if c['source_id']==sid)
    assert [s['text'] for s in chosen['spans']] == [response]
    assert chosen['reading_status']=='cached_unread'
    # This same passage is still eligible when already read but not marked.
    state.data['sources'][sid]['read_ranges'].append(dict(version=doc['version'],block=1,start=0,end=len(response)))
    chosen = next(c for c in cached_candidates(state,finish([kept])) if c['source_id']==sid)
    assert chosen['reading_status']=='read_unmarked'
    context = context_for(state)
    source = next(s for s in context['sources'] if s['source_id']==sid)
    assert any(s['text']==response and s['mark_status']=='unmarked' for s in source['read_evidence'])


def test_read_unmarked_remains_eligible_at_source_limit(tmp_path):
    state,tools = setup(tmp_path,max_read_sources=1)
    text = 'Ada Vale stipulated that Orion needed local approval.'
    sid,doc = saved(tools,'interview',text)
    state.data['sources'][sid]['read_ranges']=[dict(version=doc['version'],block=0,start=0,end=len(text))]
    state.data['read_sources']=[sid]
    assert cached_candidates(state,finish([sid]))[0]['source_id']==sid


def test_report_person_mentions_and_question_only_blocks_do_not_trigger_review(tmp_path):
    state,tools = setup(tmp_path)
    kept,_ = saved(tools,'release','Ada Vale approved the Orion education commitment.',read=True)
    report = 'General accounts.\n\n'+'\n\n'.join(['Ada Vale chairs the board.']*85)
    saved(tools,'report',report)
    saved(tools,'question','INTERVIEWER: Did Ada Vale approve the Orion commitment?')
    action = finish([kept],fact_checks=[dict(question='Was Orion approved?',status='supported',source_ids=[kept],detail='Approved.',
        evidence=[mark(kept,0,'Ada Vale approved the Orion education commitment.')])])
    assert cached_candidates(state,action)==[]
    run_agent(state,tools,lambda _:action)
    assert state.data['status']=='finished' and state.data['usage']['model']==1


def test_actual_copied_quote_does_not_hide_a_phone_response(tmp_path):
    state,tools = setup(tmp_path)
    quote = ('We welcome Ada Vale and the Orion commitment. '*10).strip()
    kept,_ = saved(tools,'release','The director said: "'+quote+'"',read=True)
    phone = 'Ada Vale told a reporter by telephone that she required local consent before approving Orion.'
    repeated = 'The director returned the compliment to Ada Vale: "'+quote+'"'
    sid,_ = saved(tools,'interview',repeated+'\n\n'+phone)
    checks=[dict(question='Was the commitment announced?',status='supported',source_ids=[kept],detail='Yes.')]
    chosen=next(c for c in cached_candidates(state,finish([kept],fact_checks=checks)) if c['source_id']==sid)
    assert phone in [s['text'] for s in chosen['spans']]


def test_unattempted_personal_research_remains_a_gap_without_finish_rescan(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'release','The Orion program was announced.',read=True)
    action=finish([sid],person_evidence=dict(status='unattempted',detail='Only the announcement was checked.'))
    feedback=execute_action(state,tools,action)
    assert 'next_steps' not in feedback and 'candidates' not in feedback
    assert any('unattempted' in gap for gap in feedback['gaps'])
    assert state.data['status']=='finished'
    assert state.data['stop_reason']=='low_gain'
    assert state.data['usage']=={'model':0,'search':0}


def test_explicit_inspected_citation_is_marked_in_the_same_decision(tmp_path):
    state,tools=setup(tmp_path)
    first='Ada Vale announced plans for the Orion education program.'
    actual='Ada Vale confirmed that Orion had opened after local consent.'
    sid,doc=saved(tools,'outcome',first+'\n\n'+actual,read=True)
    # Start from an inspected source whose final sentence was missed by marking.
    state.data['priority_passages']=[p for p in state.data['priority_passages'] if p['block']==0]
    ref=mark(sid,1,actual)
    check=dict(question='Did Orion actually open?',status='supported',source_ids=[sid],
               detail='Orion opened after local consent.',evidence=[ref])
    action=finish([sid],fact_checks=[check])
    run_agent(state,tools,lambda _:deepcopy(action),max_steps=1)
    assert state.data['status']=='finished' and state.data['usage']=={'model':1,'search':0}
    selected=json.loads((state.run_dir/'selection.json').read_text())
    assert selected['fact_checks'][0]['citation_status']=='delivered'
    assert not selected['delivery_issues']
    assert actual in (state.run_dir/'builder_input.json').read_text()
    assert not state.data.get('finish_candidate_review')
    assert tools.sources.document(sid,doc['version'])==doc


def test_forced_finish_cannot_claim_undelivered_support(tmp_path):
    state,tools=setup(tmp_path)
    first='Ada Vale announced the Orion program.'
    actual='Ada Vale confirmed completion of Orion after local approval.'
    sid,_=saved(tools,'outcome',first+'\n\n'+actual,read=True)
    state.data['priority_passages']=[p for p in state.data['priority_passages'] if p['block']==0]
    state.data['finalization_trigger']='model_call_budget'
    check=dict(question='Was Orion completed?',status='supported',source_ids=[sid],
               detail='The program was completed.',evidence=[dict(mark(sid,1,actual),version='obsolete')])
    execute_action(state,tools,finish([sid],fact_checks=[check],reason_detail=check['detail']))
    selection=json.loads((state.run_dir/'selection.json').read_text())
    assert state.data['stop_reason']==selection['reason']=='low_gain'
    assert state.data['fact_checks'][0]['status']==selection['fact_checks'][0]['status']=='missing'
    assert check['detail'] not in state.data['stop_detail']
    assert 'Supporting original was not delivered' in str(selection['gaps'])
    assert not (state.data.get('finish_candidate_review'))


@pytest.mark.parametrize('ref',[
    dict(source_id='s',block=0,start=0,end=10),
    dict(source_id='s',version='old',block=0,start=0,end=4),
    dict(source_id=['s'],block=0,start=0,end=4),
])
def test_citations_reject_holes_old_versions_and_invalid_ids(ref):
    checks=[dict(question='Did it happen?',status='supported',source_ids=['s'],detail='It happened.',evidence=[ref])]
    selected=[dict(source_id='s',version='new',ranges=[dict(block=0,start=0,end=4),dict(block=0,start=6,end=10)])]
    result,issues=delivered_checks(checks,selected)
    assert issues and result[0]['status']=='missing'


def test_partial_duplicate_keeps_the_sources_other_evidence(tmp_path):
    state,tools=setup(tmp_path)
    statement='Ada Vale approved the Orion commitment.'
    extra='Ada Vale made the Orion commitment conditional on local consent.'
    ids=[]
    for name,prefix in [('release','Official notice.'),('repost','Reposted notice.')]:
        sid,_=saved(tools,name,prefix+'\n\n'+statement+('\n\n'+extra if name=='repost' else ''),read=True)
        ids.append(sid)
    state.data['priority_passages']=[]
    for sid in ids:
        record_passages(state,[mark(sid,1,statement,evidence_role='corroboration',independence_key=sid)])
    record_passages(state,[mark(ids[1],2,extra,evidence_role='condition')])
    _,complete=prepare_complete_sources(state,ids)
    payload,selection=derive_input(state,complete)
    body='\n'.join(s['content'] for s in payload['samples'])
    assert body.count(statement)==1 and extra in body
    assert any(d['status']=='redundant' for d in selection['allocation']['priority_decisions'])


@pytest.mark.parametrize('with_header',[True,False])
def test_table_rows_keep_original_units_and_never_invent_headers(tmp_path,with_header):
    state,tools=setup(tmp_path)
    header='Shares | Company | Value (millions)'
    table='| 40 | Elsewhere | 2 |\n| --- | --- | --- |\n| 50 | Orion | 3 |\n| 60 | Unrelated | 4 |'
    sid,doc=saved(tools,'table',header+'\n\n'+table,read=True)
    state.data['priority_passages']=[]
    record_passages(state,[mark(sid,1,table)])
    if with_header:record_passages(state,[mark(sid,0,header)])
    _,complete=prepare_complete_sources(state,[sid]); payload,selection=derive_input(state,complete)
    body=payload['samples'][0]['content']
    assert '| 50 | Orion | 3 |' in body
    if with_header:
        assert header in body and 'Elsewhere' not in body and 'Unrelated' not in body
        assert any(d.get('selection')=='target_table_rows' for d in selection['allocation']['priority_decisions'])
    else:
        assert table in body
    assert tools.sources.document(sid,doc['version'])==doc
    # Frozen old policies still use their original marked spans.
    complete.pop('evidence_policy');complete.pop('complete_id');complete['complete_id']=digest(complete)
    assert table in derive_input(state,complete)[0]['samples'][0]['content']


def test_third_party_comment_does_not_outrank_the_persons_own_statement(tmp_path):
    state,tools=setup(tmp_path)
    kept,_=saved(tools,'release','The Orion program launched.',read=True)
    analyst='Ada Vale is "taking less risk," said analyst Iris Fox about the Orion program.'
    original='Ada Vale told Iris Fox by telephone that she welcomed the Orion agreement.'
    sid,_=saved(tools,'interview',analyst+'\n\n'+original)
    checks=[dict(question='Did Orion launch?',status='supported',source_ids=[kept],detail='Yes.')]
    chosen=next(c for c in cached_candidates(state,finish([kept],fact_checks=checks)) if c['source_id']==sid)
    assert chosen['spans'][0]['text']==original


def test_short_chinese_original_is_not_filtered_by_english_length(tmp_path):
    state,tools=setup(tmp_path)
    text='Ada Vale表示，她支持Orion计划，但需要社区同意。'
    sid,_=saved(tools,'interview',text)
    assert any(c['source_id']==sid for c in cached_candidates(state,finish([])))


def test_legacy_full_block_selection_accepts_located_fact_check(tmp_path):
    state,tools=setup(tmp_path)
    state.data.pop('retrieval_plan',None)
    text='Ada Vale approved the Orion commitment.'
    sid,_=saved(tools,'release',text,read=True)
    state.data['finalization_trigger']='model_call_budget'
    check=dict(question='Was Orion approved?',status='supported',source_ids=[sid],detail='Approved.',
               evidence=[mark(sid,0,text)])
    execute_action(state,tools,finish([sid],fact_checks=[check],person_evidence=[]))
    assert state.data['fact_checks'][0]['citation_status']=='delivered'
