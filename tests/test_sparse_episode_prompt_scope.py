"""Offline prompt regressions for scene selection without changing source inputs."""

import hashlib
import json
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build import prompts
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput


FACT_ROLES = {"ParticipantReconstructor", "TransactionReconstructor"}


class SparseEpisodePromptScopeTest(unittest.TestCase):
    def test_both_fact_roles_receive_scene_and_occurrence_time_rules(self):
        _, users = prompts.get_agent_prompts()
        rules = (
            "TargetEpisode defines this response's factual and temporal scope",
            "person coverage period, TargetStage and other episodes do not expand",
            "do not extract every scene mentioned",
            "publication date the action's date",
            "own supported statement date",
            "Match each action or transfer verb to the time of that occurrence",
            "Keep subsequent reports, explanations and recollections in their own scene",
            "Exclude supported out-of-scope occurrences from this response",
            "source text remains available unchanged",
            "with their actual actors, including company acts",
            "Do not relabel a statement as its described action, replace its actor or date",
            "remove a known date / use unknown",
            "focal person need not act in every episode",
            "participant with no in-scope action may have actions=[]",
            "discard the company's action to center the focal person",
        )
        for role in FACT_ROLES:
            with self.subTest(role=role):
                normalized = " ".join(users[role].split())
                for rule in rules:
                    self.assertIn(rule, normalized)
                self.assertEqual(users[role].count(prompts.EPISODE_FACT_SCOPE_POLICY), 1)

    def test_role_rendering_keeps_all_original_sources_and_json_contract(self):
        # The later statement stays in Content even when the selected scene is
        # the earlier company action. A small retrieval budget cannot trim it.
        originals = [
            'Company Delta completed the purchase in 2020. {"amount": 25}\n'
            + "Original evidence 原始资料. " * 600 + "END_OF_FIRST_SOURCE",
            "On 2021-03-04, Jordan described Delta's 2020 purchase. END_OF_LATER_SOURCE",
        ]
        inputs = SimpleNamespace(
            user_query=UserQueryInput(query_text="Jordan and Delta purchase", key_words=["Delta"]),
            samples=[DataSample(sample_id=f"s{i}", raw_data_id=f"r{i}", content=source,
                                category="article", knowledge_field="finance")
                     for i, source in enumerate(originals)],
        )
        builder = SparseRagBuilder.__new__(SparseRagBuilder)
        builder.build_config = {
            "reconstruction": {"mode": "person", "subject": {
                "subject_id": "person_jordan", "name": "Jordan",
                "coverage_start": "2020", "coverage_end": "2021",
            }},
            "sparse_builder_config": {"max_context_chars": 400},
        }
        target = json.dumps({"episode_id": "E1", "name": "Delta purchase",
                             "time_start": "2020", "time_end": "2020"})
        expected_content = "\n\n".join(
            f'SOURCE {{"sample_id": "s{i}", "raw_data_id": "r{i}"}}\n{source}'
            for i, source in enumerate(originals)
        )
        for role in FACT_ROLES:
            with self.subTest(role=role):
                kwargs = builder._build_prompt_kwargs(
                    build_input=inputs, agent_name=role,
                    target_stage="2020–2021 capital allocation", target_episode=target,
                )
                system, user = builder._format_agent_messages(role, kwargs)
                rendered_content = user.split("=== CONTENT BEGIN ===\n", 1)[1].split(
                    "\n=== CONTENT END ===", 1)[0]
                self.assertEqual(rendered_content, expected_content)
                self.assertEqual(kwargs["Content"], expected_content)
                self.assertIn(target, user)
                self.assertIn(prompts.EPISODE_FACT_SCOPE_POLICY, user)
                self.assertIn(prompts.structure_spec(role), system)
                self.assertIn("Return one complete JSON object with the exact fields and types",
                              " ".join(system.split()))

    def test_shared_policy_and_other_five_roles_remain_unchanged(self):
        # Snapshot the existing shared blocks and unaffected user templates:
        # this fix must not alter global extraction or other role semantics.
        snapshots = {
            "COMMON_SYSTEM_PROMPT": "c5ee21d88e73a9a1e6690bdea28bf8eb62418237d578e663f40d2cd0d5c5a73b",
            "COMMON_USER_INPUT_BLOCK": "07cea4cc64fb5cb7b33ed49a17c1969c702c9dae0160dd6bd2274bd3c7ef6f87",
            "EventLayoutReconstructorUser": "b366988860374db491cc1d6a531a880b8d1a143fb82a73a68a6221fb9728909a",
            "SkeletonCheckerUser": "77f4876e1b815992420c4ec6cabf16bfdc41498287ff2142db1f6f3efdbf4f7b",
            "EpisodeReconstructorUser": "d8513121d2993c2598b144a1ae9ca9f73e4b6618ad8e318cbb47d9ea254bc994",
            "StageDescriptionReconstructorUser": "c1d23c02d0010c5019ec7cb4c5475d47c85085bd3db4cd7160c80c62272d9a29",
            "EventDescriptionReconstructorUser": "9ce1459c00cdd22eaa5201a3be8c8459993b9ce4422168af7f2a957630e52890",
        }
        for name, digest in snapshots.items():
            with self.subTest(template=name):
                self.assertEqual(hashlib.sha256(getattr(prompts, name).encode()).hexdigest(), digest)
        systems, users = prompts.get_agent_prompts()
        self.assertEqual(set(users), FACT_ROLES | {
            "SkeletonReconstructor", "SkeletonChecker", "EpisodeReconstructor",
            "StageDescriptionReconstructor", "EventDescriptionReconstructor",
        })
        self.assertEqual(set(systems), set(users))
        for role in users:
            self.assertEqual(systems[role], prompts.COMMON_SYSTEM_PROMPT)
            if role not in FACT_ROLES:
                self.assertNotIn(prompts.EPISODE_FACT_SCOPE_POLICY, users[role])


if __name__ == "__main__":
    unittest.main()
