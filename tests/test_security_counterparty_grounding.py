"""Counterparty review is semantic, bounded by the shared inference ledger."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.prompts import get_agent_prompts
from finmy.builder.sparse_build.relation_grounding import (
    CounterpartyEvidenceGuard, RelationGroundingError, ReviewUnavailableError, SECURITY_ROLE_POLICY,
    counterparty_candidates,
)


QUOTE = 'Berkshire Hathaway以2.5亿美元的价格新购买了西方石油430万股股份'
DIRECT = 'Berkshire subscribed for newly issued Occidental shares directly from Occidental.'


def episode(quote=QUOTE):
    return {'episode_id': 'E1', 'name': {'value': 'Share purchase'},
            'descriptions': [{'value': 'A documented purchase', 'evidence_source_contents': [quote]}],
            'participant_relations': [{'from_participant_id': 'P2', 'to_participant_id': 'P3',
                'relation_type': {'value': 'counterparty'},
                'relation_name': {'value': 'share purchase', 'evidence_source_contents': [quote]}}]}


def decision(verdict, quotes=None):
    return {'decisions': [{'index': 0, 'verdict': verdict,
        'reason': 'The source identifies the issuer but not the market seller.' if verdict != 'supported'
                  else 'The source explicitly identifies both direct subscribing parties.',
        'evidence_quotes': [QUOTE] if quotes is None else quotes}]}


class SecurityCounterpartyGroundingTests(unittest.TestCase):
    def guard(self, reply, source=QUOTE):
        self.calls, self.saved = [], {}
        def infer(system, user, name, validator):
            self.calls.append((system, json.loads(user)))
            validator(reply)
            return copy.deepcopy(reply)
        return CounterpartyEvidenceGuard(source, [{'participant_id': 'P2', 'name': 'Berkshire'},
            {'participant_id': 'P3', 'name': 'Occidental'}], infer,
            lambda data, name: self.saved.update({name: data}), 'Episode-1')

    def test_actual_purchase_quote_does_not_certify_issuer_counterparty(self):
        candidate = episode()
        before = copy.deepcopy(candidate)
        guard = self.guard(decision('unsupported'))
        with self.assertRaises(RelationGroundingError) as caught:
            guard(candidate)
        self.assertIn('participant_relations[0]', str(caught.exception))
        self.assertFalse(next(iter(self.saved.values()))['automatic_edits'])
        self.assertEqual(candidate, before)
        with self.assertRaises(RelationGroundingError):
            guard(candidate)
        self.assertEqual(len(self.calls), 1)

    def test_direct_issuer_subscription_is_not_categorically_rejected(self):
        candidate = episode(DIRECT)
        before = copy.deepcopy(candidate)
        self.guard(decision('supported', [DIRECT]), source=DIRECT)(candidate)
        self.assertEqual(candidate, before)
        self.assertEqual(len(self.calls), 1)

    def test_uncertain_review_does_not_certify_counterparty(self):
        with self.assertRaises(RelationGroundingError):
            self.guard(decision('uncertain', []))(episode())

    def test_supported_review_requires_original_quotes(self):
        for quotes in ([], ['Invented direct purchase agreement']):
            with self.subTest(quotes=quotes), self.assertRaises(ReviewUnavailableError):
                self.guard(decision('supported', quotes))(episode())

    def test_unavailable_review_keeps_candidate_without_reextracting_episode(self):
        for failure, max_calls, expected_calls in [
                ({'decisions': []}, 6, 2),
                (ValueError('client configuration rejected'), 6, 2),
                (TimeoutError('review offline'), 6, 2),
                (None, 1, 1)]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                builder = SparseRagBuilder.__new__(SparseRagBuilder)
                builder.build_config = {'sparse_builder_config': {
                    'max_json_attempts': 3, 'max_calls': max_calls}}
                builder.save_dir = directory
                candidate = episode()
                replies = [copy.deepcopy(candidate), failure]
                calls = []
                def run(infer_input=None, **kwargs):
                    calls.append(infer_input)
                    reply = replies.pop(0)
                    if isinstance(reply, Exception):
                        raise reply
                    response = json.dumps(reply, ensure_ascii=False)
                    return SimpleNamespace(response=response,
                        cost=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
                        extras={'finish_reason': 'stop'}, to_dict=lambda: {'response': response})
                builder.agents_lm = SimpleNamespace(run=run)
                guard = CounterpartyEvidenceGuard(QUOTE, [],
                    lambda system, user, name, validator: builder._infer_and_parse_json(
                        'CounterpartyEvidenceReview', system, user, {}, name, validator=validator),
                    lambda data, name: builder._save_agent_result(data, name), 'Episode-1')
                with self.assertRaises(ReviewUnavailableError) as caught:
                    builder._infer_and_parse_json('EpisodeReconstructor', 'JSON', QUOTE, {},
                                                 'Episode-1', validator=guard)
                self.assertEqual(len(calls), expected_calls)
                audit = json.loads(Path(directory, caught.exception.audit_artifact).read_text())
                self.assertEqual(audit['candidate'], candidate)
                self.assertEqual(audit['status'], 'review_unavailable')
                self.assertFalse(audit['semantic_approval'])
                self.assertIsNotNone(caught.exception.__cause__)
                ledger = json.loads(Path(directory, 'CallLedger.json').read_text())
                self.assertEqual(ledger[0]['status'], 'review_pending')
                self.assertFalse(Path(directory, 'Episode-1-Result.json').exists())

    def test_other_relations_and_nonsecurity_counterparties_do_not_add_calls(self):
        guard = self.guard(decision('unsupported'))
        candidate = episode()
        candidate['participant_relations'][0]['relation_type']['value'] = 'ownership'
        guard(candidate)
        candidate = {'name': {'value': 'Equipment transfer'}, 'participant_relations': [{
            'relation_type': {'value': 'counterparty'}, 'relation_name': {'value': 'equipment seller'}}]}
        guard(candidate)
        self.assertEqual(self.calls, [])
        self.assertEqual(counterparty_candidates(candidate), [])

    def test_failed_audit_write_does_not_replace_review_error(self):
        guard = self.guard({'decisions': []})
        def cannot_save(data, name):
            raise PermissionError('read-only checkpoint directory')
        guard.save = cannot_save
        with self.assertRaises(ReviewUnavailableError) as caught:
            guard(episode())
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertFalse(caught.exception.audit_saved)
        self.assertIn('checkpoint could not be written', str(caught.exception))

    def test_roles_get_specific_actor_issuer_and_counterparty_policy(self):
        _, users = get_agent_prompts()
        for role in ['SkeletonChecker', 'ParticipantReconstructor',
                     'TransactionReconstructor', 'EpisodeReconstructor']:
            self.assertIn(SECURITY_ROLE_POLICY, users[role])

    def test_execute_agent_runs_review_before_accepting_episode(self):
        from test_sparse_rag_builder_routing_regression import _state
        state = _state({"transaction_tier": "skip"})
        state["build_input"].samples[0].content = QUOTE
        participants = state["agent_results"][-1]["ParticipantReconstructor"]["participants"]
        participants[:] = [{"participant_id": "P2", "name": {"value": "Berkshire"}},
                           {"participant_id": "P3", "name": {"value": "Occidental"}}]
        bad = episode()
        target = state["agent_results"][1]["SkeletonChecker"]["stages"][0]["episodes"][0]
        target["index_in_stage"] = 0
        bad.update({key: copy.deepcopy(target[key]) for key in ("name", "start_time", "end_time")})
        bad.update(index_in_stage=0, participants="Results of ParticipantReconstructor",
                   transactions="Results of TransactionReconstructor")
        corrected = copy.deepcopy(bad)
        corrected["participant_relations"] = []
        replies = [bad, decision('unsupported'), corrected]
        with tempfile.TemporaryDirectory() as directory:
            builder = SparseRagBuilder.__new__(SparseRagBuilder)
            builder.build_config = {'sparse_builder_config': {'max_json_attempts': 3, 'max_calls': 6}}
            builder.save_dir = directory
            def run(infer_input=None, **kwargs):
                response = json.dumps(replies.pop(0), ensure_ascii=False)
                return SimpleNamespace(response=response,
                    cost=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
                    extras={'finish_reason': 'stop'}, to_dict=lambda: {'response': response})
            builder.agents_lm = SimpleNamespace(run=run)
            builder.execute_agent(state, 'EpisodeReconstructor')
            accepted = state['agent_results'][-1]['EpisodeReconstructor']
            self.assertEqual(accepted['participant_relations'], [])
            self.assertEqual(accepted['descriptions'], bad['descriptions'])
            self.assertEqual(replies, [])
            self.assertTrue(list(Path(directory).glob('*CounterpartyEvidenceReview*Audit-Result.json')))

    def test_explicit_model_correction_preserves_purchase_and_shared_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = SparseRagBuilder.__new__(SparseRagBuilder)
            builder.build_config = {'sparse_builder_config': {'max_json_attempts': 3, 'max_calls': 6}}
            builder.save_dir = directory
            bad = episode()
            corrected = copy.deepcopy(bad)
            corrected['participant_relations'] = []  # Explicit model response, not a program edit.
            replies = [bad, decision('unsupported'), corrected]
            calls = []
            def run(infer_input=None, **kwargs):
                calls.append(infer_input)
                response = json.dumps(replies.pop(0), ensure_ascii=False)
                return SimpleNamespace(response=response,
                    cost=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
                    extras={'finish_reason': 'stop'}, to_dict=lambda: {'response': response})
            builder.agents_lm = SimpleNamespace(run=run)
            guard = CounterpartyEvidenceGuard(QUOTE, [],
                lambda system, user, name, validator: builder._infer_and_parse_json(
                    'CounterpartyEvidenceReview', system, user, {}, name, validator=validator),
                lambda data, name: builder._save_agent_result(data, name), 'Episode-1')
            result = builder._infer_and_parse_json('EpisodeReconstructor', 'JSON', QUOTE, {},
                                                  'Episode-1', validator=guard)
            self.assertEqual(result['descriptions'], bad['descriptions'])
            self.assertEqual(result['participant_relations'], [])
            self.assertEqual(len(calls), 3)
            self.assertIn('RELATION EVIDENCE CORRECTION', calls[2].user_msg)
            self.assertIn(QUOTE, calls[2].user_msg)
            ledger = json.loads(Path(directory, 'CallLedger.json').read_text())
            self.assertEqual([r['agent'] for r in ledger],
                ['EpisodeReconstructor', 'CounterpartyEvidenceReview', 'EpisodeReconstructor'])
            self.assertEqual(ledger[0]['validation_kind'], 'relation_evidence')


if __name__ == '__main__':
    unittest.main()
