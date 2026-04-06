import unittest

from finmy.context import (
    LocalContextBuilder,
    LocalContextPackage,
    LocalContextRequest,
)
from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


class LocalContextBuilderTest(unittest.TestCase):
    def test_exports_are_available_from_context_package(self):
        self.assertTrue(LocalContextBuilder)
        self.assertTrue(LocalContextPackage)
        self.assertTrue(LocalContextRequest)

    def test_build_query_bundle_for_global_agent_defines_bundle_shape(self):
        builder = LocalContextBuilder()
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        query_bundle = builder.build_query_bundle(request)

        self.assertEqual(query_bundle["scope"], "global")
        self.assertEqual(query_bundle["agent_name"], "EventDescriptionReconstructor")
        self.assertEqual(
            query_bundle["query_text"],
            "What is the case involving fraud and money laundering by Qian Zhimin?",
        )
        self.assertIn("keyword_hints", query_bundle)
        self.assertIn("global_phase_hints", query_bundle)
        self.assertTrue(query_bundle["keyword_hints"])
        self.assertTrue(query_bundle["global_phase_hints"])
        self.assertNotIn("stage_name", query_bundle)
        self.assertNotIn("episode_name", query_bundle)
        self.assertNotIn("entity_hints", query_bundle)
        self.assertNotIn("action_hints", query_bundle)
        self.assertNotIn("time_hints", query_bundle)

    def test_build_query_bundle_for_stage_agent_defines_stage_specific_fields(self):
        builder = LocalContextBuilder()
        request = LocalContextRequest(
            agent_name="StageDescriptionReconstructor",
            query_text="What happened during the fraud operation stage?",
            key_words=["fraud"],
            target_stage="Fraud Operation in China",
        )

        query_bundle = builder.build_query_bundle(request)

        self.assertEqual(query_bundle["scope"], "stage")
        self.assertEqual(query_bundle["agent_name"], "StageDescriptionReconstructor")
        self.assertEqual(query_bundle["stage_name"], "Fraud Operation in China")
        self.assertIn("keyword_hints", query_bundle)
        self.assertIn("stage_hints", query_bundle)
        self.assertTrue(query_bundle["keyword_hints"])
        self.assertTrue(query_bundle["stage_hints"])
        self.assertNotIn("episode_name", query_bundle)
        self.assertNotIn("entity_hints", query_bundle)
        self.assertNotIn("action_hints", query_bundle)
        self.assertNotIn("time_hints", query_bundle)

    def test_build_query_bundle_for_episode_agent_defines_episode_specific_fields(self):
        builder = LocalContextBuilder()
        request = LocalContextRequest(
            agent_name="EpisodeReconstructor",
            query_text="How did the Blue Sky episode unfold?",
            key_words=["Blue Sky"],
            target_stage="Fraud Operation in China",
            target_episode="Large-Scale Blue Sky Ponzi Scheme",
        )

        query_bundle = builder.build_query_bundle(request)

        self.assertEqual(query_bundle["scope"], "episode")
        self.assertEqual(query_bundle["agent_name"], "EpisodeReconstructor")
        self.assertEqual(query_bundle["stage_name"], "Fraud Operation in China")
        self.assertEqual(query_bundle["episode_name"], "Large-Scale Blue Sky Ponzi Scheme")
        self.assertIn("entity_hints", query_bundle)
        self.assertIn("action_hints", query_bundle)
        self.assertIn("time_hints", query_bundle)
        self.assertIsInstance(query_bundle["entity_hints"], list)
        self.assertIsInstance(query_bundle["action_hints"], list)
        self.assertIsInstance(query_bundle["time_hints"], list)
        self.assertNotIn("global_phase_hints", query_bundle)
        self.assertNotIn("stage_hints", query_bundle)

    def test_stage_and_episode_query_bundle_keep_stable_name_fields_when_targets_are_missing(self):
        builder = LocalContextBuilder()

        stage_bundle = builder.build_query_bundle(
            LocalContextRequest(
                agent_name="StageDescriptionReconstructor",
                query_text="alpha stage",
                key_words=["alpha"],
            )
        )
        episode_bundle = builder.build_query_bundle(
            LocalContextRequest(
                agent_name="EpisodeReconstructor",
                query_text="alpha episode",
                key_words=["alpha"],
            )
        )

        self.assertEqual(stage_bundle["scope"], "stage")
        self.assertIn("stage_name", stage_bundle)
        self.assertEqual(stage_bundle["stage_name"], "")
        self.assertEqual(episode_bundle["scope"], "episode")
        self.assertIn("stage_name", episode_bundle)
        self.assertIn("episode_name", episode_bundle)
        self.assertEqual(episode_bundle["stage_name"], "")
        self.assertEqual(episode_bundle["episode_name"], "")

    def test_query_bundle_uses_empty_hint_lists_when_no_real_scope_hints_exist(self):
        builder = LocalContextBuilder()

        global_bundle = builder.build_query_bundle(
            LocalContextRequest(
                agent_name="EventDescriptionReconstructor",
                query_text="alpha topic",
                key_words=["alpha"],
            )
        )
        episode_bundle = builder.build_query_bundle(
            LocalContextRequest(
                agent_name="EpisodeReconstructor",
                query_text="alpha episode",
                key_words=["alpha"],
            )
        )

        self.assertEqual(global_bundle["global_phase_hints"], [])
        self.assertEqual(episode_bundle["action_hints"], [])
        self.assertEqual(episode_bundle["time_hints"], [])

    def test_local_context_package_exposes_task_facing_metadata_from_request_assets(self):
        builder = LocalContextBuilder()
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Qian Zhimin used bitcoin to launder proceeds from Blue Sky.",
                    tokens=[
                        "qian",
                        "zhimin",
                        "bitcoin",
                        "launder",
                        "proceeds",
                        "blue",
                        "sky",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EpisodeReconstructor",
            query_text="How did the Blue Sky episode unfold?",
            key_words=["Blue Sky"],
            target_stage="Fraud Operation in China",
            target_episode="Large-Scale Blue Sky Ponzi Scheme",
            context_assets=bundle,
        )

        package = builder.build(request)

        self.assertEqual(package.query_bundle["scope"], "episode")
        self.assertEqual(package.query_bundle["episode_name"], "Large-Scale Blue Sky Ponzi Scheme")
        self.assertTrue(package.query_bundle["keyword_hints"])
        self.assertTrue(package.memory["selected_hint_counts"])
        self.assertEqual(package.memory["selected_sample_ids"], ["sample-1"])
        self.assertIn("used_card_count", package.budget_summary)
        self.assertGreater(package.budget_summary["used_card_count"], 0)

    def test_build_without_assets_reports_missing_context_assets_explicitly(self):
        package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="StageDescriptionReconstructor",
                query_text="alpha stage",
                key_words=["alpha"],
            )
        )

        self.assertEqual(package.retrieval_status, "missing_context_assets")
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.budget_summary["available_card_count"], 0)
        self.assertEqual(package.budget_summary["used_card_count"], 0)
        self.assertEqual(package.memory["asset_status"], "missing")

    def test_scope_mapping_is_explicit_for_known_agent_names(self):
        builder = LocalContextBuilder()

        episode_request = LocalContextRequest(
            agent_name="EpisodeReconstructor",
            query_text="alpha episode",
            key_words=["alpha"],
        )
        stage_request = LocalContextRequest(
            agent_name="StageDescriptionReconstructor",
            query_text="alpha stage",
            key_words=["alpha"],
        )
        global_request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="alpha event",
            key_words=["alpha"],
        )
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[],
        )

        self.assertEqual(builder.build(episode_request, bundle).scope, "episode")
        self.assertEqual(builder.build(stage_request, bundle).scope, "stage")
        self.assertEqual(builder.build(global_request, bundle).scope, "global")

    def test_unknown_agent_name_uses_target_scope_hints(self):
        builder = LocalContextBuilder()
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[],
        )

        episode_request = LocalContextRequest(
            agent_name="CustomAgent",
            query_text="alpha episode",
            key_words=["alpha"],
            target_episode="episode-9",
        )
        stage_request = LocalContextRequest(
            agent_name="CustomAgent",
            query_text="alpha stage",
            key_words=["alpha"],
            target_stage="stage-9",
        )
        global_request = LocalContextRequest(
            agent_name="CustomAgent",
            query_text="alpha global",
            key_words=["alpha"],
        )

        self.assertEqual(builder.build(episode_request, bundle).scope, "episode")
        self.assertEqual(builder.build(stage_request, bundle).scope, "stage")
        self.assertEqual(builder.build(global_request, bundle).scope, "global")

    def test_episode_request_prefers_episode_scope(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="alpha episode excerpt",
                    tokens=["alpha", "episode"],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EpisodeReconstructor",
            query_text="alpha episode",
            key_words=["alpha"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "episode")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.summary["selected_count"], 1)
        self.assertEqual(package.selected_sample_ids, ["sample-1"])
        self.assertIn("alpha episode excerpt", package.rendered_context)

    def test_scope_specific_query_bundle_fields_can_change_selected_card_from_same_bundle(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=1),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-stage",
                    title="sample-stage",
                    excerpt="Myanmar Network Stage moved alpha transfer funds.",
                    tokens=["alpha", "transfer", "myanmar", "network", "stage"],
                    entity_hints=["myanmar network stage"],
                    action_hints=["transfer"],
                ),
                EvidenceCard(
                    sample_id="sample-episode",
                    title="sample-episode",
                    excerpt="Large-Scale Blue Sky Ponzi Scheme used alpha transfer funds.",
                    tokens=["alpha", "transfer", "blue", "sky", "scheme"],
                    entity_hints=["Large-Scale Blue Sky Ponzi Scheme"],
                    action_hints=["launder"],
                    time_hints=["2019"],
                ),
            ],
        )
        stage_request = LocalContextRequest(
            agent_name="StageDescriptionReconstructor",
            query_text="alpha transfer",
            key_words=["alpha"],
            target_stage="Myanmar Network Stage",
        )
        episode_request = LocalContextRequest(
            agent_name="EpisodeReconstructor",
            query_text="alpha transfer",
            key_words=["alpha"],
            target_stage="Myanmar Network Stage",
            target_episode="Large-Scale Blue Sky Ponzi Scheme",
        )

        stage_package = LocalContextBuilder().build(stage_request, bundle)
        episode_package = LocalContextBuilder().build(episode_request, bundle)

        self.assertEqual(stage_package.selected_sample_ids, ["sample-stage"])
        self.assertEqual(episode_package.selected_sample_ids, ["sample-episode"])

    def test_scope_specific_budget_and_rationale_are_exposed(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-stage",
                    title="sample-stage",
                    excerpt="Myanmar Network Stage moved alpha transfer funds.",
                    tokens=["alpha", "transfer", "myanmar", "network", "stage"],
                    entity_hints=["myanmar network stage"],
                    action_hints=["transfer"],
                ),
                EvidenceCard(
                    sample_id="sample-episode",
                    title="sample-episode",
                    excerpt="Large-Scale Blue Sky Ponzi Scheme laundered alpha transfer funds in 2019.",
                    tokens=["alpha", "transfer", "blue", "sky", "scheme", "2019"],
                    entity_hints=["Large-Scale Blue Sky Ponzi Scheme"],
                    action_hints=["launder"],
                    time_hints=["2019"],
                ),
            ],
        )
        stage_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="StageDescriptionReconstructor",
                query_text="alpha transfer",
                key_words=["alpha"],
                target_stage="Myanmar Network Stage",
            ),
            bundle,
        )
        episode_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EpisodeReconstructor",
                query_text="alpha transfer",
                key_words=["alpha"],
                target_stage="Myanmar Network Stage",
                target_episode="Large-Scale Blue Sky Ponzi Scheme",
            ),
            bundle,
        )

        self.assertNotEqual(
            stage_package.budget_summary["target_card_budget"],
            episode_package.budget_summary["target_card_budget"],
        )
        self.assertEqual(
            stage_package.memory["selection_rationale"][0]["matched_fields"],
            ["query_tokens", "stage_name", "stage_hints"],
        )
        self.assertIn(
            "episode_name",
            episode_package.memory["selection_rationale"][0]["matched_fields"],
        )
        self.assertIn(
            "entity_hints",
            episode_package.memory["selection_rationale"][0]["matched_fields"],
        )

    def test_transaction_reconstructor_keeps_tighter_budget_than_stage_path_when_episode_hint_is_missing(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=5),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-narrative",
                    title="sample-narrative",
                    excerpt="Investigators described the broader episode narrative.",
                    tokens=["bitcoin", "transfer", "episode", "investigators", "narrative"],
                ),
                EvidenceCard(
                    sample_id="sample-money",
                    title="sample-money",
                    excerpt="Bitcoin proceeds were transferred through the episode account.",
                    tokens=["bitcoin", "transfer", "episode", "proceeds", "account"],
                    money_hints=["bitcoin"],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="TransactionReconstructor",
            query_text="How was bitcoin transferred in this episode?",
            key_words=["bitcoin", "transfer"],
            target_stage="Stage 1",
        )

        package = LocalContextBuilder().build(request, bundle)
        stage_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="StageDescriptionReconstructor",
                query_text="How was bitcoin transferred in this episode?",
                key_words=["bitcoin", "transfer"],
                target_stage="Stage 1",
            ),
            bundle,
        )

        self.assertEqual(package.scope, "stage")
        self.assertLess(
            package.budget_summary["target_card_budget"],
            stage_package.budget_summary["target_card_budget"],
        )
        self.assertEqual(package.selected_sample_ids, ["sample-money"])

    def test_transaction_reconstructor_prefers_money_relevant_evidence_over_narrative_evidence(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=1),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="narrative-card",
                    title="narrative-card",
                    excerpt="Investigators described the broader episode narrative.",
                    tokens=["bitcoin", "transfer", "episode", "investigators", "narrative"],
                ),
                EvidenceCard(
                    sample_id="money-card",
                    title="money-card",
                    excerpt="Bitcoin proceeds were transferred through the episode account.",
                    tokens=["bitcoin", "transfer", "episode", "proceeds", "account"],
                    money_hints=["bitcoin"],
                    action_hints=["transfer"],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="TransactionReconstructor",
            query_text="How was bitcoin transferred in this episode?",
            key_words=["bitcoin", "transfer"],
            target_stage="Stage 1",
            target_episode="Episode 1",
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.selected_sample_ids, ["money-card"])
        self.assertIn(
            "money_hints",
            package.memory["selection_rationale"][0]["matched_fields"],
        )
        self.assertIn(
            "action_hints",
            package.memory["selection_rationale"][0]["matched_fields"],
        )

    def test_participant_reconstructor_uses_its_own_budget_tier_before_scope_defaults(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=5),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="A participant was linked to the transfer.",
                    tokens=["participant", "transfer"],
                )
            ],
        )
        participant_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="ParticipantReconstructor",
                query_text="Who handled the transfer?",
                key_words=["transfer"],
                target_stage="Stage 1",
            ),
            bundle,
        )
        stage_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="StageDescriptionReconstructor",
                query_text="Who handled the transfer?",
                key_words=["transfer"],
                target_stage="Stage 1",
            ),
            bundle,
        )

        self.assertLess(
            participant_package.budget_summary["target_card_budget"],
            stage_package.budget_summary["target_card_budget"],
        )

    def test_global_scope_respects_resolved_card_budget_reported_in_budget_summary(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=5),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Qian Zhimin ran a Blue Sky ponzi scheme in 2014.",
                    tokens=["qian", "zhimin", "fraud", "ponzi", "blue", "sky", "2014"],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt="Investigators traced bitcoin laundering through Myanmar in 2018.",
                    tokens=["investigators", "traced", "bitcoin", "laundering", "myanmar", "2018"],
                ),
                EvidenceCard(
                    sample_id="sample-3",
                    title="sample-3",
                    excerpt="Qian Zhimin converted bitcoin proceeds after fleeing China.",
                    tokens=["qian", "zhimin", "bitcoin", "proceeds", "china", "converted"],
                ),
                EvidenceCard(
                    sample_id="sample-4",
                    title="sample-4",
                    excerpt="Blue Sky organizers recruited investors in 2015.",
                    tokens=["blue", "sky", "organizers", "investors", "2015"],
                ),
                EvidenceCard(
                    sample_id="sample-5",
                    title="sample-5",
                    excerpt="Bitcoin transfers moved proceeds through Myanmar in 2019.",
                    tokens=["bitcoin", "transfers", "proceeds", "myanmar", "2019"],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.budget_summary["target_card_budget"], 3)
        self.assertEqual(package.budget_summary["used_card_count"], 3)
        self.assertEqual(len(package.selected_sample_ids), 3)
        self.assertEqual(package.budget_summary["remaining_card_budget"], 0)

    def test_global_scope_selection_rationale_uses_query_bundle_phase_and_match_kind(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=2),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-strong",
                    title="sample-strong",
                    excerpt="Qian Zhimin ran a Blue Sky ponzi scheme in 2014.",
                    tokens=["qian", "zhimin", "fraud", "ponzi", "blue", "sky", "2014"],
                ),
                EvidenceCard(
                    sample_id="sample-backstop",
                    title="sample-backstop",
                    excerpt="Authorities traced cryptocurrency to London property purchases and shell transfers.",
                    tokens=["authorities", "traced", "cryptocurrency", "london", "property", "purchases", "shell", "transfers"],
                ),
            ],
        )
        strong_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EventDescriptionReconstructor",
                query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
                key_words=["fraud", "money laundering"],
            ),
            bundle,
        )
        backstop_package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EventDescriptionReconstructor",
                query_text="How were cryptocurrency assets used in London property purchases?",
                key_words=["cryptocurrency", "London property"],
            ),
            bundle,
        )

        self.assertEqual(
            strong_package.memory["selection_rationale"][0]["matched_fields"],
            ["query_tokens", "global_phase_hints"],
        )
        self.assertEqual(
            strong_package.memory["selection_rationale"][0]["match_kind"],
            "strong",
        )
        self.assertEqual(
            backstop_package.memory["selection_rationale"][0]["match_kind"],
            "backstop",
        )

    def test_max_cards_keeps_the_most_relevant_matches(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=1),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="alpha stale score excerpt",
                    tokens=["alpha"],
                    score=999,
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt="alpha beta strongest excerpt",
                    tokens=["alpha", "beta"],
                    score=1,
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="StageDescriptionReconstructor",
            query_text="alpha beta",
            key_words=[],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "stage")
        self.assertEqual(package.summary["selected_count"], 1)
        self.assertEqual(package.selected_sample_ids, ["sample-2"])
        self.assertIn("alpha beta strongest excerpt", package.rendered_context)
        self.assertNotIn("alpha stale score excerpt", package.rendered_context)

    def test_max_cards_prioritizes_strong_case_signal_over_high_information_backstop(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=1),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Authorities traced cryptocurrency to London property purchases "
                        "and shell transfers."
                    ),
                    tokens=[
                        "authorities",
                        "traced",
                        "cryptocurrency",
                        "london",
                        "property",
                        "purchases",
                        "shell",
                        "transfers",
                    ],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt="Qian Zhimin used bitcoin to launder proceeds from Blue Sky.",
                    tokens=[
                        "qian",
                        "zhimin",
                        "bitcoin",
                        "launder",
                        "proceeds",
                        "blue",
                        "sky",
                    ],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-2"])

    def test_global_request_falls_back_when_no_cards_overlap(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="gamma excerpt",
                    tokens=["gamma"],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="alpha risk",
            key_words=["alpha"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

    def test_global_request_falls_back_when_overlap_is_generic_institutional_terms(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="The legal service reviewed the institutional matter and filed a report.",
                    tokens=[
                        "the",
                        "legal",
                        "service",
                        "reviewed",
                        "institutional",
                        "matter",
                        "filed",
                        "report",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the legal service matter at the institution?",
            key_words=["legal service", "institutional matter"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

    def test_global_request_falls_back_when_overlap_is_only_stopwords(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="What the Crown Prosecution Service is and how it works.",
                    tokens=[
                        "what",
                        "the",
                        "crown",
                        "prosecution",
                        "service",
                        "is",
                        "and",
                        "how",
                        "it",
                        "works",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What happened to cryptocurrency in the case?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

    def test_global_request_falls_back_when_selection_is_late_only(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Qian Zhimin was sentenced in court in 2025 after trial.",
                    tokens=[
                        "qian",
                        "zhimin",
                        "sentenced",
                        "court",
                        "2025",
                        "trial",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

    def test_global_request_stays_sufficient_when_selection_covers_multiple_phases(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Qian Zhimin ran a Blue Sky ponzi scheme in 2014.",
                    tokens=[
                        "qian",
                        "zhimin",
                        "fraud",
                        "ponzi",
                        "blue",
                        "sky",
                        "2014",
                    ],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt=(
                        "Investigators traced bitcoin laundering through Myanmar in 2018."
                    ),
                    tokens=[
                        "investigators",
                        "traced",
                        "bitcoin",
                        "laundering",
                        "myanmar",
                        "2018",
                    ],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.summary["selected_count"], 2)
        self.assertEqual(package.selected_sample_ids, ["sample-1", "sample-2"])
        self.assertIn("Blue Sky ponzi scheme", package.rendered_context)
        self.assertIn("bitcoin laundering", package.rendered_context)

    def test_global_request_is_sufficient_when_case_terms_overlap(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Qian Zhimin used bitcoin to launder proceeds from Blue Sky.",
                    tokens=[
                        "qian",
                        "zhimin",
                        "bitcoin",
                        "launder",
                        "proceeds",
                        "blue",
                        "sky",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])
        self.assertIn("Qian Zhimin", package.rendered_context)

    def test_global_request_accepts_high_information_overlap_without_exact_case_tokens(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Authorities traced cryptocurrency to London property purchases "
                        "and shell transfers."
                    ),
                    tokens=[
                        "authorities",
                        "traced",
                        "cryptocurrency",
                        "london",
                        "property",
                        "purchases",
                        "shell",
                        "transfers",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="How were cryptocurrency assets used in London property purchases?",
            key_words=["cryptocurrency", "London property"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_request_falls_back_when_only_one_incidental_long_token_overlaps(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="Cryptocurrency market update and outlook.",
                    tokens=["cryptocurrency", "market", "update", "outlook"],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="How were cryptocurrency assets moved?",
            key_words=["cryptocurrency"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])

    def test_global_request_keeps_signal_card_with_noisy_prefix_when_body_has_case_terms(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content International edition Qian Zhimin converted bitcoin "
                        "proceeds after fleeing China."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "international",
                        "edition",
                        "qian",
                        "zhimin",
                        "converted",
                        "bitcoin",
                        "proceeds",
                        "after",
                        "fleeing",
                        "china",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_noise_filter_uses_leading_chrome_not_whole_excerpt_substring(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content International edition. Qian Zhimin pleaded guilty "
                        "after investigators traced bitcoin proceeds."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "international",
                        "edition",
                        "qian",
                        "zhimin",
                        "pleaded",
                        "guilty",
                        "after",
                        "investigators",
                        "traced",
                        "bitcoin",
                        "proceeds",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_request_rejects_leading_chrome_topic_keyword_pileup_without_substantive_body(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content International edition Cryptocurrency property "
                        "purchases Latest headlines"
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "international",
                        "edition",
                        "cryptocurrency",
                        "property",
                        "purchases",
                        "latest",
                        "headlines",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="How were cryptocurrency assets used in London property purchases?",
            key_words=["cryptocurrency", "property purchases"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])

    def test_global_request_keeps_leading_chrome_card_with_high_information_only_body(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content Authorities traced cryptocurrency assets to "
                        "London property purchases and shell transfers."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "authorities",
                        "traced",
                        "cryptocurrency",
                        "assets",
                        "london",
                        "property",
                        "purchases",
                        "shell",
                        "transfers",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="How were cryptocurrency assets used in London property purchases?",
            key_words=["cryptocurrency assets", "london property purchases"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_request_keeps_legitimate_ad_feedback_prose_when_it_is_informative(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Ad Feedback improved attribution analysis."
                    ),
                    tokens=[
                        "ad",
                        "feedback",
                        "improved",
                        "attribution",
                        "analysis",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What role did ad feedback play in improved attribution analysis?",
            key_words=["ad feedback", "improved attribution analysis"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_request_keeps_signal_card_in_mixed_bundle_and_rejects_chrome(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content International edition Qian Zhimin converted bitcoin "
                        "proceeds after fleeing China."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "international",
                        "edition",
                        "qian",
                        "zhimin",
                        "converted",
                        "bitcoin",
                        "proceeds",
                        "after",
                        "fleeing",
                        "china",
                    ],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt=(
                        "Skip to main content Search for Careers Contact About us International "
                        "edition Latest headlines"
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "search",
                        "for",
                        "careers",
                        "contact",
                        "about",
                        "us",
                        "international",
                        "edition",
                        "latest",
                        "headlines",
                    ],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-1"])

    def test_global_request_keeps_signal_card_when_chrome_leads_in_mixed_bundle(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content Search for Careers Contact About us International "
                        "edition Latest headlines"
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "search",
                        "for",
                        "careers",
                        "contact",
                        "about",
                        "us",
                        "international",
                        "edition",
                        "latest",
                        "headlines",
                    ],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt=(
                        "Skip to main content International edition Qian Zhimin converted bitcoin "
                        "proceeds after fleeing China."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "international",
                        "edition",
                        "qian",
                        "zhimin",
                        "converted",
                        "bitcoin",
                        "proceeds",
                        "after",
                        "fleeing",
                        "china",
                    ],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["sample-2"])

    def test_global_request_still_rejects_pure_page_chrome_cards(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content Search for Careers Contact About us International "
                        "edition Latest headlines"
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "search",
                        "for",
                        "careers",
                        "contact",
                        "about",
                        "us",
                        "international",
                        "edition",
                        "latest",
                        "headlines",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])

    def test_global_request_falls_back_when_selected_cards_are_navigation_noise(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt=(
                        "Skip to main content Search for Careers Contact About us "
                        "Latest headlines Related stories Sign up for newsletters."
                    ),
                    tokens=[
                        "skip",
                        "to",
                        "main",
                        "content",
                        "search",
                        "for",
                        "careers",
                        "contact",
                        "about",
                        "us",
                        "latest",
                        "headlines",
                        "related",
                        "stories",
                        "sign",
                        "up",
                        "newsletters",
                    ],
                )
            ],
        )
        request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")


if __name__ == "__main__":
    unittest.main()
