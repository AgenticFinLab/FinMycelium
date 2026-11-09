"""Overview truncation is local; real saved extraction can resume without new searches."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from test_sparse_person_full_flow import (
    SequencedInference, extraction_responses, organization_plan, cited,
)
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.person_recovery import (
    load_person_checkpoint, config_from_checkpoint, recover_person,
)
from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError
import test_sparse_person_full_flow as fixtures


class TruncatedSummary(SequencedInference):
    def __init__(self, values, position=7):
        super().__init__(values)
        self.position = position

    def run(self, infer_input=None, **kwargs):
        out = super().run(infer_input, **kwargs)
        if len(self.calls) == self.position:
            out.response = '{"descriptions": [{"value": "DO NOT ACCEPT THIS FRAGMENT'
            out.extras['finish_reason'] = 'length'
            out.cost.completion_tokens = 8192
        return out


class EventSummaryTest(unittest.TestCase):
    """The retained single-event builder still needs compact, local summaries.

    Person checkpoint migration and final event overview are covered by the
    canonical recovery/overview suites; this module does not select a legacy
    Person execution path.
    """
    artifact = fixtures.SparsePersonFullFlowTest.artifact

    def setUp(self):
        fixtures.SparsePersonFullFlowTest.setUp(self)
        self.config["reconstruction"] = {"mode": "event"}

    def builder(self, sequence):
        with patch('finmy.builder.sparse_build.inference.SparseAPIInference', return_value=sequence):
            return SparseRagBuilder(build_config=copy.deepcopy(self.config))

    def replay(self, output):
        verifier = SparseRagBuilder.__new__(SparseRagBuilder)
        verifier.save_dir = output.extras['run_directory']
        verifier.build_config = {}
        self.assertEqual(verifier.integrate_from_files(strict=True), output.event_cascades)

    def test_summary_uses_only_stage_overviews_and_verified_quotes(self):
        self.inputs.samples[0].content += ' NEVER_SEND_THIS_WHOLE_SOURCE_TO_SUMMARY ' * 2000
        extraction = extraction_responses()
        extraction[5] = {'descriptions': [cited('Alpha transferred funds to Beta.')]}
        sequence = SequencedInference(extraction)
        builder = self.builder(sequence)
        output = builder.run(self.inputs)
        prompt = sequence.calls[6][0]
        self.assertNotIn('NEVER_SEND_THIS', prompt.user_msg)
        self.assertNotIn('participant_id', prompt.user_msg)
        self.assertNotIn('instruments', prompt.user_msg)
        self.assertIn('Alpha transferred funds to Beta.', prompt.user_msg)
        self.assertIn('On 2025-01-01 Alpha authorized', prompt.user_msg)
        self.assertIn('not another extraction', prompt.system_msg)
        self.assertEqual(len(output.event_cascades['stages'][0]['episodes']), 1)

    def test_truncation_falls_back_and_event_strict_replay_succeeds(self):
        extraction = extraction_responses()
        sequence = TruncatedSummary(extraction)
        builder = self.builder(sequence)
        output = builder.run(self.inputs)
        self.assertEqual(output.event_cascades['descriptions'], extraction[5]['descriptions'])
        self.assertNotIn('DO NOT ACCEPT', json.dumps(output.event_cascades))
        status = self.artifact(builder, 'EventSummaryStatus')
        self.assertEqual(status['status'], 'degraded')
        self.assertFalse(status['partial_response_used'])
        self.assertEqual(self.artifact(builder, 'RunManifest')['event_summary'], status)
        self.assertEqual(self.artifact(builder, 'CallLedger')[6]['status'], 'incomplete_response')
        self.assertEqual(len(sequence.calls), 7)
        self.replay(output)

    def test_transport_failure_is_local_to_overview(self):
        sequence = SequencedInference(extraction_responses()[:6] + [TimeoutError('timeout')])
        builder = self.builder(sequence)
        output = builder.run(self.inputs)
        self.assertEqual(output.extras['event_summary']['error_type'], 'TimeoutError')
        self.assertEqual(self.artifact(builder, 'CallLedger')[6]['status'], 'transport_error')
        self.replay(output)

    def test_invalid_summary_after_retries_uses_existing_descriptions(self):
        sequence = SequencedInference(extraction_responses()[:6] + [{}, {}])
        builder = self.builder(sequence)
        output = builder.run(self.inputs)
        self.assertEqual(output.extras['event_summary']['status'], 'degraded')
        self.assertEqual(len(sequence.calls), 8)
        self.replay(output)

    def test_checkpoint_write_failure_is_not_misreported_as_summary_failure(self):
        sequence = SequencedInference(extraction_responses())
        builder = self.builder(sequence)
        original = builder._save_agent_result
        def fail_write(value, name):
            if name == 'EventDescriptionReconstructor-1':
                raise OSError('disk full')
            return original(value, name)
        with patch.object(builder, '_save_agent_result', side_effect=fail_write):
            with self.assertRaises(OSError):
                builder.run(self.inputs)
        self.assertFalse(Path(builder.save_dir, 'EventSummaryStatus.json').exists())


if __name__ == '__main__':
    unittest.main()
