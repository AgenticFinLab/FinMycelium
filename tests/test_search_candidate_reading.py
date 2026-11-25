"""Uncached leads use ordinary reading and budgets; no live services or extra agents."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search.agent import context_for, execute_action, run_agent
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


TASK = dict(target_type='person', target_name='Ada Example',
            query_text='Trace Ada\'s public commitment to the community schools.',
            catalog=dict(kind='person_event', storyline_name='Philanthropy'))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('No live network in candidate reading checks')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def lead(store, name, provider='bocha', summary='Ada discussed community approval before committing.'):
    return store.register('https://example.org/' + name, title=name,
        discovery=dict(provider=provider, query='Ada school commitment', snippet=summary,
                       summary=summary, published_at='2001-01-01'))


def save(store, sid, text):
    return store.save_raw(sid, text.encode(), 'txt')


@pytest.mark.parametrize('finalize', [False, True])
@pytest.mark.parametrize('summary', ['Ada discussed community approval before committing.', ''])
def test_uncached_and_cached_unread_hints_survive_without_implicit_fetch(tmp_path, finalize, summary):
    state = SearchState(tmp_path, 'case', task=TASK)
    store = SourceStore(state)
    cached = lead(store, 'cached', 'exa', summary=summary)
    save(store, cached, 'The schools opened.')
    unfetched = lead(store, 'interview', 'baidu', summary=summary)
    failed = lead(store, 'unavailable', summary=summary)
    def blocked(url):
        raise OSError('Synthetic inaccessible page')
    assert SearchTools(state, fetcher=blocked).read_source(failed)['status'] == 'fetch_failed'
    before = deepcopy(state.data)
    files = {p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    context = context_for(state, finalize=finalize)
    candidates = {s['source_id']:s for s in context['sources']}
    for sid in (cached, unfetched, failed):
        assert not candidates[sid]['reviewed']
        assert candidates[sid]['title'] and candidates[sid]['url']
        hint = candidates[sid]['leads'][0]
        assert hint['query'] == 'Ada school commitment'  # Usable even with empty provider excerpts.
        assert hint['summary'] == hint['snippet'] == summary
        assert 'read_evidence' not in candidates[sid]
    assert candidates[cached]['body_available']
    assert not candidates[unfetched]['body_available']
    assert candidates[failed]['fetch_error'] == 'OSError'
    assert context['reading_summary'] == dict(candidates=3, inspected=0,
        unread_candidates=3, saved_unread=1, unfetched_candidates=1, fetch_failed=1, parse_failed=0)
    assert context['allowed_actions'] == (['finish'] if finalize else ['search','read_source','finish'])
    assert state.data == before
    assert files == {p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('provider', ['baidu', 'bocha', 'exa'])
def test_promising_uncached_read_enters_handoff_as_original_not_discovery_summary(tmp_path, provider):
    state = SearchState(tmp_path, 'case', task=TASK,
                        config=SearchConfig(max_read_sources=2, max_model_calls=8))
    store = SourceStore(state)
    cached = lead(store, 'announcement', 'exa')
    save(store, cached, 'The foundation announced support for schools.')
    store.read(cached)
    pending = lead(store, 'interview', provider,
                   summary='UNVERIFIED: Ada personally constructed every school.')
    ignored = lead(store, 'unrelated', 'bocha')
    original = 'Ada requested community approval before promising support.\n\nThe precise day was not reported.'
    fetched = []
    def fetch(url):
        fetched.append(url)
        assert url == 'https://example.org/interview'
        return original.encode(), 'txt', 'utf-8'
    calls = []
    def decide(context):
        calls.append(context)
        candidate = next(s for s in context['sources'] if s['source_id'] == pending)
        if len(calls) == 1:
            assert not candidate['body_available'] and not candidate['reviewed']
            return dict(action='read_source', source=pending, query='community approval',
                        gap='Clarify her condition before committing support.')
        assert candidate['reviewed'] and candidate['body_available']
        return dict(action='finish', source_ids=[cached, pending], gaps=[], reason='supported',
                    person_evidence=dict(status='supported', detail='The interview reports her condition.'))
    run_agent(state, SearchTools(state, fetcher=fetch,
              transport=lambda *a:pytest.fail('No extra search')), decide)
    assert state.data['status'] == 'finished'
    assert state.data['usage'] == {'model':2, 'search':0}
    assert fetched == ['https://example.org/interview']
    assert state.data['read_sources'] == [cached, pending]
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']:
        DataSample(**sample)
    text = '\n'.join(s['content'] for s in payload['samples'])
    assert original in text and 'UNVERIFIED' not in text
    assert ignored not in {s['raw_data_id'] for s in payload['samples']}
    assert not state.data['sources'][ignored].get('version')


def test_failed_lead_can_trace_an_original_with_existing_search_and_read_budgets(tmp_path):
    state = SearchState(tmp_path, 'case', task=TASK,
                        config=SearchConfig(providers=['bocha'], max_search_requests=1, max_read_sources=2, max_model_calls=8))
    secondary_url, original_url = 'https://example.org/secondary', 'https://example.org/original'
    store = SourceStore(state)
    secondary = lead(store, 'secondary')
    original = digest(original_url)[:24]
    fetched, searches, calls = [], [], []
    def fetch(url):
        fetched.append(url)
        if url == secondary_url:
            raise OSError('Synthetic inaccessible page')
        assert url == original_url
        return b'Ada made the promise conditional on community approval.', 'txt', 'utf-8'
    def provider(name, request, config):
        searches.append((name, request['query']))
        return {'data': {'webPages': {'value': [dict(url=original_url, name='Original interview')]}}}
    def decide(context):
        calls.append(context)
        if len(calls) == 1:
            return dict(action='read_source', source=secondary)
        if len(calls) == 2:
            failed = next(s for s in context['sources'] if s['source_id'] == secondary)
            assert failed['status'] == 'fetch_failed' and failed['fetch_error'] == 'OSError'
            assert context['reading_summary']['fetch_failed'] == 1
            return dict(action='search', query='Ada interview community approval',
                        gap='Locate the original interview after the secondary page was inaccessible.')
        if len(calls) == 3:
            assert context['remaining']['read_sources'] == 1
            return dict(action='read_source', source=original)
        return dict(action='finish', source_ids=[original], reason='supported',
                    gaps=['The secondary page was inaccessible; the original interview was read.'])
    run_agent(state, SearchTools(state, transport=provider, fetcher=fetch), decide)
    assert state.data['usage'] == {'model':4, 'search':1}
    assert fetched == [secondary_url, original_url]
    assert searches == [('bocha', 'Ada interview community approval')]
    assert state.data['read_sources'] == [secondary, original]
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert [s['raw_data_id'] for s in payload['samples']] == [original]
    assert 'conditional on community approval' in payload['samples'][0]['content']


def test_misnested_cursor_reads_exact_position_without_extra_model_call(tmp_path):
    state = SearchState(tmp_path, 'case', task=TASK)
    store = SourceStore(state)
    sid = store.register('https://example.org/interview')
    store.save_raw(sid, b'First statement. Then consent was given.', 'txt')
    action = dict(action='read_source', source=sid, block=0, offset=17, query='')
    before = deepcopy(action)
    result = execute_action(state, SearchTools(state), action)
    assert result['spans'][0]['start'] == 17
    assert result['spans'][0]['text'].startswith('Then consent')
    assert action == before and state.data['usage']['model'] == 0
    events = [json.loads(line) for line in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    repair = next(e for e in events if e['action'] == 'action_normalized')
    assert repair['location'] == {'block':0, 'offset':17} and repair['removed_empty_query']


@pytest.mark.parametrize('fields', [
    {'block':0, 'offset':0, 'query':'consent'},
    {'block':0, 'location':{'block':1}},
    {'block':True}, {'block':-1}, {'offset':10},
    {'block':0, 'location':{'start':0}},
])
def test_ambiguous_or_invalid_cursor_never_fetches(tmp_path, fields):
    state = SearchState(tmp_path, 'case', task=TASK)
    sid = lead(SourceStore(state), 'interview')
    tools = SearchTools(state, fetcher=lambda *a:pytest.fail('Invalid cursor must not fetch'))
    before = deepcopy(state.data)
    with pytest.raises(ValueError):
        execute_action(state, tools, dict(action='read_source', source=sid, **fields))
    assert state.data == before
