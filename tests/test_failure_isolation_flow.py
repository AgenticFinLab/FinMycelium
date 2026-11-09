"""Eight event searches survive a provider outage and resume original quotas."""
from collections import Counter
import json
import unittest
from unittest.mock import patch

import requests

from finmy.search.state import digest
import test_initial_storyline_search as fixtures


class FailureIsolationFlowTests(unittest.TestCase):
    def test_eight_events_pause_independently_then_resume_with_cumulative_usage(self):
        fixture = fixtures.InitialStorylineSearchTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        settings = fixture.config['search_config']
        settings['event_search'].update(max_search_requests=4, max_read_sources=1,
            max_model_calls=4, max_concurrent_events=2, reuse_sources=False)
        settings['enhancement'].update(max_search_requests=32, max_read_sources=8,
            max_model_calls=32)
        fixture.candidates['events'] = [dict(event_id=f'event_{index}', domain_id='invest',
            label=f'Investment matter {index}', summary=f'Investigate distinct investment {index}',
            person_connection='Investigate the documented investment decisions',
            scope=f'Only investment matter {index}', event_terms=[f'matter {index}'],
            questions=['What decisions and actions were documented?']) for index in range(8)]

        # An old phase-level disabled file is not authority over new task health.
        phase_root = fixture.root/'initial_event_search'
        phase_root.mkdir()
        legacy_health = phase_root/'provider_health.json'
        legacy_health.write_text(json.dumps({'version':1, 'scopes':{
            digest({'providers':['baidu', 'bocha'], 'generation':0}):{
                'bocha':{'disabled':True}, 'baidu':{'disabled':True}}}}))
        original_legacy = legacy_health.read_bytes()
        clock = [5000.0]
        recovered = [False]
        calls = []

        def model(context):
            action = fixture.model(context)
            if action['action'] == 'search':
                action['gap'] = ('Need original reporting of the investment decisions; '
                                 'no usable source was returned before the outage.')
            return action

        def transport(provider, payload, config):
            query = payload['query'] if provider == 'bocha' else payload['messages'][0]['content']
            calls.append((provider, query))
            if recovered[0]:
                return fixture.transport(provider, payload, config)
            response = requests.Response()
            response.status_code = 403 if provider == 'bocha' else 429
            response._content = json.dumps({'error_code':
                'AccessDenied' if provider == 'bocha' else 'QpsLimitExceeded'}).encode()
            if provider == 'baidu':
                response.headers['Retry-After'] = '60'
            raise requests.HTTPError('do-not-persist-credential', response=response)

        with patch('finmy.search.provider_health.time.time', side_effect=lambda:clock[0]):
            first = fixture.collect(dependencies={'transport':transport, 'model':model})
            self.assertEqual(first['status'], 'waiting')
            self.assertEqual(first['documents'], [])
            self.assertEqual(len(first['unresolved_events']), 8)
            self.assertEqual(len(fixture.discovery_calls), 1)
            self.assertEqual(len(fixture.contexts), 8)  # One search decision per event; no empty finish.
            self.assertTrue(all(context['phase'] == 'research' for context in fixture.contexts))
            self.assertEqual(first['usage']['search_calls'], 16)
            self.assertEqual(first['usage']['search_model_calls'], 8)
            self.assertEqual(first['usage']['parse_calls'], 0)
            self.assertEqual(Counter(provider for provider, query in calls), {'bocha':8, 'baidu':8})
            self.assertEqual(len({query for provider, query in calls}), 8)
            for record in first['reports']:
                self.assertEqual(record['status'], 'paused')
                self.assertEqual(record['stop_reason'], 'provider_cooldown')
                self.assertTrue(record['resume']['resumable'])
                self.assertTrue(record['resume']['requires_action'])
                self.assertEqual(record['resume']['next_retry_at'], 5060.0)
                self.assertEqual(record['usage'], {'search_calls':2, 'parse_calls':0,
                                                  'search_model_calls':1})
            self.assertFalse(list(phase_root.glob('event_*/runs/initial/selection.json')))

            clock[0] = 5061.0
            recovered[0] = True
            second = fixture.collect(dependencies={'transport':transport, 'model':model})
            self.assertEqual(second['status'], 'finished', second['reports'][0])
            self.assertEqual(second['unresolved_events'], [])
            self.assertEqual(len(second['documents']), 8)
            self.assertEqual(len(fixture.discovery_calls), 1)
            self.assertEqual(second['storyline_plan']['usage']['new_model_calls'], 0)
            self.assertEqual(second['usage']['search_calls'], 32)
            self.assertEqual(second['usage']['search_model_calls'], 32)
            self.assertEqual(second['usage']['parse_calls'], 8)
            self.assertEqual(len(calls), 32)
            for record in second['reports']:
                self.assertEqual(record['status'], 'finished')
                self.assertEqual(record['usage'], {'search_calls':4, 'parse_calls':1,
                                                  'search_model_calls':4})
                self.assertEqual(record['config']['max_search_requests'], 4)
                state_path = phase_root/record['task_id']/'runs/initial/run.json'
                saved = json.loads(state_path.read_text())
                self.assertEqual(saved['usage'], {'search':4, 'model':4})
                self.assertEqual(saved.get('config_history', []), [])
            self.assertTrue(all(document['raw_text'] == fixture.body for document in second['documents']))
            self.assertEqual(len({event_id for document in second['documents']
                                  for event_id in document['event_ids']}), 8)
            self.assertEqual(legacy_health.read_bytes(), original_legacy)

            counts = (len(calls), len(fixture.contexts), len(fixture.fetches))
            third = fixture.collect(dependencies={'transport':transport, 'model':model})
            self.assertEqual(third['documents'], second['documents'])
            self.assertEqual(third['usage'], second['usage'])
            self.assertEqual(counts, (len(calls), len(fixture.contexts), len(fixture.fetches)))
            self.assertEqual(len(fixture.discovery_calls), 1)
        traces = '\n'.join(path.read_text() for path in fixture.root.rglob('trace.jsonl'))
        self.assertNotIn('do-not-persist-credential', traces)


if __name__ == '__main__':
    unittest.main()
