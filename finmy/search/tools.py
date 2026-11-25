"""Provider adapters behind one search operation. No provider-specific agent loop."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from urllib.parse import urlsplit
from .sources import SourceStore
from .errors import SearchConfigurationError, api_configuration_error
from .state import LimitReached, digest, write_json
from .reading import bound_replayed_text, unread_ranges

ENDPOINTS = {'baidu': ('https://qianfan.baidubce.com/v2/ai_search/web_search', 'BAIDUSEARCH_API_KEY'),
             'bocha': ('https://api.bocha.cn/v1/web-search', 'BOCHA_API_KEY'),
             'exa': ('https://api.exa.ai/search', 'EXA_API_KEY')}


BAIDU_QUERY_UNITS = 72


def query_units(query):
    return sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in query)


def search_constraints(config):
    """Expose the same limits used by payload validation to the decision model."""
    return dict(providers=config.providers, requests_per_new_query=len(config.providers),
                follow_up_requires_gap=True,
                source_reading=dict(query_or_location=True, max_chars=config.max_read_chars,
                                    query_uses_saved_body=True, consumes_search_requests=False,
                                    partial_body_original_fetch_once=True),
                max_results_per_provider=config.max_results,
                query_max_units=None, provider_query_max_units={'baidu': BAIDU_QUERY_UNITS},
                query_unit_rule='U+4E00..U+9FFF counts 2; each other character counts 1',
                provider_queries='For selected baidu, include a <=72-unit same-question variant in this action; optional for other providers',
                strategy='All selected providers search the same question; optional provider_queries adapts its expression, not its scope.')


def request_payload(provider, query, config):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Query must be nonempty')
    start, end = config.publication_start, config.publication_end
    if provider == 'baidu':
        units = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in query)
        if units > BAIDU_QUERY_UNITS:
            raise ValueError(f'Query has {units} units; Baidu limit is {BAIDU_QUERY_UNITS} '
                             f'(CJK characters count 2, others 1). Shorten or split this rejected query: {query[:120]!r}')
        if bool(start) != bool(end):
            raise SearchConfigurationError('Baidu requires both publication bounds; correct the task configuration before retrying.')
        payload = dict(messages=[{'role':'user','content':query}], edition='standard',
                       search_source='baidu_search_v2', query_policy={'enable_rewrite':config.baidu_rewrite},
                       resource_type_filter=[{'type':'web','top_k':config.results_for(provider)}])
        if config.include_domains:
            payload['search_filter'] = {'match': {'site': config.include_domains}}
        if config.exclude_domains:
            payload['block_websites'] = config.exclude_domains
        if start:
            payload.setdefault('search_filter', {})['range'] = {'page_time': {'gte': start, 'lte': end}}
        return payload
    if provider == 'bocha':
        if config.include_domains or config.exclude_domains:
            raise SearchConfigurationError('Bocha domain filter mapping is not yet verified; correct the task configuration before retrying.')
        if bool(start) != bool(end):
            raise SearchConfigurationError('Bocha requires both publication bounds; correct the task configuration before retrying.')
        payload = dict(query=query, summary=True, count=config.results_for(provider))
        if start:
            payload['freshness'] = start + '..' + end
        return payload
    if provider == 'exa':
        payload = dict(query=query, type='auto', numResults=config.results_for(provider), contents={'text':True})
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
        raise SearchConfigurationError('Network execution is disabled; enable external calls before retrying.')
    import requests
    url, key_name = ENDPOINTS[provider]
    key = os.environ.get(key_name)
    if not key:
        raise SearchConfigurationError('Set ' + key_name + ' before retrying this task.')
    headers = {'Content-Type': 'application/json'}
    headers['x-api-key' if provider == 'exa' else 'Authorization'] = key if provider == 'exa' else 'Bearer ' + key
    response = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
    response.raise_for_status()
    return response.json()


def normalize(provider, response):
    if not isinstance(response, dict):
        raise ValueError('Malformed provider response')
    if provider == 'bocha':
        if response.get('code') in (401, 403):
            raise SearchConfigurationError('Bocha rejected access; check BOCHA_API_KEY and permissions before retrying this task.')
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
        # Only documented original-text fields can become partial source bodies.
        # Bocha summary and generic snippets remain discovery leads.
        field = {'baidu':'content', 'exa':'text'}.get(provider)
        body = item.get(field) if field else None
        results.append(dict(url=item['url'], title=item.get('title',item.get('name','')),
            snippet=item.get('snippet') or (body if provider == 'baidu' and isinstance(body, str) else ''),
            summary=item.get('summary',''),
            published_at=item.get('publishedDate',item.get('datePublished',item.get('date'))),
            text=body, text_field=field))
    return results


class SearchTools:
    def __init__(self, state, *, transport=None, fetcher=None):
        self.state = state
        self.sources = SourceStore(state, fetcher)
        self.transport = transport or http_transport

    def search(self, query, *, provider_queries=None):
        config = self.state.config
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Query must be nonempty')
        if provider_queries is None:
            provider_queries = {}
        if (not isinstance(provider_queries, dict) or set(provider_queries) - set(config.providers)
                or any(not isinstance(q, str) or not q.strip() for q in provider_queries.values())):
            raise ValueError('provider_queries must map selected providers to nonempty query strings')
        # A provider's length limit must not reject the entire search action.
        queries = {p:provider_queries.get(p, query) for p in config.providers}
        payloads, found, outcomes = {}, [], []
        for provider, original in queries.items():
            adapted = ' '.join(original.split())
            if provider == 'baidu' and query_units(adapted) > BAIDU_QUERY_UNITS:
                # Do not delete entity tokens, negation, qualifiers or operators
                # to satisfy one provider. Preserve the full question elsewhere.
                self.state.trace(dict(action='query_adapted', provider=provider,
                                      original=original, query=adapted))
                if query_units(adapted) > BAIDU_QUERY_UNITS:
                    outcomes.append(dict(provider=provider, query=original, status='skipped_length',
                        hint='Other providers retain the full question. Use a shorter provider_queries variant only if this provider is needed.'))
                    continue
            queries[provider] = adapted
            payloads[provider] = request_payload(provider, adapted, config)
        for provider, payload in payloads.items():
            configuration_error = None
            key = digest([provider, payload])
            cached = self.state.data['cache'].get(key)
            if cached is not None:
                outcomes.append(dict(provider=provider, query=queries[provider], status='cached'))
                found.extend(cached)
                continue
            try:
                self.state.consume('search')
            except LimitReached:
                outcomes.append(dict(provider=provider,query=queries[provider],status='limit'))
                continue
            started = time.monotonic()
            self.state.trace(dict(action='provider_started',provider=provider,query=queries[provider]))
            try:
                response = self.transport(provider, payload, config)
                items = normalize(provider, response)[:config.results_for(provider)]
                write_json(self.state.run_dir / 'responses' / (str(self.state.data['usage']['search']) + '.json'),
                           dict(provider=provider, request=payload, response=response))
                ids = []
                for item in items:
                    sid = self.sources.register(item['url'],title=item['title'],
                        discovery=dict(provider=provider,query=queries[provider],options=payload,
                                       snippet=item['snippet'],summary=item['summary'],published_at=item['published_at']))
                    ids.append(sid)
                    # Search-returned text may be incomplete. Never label it a full document.
                    if isinstance(item['text'], str) and item['text'].strip() and not self.state.data['sources'][sid].get('version'):
                        self.sources.save_raw(sid, item['text'].encode(), 'txt', partial=True,
                            fetch_metadata=dict(origin='search_response', provider=provider,
                                                content_field=item['text_field']))
                self.state.data['cache'][key] = ids
                found.extend(ids)
                outcomes.append(dict(provider=provider,query=queries[provider],status='success' if ids else 'no_results'))
            except Exception as exc:
                outcomes.append(dict(provider=provider,query=queries[provider],status='failed',error_type=type(exc).__name__))
                configuration_error = (exc if isinstance(exc, SearchConfigurationError)
                                       else api_configuration_error(exc, provider + ' search API'))
            self.state.trace(dict(action='provider_result',**outcomes[-1],
                                  result_count=len(ids) if outcomes[-1]['status'] in {'success','no_results'} else None,
                                  duration_seconds=round(time.monotonic()-started,3)))
            self.state.save()
            if configuration_error:
                raise configuration_error
        ids = list(dict.fromkeys(found))
        # Finish acquisition for providers that return leads without originals.
        # Reuse cached bodies across providers/queries/resume. Failed discovery
        # downloads are not retried here; explicit reads retain their retry policy.
        missing = [sid for sid in ids if self.sources.can_complete_partial
            and not self.state.data['sources'][sid].get('version')
            and not self.state.data['sources'][sid].get('fetch_attempts')
            and any(d.get('provider') in {'baidu','bocha'}
                    for d in self.state.data['sources'][sid]['discoveries'])]
        if missing:
            # Download concurrently; parse and persist only on this writer thread.
            with ThreadPoolExecutor(max_workers=min(3, len(missing))) as pool:
                downloads = {sid:pool.submit(self.sources.partial_fetcher,
                    self.state.data['sources'][sid]['url']) for sid in missing}
                for sid, download in downloads.items():
                    started = time.monotonic()
                    self.sources.acquire(sid, fetcher=lambda url, result=download:result.result())
                    self.state.trace(dict(action='search_body_acquisition', source=sid,
                        status=self.state.data['sources'][sid]['status'],
                        wait_and_save_seconds=round(time.monotonic()-started,3)))
        result = dict(source_ids=ids, providers=outcomes)
        self.state.trace(dict(action='search',query=query,provider_queries=provider_queries,result=result))
        return result

    def read_source(self, source, location=None, *, query=None, agent_feedback=False, question=None):
        if question is not None and (not isinstance(question,str) or not question.strip()):
            raise ValueError('Reading question must be nonempty text')
        if location is not None and (not isinstance(location,dict) or set(location)-{'block','offset'}
                or any(type(v) is not int or v<0 for v in location.values())):
            raise ValueError('Copy read_location into location: {"block": integer, "offset": integer}; '
                             'block/start/end identifies evidence, not a reading cursor')
        if query is not None and (not isinstance(query, str) or not query.strip()):
            raise ValueError('Reading query must be nonempty text')
        if query is not None and location:
            raise ValueError('Choose a reading query or an explicit location, not both')
        if source not in self.state.data['sources']:
            if urlsplit(source).scheme not in {'http', 'https'}:
                raise ValueError('Unknown runtime source ID; copy source_id from sources or use a public '
                                 'HTTP(S) URL. Research-plan citations are not runtime IDs; nothing was read.')
            source = self.sources.register_link(source)
        else:
            url = self.state.data['sources'][source]['url']
            if urlsplit(url).scheme in {'http', 'https'}:
                self.sources.register_link(url)
        guarded = agent_feedback and self.state.config.retrieval.get('mode') == 'bm25'
        if guarded:
            from .progress import query_read_feedback, record_query_read
            feedback = query_read_feedback(self.state, source, query, question=question) if query is not None else None
            if feedback:
                self.state.trace(dict(action='read_deferred', source=source, result=feedback))
                return feedback
        started = time.monotonic()
        previous = list(self.state.data['sources'][source].get('read_ranges', []))
        self.state.trace(dict(action='read_started',source=source,location=location or {},query=query))
        result = self.sources.read(source, **(location or {}), query=query)
        if result.get('status') == 'partial':
            result['body_origin'] = self.sources.document(source, result['version']).get('fetch_metadata', {})
        if result.get('status') not in {'success', 'partial'}:
            # Keep leads visible on acquisition failure, outside evidence spans.
            result['search_leads'] = [
                {k:d[k] for k in ('provider', 'snippet', 'summary') if d.get(k)}
                for d in self.state.data['sources'][source]['discoveries'][-2:]
                if d.get('snippet') or d.get('summary')]
        current = [r for r in previous if r['version'] == result.get('version')]
        new_chars = 0
        for span in result.get('spans', []):
            new_chars += sum(b-a for a,b in unread_ranges(span['block'], span['start'], span['end'], current))
            current.append(span)
        result['progress'] = dict(new_chars=new_chars,
            returned_chars=sum(len(s['text']) for s in result.get('spans', [])))
        entry = self.state.data['sources'][source]
        priority_key = digest(sorted((p['block'], p['start'], p['end'])
            for p in self.state.data.get('priority_passages', [])
            if p['source_id'] == source and p['version'] == result.get('version')))
        if agent_feedback:
            bound_replayed_text(entry, result, priority_key=priority_key)
        if not new_chars and 'hint' not in result['progress']:
            result['progress']['hint'] = ('No new original text. Mark useful already-read passages now; '
                'use an unread location, another source or a targeted search, or finish with gaps. '
                'Changing keywords on a fully read saved body does not acquire missing article parts.')
        self.state.data['sources'][source]['last_read'] = result['progress']
        if guarded:
            record_query_read(self.state, source, query, result, question=question)
        self.state.save()
        self.state.trace(dict(action='read_source',source=source,result=result,duration_seconds=round(time.monotonic()-started,3)))
        return result
