"""Cost and scope regressions; synthetic fixtures only, no provider calls."""

import ast
import copy
from dataclasses import fields
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from finmy.builder.agent_build import structure
from finmy.builder.sparse_build.contracts import (
    ROLE_RESULTS, check_temporal_scope, compact_values, construction_report,
    date_interval, episode_scope, participant_registry, stage_scope,
    validate_episode_reuse, validate_participant_identity,
)
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.prompts import structure_spec
from finmy.builder.sparse_build.validation import validate_role
from finmy.generic import DataSample, UserQueryInput
from test_sparse_role_contracts import cascade, vf


class CompactContractTest(unittest.TestCase):
    def setUp(self):
        self.target = {**cascade()["stages"][0]["episodes"][0],
                       "start_time": vf("2020-02"), "end_time": vf("2020-09")}
        self.participants = copy.deepcopy(self.target["participants"])
        self.participants[0]["participant_type"] = vf("organization")
        self.participants[0]["actions"][0]["timestamp"] = vf("2020-02-15")
        self.previous = [{"ParticipantReconstructor": {"participants": self.participants}}]

    def test_projection_preserves_every_value_and_order_without_mutation(self):
        original = {"values": [vf("A"), vf("B")], "n": 2, "flag": False}
        original["values"][0].update(evidence_source_contents=["quote-marker"], reasons=["reason-marker"])
        before = copy.deepcopy(original)
        self.assertEqual(compact_values(original), {"values": ["A", "B"], "n": 2, "flag": False})
        self.assertEqual(original, before)

    def test_scope_projection_contains_no_previous_actions_or_quotes(self):
        scope = stage_scope(cascade()["stages"][0])
        self.assertNotIn("action-detail-marker", json.dumps(scope))
        self.assertNotIn("evidence_source_contents", json.dumps(scope))
        self.assertEqual(scope["episodes"][0]["episode_id"], "E1")

    def test_registry_keeps_named_bindings_but_not_action_history(self):
        before = copy.deepcopy(self.previous)
        registry = participant_registry(self.previous)
        self.assertEqual(registry[0]["name"], "Local service")
        self.assertEqual(registry[0]["participant_type"], "organization")
        self.assertNotIn("actions", registry[0])
        self.assertEqual(before, self.previous)

    def test_same_id_different_name_or_type_is_rejected(self):
        for key, value in (("name", "Different entity"), ("participant_type", "individual")):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.participants)
                changed[0][key] = vf(value)
                with self.assertRaisesRegex(ValueError, "identity drift"):
                    validate_participant_identity(changed, self.previous)

    def test_known_identity_cannot_be_erased(self):
        changed = copy.deepcopy(self.participants)
        changed[0]["name"] = vf("unknown")
        with self.assertRaisesRegex(ValueError, "identity drift"):
            validate_participant_identity(changed, self.previous)

    def test_role_changes_allowed_and_names_do_not_automatically_merge(self):
        changed = copy.deepcopy(self.participants)
        changed[0]["base_role"] = vf("later responder")
        registry = validate_participant_identity(changed, self.previous)
        self.assertEqual(registry[0]["base_role"], "later responder")
        changed[0]["participant_id"] = "P_2"
        self.assertEqual(len(validate_participant_identity(changed, self.previous)), 2)

    def test_episode_requires_exact_result_reuse(self):
        output = {**self.target, **ROLE_RESULTS}
        validate_episode_reuse(output, self.target)
        for key in ROLE_RESULTS:
            for value in ([], self.participants, "results", None):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "must equal"):
                    validate_episode_reuse({**output, key: value}, self.target)

    def test_episode_cannot_relabel_or_move_scope(self):
        for key, value in (("episode_id", "E8"), ("index_in_stage", 3), ("name", vf("Other")),
                           ("start_time", vf("2019")), ("end_time", vf("2024"))):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "scope drift"):
                validate_episode_reuse({**self.target, **ROLE_RESULTS, key: value}, self.target)

    def test_episode_schema_contains_no_array_reconstruction_or_phantom_flag(self):
        spec = structure_spec("EpisodeReconstructor")
        self.assertNotIn("is_bidirectional", spec)
        self.assertNotIn("class Participant:", spec)
        self.assertNotIn("class Transaction:", spec)
        self.assertIn('participants: str  # Must be exactly "Results of ParticipantReconstructor"', spec)

    def test_all_projected_fields_exist_on_authoritative_dataclasses(self):
        roles, _ = SparseRagBuilder.__new__(SparseRagBuilder)._get_agent_prompts()
        annotations = {cls.name: {field.target.id: ast.unparse(field.annotation) for field in cls.body
                                 if isinstance(field, ast.AnnAssign)}
                       for cls in ast.parse(Path(structure.__file__).read_text()).body
                       if isinstance(cls, ast.ClassDef)}
        for role in roles:
            for cls in ast.parse(structure_spec(role)).body:
                original = {field.name: field for field in fields(getattr(structure, cls.name))}
                for field in cls.body:
                    self.assertIn(field.target.id, original, (role, cls.name))
                    if role != "EpisodeReconstructor" or field.target.id not in ROLE_RESULTS:
                        self.assertEqual(ast.unparse(field.annotation), annotations[cls.name][field.target.id])

    def test_generic_old_episode_shape_remains_supported(self):
        validate_role("EpisodeReconstructor", self.target)
        validate_role("EpisodeReconstructor", {**self.target, **ROLE_RESULTS})

    def test_date_precision_and_leap_year(self):
        self.assertEqual(date_interval("2020")[1].strftime("%m-%d"), "12-31")
        self.assertEqual(date_interval("2020-02")[1].day, 29)
        self.assertEqual(date_interval("February 2020"), date_interval("2020-02"))
        self.assertEqual(date_interval("End of September 2020"), date_interval("2020-09"))
        self.assertEqual(date_interval("29 February 2020"), date_interval("2020-02-29"))
        self.assertIsNone(date_interval("2021-02-29"))
        self.assertIsNone(date_interval("around the crisis"))

    def test_timestamp_timezone_is_normalized(self):
        self.assertEqual(date_interval("2020-02-01T09:00:00+08:00"), date_interval("2020-02-01T01:00:00Z"))

    def test_overlapping_coarse_dates_are_not_false_positive(self):
        for stamp in ("2020", "2020-02", "2020-09-30", "February 2020"):
            with self.subTest(stamp=stamp):
                changed = copy.deepcopy(self.participants)
                changed[0]["actions"][0]["timestamp"] = vf(stamp)
                check = check_temporal_scope(self.target, participants=changed)
                self.assertEqual(check["items"][0]["status"], "overlaps_known_bounds")

    def test_action_and_transaction_outside_episode_rejected(self):
        for stamp in ("2019", "2020-01-31", "2020-10", "2023-03-09"):
            with self.subTest(stamp=stamp):
                changed = copy.deepcopy(self.participants)
                changed[0]["actions"][0]["timestamp"] = vf(stamp)
                with self.assertRaisesRegex(ValueError, "outside target"):
                    check_temporal_scope(self.target, participants=changed)
                with self.assertRaisesRegex(ValueError, "outside target"):
                    check_temporal_scope(self.target, transactions=[{"timestamp": vf(stamp)}])

    def test_unparsed_and_unknown_dates_are_explicitly_unchecked(self):
        for stamp in (None, vf("unknown"), vf("between spring and summer")):
            check = check_temporal_scope(self.target, transactions=[{"timestamp": stamp}])
            self.assertEqual(check["items"][0]["status"], "unchecked")
        unknown = {**self.target, "start_time": None, "end_time": vf("ongoing")}
        self.assertEqual(check_temporal_scope(unknown, participants=self.participants)["items"][0]["status"], "unchecked")

    def test_one_sided_window_and_inverted_window(self):
        target = {**self.target, "end_time": vf("unknown")}
        check_temporal_scope(target, transactions=[{"timestamp": vf("2024")}])
        with self.assertRaisesRegex(ValueError, "outside"):
            check_temporal_scope(target, transactions=[{"timestamp": vf("2019")}])
        with self.assertRaisesRegex(ValueError, "later than"):
            check_temporal_scope({"start_time": vf("2024"), "end_time": vf("2020")})

    def test_report_includes_identity_scope_and_repetition_candidates(self):
        graph = cascade()
        report = construction_report(graph)
        self.assertEqual(report["contract_version"], 2)
        self.assertEqual(len(report["identity_map"]), 1)
        self.assertEqual(len(report["repeated_action_candidates"]), 1)
        self.assertFalse(report["semantic_support_checked"])

    def test_new_live_contract_rejects_reconstruction_arrays_but_legacy_replay_accepts(self):
        builder = SparseRagBuilder.__new__(SparseRagBuilder)
        graph = cascade()
        target = graph["stages"][0]["episodes"][0]
        state = {"agent_results": [{"SkeletonChecker": graph},
                                   {"ParticipantReconstructor": {"participants": target["participants"]}},
                                   {"TransactionReconstructor": {"transactions": []}}],
                 "agent_executed": ["SkeletonChecker", "ParticipantReconstructor", "TransactionReconstructor"],
                 "episode_execution_plan": {"episodes": []}}
        with self.assertRaisesRegex(ValueError, "must equal"):
            builder._validate_agent_output(state, "EpisodeReconstructor", target)
        builder._validate_agent_output({**state, "construction_contract_version": 1}, "EpisodeReconstructor", target)
        builder._validate_agent_output(state, "EpisodeReconstructor", {**target, **ROLE_RESULTS})

    def test_compact_context_keeps_full_source_and_current_facts(self):
        builder = SparseRagBuilder.__new__(SparseRagBuilder)
        builder.build_config = {"sparse_builder_config": {"enable_context_assets": False}}
        content = 'Complete source {"x":"{Query}"}\nSpacing  remains. '
        inputs = SimpleNamespace(user_query=UserQueryInput(query_text="Synthetic", key_words=[]),
                                 samples=[DataSample(sample_id="s1", raw_data_id="r1", content=content)])
        graph = cascade()
        target = graph["stages"][0]["episodes"][0]
        participants = copy.deepcopy(target["participants"])
        participants[0]["name"]["evidence_source_contents"] = ["old-quote-marker"]
        state = {"build_input": inputs, "agent_results": [{"SkeletonChecker": graph},
                 {"ParticipantReconstructor": {"participants": participants}},
                 {"TransactionReconstructor": {"transactions": []}}],
                 "agent_executed": ["SkeletonChecker", "ParticipantReconstructor", "TransactionReconstructor"],
                 "episode_execution_plan": {"episodes": []}}
        stage, ep, budget, extra = builder._prompt_context_for_agent(state, "EpisodeReconstructor")
        kwargs = builder._build_prompt_kwargs(inputs, "EpisodeReconstructor", target_stage=stage,
                                             target_episode=ep, episode_budget=budget, **extra)
        _, user = builder._format_agent_messages("EpisodeReconstructor", kwargs)
        self.assertIn(content, user)
        self.assertIn("action-detail-marker", user)
        self.assertIn("Local service", user)
        self.assertNotIn("old-quote-marker", user)
        self.assertEqual(extra["StageSkeleton"]["episodes"][0], episode_scope(target))


if __name__ == "__main__":
    unittest.main()
