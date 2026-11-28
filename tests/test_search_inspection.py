"""Shown evidence must receive a decision; unrelated errors cannot discard selections."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import SYSTEM_PROMPT, context_for, execute_action, model_context, run_agent
from finmy.search.inspection import (accept_presentation, context_passages, passage_id,
                                     pending_passages)
from finmy.search.progress import NO_PROGRESS_LIMIT
from finmy.search.review import record_checks
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_evidence_routing import check
from test_search_integrated_review import mark


def unselected(tools, name, text):
    sid, doc = saved(tools, name, text, read=True)
    tools.state.data['priority_passages'] = [m for m in tools.state.data['priority_passages'] if m['source_id'] != sid]
    return sid, doc


def selected_text(state):
    return '\n'.join(s['content'] for s in json.loads((state.run_dir/'builder_input.json').read_text())['samples'])


def test_supported_broad_question_cannot_hide_shown_condition_after_resume(tmp_path, monkeypatch):
    state, tools = setup(tmp_path)
    accepted = 'Ada Vale accepted the invitation to support the Orion program.'
    condition = 'ADA VALE: If the local council would not act, I would not fund Orion.'
    sid, doc = unselected(tools, 'interview', accepted+'\n\n'+condition)
    record_checks(state, [check('Did Ada accept?', sid, mark(sid,0,accepted))], mark_support=True)
    monkeypatch.setattr(tools, 'read_source', lambda *a, **k: pytest.fail('No reread'))
    calls = []
    def ignore(context):
        calls.append(context)
        assert condition in str(context)
        return finish([sid])
    run_agent(state, tools, ignore, max_steps=1)
    assert state.data['feedback']['kind']=='pending_evidence'
    assert not state.data.get('actions') and not (state.run_dir/'builder_input.json').exists()
    assert len(pending_passages(state))==1
    assert state.data['fact_checks'][0]['status']=='supported'

    restored = SearchState(tmp_path, 'case')
    def keep(context):
        row, = context['pending_evidence']
        assert row['text']==condition and not context.get('cached_evidence')
        return finish([sid], fact_checks=[check('What did Ada require?',sid,mark(sid,1,condition))])
    run_agent(restored, SearchTools(restored), keep)
    assert restored.data['usage']=={'model':2,'search':0}
    assert not pending_passages(restored)
    assert condition in selected_text(restored)
    assert len(restored.data['actions'])==1
    assert tools.sources.document(sid)==doc


@pytest.mark.parametrize('extra', [{'replaces':['Old question']}, {'block':0,'query':'Orion'},
                                   {'source':False}, {'action':'unknown'}])
def test_valid_selection_commits_before_invalid_next_action(tmp_path, extra):
    state, tools = setup(tmp_path)
    text='Ada Vale described Orion as an exceptional program.'
    sid, doc = unselected(tools,'evaluation',text)
    accept_presentation(state,context_for(state))
    action=dict(action='read_source',source=sid,location={'block':0},
                fact_checks=[check('How did Ada evaluate Orion?',sid,mark(sid,0,text))])
    action.update(extra)
    with pytest.raises(ValueError):
        execute_action(state,tools,action)
    restored=SearchState(tmp_path,'case')
    assert len(restored.data['priority_passages'])==1
    assert restored.data['fact_checks'][0]['status']=='supported'
    assert not pending_passages(restored)
    execute_action(restored,SearchTools(restored),finish([sid]))
    assert text in selected_text(restored)
    assert tools.sources.document(sid)==doc


@pytest.mark.parametrize('status', ['planned','missing','conflicting'])
def test_partial_evidence_survives_other_bad_fact_and_tool_still_runs(tmp_path,status):
    state,tools=setup(tmp_path)
    text='The committee announced that Ada Vale would receive the Orion grant in June.'
    sid,_=unselected(tools,'announcement',text)
    accept_presentation(state,context_for(state))
    calls=[]
    tools.read_source=lambda *a,**k: calls.append((a,k)) or dict(spans=[])
    good=check('Was the grant actually received?',sid,mark(sid,0,text),status=status,
               detail='An announcement is available; actual receipt is unresolved.')
    bad=check('Did the program expand?',status='planned',detail='')
    feedback=execute_action(state,tools,dict(action='read_source',source=sid,query='receipt',
        question='Who confirmed receipt?',fact_checks=[bad,good]))
    assert len(calls)==1 and not feedback.get('operation_deferred')
    assert state.data['fact_checks'][0]['status']==status
    assert len(state.data['priority_passages'])==1 and not pending_passages(state)
    assert state.data['evidence_feedback']['fact_checks']['rejected'][0]['index']==0
    execute_action(state,tools,finish([sid]))
    assert text in selected_text(state)
    assert state.data['fact_checks'][0]['status']==status
    assert state.data['stop_reason']=='low_gain'


def test_bad_rename_preserves_old_question_and_other_valid_updates(tmp_path):
    state,tools=setup(tmp_path)
    text='Ada Vale approved Orion subject to local consent.'
    sid,_=unselected(tools,'condition',text)
    old=check('Was Orion completed?',status='planned')
    record_checks(state,[old])
    updates=[dict(check('Was receipt confirmed?',status='missing'),replaces=[old['question']]),
             dict(old,detail=''),check('What condition applied?',sid,mark(sid,0,text))]
    record_checks(state,updates,mark_support=True)
    assert state.data['fact_checks'][0]==old
    assert len(state.data['fact_checks'])==2 and len(state.data['priority_passages'])==1
    assert len(state.data['evidence_feedback']['fact_checks']['rejected'])==2


def test_partial_mark_keeps_tail_pending_and_exclusion_only_covers_shown_remainder(tmp_path):
    state,tools=setup(tmp_path)
    first='Ada Vale accepted the Orion invitation.'
    tail=' Work could begin only after local consent.'
    sid,doc=unselected(tools,'condition',first+tail)
    context=context_for(state)
    shown,=list(context_passages(context))
    accept_presentation(state,context)
    feedback=execute_action(state,tools,finish([sid],priority_passages=[mark(sid,0,first)],
        source_exclusions={sid:'Does not decide the passage remainder.'}))
    assert feedback['operation_deferred']
    assert pending_passages(state)==[dict(source_id=sid,version=doc['version'],block=0,start=len(first),end=len(first+tail))]
    context=context_for(state)
    row,=context['pending_evidence']
    assert row['text']==tail and row['passage_id']!=shown['passage_id']
    accept_presentation(state,context)
    feedback=execute_action(state,tools,finish([sid],passage_exclusions={row['passage_id']:''}))
    assert feedback['operation_deferred'] and state.data['evidence_feedback']['passage_exclusions']['rejected']
    # An explicit exclusion resolves only this shown remainder; already kept text survives.
    execute_action(state,tools,finish([sid],passage_exclusions={row['passage_id']:'Condition is outside this narrowed task.'}))
    assert not pending_passages(state) and first in selected_text(state) and tail not in selected_text(state)


def test_only_actual_context_is_pending_and_excluded_ranges_are_not_reoffered(tmp_path):
    state,tools=setup(tmp_path,max_model_context_chars=len(SYSTEM_PROMPT)+6500)
    body='\n\n'.join(f'Ada Vale discussed Orion district {i}: '+ 'Public program details. '*18 for i in range(20))
    sid,doc=unselected(tools,'long',body)
    before=deepcopy(state.data['sources'][sid]['read_ranges'])
    context=context_for(state)
    assert len(SYSTEM_PROMPT)+len(model_context(context))<=state.config.max_model_context_chars
    rows=list(context_passages(context))
    assert rows and {r['block'] for r in rows} < {r['block'] for r in before}
    assert not state.data.get('passage_reviews')
    accept_presentation(state,context)
    assert len(state.data['passage_reviews'])==len(rows)
    assert state.data['sources'][sid]['read_ranges']==before
    execute_action(state,tools,dict(action='read_source',source=sid,location={'block':0},
        passage_exclusions={r['passage_id']:'Repeated district background.' for r in rows}))
    assert not pending_passages(state)
    next_rows=list(context_passages(context_for(state)))
    assert not any(a['block']==b['block'] and a['start']<b['end'] and a['end']>b['start']
                   for a in rows for b in next_rows)
    assert tools.sources.document(sid)==doc


def test_failed_call_or_context_construction_does_not_establish_presentation(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'cache','ADA VALE: Orion could proceed only after local consent.')
    before=deepcopy(state.data)
    assert context_for(state)['cached_evidence']
    assert state.data==before
    def fail(_):raise RuntimeError('Synthetic request failure')
    run_agent(state,tools,fail,max_steps=1)
    assert not state.data.get('passage_reviews') and not state.data['sources'][sid].get('read_ranges')


def test_malformed_reply_still_records_shown_originals(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'cache','ADA VALE: Orion could proceed only after local consent.')
    run_agent(state,tools,lambda _: 'invalid json',max_steps=1)
    assert pending_passages(state) and state.data['sources'][sid]['read_ranges']
    assert not state.data.get('priority_passages')


def test_new_version_requires_new_decisions_and_preserves_old_coordinates(tmp_path):
    state,tools=setup(tmp_path)
    sid,doc=unselected(tools,'notice','Ada Vale approved Orion.')
    context=context_for(state);accept_presentation(state,context)
    old,=state.data['passage_reviews']
    execute_action(state,tools,finish([],passage_exclusions={old:'Repetition.'}))
    newdoc=tools.sources.save_raw(sid,b'Ada Vale cancelled Orion.', 'txt')
    tools.read_source(sid,location={'block':0})
    assert not pending_passages(state)
    newcontext=context_for(state);accept_presentation(state,newcontext)
    assert pending_passages(state)[0]['version']==newdoc['version']
    assert state.data['passage_reviews'][old]['version']==doc['version']
    assert passage_id(sid,newdoc['version'],dict(block=0,start=0,end=25))!=old


@pytest.mark.parametrize('max_calls', [1, 20])
def test_ignored_passages_have_bounded_retries_and_located_final_gaps(tmp_path,max_calls):
    state,tools=setup(tmp_path,max_model_calls=max_calls)
    kept,_=saved(tools,'notice','The Orion program was announced.',read=True)
    sid,doc=unselected(tools,'condition','Ada Vale required local consent before funding Orion.')
    run_agent(state,tools,lambda _:finish([kept,sid]))
    assert state.data['usage']['model']<=min(max_calls,NO_PROGRESS_LIMIT+1)
    assert state.data['usage']['search']==0 and state.data['stop_reason']=='low_gain'
    report=json.loads((state.run_dir/'selection.json').read_text())
    assert any(sid in g and doc['version'] in g and 'block=0' in g for g in report['gaps'])
    assert 'required local consent' not in selected_text(state)
    assert pending_passages(state)  # Never silently converted to an exclusion or evidence.


def test_cache_selection_and_exclusion_finish_in_the_same_call(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'interview','QUESTION: What did Orion require?\n\nADA VALE: Orion required local consent.')
    def decide(context):
        rows=list(context_passages(context))
        useful=[r for r in rows if 'ADA VALE' in r['text']]
        rest=[r for r in rows if r not in useful]
        return finish([sid],priority_passages=[{k:r[k] for k in ('source_id','version','block','start','end')} for r in useful],
                      passage_exclusions={r['passage_id']:'Interviewer question adds no distinct evidence.' for r in rest})
    run_agent(state,tools,decide)
    assert state.data['usage']=={'model':1,'search':0}
    assert not pending_passages(state)
    assert 'Orion required local consent.' in selected_text(state)


def test_pending_text_without_context_room_finishes_instead_of_retrying_blindly(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=unselected(tools,'condition','Ada Vale required local consent before funding Orion.')
    accept_presentation(state,context_for(state))
    context=context_for(state)
    context.pop('pending_evidence');context.pop('pending_evidence_count')
    context.pop('evidence_review')  # Charge the forthcoming review contract separately.
    state.config.max_model_context_chars=len(SYSTEM_PROMPT)+len(model_context(context))+1024+50
    constrained=context_for(state)
    assert constrained['pending_evidence']==[]
    assert constrained['phase']=='finalize' and constrained['finalization_reason']=='context_limit'
    assert len(SYSTEM_PROMPT)+len(model_context(constrained))<state.config.max_model_context_chars
    assert pending_passages(state)[0]['source_id']==sid


def test_old_finish_preview_cannot_bypass_shared_excerpt_budget(tmp_path):
    state,tools=setup(tmp_path,max_read_chars=200)
    text='Ada Vale required local consent before funding Orion.'
    sid,_=saved(tools,'condition',text)
    state.data['feedback']=dict(kind='finish_candidate_review',candidates=[dict(
        source_id=sid,spans=[dict(text=text*1000)])])
    before=deepcopy(state.data)
    context=context_for(state)
    assert 'candidates' not in context['feedback']
    assert len(SYSTEM_PROMPT)+len(model_context(context))<state.config.max_model_context_chars
    assert sum(len(r['text']) for r in context_passages(context))<=200
    assert state.data==before
