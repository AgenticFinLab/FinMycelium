"""Search excerpts, original acquisition and provider queries, without services."""
import json
import socket

import pytest

from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, query_units
from finmy.search.agent import context_for, execute_action


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
def test_bocha_body_is_cached_before_selection_without_promoting_summary(tmp_path, fetch_ok):
    state = state_at(tmp_path, ['bocha'])
    item = dict(url='https://example.org/interview', snippet='Interview lead',
                summary='A search summary describing the commitment.')
    downloads = []
    def fetch(url):
        downloads.append(url)
        if not fetch_ok: raise TimeoutError()
        return b'Ada said: I would sign only after local consent.', 'txt', None
    tools = SearchTools(state, transport=lambda p, *_: response(p, item), fetcher=fetch)
    search = tools.search('Ada consent')
    sid = search['source_ids'][0]
    assert len(downloads) == 1
    assert state.data['read_sources'] == []
    assert not state.data['sources'][sid].get('read_ranges')
    assert 'body_previews' not in search
    if fetch_ok:
        assert state.data['sources'][sid].get('version')
        assert 'I would sign' in tools.sources.document(sid)['blocks'][0]['text']
    else:
        assert not state.data['sources'][sid].get('version')
    tools.search('Ada consent again')
    assert len(downloads) == 1  # A second search must not download/retry it again.
    result = tools.read_source(sid)
    if fetch_ok:
        assert result['status'] == 'success' and 'I would sign' in result['spans'][0]['text']
        assert item['summary'] not in result['spans'][0]['text']
    else:
        assert result['status'] == 'fetch_failed' and not result.get('spans')
        assert result['search_leads'][-1] == dict(provider='bocha', snippet=item['snippet'], summary=item['summary'])
        assert not state.data['sources'][sid].get('version')


@pytest.mark.parametrize('provider', ['baidu', 'bocha'])
def test_cached_body_reaches_agent_read_and_handoff_with_plain_marks(tmp_path, provider):
    state = state_at(tmp_path, [provider])
    body = 'Ada said: I would sign only after local consent.'
    item = dict(url='https://example.org/interview', snippet='Interview lead', summary='Generated summary')
    if provider=='baidu': item['content']=body
    fetched=[]
    def fetch(url):
        fetched.append(url)
        return body.encode(), 'txt', None
    tools=SearchTools(state, transport=lambda p,*_:response(p,item), fetcher=fetch)
    search=execute_action(state,tools,dict(action='search',query='Ada consent'))
    state.data['feedback']=search
    sid=search['source_ids'][0]
    context=context_for(state)
    assert 'body_previews' not in context['feedback']
    assert context['sources'][0]['source_id']==sid and context['sources'][0]['body_available']
    assert not state.data['sources'][sid].get('read_ranges')
    result=execute_action(state,tools,dict(action='read_source',source=sid,query='Ada consent'))
    span=next(s for s in result['spans'] if body in s['text'])
    mark=dict(source_id=sid,**{k:span[k] for k in ('block','start','end')},reason='Consent condition')
    finish=execute_action(state,tools,dict(action='finish',source_ids=[sid],gaps=[],reason='supported',priority_passages=[mark]))
    assert 'handoff' in finish and state.data['stop_reason']=='supported'
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert body in payload['samples'][0]['content']
    assert 'Generated summary' not in payload['samples'][0]['content']
    assert not state.data.get('followup_finish_reviewed')
    assert state.data['usage']=={'search':1,'model':0}
    resumed=SearchState(tmp_path,'case')
    again=SearchTools(resumed,fetcher=lambda u:pytest.fail('Cached original was fetched again'))
    assert body in str(again.read_source(sid)['spans'])
    assert len(fetched)==1


def test_missing_baidu_body_is_fetched_and_multi_provider_url_is_fetched_once(tmp_path):
    state=state_at(tmp_path,['baidu','bocha'])
    item=dict(url='https://example.org/shared',snippet='Lead',summary='Summary')
    calls=[]
    def fetch(url):
        calls.append(url)
        return b'Ada obtained local consent before signing.', 'txt', None
    tools=SearchTools(state,transport=lambda p,*_:response(p,item),fetcher=fetch)
    result=tools.search('Ada consent')
    assert len(result['source_ids'])==1 and calls==[item['url']]
    assert 'body_previews' not in result
    assert 'local consent' in tools.sources.document(result['source_ids'][0])['blocks'][0]['text']
    assert state.data['usage']=={'search':2,'model':0}


def test_all_provider_bodies_stay_cached_without_search_previews(tmp_path):
    state=state_at(tmp_path,['baidu','bocha','exa'])
    body='Ada needs local consent before signing the agreement.'
    def transport(provider,*_):
        item=dict(url='https://example.org/'+provider,snippet='Discovery lead',
                  content=body,text=body,summary='Summary')
        return response(provider,item)
    tools=SearchTools(state,transport=transport,fetcher=lambda u:(body.encode(),'txt',None))
    result=tools.search('Ada consent')
    assert 'body_previews' not in result and len(result['source_ids'])==3
    assert all(body==tools.sources.document(sid)['blocks'][0]['text'] for sid in result['source_ids'])
    state.data['feedback']=result
    assert body not in json.dumps(context_for(state))
    assert not state.data['read_sources']
    assert all(not e.get('read_ranges') for e in state.data['sources'].values())


@pytest.mark.parametrize('finalize',[False,True])
def test_resume_drops_old_search_previews_from_context(tmp_path,finalize):
    state=state_at(tmp_path,['bocha'])
    state.data['feedback']=dict(source_ids=[],providers=[],body_previews=[dict(text='OLD_PREVIEW')])
    state.save()
    resumed=SearchState(tmp_path,'case')
    context=context_for(resumed,finalize=finalize)
    assert context['feedback']==dict(source_ids=[],providers=[])
    assert 'OLD_PREVIEW' not in json.dumps(context)
    assert resumed.data['feedback']==state.data['feedback']


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
