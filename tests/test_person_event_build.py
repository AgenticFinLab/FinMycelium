from copy import deepcopy
import json
import socket

import pytest

from finmy.person_epg.build import run_legacy_event as run_event, check_identity
from finmy.person_epg.input import validate_scope
from finmy.search.state import digest

TEXT = 'On 2025-01-01 Alex authorized a transfer to Example Foundation. The foundation received the funds.'


def payload():
    event = dict(person_id='PERSON-TEST', person_name='Alex', storyline_id='PERSON-TEST-S1',
                 storyline_name='Charitable commitments', event_id='PERSON-TEST-E1', event_name='Foundation transfer',
                 scope=dict(period='2025', include='Authorization and execution of the transfer', exclude='Other gifts'), aliases=[])
    return dict(user_query=dict(query_text='Research this confirmed transfer.', key_words=['transfer'],
                extras=dict(person_event=event, source_registry={'r1':dict(document_id='DOC_1', source_url='https://example.org/notice',title='Test notice')})),
                samples=[dict(sample_id='s1',raw_data_id='r1',content=TEXT)])


class SyntheticModel:
    def __init__(self, fail=None, bad_neighbor=False):
        self.calls=[];self.fail=fail;self.bad_neighbor=bad_neighbor;self.last_usage=None

    def __call__(self, system, user, name):
        self.calls.append(name)
        self.last_usage={'prompt_tokens':20, 'completion_tokens':20}
        if self.fail and self.fail in name:
            raise TimeoutError('Synthetic provider failure')
        request, end = json.JSONDecoder().raw_decode(user)
        tail=user[end:]
        if 'source' in request:
            assert 'fixed research boundary' in system
            assert request['confirmed_event']['event_id']=='PERSON-TEST-E1'
            doc=request['source']['document_id']
            field=lambda value:dict(value=value,citations=[dict(document_id=doc,quote=TEXT)])
            actions=[dict(action_id='A1',actor_id='PERSON-TEST',action_type=field('Authorize transfer'),
                          timestamp=field('2025-01-01'),details=[field('Authorization of the foundation transfer')])]
            if self.bad_neighbor:
                actions.append(dict(action_id='BAD',actor_id='missing',action_type=field('Invalid actor'),timestamp=field('2025'),details=[]))
            return dict(entities=[dict(entity_id='foundation',name=field('Example Foundation'),entity_type='organization',aliases=[],attributes={})],
                        occurrences=[dict(occurrence_id='O1',title=field('Foundation transfer'),subject_relevance=field('Alex authorized the transfer'),
                            start_time=field('2025-01-01'),end_time=field('2025-01-01'),descriptions=[],actions=actions,
                            transactions=[dict(transaction_id='T1',name=field('Transfer'),from_entity_id='PERSON-TEST',to_entity_id='foundation',
                                               timestamp=field('2025-01-01'),details=[field('Funds delivered')],instruments=[])])])
        if 'assigned_occurrence_ids' in request:
            return dict(operations=[],reviewed_occurrence_ids=request['assigned_occurrence_ids'])
        task=json.JSONDecoder().raw_decode(tail.split('\n\nBATCH TASK:\n',1)[1])[0]
        assert 'confirmed_event' in request
        vf=lambda value:dict(value=value,evidence_source_contents=[TEXT],reasons=['Supported by the retained test notice'])
        if task['phase']=='Placement':
            return dict(memberships=[dict(event_id='PERSON-TEST-E1',activity_id=aid) for aid in task['assigned_ids']],
                        unassigned_reasons=[],occurrence_issues=[],occurrence_relevance=[dict(occurrence_id=oid,subject_relevance=vf('Alex authorized the transfer')) for oid in task['relevance_ids']])
        if task['phase']=='EventStructure':
            return dict(summary=vf('Alex authorized the foundation transfer'),stages=[dict(event_id='PERSON-TEST-E1',stage_id='ST1',label='Authorization and execution',boundary_reason=vf('The authorization and delivery form this phase'))],
                        stage_assignments=[dict(activity_id=aid,stage_id='ST1') for aid in task['assigned_ids']])
        if task['phase']=='Relations':return {'candidates':[]}
        raise AssertionError('Unexpected phase: '+task['phase'])


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('Real networking is forbidden'))


def test_full_native_single_event_and_source_anchors(tmp_path):
    source=payload();original=deepcopy(source);model=SyntheticModel()
    state=run_event(source,tmp_path/'run',model=model)
    assert state['status']=='completed',state
    graph=json.loads((tmp_path/'run'/state['output']).read_text())
    check_identity(graph,source['user_query']['extras']['person_event'])
    assert len(graph['event'])==len(graph['domain'])==1
    assert len(graph['action'])==len(graph['financial_transaction'])==1
    assert graph['source_document'][0]['source_url']=='https://example.org/notice'
    doc={d['document_id']:d['content'] for d in graph['source_document']}
    assert graph['evidence_span']
    mapping=json.loads(((tmp_path/'run'/state['output']).with_name('SourceMap.json')).read_text())
    assert mapping['sources'][0]['sample_id']=='s1'
    assert mapping['sources'][0]['document_id']==graph['source_document'][0]['document_id']
    for span in graph['evidence_span']:
        assert doc[span['document_id']][span['char_start']:span['char_end']]==span['quote']
    assert source==original and state['review_required']
    assert not any('EventLayout' in n for n in model.calls)
    before=len(model.calls)
    assert run_event(source,tmp_path/'run',model=model,resume=True)['status']=='completed'
    assert len(model.calls)==before


def test_no_permission_creates_no_run(tmp_path):
    with pytest.raises(PermissionError):run_event(payload(),tmp_path/'run')
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('problem', ['extras', 'event', 'scope', 'aliases', 'registry', 'source_id', 'empty_id', 'unknown_field'])
def test_invalid_input_is_rejected_before_creating_a_run(tmp_path, problem):
    source = payload()
    extras = source['user_query']['extras']
    event = extras['person_event']
    if problem == 'extras': source['user_query']['extras'] = None
    elif problem == 'event': extras['person_event'] = None
    elif problem == 'scope': event['scope'] = None
    elif problem == 'aliases': event['aliases'] = 'Alex'
    elif problem == 'registry': extras['source_registry'] = []
    elif problem == 'source_id': source['samples'][0]['raw_data_id'] = []
    elif problem == 'empty_id': source['samples'][0]['sample_id'] = ' '
    else: source['samples'][0]['unexpected'] = True
    model = SyntheticModel()
    with pytest.raises(ValueError):
        run_event(source, tmp_path/'run', model=model)
    assert model.calls == [] and not (tmp_path/'run').exists()


def test_long_names_follow_native_schema_while_ids_remain_bounded():
    event = payload()['user_query']['extras']['person_event']
    event['event_name'] = 'A documented event with an extensive but valid title. ' * 4
    assert validate_scope(event) == event
    event['event_id'] = 'x' * 129
    with pytest.raises(ValueError, match='128 characters'):
        validate_scope(event)


def test_cumulative_limit_and_resume_reuse(tmp_path):
    model=SyntheticModel();source=payload()
    first=run_event(source,tmp_path/'run',{'max_calls':1},model=model)
    assert first['status']=='limit' and len(model.calls)==1
    same=run_event(source,tmp_path/'run',{'max_calls':1},model=model,resume=True)
    assert same['status']=='limit' and len(model.calls)==1
    resumed=run_event(source,tmp_path/'run',{'max_calls':12},model=model,resume=True)
    assert resumed['status']=='completed',resumed
    assert sum('Extract' in n for n in model.calls)==1
    assert len(resumed['calls'])==len(model.calls)


def test_recovery_rejects_changed_input_and_corrupted_facts(tmp_path):
    source=payload();model=SyntheticModel()
    run_event(source,tmp_path/'run',{'max_calls':1},model=model)
    revised=deepcopy(source);revised['samples'][0]['content']+=' Changed.'
    with pytest.raises(ValueError,match='Input or implementation'):
        run_event(revised,tmp_path/'run',{'max_calls':8},model=model,resume=True)
    file=tmp_path/'run/canonical-checkpoint.json'
    value=json.loads(file.read_text());value['package']['entity'][0]['name']='Wrong identity';file.write_text(json.dumps(value))
    count=len(model.calls)
    result=run_event(source,tmp_path/'run',{'max_calls':8},model=model,resume=True)
    assert result['status']=='failed' and len(model.calls)==count


def test_partial_structure_recovers_without_reextracting(tmp_path):
    model=SyntheticModel(fail='EventStructure')
    first=run_event(payload(),tmp_path/'run',model=model)
    assert first['status']=='partial',first
    old=(tmp_path/'run'/first['output']).read_bytes()
    model.fail=None
    result=run_event(payload(),tmp_path/'run',model=model,resume=True)
    assert result['status']=='completed',result
    assert sum('Extract' in n for n in model.calls)==1
    assert (tmp_path/'run'/first['output']).read_bytes()==old
    assert result['output']!=first['output']


def test_invalid_neighbor_preserves_usable_facts(tmp_path):
    result=run_event(payload(),tmp_path/'run',model=SyntheticModel(bad_neighbor=True))
    assert result['status']=='partial',result
    graph=json.loads((tmp_path/'run'/result['output']).read_text())
    assert [r['action_id'] for r in graph['action']]==['A1']


def test_identity_check_rejects_added_event(tmp_path):
    source=payload();result=run_event(source,tmp_path/'run',model=SyntheticModel())
    graph=json.loads((tmp_path/'run'/result['output']).read_text())
    graph['domain'][0]['label']='Different scope'
    with pytest.raises(ValueError,match='storyline'):check_identity(graph,source['user_query']['extras']['person_event'])


def test_completed_draft_integrity_checked_before_reuse(tmp_path):
    model=SyntheticModel();source=payload()
    result=run_event(source,tmp_path/'run',model=model)
    path=tmp_path/'run'/result['output'];graph=json.loads(path.read_text())
    graph['graph']['title']='Unexpected change';path.write_text(json.dumps(graph))
    before=len(model.calls)
    with pytest.raises(ValueError,match='integrity'):
        run_event(source,tmp_path/'run',model=model,resume=True)
    assert len(model.calls)==before


def test_empty_evidence_does_not_invent_an_event(tmp_path):
    result=run_event(payload(),tmp_path/'run',model=lambda *args: {'entities':[], 'occurrences':[]})
    assert result['status']=='insufficient'
    assert not result.get('output') and not list((tmp_path/'run').rglob('epg.json'))
