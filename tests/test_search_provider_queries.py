"""Provider limits do not discard another provider's results or consume its quota twice."""
import socket

import pytest

from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, search_constraints


ACTIVISION_QUERY = 'Buffett Berkshire Activision stake 2022 annual meeting arbitrage comments'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Unexpected network'))


def make_tools(tmp_path, **options):
    state = SearchState(tmp_path, 'case', task=dict(
        target_type='event', target_name='Activision', query_text='Buffett 2022–2023'),
        config=SearchConfig(**options))
    calls = []
    def transport(provider, payload, config):
        calls.append((provider, payload))
        item = dict(url='https://example.org/' + provider, title=provider)
        if provider == 'bocha':
            return {'data': {'webPages': {'value': [item]}}}
        if provider == 'baidu':
            return {'references': [item]}
        return {'results': [item]}
    return state, SearchTools(state, transport=transport), calls


@pytest.mark.parametrize('providers', [['baidu', 'bocha'], ['bocha', 'baidu']])
def test_actual_73_unit_query_preserves_bocha_results_in_either_order(tmp_path, providers):
    state, tools, calls = make_tools(tmp_path, providers=providers)
    result = tools.search(ACTIVISION_QUERY)
    assert [provider for provider, _ in calls] == ['bocha']
    assert calls[0][1]['query'] == ACTIVISION_QUERY  # No words are silently removed.
    assert len(result['source_ids']) == 1
    assert state.data['usage']['search'] == 1
    rejected = next(o for o in result['providers'] if o['provider'] == 'baidu')
    assert rejected['status'] == 'invalid_query'
    assert rejected['query_units'] == 73 and rejected['query_max_units'] == 72
    assert rejected['request_sent'] is False
    assert 'provider_queries["baidu"]' in rejected['hint']


def test_provider_specific_repair_reuses_successful_provider_cache(tmp_path):
    state, tools, calls = make_tools(tmp_path, providers=['bocha', 'baidu'])
    initial = tools.search(ACTIVISION_QUERY)
    repeated = tools.search(ACTIVISION_QUERY)
    assert [o['status'] for o in repeated['providers']] == ['cached', 'invalid_query']
    assert repeated['source_ids'] == initial['source_ids']
    assert state.data['usage']['search'] == 1
    short = 'Buffett Activision arbitrage rationale 2022 annual meeting'
    repaired = tools.search(ACTIVISION_QUERY, provider_queries={'baidu': short})
    assert [provider for provider, _ in calls] == ['bocha', 'baidu']
    assert calls[1][1]['messages'][0]['content'] == short
    assert len(repaired['source_ids']) == 2 and repaired['needs_query_repair'] is False
    assert [o['status'] for o in repaired['providers']] == ['cached', 'success']
    assert state.data['usage']['search'] == 2
    baidu = next(s for s in state.data['sources'].values() if s['url'].endswith('/baidu'))
    assert baidu['discoveries'][0]['query'] == short
    resumed = SearchState(tmp_path, 'case')
    saved = SearchTools(resumed, transport=lambda *a: pytest.fail('Should reuse cache'))
    assert [o['status'] for o in saved.search(ACTIVISION_QUERY, provider_queries={'baidu': short})['providers']] == ['cached', 'cached']


def test_single_baidu_reports_repair_without_consuming_requests(tmp_path):
    state, tools, calls = make_tools(tmp_path, providers=['baidu'])
    for _ in range(3):
        result = tools.search(ACTIVISION_QUERY)
        assert result['source_ids'] == [] and result['needs_query_repair']
    assert calls == [] and state.data['usage']['search'] == 0
    assert 'invalid_query' in (state.run_dir / 'trace.jsonl').read_text()


def test_provider_override_respects_remaining_budget(tmp_path):
    state, tools, calls = make_tools(tmp_path, providers=['bocha', 'baidu'], max_search_requests=1)
    tools.search(ACTIVISION_QUERY)
    result = tools.search(ACTIVISION_QUERY, provider_queries={'baidu': 'Buffett Activision arbitrage 2022'})
    assert [o['status'] for o in result['providers']] == ['cached', 'limit']
    assert len(calls) == 1 and state.data['usage']['search'] == 1
    assert len(result['source_ids']) == 1


def test_filter_rejection_does_not_drop_filter_or_block_supported_provider(tmp_path):
    state, tools, calls = make_tools(tmp_path, providers=['bocha', 'baidu'], include_domains=['berkshirehathaway.com'])
    result = tools.search('Buffett donations 2023')
    assert [p for p, _ in calls] == ['baidu']
    assert calls[0][1]['search_filter']['match']['site'] == ['berkshirehathaway.com']
    assert [o['status'] for o in result['providers']] == ['invalid_request', 'success']
    assert state.data['usage']['search'] == 1 and len(result['source_ids']) == 1


@pytest.mark.parametrize('overrides', ['baidu', {'not_configured': 'query'}])
def test_invalid_override_shape_rejected_before_requests(tmp_path, overrides):
    state, tools, calls = make_tools(tmp_path, providers=['bocha', 'baidu'])
    with pytest.raises(ValueError, match='provider_queries'):
        tools.search('Buffett', provider_queries=overrides)
    assert calls == [] and state.data['usage']['search'] == 0


def test_invalid_provider_override_does_not_block_other_providers(tmp_path):
    state, tools, calls = make_tools(tmp_path, providers=['baidu', 'bocha'])
    result = tools.search('Buffett', provider_queries={'baidu': ''})
    assert [p for p, _ in calls] == ['bocha']
    assert [o['status'] for o in result['providers']] == ['invalid_request', 'success']


def test_constraints_explain_provider_specific_limits():
    result = search_constraints(SearchConfig(providers=['bocha', 'baidu']))
    assert result['provider_queries_supported']
    assert result['query_limit_scope'] == 'per_provider'
    assert result['provider_constraints']['bocha']['query_max_units'] is None
    assert result['provider_constraints']['baidu']['query_max_units'] == 72
