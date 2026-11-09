"""Evidence-led boundary review keeps accepted facts and strict replay coherent."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()
from finmy.builder.sparse_build.contracts import date_interval
from finmy.builder.sparse_build.temporal_scope_review import apply_revision, validate_proposal
from finmy.builder.sparse_build.person_recovery import load_person_checkpoint
import test_sparse_person_full_flow as flow


class TemporalScopeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = flow.SparsePersonFullFlowTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def proposal(self, episode, end, name='Transfer execution and later receipt'):
        return {'decision': 'revise_scope', 'reason': 'The original documents describe the same transfer process.',
                'episode': {'name': flow.cited(name), 'start_time': copy.deepcopy(episode['start_time']),
                            'end_time': flow.cited(end)}}

    def scenario(self):
        responses = flow.extraction_responses()
        for skeleton in responses[:2]:
            skeleton['end_time']['value'] = '2025-01-01'
            skeleton['stages'][0]['end_time']['value'] = '2025-01-01'
            skeleton['stages'][0]['episodes'][0]['end_time']['value'] = '2025-01-01'
        # A source-supported receipt belongs to the same process the next day.
        self.fixture.inputs.samples[0].content += ' Beta received this same transfer on 2025-01-02.'
        responses[2]['participants'][1]['actions'][0]['timestamp'] = flow.cited(
            '2025-01-02', 'Beta received this same transfer on 2025-01-02.')
        proposal = self.proposal(responses[1]['stages'][0]['episodes'][0], '2025-01-02')
        proposal['episode']['end_time'] = flow.cited('2025-01-02', 'Beta received this same transfer on 2025-01-02.')
        responses[4].update(copy.deepcopy(proposal['episode']))
        responses.insert(3, proposal)
        return responses

    def test_scope_revision_propagates_to_parents_and_strict_replay(self):
        responses = self.scenario()
        original = copy.deepcopy(responses[1])
        builder, sequence = self.fixture.builder(extraction=responses)
        output = builder.run(self.fixture.inputs)
        self.assertEqual(len(sequence.calls), 9)
        self.assertEqual(output.extras['usage']['calls'], 9)
        saved = self.fixture.artifact(builder, 'SkeletonChecker-1-Result')
        for item in (saved, saved['stages'][0], saved['stages'][0]['episodes'][0]):
            self.assertEqual(item['end_time']['value'], '2025-01-02')
        self.assertEqual(saved['stages'][0]['episodes'][0]['episode_id'], 'E1')
        audit = self.fixture.artifact(builder, 'TemporalScopeAudit-ParticipantReconstructor-1-Stage0-Episode0-Result')
        self.assertEqual(audit['before'], original)
        self.assertEqual(audit['status'], 'revised')
        self.assertEqual(builder.integrate_from_files(strict=True), output.event_cascades)
        self.assertEqual(builder.integrate_person_from_files(strict=True), output.extras['person_epg'])
        ledger = self.fixture.artifact(builder, 'CallLedger')
        accepted = [row for row in ledger if row.get('scope_revision')]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['status'], 'accepted')

    def test_organization_failure_after_revision_remains_recoverable(self):
        builder, _ = self.fixture.builder(extraction=self.scenario(), organization=[RuntimeError('offline failure')])
        with self.assertRaisesRegex(RuntimeError, 'offline failure'):
            builder.run(self.fixture.inputs)
        checkpoint = load_person_checkpoint(builder.save_dir)
        self.assertEqual(len(checkpoint.historical_calls), 9)
        self.assertIn('EpisodeScopeReviewer', [r['agent'] for r in checkpoint.historical_calls])
        self.assertEqual(checkpoint.cascade['stages'][0]['episodes'][0]['end_time']['value'], '2025-01-02')

    def test_actual_quarter_vs_august_conflict_can_revise_without_rewriting_fact(self):
        quote = 'Ownership was 20.2% as of Aug. 8, 2022.'
        target = {'episode_id': 'E2', 'index_in_stage': 1,
                  'name': flow.cited('Q2 2022 purchases raising stake to 20.2%', quote),
                  'start_time': flow.cited('2022-Q2', quote), 'end_time': flow.cited('2022-06-30', quote)}
        participants = [{'participant_id': 'P_2', 'actions': [{'timestamp': flow.cited('2022-08-08', quote)}]}]
        candidate = {'decision': 'revise_scope', 'reason': 'Same buildup, later holding snapshot; distinguish the two times.',
                     'episode': {'name': flow.cited('2022 purchases and August holding disclosure', quote),
                                 'start_time': target['start_time'], 'end_time': flow.cited('2022-08', quote)}}
        before = copy.deepcopy((target, participants))
        validate_proposal(candidate, target, [SimpleNamespace(sample_id='s', content=quote)], participants, [])
        self.assertEqual((target, participants), before)
        self.assertEqual(date_interval('2022-Q2')[0].isoformat(), '2022-04-01T00:00:00')
        self.assertEqual(date_interval('Q2 2022'), date_interval('2022-Q2'))
        candidate['episode']['end_time'] = flow.cited('unknown', quote)
        with self.assertRaisesRegex(ValueError, 'erase or obscure'):
            validate_proposal(candidate, target, [SimpleNamespace(sample_id='s', content=quote)], participants, [])

    def test_scope_review_rejects_invented_quotes_and_unresolved_conflicts(self):
        skeleton = flow.extraction_responses()[1]
        target = skeleton['stages'][0]['episodes'][0]
        proposal = self.proposal(target, '2025-01-03')
        proposal['episode']['end_time']['evidence_source_contents'] = ['not in any source']
        with self.assertRaisesRegex(ValueError, 'original evidence'):
            validate_proposal(proposal, target, self.fixture.inputs.samples, [], [])
        proposal['episode']['end_time'] = flow.cited('2025-01-03')
        with self.assertRaisesRegex(ValueError, 'outside target bounds'):
            validate_proposal(proposal, target, self.fixture.inputs.samples,
                [{'actions': [{'timestamp': flow.cited('2026-01-01')}]}], [])
        proposal['episode']['episode_id'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'only name'):
            validate_proposal(proposal, target, self.fixture.inputs.samples, [], [])

    def test_review_respects_global_call_budget(self):
        builder, sequence = self.fixture.builder(extraction=self.scenario())
        builder.build_config['sparse_builder_config']['max_calls'] = 3
        with self.assertRaisesRegex(RuntimeError, 'model call limit'):
            builder.run(self.fixture.inputs)
        self.assertEqual(len(sequence.calls), 3)
        self.assertEqual(self.fixture.artifact(builder, 'RunManifest')['usage']['calls'], 3)
        checkpoint = self.fixture.artifact(builder, 'BuildInterruption')
        self.assertEqual(checkpoint['status'], 'checkpointed_incomplete')
        self.assertFalse(checkpoint['final_artifact_allowed'])
        self.assertEqual(checkpoint['recovery_scope'], 'manual_extraction_recovery')
        audit = json.loads(Path(builder.save_dir, checkpoint['pending_candidate_artifacts'][0]).read_text())
        self.assertEqual(audit['status'], 'review_unavailable')
        self.assertEqual(audit['review_status'], 'not_called')
        self.assertEqual(audit['candidate']['participants'][1]['actions'][0]['timestamp']['value'], '2025-01-02')
        self.assertTrue(Path(builder.save_dir, 'SkeletonChecker-1-Result.json').exists())

    def test_scope_review_transport_value_error_is_not_fact_correction(self):
        responses = self.scenario()
        original = copy.deepcopy(responses[1])
        responses[3] = ValueError('client configuration failure')
        builder, sequence = self.fixture.builder(extraction=responses)
        with self.assertRaisesRegex(RuntimeError, 'EpisodeScopeReviewer did not complete'):
            builder.run(self.fixture.inputs)
        self.assertEqual(len(sequence.calls), 4)
        self.assertEqual(self.fixture.artifact(builder, 'SkeletonChecker-1-Result'), original)
        checkpoint = self.fixture.artifact(builder, 'BuildInterruption')
        audit = json.loads(Path(builder.save_dir, checkpoint['pending_candidate_artifacts'][0]).read_text())
        self.assertEqual(audit['review_status'], 'transport_error')
        self.assertFalse(audit['semantic_approval'])
        self.assertEqual(audit['before'], original)
        self.assertFalse(Path(builder.save_dir, 'FinalPersonEPG.json').exists())

    def test_failed_diagnostic_writes_preserve_original_request_failure(self):
        original_error = RuntimeError('model request failed')
        builder, sequence = self.fixture.builder(extraction=[original_error])
        save = builder.save_traces
        def write(data, name, file_format, **kwargs):
            if (name == 'BuildInterruption'
                    or name == 'RunManifest' and data.get('status') == 'failed'
                    or name == 'CallLedger' and any(row.get('status') == 'transport_error' for row in data)):
                raise PermissionError('cannot write failure diagnostics')
            return save(data, name, file_format, **kwargs)
        builder.save_traces = write
        with self.assertRaises(RuntimeError) as caught:
            builder.run(self.fixture.inputs)
        self.assertIs(caught.exception, original_error)
        self.assertEqual(len(sequence.calls), 1)


if __name__ == '__main__':
    unittest.main()
