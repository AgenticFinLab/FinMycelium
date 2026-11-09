"""Search service failures are bounded locally and explicitly resumable."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools
from finmy.search.provider_health import failure_details


def http_error(status, body, headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.headers.update(headers or {})
    return requests.HTTPError('secret-token raw request content', response=response)


class ProviderHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = []
        self.clock = [100.0]

    def tools(self, transport, task='one', providers=None):
        state = SearchState(self.root, task, task={'target_type':'event',
            'target_name':task, 'query_text':'Trace event'},
            config=SearchConfig(providers=providers or ['bocha', 'baidu'], max_search_requests=20))
        def recorded(*args):
            self.calls.append(args[0])
            return transport(*args)
        tools = SearchTools(state, transport=recorded)
        tools.provider_health.clock = lambda: self.clock[0]
        return tools

    @staticmethod
    def success(provider, payload, config):
        row = {'url':'https://example.test/evidence', 'name':'Original', 'title':'Original'}
        return {'data':{'webPages':{'value':[row]}}} if provider=='bocha' else {'references':[row]}

    def test_access_failure_isolated_to_event_healthy_provider_continues(self):
        def transport(provider, payload, config):
            if provider=='baidu':
                raise http_error(401, {'error_code':'invalid_api_key','message':'secret-token'})
            return self.success(provider, payload, config)
        first = self.tools(transport)
        result = first.search('first query')
        self.assertEqual(result['providers'][1]['error_details']['category'], 'authentication')
        second = self.tools(transport, 'two')
        result = second.search('second query')
        self.assertEqual(self.calls, ['bocha','baidu','bocha','baidu'])
        self.assertEqual(second.state.data['usage']['search'], 2)
        self.assertEqual(result['providers'][1]['provider_state'], 'blocked')
        self.assertEqual(result['providers_available'], ['bocha'])

    def test_cached_success_remains_usable_after_provider_disabled(self):
        tools = self.tools(self.success, providers=['bocha'])
        good = tools.search('saved query')['source_ids']
        tools.transport = lambda *args: (_ for _ in ()).throw(http_error(402, {'message':'Insufficient balance'}))
        tools.search('new query')
        used = tools.state.data['usage']['search']
        result = tools.search('saved query')
        self.assertEqual(result['source_ids'], good)
        self.assertEqual(result['providers'][0]['status'], 'cached')
        self.assertEqual(tools.state.data['usage']['search'], used)

    def test_other_event_success_does_not_clear_local_access_failure(self):
        first = self.tools(self.success, providers=['baidu'])
        second = self.tools(self.success, task='two', providers=['baidu'])
        first.provider_health.failure('baidu', failure_details(http_error(402, {})))
        second.provider_health.success('baidu')
        self.assertEqual(first.provider_health.status('baidu')['status'], 'blocked')
        self.assertEqual(second.provider_health.status('baidu')['status'], 'available')

    def test_transient_errors_have_cooldown_then_bounded_attempts(self):
        def failing(*args):
            raise http_error(503, {'error_code':50003, 'message':'server unavailable'})
        tools = self.tools(failing, providers=['baidu'])
        for index in range(3):
            result = tools.search('query '+str(index))
            self.assertEqual(result['providers'][0]['status'], 'failed')
            used = tools.state.data['usage']['search']
            skipped = tools.search('changed keywords')
            self.assertIn(skipped['providers'][0]['status'], {'cooldown','retry_exhausted'})
            self.assertEqual(tools.state.data['usage']['search'], used)
            self.clock[0] += 100
        self.assertEqual(tools.search('after cooldown')['providers'][0]['status'], 'retry_exhausted')
        self.assertEqual(len(self.calls), 3)
        tools.begin_invocation()
        tools.transport = self.success
        result = tools.search('recovered on resume')
        self.assertEqual(result['providers'][0]['status'], 'success')
        self.assertEqual(tools.state.data['usage']['search'], 4)

    def test_success_resets_transient_failure_streak(self):
        tools = self.tools(lambda *a: (_ for _ in ()).throw(requests.ReadTimeout('secret')), providers=['bocha'])
        result = tools.search('first')
        self.assertEqual(result['providers'][0]['error_details']['category'], 'network')
        self.clock[0] += 100
        tools.transport = self.success
        tools.search('second')
        with tools.provider_health._records() as records:
            self.assertEqual(records['bocha']['consecutive_failures'], 0)

    def test_rate_limit_records_retry_after_without_sleep_or_quota_on_skip(self):
        tools = self.tools(lambda *a: (_ for _ in ()).throw(
            http_error(429, {'error':{'code':'rate_limit_exceeded'}}, {'Retry-After':'45'})), providers=['bocha'])
        result = tools.search('first')
        details = result['providers'][0]['error_details']
        self.assertEqual(details['category'], 'rate_limit')
        self.assertEqual(details['retry_after_seconds'], 45)
        self.assertEqual(tools.search('again')['providers'][0]['status'], 'cooldown')
        self.assertEqual(len(self.calls), 1)

    def test_http_200_error_payload_is_not_saved_as_raw_source_or_success(self):
        tools = self.tools(lambda *a: {'code':400,'message':'insufficient balance secret-token'}, providers=['bocha'])
        result = tools.search('first')
        self.assertEqual(result['providers'][0]['error_details']['category'], 'balance_or_quota')
        self.assertEqual(result['source_ids'], [])
        saved = (tools.state.run_dir/'responses/1.json').read_text()
        self.assertNotIn('secret-token', saved)
        self.assertNotIn('secret-token', (tools.state.run_dir/'provider_health.json').read_text())
        self.assertNotIn('secret-token', (tools.state.run_dir/'trace.jsonl').read_text())

    def test_unknown_http_error_does_not_become_balance(self):
        details = failure_details(http_error(400, {'error_code':'echoed-secret-token','message':'arbitrary failure'}))
        self.assertEqual(details['category'], 'invalid_request')
        self.assertEqual(details['http_status'], 400)
        self.assertTrue(details['provider_code'].startswith('unrecognized:'))
        self.assertNotIn('secret', str(details))

    def test_http_200_baidu_error_retains_code_without_secret_message(self):
        tools = self.tools(lambda *a: {'error_code':111,
            'error_msg':'Access token invalid or no longer valid: secret-token'}, providers=['baidu'])
        result = tools.search('first')
        details = result['providers'][0]['error_details']
        self.assertEqual(details['category'], 'authentication')
        self.assertEqual(details['provider_code'], 111)
        self.assertIsNone(details['http_status'])
        self.assertTrue(result['all_providers_unavailable'])
        self.assertNotIn('secret-token', (tools.state.run_dir/'responses/1.json').read_text())

    def test_explicit_revision_reopens_provider_without_resetting_calls(self):
        tools = self.tools(lambda *a: (_ for _ in ()).throw(http_error(403, {})), providers=['bocha'])
        tools.search('first')
        self.assertEqual(tools.search_availability()['all_providers_unavailable'], True)
        tools.state.data['config_history'] = [{'config':tools.state.data['config']}]
        tools.state.save()
        from finmy.search.provider_health import ProviderHealth
        tools.provider_health = ProviderHealth(tools.state, clock=lambda:self.clock[0])
        tools.transport = self.success
        tools.search('after revision')
        self.assertEqual(tools.state.data['usage']['search'], 2)

    def test_manual_resume_retries_corrected_access_without_configuration_change(self):
        tools = self.tools(lambda *a: (_ for _ in ()).throw(http_error(403, {})), providers=['bocha'])
        tools.search('first')
        skipped = tools.search('again')
        self.assertEqual(skipped['providers'][0]['status'], 'blocked')
        self.assertEqual(tools.state.data['usage']['search'], 1)
        resumed = self.tools(self.success, providers=['bocha'])
        self.assertEqual(resumed.search_availability()['blocked_providers'], ['bocha'])
        resumed.begin_invocation()
        result = resumed.search('again')
        self.assertEqual(result['providers'][0]['status'], 'success')
        self.assertEqual(resumed.state.data['usage']['search'], 2)

    def test_http_date_retry_after_persists_deadline_across_resume(self):
        self.clock[0] = 1445412480.0
        tools = self.tools(lambda *a: (_ for _ in ()).throw(http_error(429,
            {'error_code':'QpsLimitExceeded'}, {'Retry-After':'Wed, 21 Oct 2015 07:28:45 GMT'})),
            providers=['bocha'])
        result = tools.search('first')
        self.assertEqual(result['providers'][0]['error_details']['provider_code'], 'QpsLimitExceeded')
        self.assertEqual(result['next_retry_at'], self.clock[0] + 45)
        resumed = self.tools(self.success, providers=['bocha'])
        resumed.begin_invocation()
        self.assertEqual(resumed.search('again')['providers'][0]['status'], 'cooldown')
        self.assertEqual(resumed.state.data['usage']['search'], 1)
        self.clock[0] += 45
        self.assertEqual(resumed.search('again')['providers'][0]['status'], 'success')
        self.assertEqual(resumed.state.data['usage']['search'], 2)

    def test_long_retry_after_is_not_shortened(self):
        details = failure_details(status=429, retry_after='7200', now=self.clock[0])
        self.assertEqual(details['retry_after_seconds'], 7200)

    def test_legacy_phase_health_does_not_block_any_event(self):
        tools = self.tools(self.success, providers=['bocha'])
        (self.root/'provider_health.json').write_text(json.dumps({'version':1, 'scopes':{
            tools.provider_health.key:{'bocha':{'disabled':True,'retry_at':9999999999}}}}))
        result = tools.search('new event request')
        self.assertEqual(result['providers'][0]['status'], 'success')

    def test_transient_cooldown_does_not_block_sibling_event(self):
        first = self.tools(lambda *a: (_ for _ in ()).throw(http_error(429, {},
            {'Retry-After':'45'})), providers=['baidu'])
        first.search('first event')
        second = self.tools(self.success, task='two', providers=['baidu'])
        self.assertEqual(second.search('second event')['providers'][0]['status'], 'success')
        self.assertEqual(first.search_availability()['retryable_providers'], ['baidu'])
        self.assertEqual(first.state.data['usage']['search'], 1)

    def test_invalid_provider_rows_do_not_discard_valid_sources(self):
        def transport(*args):
            return {'code':'200', 'data':{'webPages':{'value':[
                {'url':'https://example.test/good', 'name':'Valid'},
                None, {'name':'No URL'}, {'url':'ftp://example.test/invalid'},
                {'url':'https://example.test/also-good', 'name':'Valid too'}]}}}
        tools = self.tools(transport, providers=['bocha'])
        result = tools.search('query')
        self.assertEqual(len(result['source_ids']), 2)
        self.assertEqual(result['providers'][0]['status'], 'success')
        self.assertEqual(result['providers'][0]['rejected_result_count'], 3)
        self.assertEqual(tools.search_availability()['providers_available'], ['bocha'])
        self.assertEqual(tools.state.data['usage']['search'], 1)

    def test_local_persistence_failure_does_not_poison_provider_health(self):
        tools = self.tools(self.success, providers=['bocha'])
        with patch('finmy.search.tools.write_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                tools.search('query')
        self.assertEqual(tools.search_availability()['providers_available'], ['bocha'])
        self.assertEqual(tools.state.data['usage']['search'], 1)

    def test_corrupt_optional_health_is_archived_without_resetting_usage(self):
        tools = self.tools(self.success, providers=['bocha'])
        tools.search('saved')
        health_path = tools.state.run_dir/'provider_health.json'
        for bad_data in ('{truncated', json.dumps({'scopes':{
                tools.provider_health.key:{'bocha':{'retry_at':'later'}}}})):
            health_path.write_text(bad_data)
            result = tools.search('saved')
            self.assertEqual(result['providers'][0]['status'], 'cached')
            self.assertEqual(tools.state.data['usage']['search'], 1)
            self.assertEqual(tools.search_availability()['providers_available'], ['bocha'])
            archives = list(tools.state.run_dir.glob('provider_health.corrupt-*.json'))
            self.assertTrue(any(path.read_text() == bad_data for path in archives))
        trace = (tools.state.run_dir/'trace.jsonl').read_text()
        self.assertIn('provider_health_recovered', trace)
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
