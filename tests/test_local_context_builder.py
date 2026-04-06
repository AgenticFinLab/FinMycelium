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
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

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
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
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
