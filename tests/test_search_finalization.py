"""Context and lifecycle regressions; no service calls or dataset writes."""
import json
import socket
from copy import deepcopy

import pytest

from finmy.search.agent import SYSTEM_PROMPT, context_for, run_agent
from finmy.search.control import SearchController
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a:pytest.fail('Unexpected network'))


def make_state(tmp_path, **kwargs):
    task = dict(target_type='person', target_name='Ada', query_text='Trace a conditional public education commitment.',
                research_scope={'include':'Public consent and decision', 'exclude':'Private motives'},
                catalog={'kind':'person_event', 'person_id':'PERSON-TEST', 'event_id':'E1',
                         'files':{'secret_local_path':'x'*8000}, 'snapshot_sha256':'a'*64})
    state = SearchState(tmp_path, 'case', task=task, config=SearchConfig(**kwargs))
    store = SourceStore(state);sid = store.register('https://example.org/grant', title='Grant announcement')
    doc = store.save_raw(sid, b'Ada committed to fund education only with local consent.', 'txt')
    store.read(sid)
    return state, sid, doc


def test_context_preserves_original_task_source_details_and_recent_actions(tmp_path):
    state, sid, doc = make_state(tmp_path)
    entry = state.data['sources'][sid]
    entry['acquisition_attempts'] = {'one':dict(status='kept_cached', reason='Body did not expand',
        artifact='local-path-'+'z'*5000, raw_sha256='b'*64,
        navigation={'observed_links':[{'url':'https://example.org/original','text':'Original interview'}]})}
    entry['read_progress'] = dict(version=doc['version'], query='consent', mode='query',
        matching_windows=2, unread_matching_windows=1, next_location={'block':0,'offset':12}, note='n'*6000)
    entry['last_read'] = dict(new_chars=20, returned_chars=50, hint='h'*6000)
    state.data['actions'] = [dict(action='read_source', source=sid, query='consent', priority_passages=[{'reason':'r'*6000}])]
    before = deepcopy(state.data)
    context = context_for(state)
    assert context['task']['query_text'] == state.data['task']['query_text']
    assert context['task']['research_scope'] == state.data['task']['research_scope']
    assert context['task'] == state.data['task']
    assert context['prior_actions'] == [dict(action='read_source',source=sid,query='consent')]
    assert context['sources'][0]['read_progress'] == entry['read_progress']
    assert context['sources'][0]['last_read'] == entry['last_read']
    assert context['sources'][0]['acquisition'] == entry['acquisition_attempts']['one']
    assert context['sources'][0]['read_progress']['next_location']['offset'] == 12
    assert context['sources'][0]['acquisition']['navigation']['observed_links'][0]['url'] == 'https://example.org/original'
    assert 'local consent' in str(context['sources'][0]['read_evidence'])
    assert state.data == before


def test_finalization_survives_error_and_resume_until_explicit_budget_change(tmp_path):
    state, sid, _ = make_state(tmp_path, max_model_context_chars=len(SYSTEM_PROMPT)+15000)
    state.data['actions'] = [dict(action='read_source',source=sid,query='consent',gap='x'*20000)]
    state.save()
    def invalid_read(context):
        assert context['phase'] == 'finalize'
        assert context['finalization_reason'] == 'context_limit'
        return {'action':'read_source','source':sid}
    run_agent(state, SearchTools(state), invalid_read, max_steps=1)
    assert state.data['status'] == 'paused'
    assert state.data['finalization_trigger'] == 'context_limit'
    state = SearchState(tmp_path, 'case')
    def finish(context):
        assert context['phase'] == 'finalize'
        return dict(action='finish',source_ids=[sid],gaps=['Private intent unknown'],reason='supported',
                    person_evidence={'status':'limited','detail':'Public commitment only.'})
    run_agent(state, SearchTools(state), finish)
    assert state.data['status'] == 'finished'
    assert state.data['stop_reason'] == 'supported'
    assert state.data['termination_trigger'] == 'context_limit'
    checkpoint = json.loads((state.run_dir/'checkpoint.json').read_text())
    assert checkpoint['termination_trigger'] == 'context_limit'


def test_repeated_simple_pause_resume_and_explicit_reads_never_lose_text(tmp_path, monkeypatch):
    state, sid, doc = make_state(tmp_path, max_read_chars=12)
    state.data['mode'] = 'simple';state.data['seeds_imported'] = True
    controller = SearchController(tmp_path)
    monkeypatch.setattr(SearchTools, 'search', lambda *a,**k:{})
    original = SearchTools.read_source
    def pause_after_read(tool, *args, **kwargs):
        result = original(tool, *args, **kwargs)
        (tool.state.root/'pause_requested').touch()
        return result
    for _ in range(2):
        with monkeypatch.context() as m:
            m.setattr(SearchTools, 'read_source', pause_after_read)
            controller._simple(state)
        assert state.data['status'] == 'paused'
        (state.root/'pause_requested').unlink()
    controller._simple(state)
    assert state.data['status'] == 'finished'
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert payload['samples']
    assert 'consent.' in payload['samples'][-1]['content']
    assert all(original(SearchTools(state),sid)['spans'] for _ in range(3))
    assert SearchTools(state).sources.document(sid) == doc
