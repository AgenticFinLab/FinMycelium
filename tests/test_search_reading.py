"""Directed source reading and bounded stop decisions, entirely offline."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.reading import read_coverage, targeted_spans, unread_ranges
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('No network in reading checks')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)


def saved(tmp_path, text, **config):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Aster transaction',
        query_text='Trace the chairperson negotiation and approval.'), config=SearchConfig(**config))
    store = SourceStore(state)
    sid = store.register('https://example.org/report', title='Original report')
    doc = store.save_raw(sid, text.encode(), 'txt')
    return state, store, sid, doc


def test_query_reads_late_passage_and_context_without_rewriting_sources(tmp_path):
    text = '\n\n'.join('Unrelated operations section ' + str(i) + '. ' + 'Routine deliveries. ' * 90 for i in range(20))
    text += '\n\nThe proposal remained conditional.\n\nThe chairperson negotiated financing with Aster.\n\nApproval required a vote.'
    state, store, sid, doc = saved(tmp_path, text, max_read_chars=3000)
    files = list((state.root/'sources'/sid/doc['version']).iterdir())
    before = {p:p.read_bytes() for p in files}
    result = execute_action(state, SearchTools(state), dict(action='read_source', source=sid, query='chairperson negotiated financing'))
    actual = '\n'.join(s['text'] for s in result['spans'])
    assert 'The chairperson negotiated financing with Aster.' in actual
    assert 'The proposal remained conditional.' in actual and 'Approval required a vote.' in actual
    assert sum(len(s['text']) for s in result['spans']) <= 3000
    assert result['next_location'] is None and not result['at_end_of_saved_text']
    for span in result['spans']:
        assert doc['blocks'][span['block']]['text'][span['start']:span['end']] == span['text']
    assert before == {p:p.read_bytes() for p in files}
    assert state.data['usage'] == {'search':0,'model':0} and state.data['read_sources'] == [sid]
    context = context_for(state)
    assert 'chairperson negotiated' in context['sources'][0]['preview']
    assert context['sources'][0]['read_chars'] < context['sources'][0]['saved_chars']
    assert context['reading_summary']['saved_unread'] == 0


def test_query_returns_more_than_three_separated_matches_within_budget(tmp_path):
    text = []
    for i in range(5):
        text.extend([f'Before milestone {i}.', f'Negotiation milestone {i}.', f'After milestone {i}.',
                     'Unrelated delivery details. ' * 200 + str(i)])
    state, store, sid, _ = saved(tmp_path, '\n\n'.join(text), max_read_chars=2000)
    result = store.read(sid, query='Negotiation')
    content = '\n'.join(s['text'] for s in result['spans'])
    assert all(f'Negotiation milestone {i}.' in content for i in range(5))
    assert sum(len(s['text']) for s in result['spans']) <= 2000
    assert result['reading']['unread_matching_windows'] == 0


def test_repeated_query_prefers_unread_matches_and_explicit_reread_still_works(tmp_path):
    text = '\n\n'.join(f'Negotiation phase {i}. ' + 'Conditions apply. ' * 8 for i in range(5))
    state, store, sid, _ = saved(tmp_path, text, max_read_chars=180)
    first = store.read(sid, query='negotiation')
    second = store.read(sid, query='negotiation')
    assert second['spans'] != first['spans']
    for _ in range(20):
        result = store.read(sid, query='negotiation')
        if not result['spans']:
            break
    assert result['reading']['match_status'] == 'already_read'
    assert len(state.data['read_sources']) == 1
    assert store.read(sid, block=0)['spans'][0]['start'] == 0


def test_legacy_long_page_uses_virtual_windows_and_preserves_original_offsets():
    text = ('Annual operating commentary.\n' * 1000 + '\nNegotiation terms were approved.\n\nFollow-up conditions apply.')
    document = {'version':'v', 'blocks':[{'page':15,'text':text}]}
    original = deepcopy(document)
    spans, info = targeted_spans(document, 'negotiation terms', 2000, [])
    assert any('Negotiation terms were approved.' in s['text'] for s in spans)
    assert all(s['block']==0 and s['locator']['page']==15 for s in spans)
    assert all(text[s['start']:s['end']]==s['text'] for s in spans)
    assert document == original and info['preview_location']['start'] > 20000


@pytest.mark.parametrize('needle', ['Negotiation', '董事会谈判'])
def test_late_match_in_indivisible_text_is_not_hidden_by_read_limit(needle):
    text = 'x' * 20000 + ' ' + needle + ' accepted ' + 'z' * 20000
    doc = {'version':'v','blocks':[{'paragraph':1,'text':text}]}
    spans, _ = targeted_spans(doc, needle, 200, [])
    assert needle in ''.join(s['text'] for s in spans)
    assert sum(len(s['text']) for s in spans) <= 200
    assert all(text[s['start']:s['end']]==s['text'] for s in spans)


def test_no_match_does_not_mark_source_reviewed_or_claim_source_is_exhausted(tmp_path):
    state, store, sid, _ = saved(tmp_path, 'A short announcement.')
    result = store.read(sid, query='negotiation')
    assert result['reading']['match_status']=='no_match' and not result['spans']
    assert not result['at_end_of_saved_text']
    source=context_for(state)['sources'][0]
    assert source['body_available'] and not source['reviewed'] and source['read_chars']==0
    assert context_for(state)['reading_summary']['saved_unread']==1
    assert store.read(sid)['spans']


def test_coverage_merges_overlaps_ignores_other_versions_and_handles_disjoint_ranges():
    doc={'version':'v','blocks':[{'text':'a'*10},{'text':'b'*10}]}
    ranges=[dict(version='v',block=0,start=0,end=6),dict(version='v',block=0,start=4,end=8),
            dict(version='old',block=1,start=0,end=10)]
    assert read_coverage(doc,ranges)==(20,8)
    assert list(unread_ranges(0,0,2,[dict(block=0,start=8,end=10)]))==[(0,2)]


@pytest.mark.parametrize('query,location', [('',None),(False,None),([],None),('terms',{'block':0})])
def test_bad_read_parameters_fail_before_fetch_or_source_budget(tmp_path,query,location):
    state, _, sid, _ = saved(tmp_path,'Original.')
    tools=SearchTools(state,fetcher=lambda *a:pytest.fail('Unexpected fetch'))
    with pytest.raises(ValueError): tools.read_source(sid,location,query=query)
    assert not state.data['read_sources']


def test_query_read_partial_body_and_new_version_accounting(tmp_path):
    state, store, sid, _ = saved(tmp_path,'Negotiation approved.')
    store.read(sid,query='negotiation')
    new=store.save_raw(sid,b'Negotiation paused.','txt',partial=True)
    c=context_for(state)['sources'][0]
    assert not c['reviewed'] and c['read_chars']==0
    result=store.read(sid,query='negotiation')
    assert result['version']==new['version'] and result['status']=='partial'
    assert result['at_end_of_saved_text']


def test_agent_can_read_saved_lead_then_stop_without_forcing_all_candidates(tmp_path):
    state, store, sid, _ = saved(tmp_path,'Negotiation terms agreed.\n\nApproval still conditional.',max_model_calls=6)
    other=store.register('https://example.org/duplicate',title='Duplicate lead')
    store.save_raw(other,b'A redundant account.','txt')
    original_config=deepcopy(state.data['config'])
    def decide(context):
        if not context['sources'][0]['reviewed']:
            assert context['reading_summary']['saved_unread']==2
            return dict(action='read_source',source=sid,query='negotiation')
        assert context['reading_summary']['saved_unread']==1
        assert 'Negotiation' in context['sources'][0]['preview']
        return dict(action='finish',source_ids=[sid],gaps=['Later approval remains unconfirmed.'],
                    reason='low_gain',reason_detail='Remaining lead is redundant; later approval needs unavailable records.')
    tools=SearchTools(state,transport=lambda *a:pytest.fail('No search'),fetcher=lambda *a:pytest.fail('No fetch'))
    run_agent(state,tools,decide)
    assert state.data['status']=='finished' and state.data['usage']=={'search':0,'model':2}
    assert 'redundant' in state.data['stop_detail'] and state.data['config']==original_config
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert set(payload)=={'user_query','samples'} and 'Approval still conditional.' in payload['samples'][0]['content']


def test_finalization_can_stop_with_unread_sources_and_explicit_gap(tmp_path):
    state, store, sid, _ = saved(tmp_path,'Negotiation reported.',max_model_calls=1)
    def decide(c):
        assert c['phase']=='finalize' and c['reading_summary']['saved_unread']==1
        return dict(action='finish',source_ids=[],gaps=['Saved source not inspected before the model limit.'],
                    reason='insufficient',reason_detail='No remaining research calls.')
    run_agent(state,SearchTools(state),decide)
    assert state.data['status']=='insufficient' and not state.data['read_sources']
    assert state.data['usage']=={'search':0,'model':1}
