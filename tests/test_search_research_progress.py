"""Language routing, failed acquisition and repeat-reading recovery, without services."""
import json
import socket
from datetime import datetime, timedelta, timezone

import pytest
import requests

from finmy.generic import DataSample, UserQueryInput
from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('No live calls in research progress checks')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def setup(tmp_path, **config):
    state = SearchState(tmp_path, 'case', task=dict(target_type='person', target_name='Ada',
                        query_text='Trace Ada public education commitment.'), config=SearchConfig(**config))
    return state, SearchTools(state)


def saved(tools, name, text='Ada made her commitment conditional on local consent.'):
    sid = tools.sources.register('https://example.org/' + name, title=name)
    doc = tools.sources.save_raw(sid, text.encode(), 'txt')
    return sid, doc


def http_error(code, retry_after=None):
    response = requests.Response()
    response.status_code = code
    if retry_after is not None:
        response.headers['Retry-After'] = retry_after
    return requests.HTTPError('Do not publish this exception: secret-example', response=response)


def test_provider_variants_use_actual_queries_validation_cache_and_provenance(tmp_path):
    state, _ = setup(tmp_path, providers=['baidu', 'bocha', 'exa'])
    calls = []
    def transport(provider, payload, config):
        query = payload.get('query') or payload['messages'][0]['content']
        calls.append((provider, query))
        items = [dict(url='https://example.org/' + provider, title='艾达的教育承诺',
                      snippet='原始访谈线索')]
        if provider == 'baidu': return dict(references=items)
        if provider == 'bocha': return dict(data=dict(webPages=dict(value=items)))
        return dict(results=items)
    tools = SearchTools(state, transport=transport)
    action = dict(action='search', query='Ada education commitment',
                  gap='Locate original accounts of the conditions for her commitment.',
                  provider_queries={'baidu':'艾达 教育计划 承诺', 'bocha':'Ada 教育计划 承诺'})
    execute_action(state, tools, action)
    assert calls == [('baidu','艾达 教育计划 承诺'), ('bocha','Ada 教育计划 承诺'),
                     ('exa','Ada education commitment')]
    assert state.data['usage']['search'] == 3
    execute_action(state, tools, action)
    assert len(calls) == 3
    # Changing one variant consumes one request; other actual-query payloads stay cached.
    changed = dict(action, provider_queries={**action['provider_queries'], 'baidu':'艾达 教育计划 条件'})
    execute_action(state, tools, changed)
    assert state.data['usage']['search'] == 4 and calls[-1] == ('baidu','艾达 教育计划 条件')
    resumed = SearchState(tmp_path, 'case')
    observed = {r['provider']:r for r in context_for(resumed)['provider_observations']}
    assert observed['baidu']['chinese_query_tried'] and observed['bocha']['chinese_query_tried']
    assert not observed['exa']['chinese_query_tried'] and observed['exa']['chinese_hints'] == 1
    traces = [json.loads(l) for l in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    assert next(e for e in traces if e['action']=='provider_started')['query'] == '艾达 教育计划 承诺'
    result=execute_action(state, tools, dict(action, provider_queries={'baidu':'文'*37}))
    assert result['providers'][0]['status']=='skipped_length'
    assert state.data['usage']['search'] == 5  # New Bocha variant; Exa remains cached.


@pytest.mark.parametrize('variants', [[], {'unknown':'question'}, {'bocha':''}, {'bocha':3}])
def test_bad_variants_do_not_spend_requests(tmp_path, variants):
    state, tools = setup(tmp_path)
    with pytest.raises(ValueError): tools.search('question', provider_queries=variants)
    assert state.data['usage']['search'] == 0


@pytest.mark.parametrize('code,attempt_limit', [(400,1), (403,1), (404,1), (503,2), (555,2)])
def test_failed_fetch_is_classified_bounded_and_persisted(tmp_path, code, attempt_limit):
    state, tools = setup(tmp_path)
    sid = tools.sources.register('https://example.org/unavailable')
    calls = []
    def fetch(url):
        calls.append(url)
        raise http_error(code)
    result = SearchTools(state, fetcher=fetch).read_source(sid)
    assert result['fetch_error']['http_status'] == code and not result.get('spans')
    assert 'secret-example' not in json.dumps(state.data)
    resumed = SearchState(tmp_path, 'case')
    for _ in range(3): result = SearchTools(resumed, fetcher=fetch).read_source(sid)
    assert len(calls) == attempt_limit and result['retry_skipped']
    assert resumed.data['read_sources'] == [sid] and resumed.data['usage']['search'] == 0
    assert context_for(resumed)['sources'][0]['acquisition_error']['http_status'] == code


def test_retry_after_waits_without_blocking_then_transient_read_can_recover(tmp_path):
    state, tools = setup(tmp_path)
    sid = tools.sources.register('https://example.org/busy')
    calls = []
    def fetch(url):
        calls.append(url)
        if len(calls) == 1: raise http_error(429, '60')
        return b'Ada explained her commitment.', 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    assert tools.read_source(sid)['fetch_error']['category'] == 'rate_limited'
    skipped = tools.read_source(sid)
    assert skipped['retry_skipped'] and skipped['retry_in_seconds'] > 0 and len(calls) == 1
    state.data['sources'][sid]['fetch_attempts'][-1]['time'] = (
        datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat()
    result = tools.read_source(sid)
    assert result['status'] == 'success' and result['progress']['new_chars'] > 0
    assert len(calls) == 2 and not state.data['sources'][sid].get('fetch_error')


def test_partial_expansion_failure_reports_status_and_keeps_original(tmp_path):
    state, tools = setup(tmp_path)
    sid = tools.sources.register('https://example.org/interview')
    original = tools.sources.save_raw(sid, b'Ada explained her commitment with conditions.', 'txt', partial=True)
    def fetch(url): raise http_error(403)
    result = SearchTools(state, fetcher=fetch).read_source(sid)
    assert result['status'] == 'partial' and result['version'] == original['version']
    acquisition = context_for(state)['sources'][0]['acquisition']
    assert acquisition['http_status'] == 403 and not acquisition['retryable']
    assert 'with conditions' in result['spans'][0]['text']


def test_read_progress_counts_new_intervals_for_queries_cursors_and_versions(tmp_path):
    state, tools = setup(tmp_path, max_read_chars=20)
    sid, _ = saved(tools, 'letter', 'Ada accepted the invitation after requesting local consent.\n\nConditions remain.')
    first = tools.read_source(sid, location={'block':0})
    second = tools.read_source(sid, location={'block':0, 'offset':10})
    assert first['progress']['new_chars'] == 20 and second['progress']['new_chars'] == 10
    replay = tools.read_source(sid, location={'block':0})
    assert replay['progress']['new_chars'] == 0 and replay['spans']
    tools.sources.save_raw(sid, b'Ada revised plans.', 'txt')
    assert tools.read_source(sid, query='Ada')['progress']['new_chars'] == len('Ada revised plans.')
    assert tools.read_source(sid, query='changed keywords')['progress']['new_chars'] == 0


def test_alternating_zero_gain_reads_finalize_without_false_completeness(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=30)
    ids = [saved(tools, 'first')[0], saved(tools, 'second')[0]]
    unused = saved(tools, 'unread')[0]
    calls = []
    def decide(context):
        calls.append(context)
        if context['phase'] == 'finalize':
            assert context['finalization_reason'] == 'no_reading_progress'
            assert context['reading_summary']['unread_candidates'] == 1
            return dict(action='finish', source_ids=ids, gaps=['An alternate account remains unread.'], reason='supported')
        sid = ids[(len(calls)-1) % 2]
        if len(calls) % 2: return dict(action='read_source', source=sid, query='commitment '+str(len(calls)))
        return dict(action='read_source', source=sid, location={'block':0})
    # Persist across a pause; a restart must not give the loop a new counter.
    run_agent(state, tools, decide, max_steps=5)
    assert state.data['research_progress']['consecutive_no_gain'] == 3
    resumed = SearchState(tmp_path, 'case')
    run_agent(resumed, SearchTools(resumed), decide)
    assert len(calls) == 9 and resumed.data['status'] == 'finished'
    assert resumed.data['stop_reason'] == 'low_gain'
    assert resumed.data['termination_trigger'] == 'no_reading_progress'
    payload = json.loads((resumed.run_dir/'builder_input.json').read_text())
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']: DataSample(**sample)
    assert unused not in {s['raw_data_id'] for s in payload['samples']}
    assert any('not certified complete' in g for g in resumed.data['feedback']['gaps'])


def test_progressive_long_read_and_valid_marks_are_not_stopped(tmp_path):
    state, tools = setup(tmp_path, max_read_chars=25, max_model_calls=30)
    text = 'Ada explained the conditions. '*10
    sid, doc = saved(tools, 'long', text)
    calls = []
    def decide(context):
        assert context['phase'] == 'research'
        calls.append(context)
        if context['sources'][0].get('priority_passages'):
            assert context['research_progress']['new_priority_marks'] == 1
            assert context['research_progress']['consecutive_no_gain'] == 0
            return dict(action='finish', source_ids=[sid], gaps=[], reason='supported')
        progress = context['sources'][0]['read_progress']
        if not progress or progress.get('next_location'):
            return dict(action='read_source', source=sid, location=(progress or {}).get('next_location') or {'block':0})
        return dict(action='read_source', source=sid, location={'block':0}, priority_passages=[
            dict(source_id=sid, block=0, start=0, end=25)])
    # The long file is read over more than six steps, all with new original text.
    run_agent(state, tools, decide)
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'supported'
    assert len(calls) > 10
