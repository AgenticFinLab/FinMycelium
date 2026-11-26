"""One research loop: inspected support, targeted discovery and frozen delivery."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.progress import query_read_feedback, record_query_read
from finmy.search.review import check_gaps, question_attempts, record_checks, research_steps
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_evidence_routing import check
from test_search_integrated_review import mark


def test_new_reason_is_saved_beside_supported_approach_in_one_decision(tmp_path):
    state, tools = setup(tmp_path)
    who = 'Ada Vale accepted the invitation to join the Orion program.'
    why = 'The committee approached Ada Vale because her longstanding local relationships enabled Orion.'
    sid, doc = saved(tools, 'interview', who+'\n\n'+why, read=True)
    state.data['priority_passages'] = [p for p in state.data['priority_passages'] if p['block']==0]
    record_checks(state, [check('Who accepted the invitation?', sid, mark(sid,0,who))])
    calls = []
    def decide(context):
        calls.append(context)
        assert context['fact_checks'][0]['status']=='supported'
        return finish([sid], fact_checks=[check('Why was Ada approached?', sid, mark(sid,1,why))])
    run_agent(state, tools, decide)
    assert len(calls)==1 and state.data['usage']=={'model':1,'search':0}
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert who in str(payload) and why in str(payload)
    assert len(state.data['fact_checks'])==2
    assert all(c['citation_status']=='delivered' for c in state.data['fact_checks'])
    assert tools.sources.document(sid)==doc


def test_completion_gap_returns_to_ordinary_search_and_cache_selection(tmp_path):
    state, tools = setup(tmp_path, providers=['exa'])
    announcement='The Orion committee announced that the handover would occur in June.'
    sid,_=saved(tools,'notice',announcement,read=True)
    question='Was the Orion handover actually completed?'
    facts=[check('What did the committee announce?',sid,mark(sid,0,announcement)),
           check(question,status='planned',detail='An announcement is available; completion has not been established.')]
    record_checks(state,facts)
    normal=context_for(state)['next_steps']
    assert normal[0]['remedy']=='search'
    assert not (state.run_dir/'builder_input.json').exists()
    state.save()
    resumed=SearchState(tmp_path,'case')
    completion='The Orion committee confirmed the handover was completed in June.'
    requests=[]
    def transport(provider,payload,config):
        requests.append(payload)
        return {'results':[{'url':'https://example.org/completion','title':'Orion handover', 'text':completion}]}
    tools=SearchTools(resumed,transport=transport,fetcher=lambda _:pytest.fail('Cached text is enough'))
    tools.sources.can_complete_partial=False  # This case tests the question loop, not acquisition.
    calls=[]
    def decide(context):
        calls.append(context)
        if len(calls)==1:
            return dict(action='search',question=question,query='Orion handover completion report',gap=question)
        candidate=next(c for c in context['cached_evidence'] if any(s['text']==completion for s in c['spans']))
        span=next(s for s in candidate['spans'] if s['text']==completion)
        ref=dict(source_id=candidate['source_id'],**{k:span[k] for k in ('block','start','end')})
        return finish([sid],fact_checks=[check(question,candidate['source_id'],ref,detail='Handover completed in June.')])
    run_agent(resumed,tools,decide,max_steps=3)
    assert resumed.data['status']=='finished' and len(calls)==2 and len(requests)==1
    assert len(question_attempts(resumed,resumed.data['fact_checks'][1]))==1
    selected=json.loads((resumed.run_dir/'selection.json').read_text())
    assert not selected['delivery_issues'] and not any(question in g for g in selected['gaps'])
    assert completion in (resumed.run_dir/'builder_input.json').read_text()


def test_unread_candidate_uses_same_navigation_without_becoming_read_at_finish(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'notice','The Orion program was announced.',read=True)
    original='Ada Vale required local consent before authorizing the Orion program.'
    candidate,doc=saved(tools,'interview',original)
    q='What local consent did Ada require before authorizing Orion?'
    record_checks(state,[check(q,status='missing')])
    normal=context_for(state)['next_steps']
    assert normal[0]['remedy']=='read_source' and normal[0]['source']==candidate
    assert not state.data['sources'][candidate].get('read_ranges')
    def fail(_): raise RuntimeError('Synthetic failure')
    run_agent(state,tools,fail,max_steps=1)
    assert not state.data['sources'][candidate].get('read_ranges')
    assert tools.sources.document(candidate)==doc


def test_renaming_preserves_search_and_read_attempts_without_resetting_them(tmp_path):
    state,tools=setup(tmp_path)
    text='The Orion program will open after local consent.'
    sid,_=saved(tools,'notice',text,read=True)
    old='Did Orion open?';new='Was the Orion opening completed?'
    record_checks(state,[check(old,status='planned')])
    state.data['actions']=[dict(action='search',question=old,query='Orion completed opening report')]
    result=tools.read_source(sid,location={'block':0})
    for _ in range(2):record_query_read(state,sid,'Orion opening',result,question=old)
    record_checks(state,[dict(check(new,status='planned'),replaces=[old])])
    state.save();restored=SearchState(tmp_path,'case')
    assert len(question_attempts(restored,restored.data['fact_checks'][0]))==1
    assert query_read_feedback(restored,sid,'different words',question=new)
    assert query_read_feedback(restored,sid,'Orion did not open 2021',question=new)
    assert not research_steps(restored)
    feedback=execute_action(restored,SearchTools(restored),finish([sid]))
    assert restored.data['status']=='finished' and new in str(feedback['gaps'])
    assert old not in str(feedback['gaps'])


@pytest.mark.parametrize('broken',['unread','old_version','missing_ref','budget'])
def test_invalid_or_undeliverable_fact_never_becomes_a_final_person_claim(tmp_path,broken):
    state,tools=setup(tmp_path,max_builder_material_chars=1 if broken=='budget' else 90000)
    sid,_=saved(tools,'notice','The Orion program was announced.',read=True)
    outcome='Ada Vale confirmed the completed Orion handover.'
    support,doc=saved(tools,'completion',outcome,read=broken!='unread')
    ref=mark(support,0,outcome)
    if broken=='old_version':ref['version']='obsolete'
    fact=check('Did Ada confirm completion?',support,None if broken=='missing_ref' else ref,
               detail='Ada confirmed the completed handover.')
    if broken=='unread':fact['source_ids']=[sid]  # A read elsewhere cannot authorize this location.
    state.data['finalization_trigger']='model_call_budget'
    execute_action(state,tools,finish([sid],fact_checks=[fact],person_evidence=dict(
        status='supported',detail='Unchecked narrative.',questions=[fact['question']])))
    report=json.loads((state.run_dir/'selection.json').read_text())
    assert report['fact_checks'][0]['status']=='missing' and report['delivery_issues']
    assert report['person_evidence']['status']=='limited'
    assert fact['detail'] not in report['person_evidence']['detail']
    assert len([g for g in report['gaps'] if g.startswith(fact['question']+':')])==1
    assert tools.sources.document(support)==doc


def test_factual_gaps_and_person_summary_share_renamed_delivered_checks(tmp_path):
    from finmy.search.review import delivered_person_evidence
    old='Has delivery happened?';new='Was the transfer received?'
    facts=[dict(check(new,'source',status='supported',detail='Transfer was received.'),replaces=[old])]
    person=delivered_person_evidence(dict(status='limited',detail='Stale prose.',questions=[old]),facts,[],derive=True)
    assert person==dict(status='supported',detail='Transfer was received.',questions=[new])
    assert check_gaps(facts,[old+': missing; Not known.',new+': planned; Future only.','Original URL inaccessible.'])==['Original URL inaccessible.']


def test_action_question_cannot_disappear_when_check_declaration_is_omitted(tmp_path):
    state,tools=setup(tmp_path)
    sid,_=saved(tools,'notice','The Orion committee announced a planned handover.',read=True)
    question='Was the Orion handover completed?'
    run_agent(state,tools,lambda _:dict(action='read_source',source=sid,
        location={'block':0},question=question),max_steps=1)
    restored=SearchState(tmp_path,'case')
    assert restored.data['fact_checks'][0]['question']==question
    assert restored.data['fact_checks'][0]['status']=='missing'
    assert question_attempts(restored,restored.data['fact_checks'][0])[0]['question']==question


@pytest.mark.parametrize('length', [120, 121, 160])
def test_question_length_cannot_reject_inspected_support(tmp_path, length):
    state, tools = setup(tmp_path)
    text = 'Ada Vale required local consent before approving the Orion program.'
    sid, doc = saved(tools, 'conditions', text, read=True)
    state.data['priority_passages'] = []
    question = ('What conditions applied to the Orion program? ' * 4)[:length]
    fact = check(question, sid, mark(sid, 0, text))
    calls = []
    def decide(context):
        calls.append(context)
        return finish([sid], fact_checks=[fact])
    run_agent(state, tools, decide)

    assert len(calls) == 1 and state.data['usage'] == {'model': 1, 'search': 0}
    assert state.data['priority_feedback'] == {'accepted': 1, 'rejected': []}
    passage = state.data['priority_passages'][0]
    key, = passage['fact_ids']
    assert 0 < len(key) <= 120
    if length <= 120:
        assert key == question  # Existing short keys remain compatible.
    assert passage['reason'] == question
    report = json.loads((state.run_dir/'selection.json').read_text())
    assert report['fact_checks'][0]['question'] == question
    assert report['fact_checks'][0]['citation_status'] == 'delivered'
    assert not report['delivery_issues']
    assert text in (state.run_dir/'builder_input.json').read_text()
    assert tools.sources.document(sid) == doc


def test_long_question_keys_preserve_distinctions_and_survive_resume(tmp_path):
    state, tools = setup(tmp_path)
    texts = ['Ada Vale required local consent before approving Orion.',
             'Ada Vale required a funding guarantee before approving Orion.',
             'The committee confirmed that local consent was required for Orion.']
    sid, _ = saved(tools, 'conditions', '\n\n'.join(texts), read=True)
    state.data['priority_passages'] = []
    prefix = 'What conditions applied to the Orion program? ' * 3
    questions = [prefix + 'Who gave consent?', prefix + 'Who guaranteed funding?']
    facts = [check(q, sid, mark(sid, i, texts[i])) for i, q in enumerate(questions)]
    facts[0]['evidence'].append(mark(sid, 2, texts[2]))
    record_checks(state, facts, mark_support=True)
    marks = deepcopy(state.data['priority_passages'])
    keys = {p['block']: p['fact_ids'] for p in marks}
    assert keys[0] == keys[2] and keys[0] != keys[1]

    # Reconstruct marks from persisted checks, without another model response.
    state.data['priority_passages'] = []
    state.save()
    restored = SearchState(tmp_path, 'case')
    record_checks(restored, [], mark_support=True)
    assert restored.data['priority_passages'] == marks
    record_checks(restored, facts, mark_support=True)
    assert restored.data['priority_passages'] == marks
    assert [c['question'] for c in restored.data['fact_checks']] == questions
    assert restored.data['usage'] == {'model': 0, 'search': 0}
