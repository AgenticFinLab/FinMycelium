"""Partial-source expansion is bounded, versioned and independent of paid APIs."""
import json
import socket

import pytest

from finmy.search.agent import context_for
from finmy.search.sources import SourceStore, parse_document
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Acquisition checks must use saved text or injected responses')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


INTRO = ('The interviewer asked Ada how she prepared the education program. '
         'Ada described obtaining consent, reallocating resources and consulting the community. '
         'The initial plan remained subject to further discussion.')
ENDING = ('Ada then explained that the resources supported several programs, including this one. '
          'Approval depended on local consent; the date of the final decision was not specified.')


def setup(tmp_path, fetcher=None, **config):
    state = SearchState(tmp_path, 'case', task=dict(target_type='person', target_name='Ada',
                        query_text='Research Ada and the education program.'), config=SearchConfig(**config))
    tools = SearchTools(state, fetcher=fetcher)
    sid = tools.sources.register('https://example.org/interview', title='An interview with Ada')
    doc = tools.sources.save_raw(sid, INTRO.encode(), 'txt', partial=True)
    return state, tools, sid, doc


def test_partial_is_expanded_before_reading_and_original_is_preserved(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        return ('<nav>Unrelated menus</nav><article><p>' + INTRO + '</p><p>' + ENDING +
                '</p></article><footer>More links</footer>').encode(), 'html', 'utf-8'
    state, tools, sid, original = setup(tmp_path, fetch)
    result = tools.read_source(sid, query='Ada preparation')
    assert ENDING in ' '.join(s['text'] for s in result['spans'])
    assert 'Unrelated menus' not in ' '.join(s['text'] for s in result['spans'])
    assert result['version'] != original['version'] and result['status'] == 'success'
    assert tools.sources.document(sid, original['version']) == original
    assert all(r['version'] == result['version'] for r in state.data['sources'][sid]['read_ranges'])
    # Resume and reread: acquisition is not retried or charged as a new source.
    resumed = SearchState(tmp_path, 'case')
    SearchTools(resumed, fetcher=fetch).read_source(sid, query='Ada preparation')
    assert len(calls) == 1 and state.data['read_sources'] == [sid]
    assert state.data['usage'] == {'search': 0, 'model': 0}
    assert context_for(resumed)['sources'][0]['acquisition']['status'] == 'expanded'
    events = [json.loads(line) for line in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    assert sum(e['action'] == 'source_acquisition_result' for e in events) == 1


@pytest.mark.parametrize('response', ['blocked', 'shorter', 'unrelated', 'oversize', 'unparseable'])
def test_failed_or_unhelpful_fetch_keeps_cached_text_and_is_not_repeated(tmp_path, response):
    calls = []
    def fetch(url):
        calls.append(url)
        if response == 'blocked':
            raise PermissionError('Access denied')
        if response == 'shorter':
            return b'<article><p>Subscribe to read the interview.</p></article>', 'html', 'utf-8'
        if response == 'unrelated':
            return ('Unrelated advertising content. '*50).encode(), 'txt', 'utf-8'
        if response == 'oversize':
            return (INTRO*20).encode(), 'txt', 'utf-8'
        return b'garbage', 'pdf', 'utf-8'
    state, tools, sid, original = setup(tmp_path, fetch, max_download_bytes=2000)
    result = tools.read_source(sid, query='Ada')
    assert result['version'] == original['version'] and result['status'] == 'partial'
    assert ''.join(s['text'] for s in result['spans']) == INTRO
    tools.read_source(sid, query='Ada')
    assert len(calls) == 1
    entry = state.data['sources'][sid]
    assert entry['versions'] == [original['version']]
    assert entry['acquisition_attempts'][original['version']]['status'] == 'kept_cached'


def test_already_inspected_versions_and_their_cursors_do_not_move(tmp_path):
    state, tools, sid, original = setup(tmp_path)
    tools.read_source(sid, query='Ada')  # Offline cached inspection.
    def forbidden(url):
        pytest.fail('An inspected location must not be rebased')
    result = SearchTools(state, fetcher=forbidden).read_source(sid, query='Ada')
    assert result['version'] == original['version']
    result = SearchTools(state, fetcher=forbidden).read_source(sid, location={'offset': 5})
    assert result['spans'][0]['start'] == 5


def test_article_main_and_plain_html_keep_only_visible_originals():
    blocks = parse_document(b'<nav>Menu</nav><main><p>Original question.</p>'
                            b'<article><p>Original answer.</p><script>untrusted command</script>'
                            b'<p>A qualification.</p></article></main><footer>Links</footer>', 'html')
    assert [b['text'] for b in blocks] == ['Original question.', 'Original answer.', 'A qualification.']
    blocks = parse_document(b'<nav>Menu</nav><main><p>Original answer.</p></main>', 'html')
    assert [b['text'] for b in blocks] == ['Original answer.']
    assert parse_document(b'<p>Plain original.</p>', 'html')[0]['text'] == 'Plain original.'
