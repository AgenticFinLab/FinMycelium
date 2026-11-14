"""Provider adapters behind one search operation. No provider-specific agent loop."""
import os
import time
from dataclasses import asdict
from .sources import SourceStore
from .state import LimitReached, digest, write_json

ENDPOINTS = {'baidu': ('https://qianfan.baidubce.com/v2/ai_search/web_search', 'BAIDUSEARCH_API_KEY'),
             'bocha': ('https://api.bocha.cn/v1/web-search', 'BOCHA_API_KEY'),
             'exa': ('https://api.exa.ai/search', 'EXA_API_KEY')}


BAIDU_QUERY_UNITS = 72


def search_constraints(config):
    """Expose the same limits used by payload validation to the decision model."""
    return dict(providers=config.providers, requests_per_new_query=len(config.providers),
                follow_up_requires_gap=True,
                source_reading=dict(query_or_location=True, max_chars=config.max_read_chars,
                                    query_uses_saved_body=True, consumes_search_requests=False),
                max_results_per_provider=config.max_results,
                query_max_units=BAIDU_QUERY_UNITS if 'baidu' in config.providers else None,
                query_unit_rule='U+4E00..U+9FFF counts 2; each other character counts 1',
                strategy='All selected providers receive the same short question; split distinct questions.')


def request_payload(provider, query, config):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Query must be nonempty')
    start, end = config.publication_start, config.publication_end
    if provider == 'baidu':
        if sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in query) > BAIDU_QUERY_UNITS:
            raise ValueError('Shorten or split query to Baidu 72-unit limit')
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
        raise ValueError('Missing credential: ' + key_name)
    headers = {'Content-Type': 'application/json'}
    headers['x-api-key' if provider == 'exa' else 'Authorization'] = key if provider == 'exa' else 'Bearer ' + key
    response = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
    response.raise_for_status()
    return response.json()


def normalize(provider, response):
    if not isinstance(response, dict):
        raise ValueError('Malformed provider response')
    if provider == 'bocha':
        if response.get('code', 200) != 200:
            raise ValueError('Bocha reported failure')
        items = response['data']['webPages']['value']
    elif provider == 'baidu':
        items = response['references']
    else:
        items = response['results']
    if not isinstance(items, list):
        raise ValueError('Malformed result list')
    results = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('url'), str):
            raise ValueError('Malformed result item')
        results.append(dict(url=item['url'], title=item.get('title',item.get('name','')),
            snippet=item.get('snippet',''), summary=item.get('summary',''),
            published_at=item.get('publishedDate',item.get('datePublished',item.get('date'))),
            text=item.get('text') if provider == 'exa' else None))
    return results


class SearchTools:
    def __init__(self, state, *, transport=None, fetcher=None):
        self.state = state
        self.sources = SourceStore(state, fetcher)
        self.transport = transport or http_transport

    def search(self, query):
        config = self.state.config
        # Validate all selected providers before any request; never silently truncate.
        payloads = {p:request_payload(p, query, config) for p in config.providers}
        found, outcomes = [], []
        for provider, payload in payloads.items():
            key = digest([provider, payload])
            cached = self.state.data['cache'].get(key)
            if cached is not None:
                outcomes.append(dict(provider=provider, status='cached'))
                found.extend(cached)
                continue
            try:
                self.state.consume('search')
            except LimitReached:
                outcomes.append(dict(provider=provider,status='limit'))
                continue
            started = time.monotonic()
            self.state.trace(dict(action='provider_started',provider=provider,query=query))
            try:
                response = self.transport(provider, payload, config)
                write_json(self.state.run_dir / 'responses' / (str(self.state.data['usage']['search']) + '.json'),
                           dict(provider=provider, request=payload, response=response))
                items = normalize(provider, response)[:config.max_results]
                ids = []
                for item in items:
                    sid = self.sources.register(item['url'],title=item['title'],
                        discovery=dict(provider=provider,query=query,options=payload,
                                       snippet=item['snippet'],summary=item['summary'],published_at=item['published_at']))
                    ids.append(sid)
                    # Search-returned text may be incomplete. Never label it a full document.
                    if isinstance(item['text'], str) and item['text'].strip() and not self.state.data['sources'][sid].get('version'):
                        self.sources.save_raw(sid, item['text'].encode(), 'txt', partial=True)
                self.state.data['cache'][key] = ids
                found.extend(ids)
                outcomes.append(dict(provider=provider,status='success' if ids else 'no_results'))
            except Exception as exc:
                outcomes.append(dict(provider=provider,status='failed',error_type=type(exc).__name__))
            self.state.trace(dict(action='provider_result',**outcomes[-1],
                                  result_count=len(ids) if outcomes[-1]['status'] in {'success','no_results'} else None,
                                  duration_seconds=round(time.monotonic()-started,3)))
            self.state.save()
        result = dict(source_ids=list(dict.fromkeys(found)), providers=outcomes)
        self.state.trace(dict(action='search',query=query,result=result))
        return result

    def read_source(self, source, location=None, *, query=None):
        if query is not None and (not isinstance(query, str) or not query.strip()):
            raise ValueError('Reading query must be nonempty text')
        if query is not None and location:
            raise ValueError('Choose a reading query or an explicit location, not both')
        if source not in self.state.data['sources']:
            source = self.sources.register(source)
        started = time.monotonic()
        self.state.trace(dict(action='read_started',source=source,location=location or {},query=query))
        result = self.sources.read(source, **(location or {}), query=query)
        self.state.trace(dict(action='read_source',source=source,result=result,duration_seconds=round(time.monotonic()-started,3)))
        return result
