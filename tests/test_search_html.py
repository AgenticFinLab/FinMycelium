"""Public body acquisition keeps original text, usable statuses and versioned evidence."""
import codecs
import json
import socket
from pathlib import Path

import pytest
import requests

from finmy.search.agent import context_for
from finmy.search.evidence import source_pool
from finmy.search.handoff import assemble_sources
from finmy.search.html import extract_html
from finmy.search.metadata import publication_metadata, source_metadata
from finmy.search.sources import SourceStore, FetchedDocument, fetch_public
from finmy.search.state import SearchState, SearchConfig, digest
from finmy.search.tools import SearchTools
from finmy.runner.sparse_build_runner import load_inputs


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Acquisition tests must not contact websites or APIs')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def setup(tmp_path, fetcher=None):
    state = SearchState(tmp_path, 'case', task=dict(target_type='person', target_name='Ada',
                        query_text='Ada public education commitment, approval and consent.'))
    tools = SearchTools(state, fetcher=fetcher)
    return state, tools


def plain(document):
    return '\n'.join(b['text'] for b in document['blocks'])


@pytest.mark.parametrize('label,codec,header', [
    ('gb2312', 'gb18030', 'ISO-8859-1'), ('GBK', 'gb18030', 'utf-8'),
    ('utf-8', 'utf-8', 'ISO-8859-1'), ('gb2312', 'utf-8', 'gb2312')])
def test_encoding_does_not_turn_chinese_originals_into_latin1(label, codec, header):
    body = '问：为何承诺？答：艾达说需要当地同意，尚未完成。𠀀'
    raw = f'<html><head><meta charset="{label}"></head><body><article><p>{body}</p></article></body></html>'.encode(codec)
    doc = extract_html(raw, header)
    assert doc['status'] == 'success' and plain(doc) == body
    assert doc['encoding'] == codec
    assert doc['declared_encoding'] == label.lower()


@pytest.mark.parametrize('codec,bom', [('utf-8', codecs.BOM_UTF8), ('utf-16-le', codecs.BOM_UTF16_LE)])
def test_bom_overrides_a_conflicting_http_hint(codec, bom):
    doc = extract_html(bom + '<article><p>Élodie pledged support 条件待定.</p></article>'.encode(codec), 'gbk')
    assert plain(doc) == 'Élodie pledged support 条件待定.'
    assert doc['encoding_basis'] == 'bom'


def test_main_preserves_questions_qualifications_and_table_columns_in_order():
    html = '''<html><head><title>Ada interview</title></head><body><nav>MENU</nav>
    <main><h1>Ada interview</h1><p>How did it start?</p>
    <article><p>We asked the community.</p><p>Was it approved?</p>
    <p>Not yet; approval depends on consent.</p>
    <aside><p>Only the initial program was discussed.</p></aside>
    <table><caption>Program support</caption><tr><th>Year</th><th>Amount</th></tr>
    <tr><td>2020</td><td>10,000</td></tr></table></article>
    <p>What happens next?</p><p>We will review the response.</p>
    <div class="advertisement">SALE</div><p hidden>Hidden</p></main><footer>MENU</footer></body></html>'''
    doc = extract_html(html.encode())
    assert doc['extractor'] == 'semantic_dom'
    body = plain(doc)
    assert body.index('How did it start?') < body.index('We asked the community.')
    assert body.index('Was it approved?') < body.index('Not yet;')
    assert body.index('What happens next?') < body.index('We will review')
    assert 'Only the initial program' in body
    assert 'Year | Amount' in body and '2020 | 10,000' in body
    assert all(word not in body for word in ('MENU', 'SALE', 'Hidden'))
    row = next(b for b in doc['blocks'] if b.get('row') == 1)
    assert row['text'] == 'Year | Amount'
    assert [c['column'] for c in row['cells']] == [1, 2]
    assert all(c['header'] for c in row['cells'])


def test_extractor_removes_chrome_from_unmarked_announcement_without_rewriting():
    paragraphs = [
        'On 14 May 2021, Aster announced that its board had approved the public education program, subject to local consent.',
        'Ada said: “We asked the community before making a commitment.” Approval does not mean that the program has begun.',
        'The funding terms provide support for two years. The municipality will review the proposal before work can start.',
        'No closing date has been set. A further notice will explain the outcome of consultation and any changes to the terms.',
    ]
    html = '<html><head><title>Aster approval</title></head><body><nav>Home Sign in</nav><div>'
    html += ''.join('<p>'+p+'</p>' for p in paragraphs) + '</div><footer>Subscribe Contact</footer></body></html>'
    doc = extract_html(html.encode())
    assert doc['extractor'].startswith('trafilatura-')
    assert [b['text'] for b in doc['blocks']] == paragraphs
    assert doc['metadata']['title'] == 'Aster approval'


def test_extractor_reordering_falls_back_to_visible_originals(monkeypatch):
    import trafilatura
    from lxml import etree
    from types import SimpleNamespace
    monkeypatch.setattr(trafilatura, 'bare_extraction', lambda *a, **kw:
                        SimpleNamespace(body=etree.fromstring(b'<body><p>Answer.</p><p>Question?</p></body>')))
    doc = extract_html(b'<html><body><div><p>Question?</p><p>Answer.</p></div></body></html>')
    assert doc['extractor'] == 'dom_fallback'
    assert [b['text'] for b in doc['blocks']] == ['Question?', 'Answer.']


@pytest.mark.parametrize('html,status', [
    ('<html><title>Just a moment...</title><body>Verify you are human</body></html>', 'blocked'),
    ('<html><body><h1>403 Forbidden</h1>Access denied</body></html>', 'blocked'),
    ('<html><body><h1>页面不存在</h1></body></html>', 'error_page'),
    ('<html><body><h1>503 Service Unavailable</h1></body></html>', 'error_page'),
    ('<html><body>Please enable JavaScript to continue.</body></html>', 'shell'),
    ('<html><title>News</title><body><div id="root"></div><script>render()</script></body></html>', 'shell'),
    ('<html><body></body></html>', 'empty'),
])
def test_http_success_error_pages_are_not_inspected_or_handed_off(tmp_path, html, status):
    state, tools = setup(tmp_path, lambda url: (html.encode(), 'html', 'utf-8'))
    sid = tools.sources.register('https://example.org/news')
    result = tools.read_source(sid)
    assert result['status'] == status and not result.get('spans')
    assert result['acquisition_error']['stage'] == 'parse'
    assert state.data['sources'][sid].get('read_ranges', []) == []
    context = context_for(state)
    assert context['sources'][0]['acquisition_state'] == 'parse_failed'
    assert context['reading_summary']['parse_failed'] == 1
    assert context['reading_summary']['fetch_failed'] == 0
    assert context['reading_summary']['inspected'] == 0
    assert source_pool(state, [])[0] == []
    with pytest.raises(ValueError, match='Inspect'):
        source_pool(state, [sid])
    doc = tools.sources.document(sid)
    assert (state.root/'sources'/sid/doc['version']/'raw').read_bytes() == html.encode()
    assert not tools.read_source(sid).get('spans')
    assert len(state.data['sources'][sid]['fetch_attempts']) == 1


def test_short_notice_is_usable_and_invalid_decoding_is_visible():
    assert extract_html(b'<article><p>The meeting was cancelled.</p></article>')['status'] == 'success'
    assert extract_html(b'<html><body>\x00\xff\xfe</body></html>')['status'] == 'garbled'


@pytest.mark.parametrize('already_known', [False, True])
def test_links_follow_redirect_base_and_preserve_actual_parent_not_independence(tmp_path, already_known):
    raw = b'''<html><head><title>Ada interview</title><meta name="author" content="A. Reporter">
    <link rel="canonical" href="/story/interview"><meta property="article:published_time" content="2021-05-14">
    <meta property="article:modified_time" content="2025-10-01"></head><body>
    <main><p>Ada committed support, conditional on consent.</p>
    <a href="./original">Original transcript</a><a href="javascript:alert(1)">Fake</a>
    <a href="http://user:secret@example.org/private">Private</a></main>
    <nav><a href="/story/part-2" rel="next">Next part</a></nav></body></html>'''
    calls = []
    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return FetchedDocument(raw, 'html', None, dict(final_url='https://publisher.org/story/interview'))
        return b'<article><p>Original interview; consent is still required.</p></article>', 'html', 'utf-8'
    state, tools = setup(tmp_path, fetch)
    sid = tools.sources.register('https://example.org/redirect')
    tools.read_source(sid)
    entry = state.data['sources'][sid]
    hints = context_for(state)['sources'][0]['navigation']
    assert hints['authors'] == ['A. Reporter']
    assert {'https://publisher.org/story/original','https://publisher.org/story/part-2'} <= {l['url'] for l in hints['observed_links']}
    assert not any('secret' in l['url'] or l['url'].startswith('javascript') for l in hints['observed_links'])
    assert publication_metadata(entry)['published_at'] == '2021-05-14'
    target = 'https://publisher.org/story/original'
    if already_known:
        target = tools.sources.register(target, discovery=dict(provider='baidu', query='Ada interview'))
    child = tools.read_source(target)['source_id']
    relation = next(d for d in state.data['sources'][child]['discoveries'] if d['provider']=='source_link')
    assert relation['source_id'] == sid and relation['source_version'] == entry['version']
    assert relation['relation'] == 'linked'
    assert len(calls) == 2 and state.data['usage'] == {'search':0, 'model':0}


def test_metadata_and_original_quotes_survive_existing_builder_handoff(tmp_path):
    state, tools = setup(tmp_path)
    sid = tools.sources.register('https://example.org/commitment', discovery=dict(provider='bocha', published_at='2021-05-14'))
    raw = b'<html><head><title>Program notice</title><meta property="article:published_time" content="2021-05-14"></head><body><article><p>Ada approved the program subject to local consent.</p></article></body></html>'
    old = tools.sources.save_raw(sid, raw, 'html')
    tools.read_source(sid)
    original_parse = (state.root/'sources'/sid/old['version']/'parsed.json').read_bytes()
    payload = assemble_sources(state, [sid])
    loaded, _ = load_inputs(state.run_dir/'builder_input.json')
    assert loaded.samples[0].content == payload['samples'][0]['content']
    assert 'Ada approved the program subject to local consent.' in loaded.samples[0].content
    assert 'Publication date (source/provider metadata): 2021-05-14' in loaded.samples[0].content
    # Re-saving and parsing a new version cannot mutate an old paragraph or date.
    assert tools.sources.save_raw(sid, raw, 'html', partial=True) == old
    tools.sources.save_raw(sid, raw.replace(b'2021-05-14', b'2022-06-15'), 'html')
    assert (state.root/'sources'/sid/old['version']/'parsed.json').read_bytes() == original_parse
    assert source_metadata(state.data['sources'][sid], old)['published_at'] == '2021-05-14'


def test_failed_expansion_preserves_download_without_replacing_inspected_evidence(tmp_path):
    blocked = b'<html><head><title>Access denied</title></head><body>Forbidden</body></html>'
    state, tools = setup(tmp_path, lambda url: (blocked, 'html', None))
    sid = tools.sources.register('https://example.org/interview')
    original = tools.sources.save_raw(sid, b'Ada said she would seek community consent before starting the public education program.', 'txt', partial=True)
    result = tools.read_source(sid)
    assert result['version'] == original['version'] and result['status'] == 'partial'
    attempt = state.data['sources'][sid]['acquisition_attempts'][original['version']]
    assert attempt['downloaded_status'] == 'blocked'
    assert (state.root/attempt['artifact']/'raw').read_bytes() == blocked
    assert attempt['raw_sha256'] == digest(blocked)
    assert state.data['sources'][sid]['versions'] == [original['version']]


def test_unattempted_access_failure_and_parser_failure_remain_distinct(tmp_path):
    state, tools = setup(tmp_path)
    for name in ('unread','denied','badpdf'):
        tools.sources.register('https://example.org/'+name)
    def fetch(url):
        if url.endswith('denied'): raise PermissionError('Private diagnostic')
        return b'Invalid PDF', 'pdf', None
    tools = SearchTools(state, fetcher=fetch)
    tools.read_source('https://example.org/denied')
    tools.read_source('https://example.org/badpdf')
    contexts = {s['url'].rsplit('/',1)[-1]:s for s in context_for(state)['sources']}
    assert contexts['unread']['acquisition_state'] == 'not_attempted'
    assert contexts['denied']['acquisition_state'] == 'access_failed'
    assert contexts['badpdf']['acquisition_state'] == 'parse_failed'


def test_http_fetch_does_not_promote_requests_implicit_latin1(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    raw = '<html><body><p>公告：批准仍有条件。</p></body></html>'.encode()
    response = SimpleNamespace(is_redirect=False, status_code=200, encoding='ISO-8859-1',
        headers={'Content-Type':'text/html'}, raise_for_status=lambda:None,
        iter_content=lambda size:iter([raw]))
    monkeypatch.setattr(requests, 'get', lambda *a, **kw:nullcontext(response))
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a, **kw:[(2,1,6,'',('93.184.216.34',443))])
    result = fetch_public('https://example.org/notice', SearchConfig(allow_network=True))
    assert result.encoding is None and result.metadata['http_status'] == 200
    assert plain(extract_html(result.raw,result.encoding)) == '公告：批准仍有条件。'


@pytest.mark.parametrize('provider', ['baidu', 'bocha', 'exa'])
def test_uncached_provider_leads_use_the_same_body_reader(tmp_path, provider):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Program',
        query_text='Program approval and consultation'), config=SearchConfig(providers=[provider]))
    def transport(name, request, config):
        item = dict(url='https://example.org/program', title='Program notice', snippet='A search lead only')
        if name == 'baidu': return dict(references=[item])
        if name == 'bocha': return dict(data=dict(webPages=dict(value=[item])))
        return dict(results=[item])
    calls = []
    def fetch(url):
        calls.append(url)
        return b'<article><p>The community approved the program after consultation.</p></article>', 'html', None
    tools = SearchTools(state, transport=transport, fetcher=fetch)
    sid = tools.search('program consent')['source_ids'][0]
    assert context_for(state)['sources'][0]['acquisition_state'] == 'not_attempted'
    result = tools.read_source(sid)
    assert result['status'] == 'success' and 'after consultation' in result['spans'][0]['text']
    assert calls == ['https://example.org/program']
    assert state.data['usage'] == {'search':1, 'model':0}
    payload = assemble_sources(state, [sid])
    assert 'A search lead only' not in payload['samples'][0]['content']


def test_known_unusable_parse_cannot_replace_a_cached_body_during_expansion(tmp_path):
    text = ('Ada described obtaining local consent before supporting the program. ' * 4)
    raw = ('<article><p>' + text + ' A later response added conditions.' * 6 + '</p></article>').encode()
    state, tools = setup(tmp_path, lambda url:(raw, 'html', None))
    sid = tools.sources.register('https://example.org/program')
    # A prior parse did not recognize this format. Same raw bytes must retain
    # that saved parse, even when the current parser would recognize them.
    rejected = tools.sources.save_raw(sid, raw, 'unsupported')
    cached = tools.sources.save_raw(sid, text.encode(), 'txt', partial=True)
    result = tools.read_source(sid)
    assert result['version'] == cached['version'] and result['status'] == 'partial'
    assert tools.sources.document(sid, rejected['version'])['status'] == 'unsupported'
    attempt = state.data['sources'][sid]['acquisition_attempts'][cached['version']]
    assert attempt['status'] == 'kept_cached'
    assert attempt['artifact'].startswith('sources/')


def test_following_a_rejected_expansion_link_records_that_download(tmp_path):
    raw = b'<article><p>Read the full transcript.</p><a href="https://publisher.org/full">Full transcript</a></article>'
    def fetch(url):
        if url == 'https://example.org/partial': return raw, 'html', None
        return b'<article><p>Ada requested public consent.</p></article>', 'html', None
    state, tools = setup(tmp_path, fetch)
    sid = tools.sources.register('https://example.org/partial')
    cached = tools.sources.save_raw(sid, b'Ada described seeking consent, and the community had not yet responded.', 'txt', partial=True)
    tools.read_source(sid)
    child = tools.read_source('https://publisher.org/full')['source_id']
    parent = next(d for d in state.data['sources'][child]['discoveries'] if d.get('provider')=='source_link')
    assert parent['source_id'] == sid and parent['source_version'] == digest(raw)
    assert (state.root/parent['source_artifact']/'raw').read_bytes() == raw
    assert state.data['sources'][sid]['version'] == cached['version']
