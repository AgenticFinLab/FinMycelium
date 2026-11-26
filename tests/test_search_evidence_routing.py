"""Keep inspected support, gap routing and the delivered assessment consistent."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.evidence import record_passages
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.review import delivery_steps, record_checks
from finmy.search.state import SearchState, digest
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_integrated_review import mark


def check(question, sid=None, ref=None, *, status='supported', detail='The inspected answer supports this fact.'):
    return dict(question=question,status=status,source_ids=[sid] if sid else [],detail=detail,
                **({'evidence':[ref]} if ref else {}))


def test_cited_answer_wins_same_labels_without_another_call(tmp_path,monkeypatch):
    state,tools=setup(tmp_path)
    question='INTERVIEWER: What did you propose for Orion?'
    answer='ADA VALE: I proposed that Orion obtain community consent, and the board accepted those terms.'
    sid,doc=saved(tools,'interview',question+'\n\n'+answer,read=True)
    state.data['priority_passages']=[]
    fields=dict(fact_ids=['negotiation'],claim_id='negotiated',evidence_role='personal')
    record_passages(state,[mark(sid,0,question,**fields),mark(sid,1,answer,**fields)])
    fact=check('What did Ada propose?',sid,mark(sid,1,answer),detail='Ada proposed the conditions and the board accepted.')
    person=dict(status='supported',detail='Unsupported extra assertion.',questions=[fact['question']])
    calls=[]
    def derive(*args,**kwargs):
        calls.append(1)
        return derive_input(*args,**kwargs)
    monkeypatch.setattr('finmy.search.agent.derive_input',derive)
    run_agent(state,tools,lambda _:finish([sid],fact_checks=[fact],person_evidence=person))
    assert state.data['status']=='finished' and state.data['usage']=={'model':1,'search':0}
    assert len(calls)==1
    body=json.loads((state.run_dir/'builder_input.json').read_text())['samples'][0]['content']
    assert answer in body and question not in body
    selection=json.loads((state.run_dir/'selection.json').read_text())
    assert not selection['delivery_issues']
    assert state.data['fact_checks']==selection['fact_checks']
    assert state.data['person_evidence']==selection['person_evidence']
    assert state.data['person_evidence']['detail']==fact['detail']
    assert tools.sources.document(sid)==doc

    # Previously frozen manifests keep their original selection behavior.
    frozen=json.loads((state.run_dir/'complete_material.json').read_text())
    frozen['evidence_policy']='located_delivery_v1'
    frozen.pop('complete_id');frozen['complete_id']=digest(frozen)
    old,report=derive_input(state,frozen)
    assert question in old['samples'][0]['content'] and answer not in old['samples'][0]['content']
    assert report['delivery_issues']


def test_distinct_cited_answers_survive_shared_claim_and_respect_budget(tmp_path):
    state,tools=setup(tmp_path)
    answers=['Ada Vale proposed local consent for Orion.',
             'Ada Vale reported that the Orion board accepted her proposal.']
    sid,_=saved(tools,'interview','\n\n'.join(answers),read=True)
    state.data['priority_passages']=[]
    marks=[mark(sid,b,text,fact_ids=['negotiation'],claim_id='negotiated',evidence_role='personal')
           for b,text in enumerate(answers)]
    record_passages(state,marks)
    record_checks(state,[check('What was proposed?',sid,marks[0]),check('Was it accepted?',sid,marks[1])])
    _,complete=prepare_complete_sources(state,[sid],reason='supported')
    payload,selected=derive_input(state,complete)
    assert all(a in payload['samples'][0]['content'] for a in answers)
    assert not selected['delivery_issues']
    limited,report=derive_input(state,complete,max_chars=1)
    assert not limited['samples'] and report['reason']=='low_gain'
    assert report['delivery_issues'] and report['material_chars']<=1


@pytest.mark.parametrize('case,expected',[
    ('unread','read_source'),('unmarked','mark_passage'),
    ('excluded','revise_selection'),('old_version','correct_citation'),
])
def test_located_support_routes_to_its_actual_stage(tmp_path,case,expected):
    state,tools=setup(tmp_path)
    text='Ada Vale confirmed completion of Orion after local approval.'
    sid,doc=saved(tools,'outcome',text,read=case!='unread')
    ref=mark(sid,0,text)
    if case=='unmarked': state.data['priority_passages']=[]
    if case=='old_version': ref['version']='obsolete'
    before=deepcopy(state.data)
    steps=delivery_steps(state,[dict(question='Was Orion completed?',source_ids=[sid],evidence=[ref])])
    assert len(steps)==1 and steps[0]['remedy']==expected
    if case=='unread': assert steps[0]['location']=={'block':0,'offset':0}
    assert state.data==before and tools.sources.document(sid)==doc


def test_ordinary_actions_save_separate_questions_and_finish_cannot_forget_them(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'announcement','The Orion program was announced.',read=True)
    questions=[check('Who initiated the approach?',status='missing',detail='No initiation evidence found.'),
               check('Was the transfer completed?',status='planned',detail='Only a future commitment is known.')]
    run_agent(state,tools,lambda _:dict(action='read_source',source=sid,location={'block':0},
                                      fact_checks=questions),max_steps=1)
    restored=SearchState(tmp_path,'case')
    assert context_for(restored)['fact_checks']==questions
    # Finishing without restating these questions cannot silently erase them.
    steps=context_for(restored)['next_steps']
    assert {s['question'] for s in steps}=={c['question'] for c in questions}
    assert all(s['remedy']=='search' for s in steps)
    feedback=execute_action(restored,SearchTools(restored),finish([sid],fact_checks=[]))
    assert all(any(c['question'] in gap for gap in feedback['gaps']) for c in questions)
    assert restored.data['status']=='finished' and restored.data['stop_reason']=='low_gain'
    assert {c['question'] for c in restored.data['fact_checks']}=={c['question'] for c in questions}


def test_names_alone_do_not_make_cached_background_answer_a_missing_question(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'notice','The Orion program was announced.',read=True)
    background,_=saved(tools,'background','Ada Vale visited the Orion cafeteria.')
    fact=check('Who introduced Ada Vale to Orion?',status='missing',detail='No introduction source found.')
    record_checks(state,[fact])
    assert context_for(state)['next_steps'][0]['remedy']=='search'
    feedback=execute_action(state,tools,finish([sid],fact_checks=[]))
    assert 'candidates' not in feedback and 'next_steps' not in feedback
    assert state.data['status']=='finished' and state.data['stop_reason']=='low_gain'
    assert any(fact['question'] in gap for gap in feedback['gaps'])
    assert not state.data['sources'][background].get('read_ranges')


@pytest.mark.parametrize('linked',[True,False])
def test_missing_delivery_clears_person_claim_in_output_and_checkpoint(tmp_path,linked):
    state,tools=setup(tmp_path)
    first='Ada Vale announced plans for Orion.'
    outcome='Ada Vale confirmed completion of Orion.'
    sid,_=saved(tools,'outcome',first+'\n\n'+outcome,read=True)
    state.data['priority_passages']=[m for m in state.data['priority_passages'] if m['block']==0]
    state.data['finalization_trigger']='model_call_budget'
    # A cited but obsolete source version cannot be rescued by automatic marking.
    facts=[check('Did Ada announce plans?',sid,mark(sid,0,first),detail='Ada announced plans.'),
           check('Did Ada confirm completion?',sid,dict(mark(sid,1,outcome),version='obsolete'),detail='Ada confirmed completion.')]
    person=dict(status='supported',detail='Ada confirmed completion.')
    if linked: person['questions']=[c['question'] for c in facts]
    run_agent(state,tools,lambda _:finish([sid],fact_checks=facts,person_evidence=person))
    selection=json.loads((state.run_dir/'selection.json').read_text())
    restored=SearchState(tmp_path,'case')
    assert restored.data['person_evidence']==selection['person_evidence']==state.data['person_evidence']
    assert restored.data['fact_checks']==selection['fact_checks']
    assert restored.data['person_evidence']['status']=='limited'
    assert 'Ada confirmed completion.' not in restored.data['person_evidence']['detail']
    if linked: assert 'Ada announced plans.' in restored.data['person_evidence']['detail']
    assert restored.data['stop_reason']=='low_gain'


def test_check_updates_are_independent_and_do_not_trust_supplied_delivery_status(tmp_path):
    state,tools=setup(tmp_path)
    sid,doc=saved(tools,'notice','Ada Vale approved Orion.',read=True)
    fact=check('Did Ada approve?',sid,mark(sid,0,'Ada Vale approved Orion.'))
    record_checks(state,[dict(fact,citation_status='delivered')])
    assert 'citation_status' not in state.data['fact_checks'][0]
    assert state.data['fact_checks'][0]['evidence'][0]['version']==doc['version']
    before=deepcopy(state.data['fact_checks'])
    record_checks(state,[check('Another question?',status='missing'),dict(fact,source_ids=['invented'])])
    assert state.data['fact_checks'][0]==before[0]
    assert state.data['fact_checks'][1]['question']=='Another question?'
    assert state.data['evidence_feedback']['fact_checks']['rejected'][0]['index']==1
