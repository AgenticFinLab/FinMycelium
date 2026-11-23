"""Search excerpts, original acquisition and provider queries, without services."""
import socket

import pytest

from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, query_units


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected network call')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def state_at(path, providers):
    return SearchState(path, 'case', task=dict(target_type='person', target_name='Ada',
        query_text='Trace the conditions on the commitment.'),
        config=SearchConfig(providers=providers, retrieval={'mode':'bm25'}))


def response(provider, item):
    if provider == 'baidu': return {'references':[item]}
    if provider == 'bocha': return {'data':{'webPages':{'value':[item]}}}
    return {'results':[item]}


@pytest.mark.parametrize('provider,field', [('baidu','content'), ('exa','text')])
@pytest.mark.parametrize('fetch_ok', [True, False])
def test_original_excerpt_is_cached_completed_or_retained_on_failure(tmp_path, provider, field, fetch_ok):
    state = state_at(tmp_path, [provider])
    excerpt = 'Ada made her commitment conditional on local consent.'
    full = excerpt + (' The council granted consent in April and she signed the agreement.'
                      ' The signed document specified the funding schedule and the parties responsible for delivery.')
    item = dict(url='https://example.org/original', **{field:excerpt})
    downloads = []
    def fetch(url):
        downloads.append(url)
        if not fetch_ok: raise TimeoutError()
        return full.encode(), 'txt', None
    tools = SearchTools(state, transport=lambda p, *_: response(p, item), fetcher=fetch)
    sid = tools.search('Ada consent')['source_ids'][0]
    assert downloads == []  # Discovery never downloads every result.
    old_version = state.data['sources'][sid]['version']
    result = tools.read_source(sid, query='Ada consent')
    text = ' '.join(s['text'] for s in result['spans'])
    assert excerpt in text
    assert result['status'] == ('success' if fetch_ok else 'partial')
    if fetch_ok:
        assert 'signed the agreement' in text and result['version'] != old_version
    else:
        assert result['version'] == old_version
        assert result['body_origin'] == dict(origin='search_response', provider=provider, content_field=field)
    resumed = SearchState(tmp_path, 'case')
    again = SearchTools(resumed, fetcher=fetch).read_source(sid, query='Ada consent')
    assert again['version'] == result['version'] and len(downloads) == 1
    assert resumed.data['usage'] == {'search':1, 'model':0}


@pytest.mark.parametrize('fetch_ok', [True, False])
def test_bocha_summary_stays_a_lead_and_selected_url_is_fetched(tmp_path, fetch_ok):
    state = state_at(tmp_path, ['bocha'])
    item = dict(url='https://example.org/interview', snippet='Interview lead',
                summary='A search summary describing the commitment.')
    def fetch(url):
        if not fetch_ok: raise TimeoutError()
        return b'Ada said: I would sign only after local consent.', 'txt', None
    tools = SearchTools(state, transport=lambda p, *_: response(p, item), fetcher=fetch)
    sid = tools.search('Ada consent')['source_ids'][0]
    assert not state.data['sources'][sid].get('version')
    result = tools.read_source(sid)
    if fetch_ok:
        assert result['status'] == 'success' and 'I would sign' in result['spans'][0]['text']
        assert item['summary'] not in result['spans'][0]['text']
    else:
        assert result['status'] == 'fetch_failed' and not result.get('spans')
        assert result['search_leads'] == [dict(provider='bocha', snippet=item['snippet'], summary=item['summary'])]
        assert not state.data['sources'][sid].get('version')


def test_baidu_short_variant_executes_alongside_full_queries_and_is_cached(tmp_path):
    state = state_at(tmp_path, ['baidu','bocha','exa'])
    calls = []
    def transport(provider, payload, config):
        calls.append((provider, payload.get('query') or payload['messages'][0]['content']))
        return response(provider, dict(url='https://example.org/' + provider, snippet='Lead'))
    tools = SearchTools(state, transport=transport)
    full = 'Ada Example 2013 commitment to the public education project conditional on consent, not a completed donation'
    short = 'Ada Example 2013 教育承诺 需同意 非已捐款'
    assert query_units(full) > 72 >= query_units(short)
    result = tools.search(full, provider_queries={'baidu':short})
    assert calls == [('baidu',short), ('bocha',full), ('exa',full)]
    assert all(p['status'] == 'success' for p in result['providers'])
    tools.search(full, provider_queries={'baidu':short})
    assert len(calls) == 3 and state.data['usage'] == {'search':3, 'model':0}


@pytest.mark.parametrize('body', [None, '', '   ', {'text':'not a string'}])
def test_missing_baidu_content_does_not_promote_snippet_to_evidence(tmp_path, body):
    state = state_at(tmp_path, ['baidu'])
    item = dict(url='https://example.org/lead', content=body, snippet='A search lead')
    tools = SearchTools(state, transport=lambda p, *_: response(p, item))
    sid = tools.search('Ada consent')['source_ids'][0]
    assert not state.data['sources'][sid].get('version')
    assert state.data['sources'][sid]['discoveries'][0]['snippet'] == item['snippet']


def test_search_excerpt_cannot_replace_an_existing_original(tmp_path):
    state = state_at(tmp_path, ['baidu'])
    item = dict(url='https://example.org/notice', content='Short search excerpt.')
    tools = SearchTools(state, transport=lambda p, *_: response(p, item))
    sid = tools.sources.register(item['url'])
    original = tools.sources.save_raw(sid, b'Ada signed the agreement after consent.', 'txt')
    tools.search('Ada consent')
    assert state.data['sources'][sid]['version'] == original['version']
    assert state.data['sources'][sid]['status'] == 'success'
