import copy
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.sparse_build.person_overview import complete_overview, apply_overview
from finmy.person_epg.validation import validate_person_epg
from test_sparse_person_organization import facts, plan, vf


class CanonicalOverviewTest(unittest.TestCase):
    def test_unavailable_overview_keeps_facts_and_uses_final_summaries(self):
        package, organization = facts(), plan()
        package['graph']['descriptions'] = ['Stale interpretation of old facts.']
        original = copy.deepcopy(package)
        saved = {}
        def unavailable(*args):
            raise RuntimeError('Provider unavailable')
        result, status = complete_overview(package, organization, infer=unavailable,
                                          save=lambda data, name: saved.update({name: data}))
        self.assertEqual(package, original)
        for key in ('activity', 'action', 'financial_transaction', 'activity_detail', 'source_document'):
            self.assertEqual(result[key], original[key])
        self.assertEqual(result['graph']['descriptions'], [organization['events'][0]['summary']['value']])
        self.assertEqual(status['status'], 'degraded')
        self.assertTrue(validate_person_epg(result)['valid'])
        self.assertEqual(apply_overview(package, saved['PersonOverviewResult']['fields']), result)

    def test_bad_quote_does_not_replace_the_final_event_summary(self):
        saved = {}
        result, status = complete_overview(facts(), plan(),
            infer=lambda *args: {'summary': vf('Unsupported new fact', 'This quote is not supplied.')},
            save=lambda data, name: saved.update({name: data}))
        self.assertEqual(status['status'], 'degraded')
        self.assertNotIn('Unsupported new fact', result['graph']['descriptions'])

    def test_overview_evidence_does_not_retain_old_description_links(self):
        package = facts()
        original_set = package['graph'].get('evidence_set_id')
        result, status = complete_overview(package, plan(),
            infer=lambda *args: {'summary': vf('Final overview.')}, save=lambda *args: None)
        self.assertEqual(status['status'], 'completed')
        self.assertNotEqual(result['graph']['evidence_set_id'], original_set)
        self.assertEqual(result['graph']['descriptions'], ['Final overview.'])


if __name__ == '__main__':
    unittest.main()
