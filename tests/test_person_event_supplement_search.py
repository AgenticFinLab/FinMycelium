"""One pinned input, one evidence decision and cumulative quotas through resume."""
from copy import deepcopy
import json
import socket

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.records import json_bytes, sha256
from finmy.person_epg.event.runtime import EventBuildConfig, kimi_workbench_config
from finmy.person_epg.event.search_passages import added_input, frozen_passages, original_search
from finmy.person_epg.event.supplement_record import input_transition
from finmy.person_epg.event.supplement_search import SEARCH_LIMITS
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest, write_json


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('Unexpected network access'))


class GateModel(SyntheticEventModel):
    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def __call__(self, system, user, name):
        request = json.loads(user)['task']
        if request['role'] != 'gap_review':
            if request.get('body', {}).get('sample_id', '').startswith('supplement-'):
                self.calls.append(name)
                return dict(entities=[], actions=[], contexts=[], relation_candidates=[], evidence=[], pending=[],
                            note='No additional distinct fact in this test response.')
            return super().__call__(system, user, name)
        self.calls.append(name)
        if name == 'supplement.questions':
            return dict(reason='Check the focal attribution in the public approval record.',
                        questions=[] if self.answer == 'skip' else [dict(
                            question='Who signed the approval notice for the disclosure restriction?', anchor=request['event']['event_id'],
                            impact='Distinguish the authorizer from the legal signatory.')])
        stage = request['stage']
        accepted = self.answer == stage
        passages = [next(iter(request['passages']))] if accepted else []
        return dict(assessments=[dict(id='Q1', status='sufficient' if accepted else 'unresolved',
                    passages=passages, reason='The passage names the signatory.' if accepted else 'No signature in this passage.')])


def cache_at(path):
    state = SearchState(path, 'original', task=dict(target_type='person',target_name='Pat',query_text='approval'))
    store = SourceStore(state)
    sid = store.register('https://test.example/approval', title='Approval notice')
    store.save_raw(sid, b'<html><body><p>Signed approval notice: the director authorized the special transfer on March 10.</p></body></html>', 'html')
    path = state.run_dir/'handoffs/v1/builder_input.json'
    write_json(path, {'samples':[]})
    return dict(source_root=str(state.root),search_task_id='original',handoff_revision='v1',
                search_input_sha256=digest({'samples':[]}))


@pytest.mark.parametrize('answer', ['skip','frozen','cache','missing'])
def test_gap_routing_and_bound_inputs(tmp_path, payload, answer):
    root = tmp_path/'build'
    provenance = cache_at(tmp_path/'search')
    config = EventBuildConfig(automatic_search=True, max_calls=50)
    model = GateModel(answer)
    state = run_event(payload, root, config, model=model, provenance=provenance)
    assert state['execution_status'] == 'finished', state.get('reason')
    info = json.loads((root / state['supplement']['comparison']).read_text())
    assert info['search']['search'] == info['search']['model'] == 0
    assert (root/'supplement/base-input.json').read_bytes() == json_bytes(payload)
    assert sha256((root/'input.json').read_bytes()) == info['input_sha256'] == state['input_sha256']
    assert [c['stage'] for c in info['checks']] == {
        'skip':[], 'frozen':['frozen'], 'cache':['frozen','cache'], 'missing':['frozen','cache','public']}[answer]
    assert info['outcome'] == dict(skip='not_needed', frozen='frozen_reread', cache='additional_evidence',
                                   missing='no_increment')[answer]
    assert bool(info['added_chars']) == (answer == 'cache')
    count = len(model.calls)
    resumed = run_event(payload, root, config, model=model, provenance=provenance, resume=True)
    assert len(model.calls) == count
    assert resumed['input_sha256'] == state['input_sha256']
    if answer == 'cache':
        from finmy.workbench.graph_collection import reviewed_artifacts
        event = payload['user_query']['extras']['person_event']
        row = dict(id='PBUILD-test', status='completed', event_id=event['event_id'],
                   body=dict(kind='person_event', artifact_directory=str(root), input_hash=digest(payload),
                             catalog={k:event[k] for k in ('event_id','person_id','storyline_id')}))
        assert reviewed_artifacts(row)['binding']['input_sha256'] == state['input_sha256']
        final = json.loads((root/'input.json').read_text())
        assert final['samples'][:len(payload['samples'])] == payload['samples']
        assert 0 < info['added_chars'] == len(final['samples'][-1]['content']) <= 8000
        assert len([c for c in state['calls'] if c['task_id'] == 'extract.0']) == 1
        # A crash between the two pointer writes is repaired using pinned bytes.
        interrupted = deepcopy(state)
        interrupted['supplement']['transition'] = 'prepared'
        (root/'provenance.json').write_bytes((root/'supplement/base-provenance.json').read_bytes())
        assert input_transition(root, interrupted, payload) == final
        assert interrupted['supplement']['transition'] == 'active'
        (root/'input.json').write_text('{}')
        with pytest.raises(ValueError, match='changed'):
            input_transition(root, interrupted, payload)


def test_caps_duplicates_and_cache_binding(tmp_path, payload):
    conf = kimi_workbench_config(automatic_search=True)
    assert (conf.max_calls, conf.max_read_calls, conf.max_read_chars) == (120, 80, 200000)
    assert kimi_workbench_config().max_calls == 60
    assert (SEARCH_LIMITS['max_search_requests'], SEARCH_LIMITS['max_read_sources'], SEARCH_LIMITS['max_model_calls']) == (6,4,12)
    provenance = cache_at(tmp_path/'search')
    with pytest.raises(ValueError, match='different handoff'):
        original_search(dict(provenance, search_input_sha256='invalid'))
    row = dict(source_id='external', metadata=dict(source_url='https://example.org/a'), version='version',
               id='one', origin='public', block=0, start=0, end=30, question_ids=['Q1'])
    rows = [dict(row, text=next(frozen_passages(payload))['text']),
            dict(row, id='too-big', text='L'*8000), dict(row, id='kept', text='A novel signature in the newly released corporate source.'),
            dict(row, id='copy', text='A novel signature in the newly released corporate source.')]
    result, included, skipped = added_input(payload, rows)
    assert len(result['samples']) == len(payload['samples']) + 1
    assert [r['id'] for r in included] == ['kept']
    assert [r['reason'] for r in skipped] == ['already_present','additional_character_limit','already_present']



def test_public_search_once_after_cache_and_resume(tmp_path, payload, monkeypatch):
    from finmy.person_epg.event import supplement_search
    from finmy.search.pipeline import run_search as public_runner
    providers = []
    requests = []
    url = 'https://example.org/public-approval-notice'
    def transport(provider, request, config):
        providers.append(provider)
        items = [dict(url=url, title='Signed approval notice')]
        if provider == 'baidu':
            return {'references':items}
        if provider == 'bocha':
            return {'data':{'webPages':{'value':items}}}
        return {'results':items}
    sid = digest(url)[:24]
    def search_model(context):
        requests.append(context['phase'])
        if len(requests) == 1:
            return dict(action='search', query='signed disclosure approval notice')
        if len(requests) == 2:
            return dict(action='read_source', source=sid)
        return dict(action='finish', source_ids=[sid], gaps=[], reason='supported',
                    reason_detail='Read the original signature.')
    def fake_transport_run(*args, **kwargs):
        raw = b'<html><body><p>The signed disclosure approval notice names the person who authorized the announcement.</p></body></html>'
        return public_runner(*args, **kwargs, model=search_model, transport=transport, fetcher=lambda url:(raw,'html','utf-8'))
    monkeypatch.setattr(supplement_search, 'run_search', fake_transport_run)
    root = tmp_path/'build'
    model = GateModel('public')
    config = EventBuildConfig(automatic_search=True, max_calls=50)
    result = run_event(payload, root, config, model=model, allow_network=True)
    assert result['execution_status'] == 'finished', result.get('reason')
    decision = json.loads((root/'supplement/decision.json').read_text())
    assert decision['outcome'] == 'additional_evidence', decision
    assert sorted(providers) == ['baidu','bocha','exa']
    assert decision['search']['model'] == len(requests) == 3
    assert decision['search']['read_sources'] == 1
    original_count = len(model.calls)
    result2 = run_event(payload,root,config,model=model,allow_network=True,resume=True)
    assert result['input_sha256'] == result2['input_sha256']
    assert len(model.calls) == original_count and len(requests) == len(providers) == 3


def test_pause_after_questions_reuses_paid_decision(tmp_path, payload):
    root = tmp_path/'build'
    base = GateModel('frozen')
    def interrupt(system, user, name):
        answer = base(system, user, name)
        if name == 'supplement.questions':
            (root/'pause_requested').touch()
        return answer
    config = EventBuildConfig(automatic_search=True)
    first = run_event(payload,root,config,model=interrupt)
    assert first['execution_status'] == 'paused'
    result = run_event(payload,root,config,model=base,resume=True)
    assert result['execution_status'] == 'finished'
    assert base.calls.count('supplement.questions') == 1
    assert result['supplement']['outcome'] == 'frozen_reread'


def test_zero_actions_can_consider_a_concrete_gap(tmp_path, payload):
    base = GateModel('missing')
    def empty(system, user, name):
        task = json.loads(user)['task']
        if task['role'] == 'extraction':
            return dict(entities=[], actions=[], contexts=[], relation_candidates=[], evidence=[], pending=[],
                        note='No demonstrated individual action in this passage.')
        return base(system,user,name)
    result = run_event(payload,tmp_path, EventBuildConfig(automatic_search=True, full_corpus_supplement=False), model=empty)
    assert result['execution_status'] == 'finished' and result['result_status'] == 'none'
    assert 'supplement.questions' in base.calls
    decision = json.loads((tmp_path/'supplement/decision.json').read_text())
    assert decision['unresolved_question_ids'] == ['Q1'] and decision['added_chars'] == 0


def test_role_views_preserve_two_endpoints_and_original_connecting_text():
    from finmy.person_epg.event.role_evidence import add_role_evidence
    text = 'Mina approved the plan. Because approval was required, Lee then released the report.'
    first, second = 'Mina approved the plan.', 'Lee then released the report.'
    evidence, actions = {}, {}
    for aid, eid, quote in [('A1','E1',first),('A2','E2',second)]:
        start = text.index(quote)
        evidence[eid] = dict(evidence_id=eid, sample_id='s', source_id='source', start=start,
            end=start+len(quote), quote=quote, location_status='matched')
        actions[aid] = dict(action_id=aid, name=quote, time={}, support=[dict(target='/description', evidence_ids=[eid])])
    package = {'samples':[dict(sample_id='s',raw_data_id='source',content=text)]}
    indexes = dict(actions=actions,evidence=evidence,contexts={})
    task = dict(role='relations',assigned_action_ids=['A1'],related_records=[],relation_candidates=[])
    add_role_evidence(task,indexes,10000,package)
    [window] = task['role_evidence']['nearby_passages']
    assert window['actions'] == ['A1','A2']
    assert window['text'] == text[window['start']:window['end']] == text
    link = dict(candidate_id='L1',from_action_id='A1',to_action_id='A2',type='enables',
                support=[dict(target='/type',evidence_ids=['E2'])])
    task = dict(role='organization',related_records=[])
    add_role_evidence(task,indexes,10000,package,[link])
    row = task['role_evidence']['records'][0]
    assert row['endpoints'] == ['A1','A2'] and row['link_by_source']['source']['/type'] == ['E2']
