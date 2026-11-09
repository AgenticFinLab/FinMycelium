"""Provider adapters behind one search operation. No provider-specific agent loop."""
import os
import time
from dataclasses import asdict
from .sources import SourceStore, canonical_url
from .state import LimitReached, digest, write_json
from .provider_health import ProviderHealth, ProviderRequestError, check_response, failure_details

ENDPOINTS = {'baidu': ('https://qianfan.baidubce.com/v2/ai_search/web_search', 'BAIDUSEARCH_API_KEY'),
             'bocha': ('https://api.bocha.cn/v1/web-search', 'BOCHA_API_KEY'),
             'exa': ('https://api.exa.ai/search', 'EXA_API_KEY')}


BAIDU_QUERY_UNITS = 72


class QueryLimitError(ValueError):
    def __init__(self, provider, units, limit):
        self.provider, self.units, self.limit = provider, units, limit
        super().__init__(f'{provider.title()} query uses {units} units; shorten or split it to at most {limit} units')


def search_constraints(config):
    """Expose the same limits used by payload validation to the decision model."""
    return dict(providers=config.providers, requests_per_new_query=len(config.providers),
                search_enabled=config.max_search_requests > 0,
                follow_up_requires_gap=True,
                max_results_per_provider=config.max_results,
                provider_queries_supported=True,
                provider_constraints={provider: {
                    'query_max_units': BAIDU_QUERY_UNITS if provider == 'baidu' else None,
                } for provider in config.providers},
                query_limit_scope='per_provider',
                query_max_units=BAIDU_QUERY_UNITS if 'baidu' in config.providers else None,
                query_unit_rule='U+4E00..U+9FFF counts 2; each other character counts 1',
                strategy=('Read shared candidates and finish without provider requests.' if not config.max_search_requests
                          else 'Providers are independent. Keep query as the original question and use '
                               'provider_queries to supply a shorter query for a constrained provider, '
                               'preserving the subject and missing fact. Other successful provider queries '
                               'remain cached; read their results even if another provider rejected its query.'))


def request_payload(provider, query, config):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Query must be nonempty')
    start, end = config.publication_start, config.publication_end
    if provider == 'baidu':
        units = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in query)
        if units > BAIDU_QUERY_UNITS:
            raise QueryLimitError(provider, units, BAIDU_QUERY_UNITS)
        if bool(start) != bool(end):
            raise ValueError('Baidu requires both publication bounds')
        payload = dict(messages=[{'role':'user','content':query}], edition='standard',
                       search_source='baidu_search_v2', query_policy={'enable_rewrite':config.baidu_rewrite},
                       resource_type_filter=[{'type':'web','top_k':config.max_results}])
        if config.include_domains:
            payload['search_filter'] = {'match': {'site': config.include_domains}}
        if config.exclude_domains:
            payload['block_websites'] = config.exclude_domains
        if start:
            payload.setdefault('search_filter', {})['range'] = {'page_time': {'gte': start, 'lte': end}}
        return payload
    if provider == 'bocha':
        if config.include_domains or config.exclude_domains:
            raise ValueError('Bocha domain filter mapping is not yet verified')
        if bool(start) != bool(end):
            raise ValueError('Bocha requires both publication bounds')
        payload = dict(query=query, summary=True, count=config.max_results)
        if start:
            payload['freshness'] = start + '..' + end
        return payload
    if provider == 'exa':
        payload = dict(query=query, type='auto', numResults=config.max_results, contents={'text':True})
        if start:
            payload['startPublishedDate'] = start + 'T00:00:00.000Z'
        if end:
            payload['endPublishedDate'] = end + 'T23:59:59.999Z'
        if config.include_domains:
            payload['includeDomains'] = config.include_domains
        if config.exclude_domains:
            payload['excludeDomains'] = config.exclude_domains
        return payload
    raise ValueError('Unknown provider')


def http_transport(provider, payload, config):
    if not config.allow_network:
        raise PermissionError('Network execution is disabled')
    import requests
    url, key_name = ENDPOINTS[provider]
    key = os.environ.get(key_name)
    if not key:
        raise ProviderRequestError({'category': 'authentication', 'http_status': None,
                                    'provider_code': None, 'retryable': False})
    headers = {'Content-Type': 'application/json'}
    headers['x-api-key' if provider == 'exa' else 'Authorization'] = key if provider == 'exa' else 'Bearer ' + key
    response = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
    response.raise_for_status()
    return response.json()


def normalize(provider, response, *, diagnostics=None):
    if not isinstance(response, dict):
        raise ValueError('Malformed provider response')
    check_response(provider, response)
    if provider == 'bocha':
        if response.get('code', 200) not in (200, '200'):
            raise ValueError('Bocha reported failure')
        items = response['data']['webPages']['value']
    elif provider == 'baidu':
        items = response['references']
    else:
        items = response['results']
    if not isinstance(items, list):
        raise ValueError('Malformed result list')
    results = []
    for index, item in enumerate(items):
        try:
            if not isinstance(item, dict) or not isinstance(item.get('url'), str):
                raise ValueError('Malformed result item')
            url = canonical_url(item['url'])
        except ValueError:
            if diagnostics is not None:
                diagnostics['rejected_result_count'] = diagnostics.get('rejected_result_count', 0) + 1
                # Index and reason locate bad rows without copying potentially
                # sensitive invalid URLs or arbitrary provider response values.
                rows = diagnostics.setdefault('rejected_results', [])
                if len(rows) < 20:
                    rows.append({'index': index, 'reason': 'invalid_result_or_url'})
            continue
        def text(name, default=''):
            value = item.get(name, default)
            return value if isinstance(value, str) else ''
        results.append(dict(url=url, title=text('title',text('name')),
            snippet=text('snippet'), summary=text('summary'),
            published_at=item.get('publishedDate',item.get('datePublished',item.get('date'))),
            text=item.get('text') if provider == 'exa' else None))
    return results


class SearchTools:
    def __init__(self, state, *, transport=None, fetcher=None, source_pool=None):
        self.state = state
        self.sources = SourceStore(state, fetcher)
        self.transport = transport or http_transport
        self.source_pool = source_pool
        self.provider_health = ProviderHealth(state)

    def search_availability(self):
        return self.provider_health.availability()

    def begin_invocation(self):
        self.provider_health.begin_invocation()

    def refresh_shared_sources(self):
        return self.source_pool.refresh(self.state) if self.source_pool is not None else []

    def search(self, query, *, provider_queries=None):
        config = self.state.config
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Query must be nonempty')
        if provider_queries is not None:
            if not isinstance(provider_queries, dict):
                raise ValueError('provider_queries must map configured provider names to query strings')
            unknown = set(provider_queries) - set(config.providers)
            if unknown:
                raise ValueError('provider_queries contains an unconfigured provider')
        overrides = provider_queries or {}
        found, outcomes = [], []
        for provider in config.providers:
            provider_query = overrides.get(provider, query)
            # Strip only surrounding whitespace. Word deletion or character slicing
            # can change the missing fact; semantic shortening belongs to the model.
            if isinstance(provider_query, str):
                provider_query = provider_query.strip()
            try:
                payload = request_payload(provider, provider_query, config)
            except ValueError as exc:
                # One provider's limits must not prevent another provider from
                # returning useful evidence. Rejected payloads consume no request.
                outcome = dict(provider=provider, status='invalid_query' if isinstance(exc, QueryLimitError)
                               else 'invalid_request', error_type=type(exc).__name__, hint=str(exc),
                               query=provider_query, request_sent=False)
                if isinstance(exc, QueryLimitError):
                    outcome.update(query_units=exc.units, query_max_units=exc.limit,
                        hint=f'{provider} query uses {exc.units} units; its limit is {exc.limit}. '
                             f'Use provider_queries["{provider}"] for a shorter query preserving the subject '
                             'and missing fact, or read the other providers\' results. No request was sent '
                             'to this provider; keep the original query to reuse other providers\' cached results.')
                outcomes.append(outcome)
                self.state.trace(dict(action='provider_result', **outcome, result_count=None,
                                      duration_seconds=0))
                continue
            key = digest([provider, payload])
            cached = self.state.data['cache'].get(key)
            if cached is not None:
                outcomes.append(dict(provider=provider, status='cached', query=provider_query))
                found.extend(cached)
                continue
            if self.state.data['usage']['search'] >= config.max_search_requests:
                outcomes.append(dict(provider=provider, status='limit'))
                continue
            health = self.provider_health.status(provider)
            if health['status'] != 'available':
                outcome = dict(provider=provider, **health, request_sent=False)
                outcomes.append(outcome)
                self.state.trace(dict(action='provider_result', **outcome,
                                      result_count=None, duration_seconds=0))
                continue
            try:
                self.state.consume('search')
            except LimitReached:
                outcomes.append(dict(provider=provider,status='limit'))
                continue
            started = time.monotonic()
            self.state.trace(dict(action='provider_started',provider=provider,query=provider_query))
            diagnostics = {}
            try:
                response = self.transport(provider, payload, config)
                items = normalize(provider, response, diagnostics=diagnostics)[:config.max_results]
            except Exception as exc:
                details = failure_details(exc, now=self.provider_health.clock())
                health = self.provider_health.failure(provider, details)
                outcomes.append(dict(provider=provider, status='failed', error_type=type(exc).__name__,
                                     error_details=details, provider_state=health['status'],
                                     request_sent=True, hint=health.get('hint', 'Inspect saved sources or another provider.')))
                # Failed response bodies may echo secrets or arbitrary source text.
                # Persist bounded diagnostics only, including for HTTP-200 errors.
                write_json(self.state.run_dir / 'responses' / (str(self.state.data['usage']['search']) + '.json'),
                           dict(provider=provider, error_type=type(exc).__name__, error_details=details))
            else:
                # Persistence failures belong to this task's storage boundary;
                # they must never mark a functioning provider as unavailable.
                self.provider_health.success(provider)
                write_json(self.state.run_dir / 'responses' / (str(self.state.data['usage']['search']) + '.json'),
                           dict(provider=provider, request=payload, response=response))
                ids = []
                for item in items:
                    sid = self.sources.register(item['url'],title=item['title'],
                        discovery=dict(provider=provider,query=provider_query,options=payload,
                                       snippet=item['snippet'],summary=item['summary'],published_at=item['published_at']))
                    ids.append(sid)
                    # Search-returned text may be incomplete. Never label it a full document.
                    if isinstance(item['text'], str) and item['text'].strip() and not self.state.data['sources'][sid].get('version'):
                        self.sources.save_raw(sid, item['text'].encode(), 'txt', partial=True)
                self.state.data['cache'][key] = ids
                found.extend(ids)
                outcomes.append(dict(provider=provider,status='success' if ids else 'no_results', **diagnostics))
            self.state.trace(dict(action='provider_result',**outcomes[-1],
                                  result_count=len(ids) if outcomes[-1]['status'] in {'success','no_results'} else None,
                                  duration_seconds=round(time.monotonic()-started,3)))
            self.state.save()
        result = dict(source_ids=list(dict.fromkeys(found)), providers=outcomes,
                      needs_query_repair=any(o['status'] == 'invalid_query' for o in outcomes),
                      **self.search_availability())
        if result['needs_query_repair']:
            result['hint'] = ('Only the listed provider queries were rejected. Use available sources now, '
                              'or correct those queries with provider_queries while keeping query unchanged '
                              'so successful providers use their cache. Do not repeat the unchanged invalid query.')
        self.state.trace(dict(action='search',query=query,result=result))
        self.state.save()
        return result

    def read_source(self, source, location=None):
        if source not in self.state.data['sources']:
            source = self.sources.register(source)
        started = time.monotonic()
        self.state.trace(dict(action='read_started',source=source,location=location or {}))
        result = self.sources.read(source, **(location or {}))
        if self.source_pool is not None:
            self.source_pool.publish(self.state)
        self.state.trace(dict(action='read_source',source=source,result=result,duration_seconds=round(time.monotonic()-started,3)))
        return result
