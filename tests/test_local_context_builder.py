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
                    excerpt="alpha first excerpt",
                    tokens=["alpha"],
                    score=1,
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt="alpha strongest excerpt",
                    tokens=["alpha"],
                    score=5,
                ),
                EvidenceCard(
                    sample_id="sample-3",
                    title="sample-3",
                    excerpt="alpha middle excerpt",
                    tokens=["alpha"],
                    score=3,
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="StageDescriptionReconstructor",
            query_text="alpha",
            key_words=[],
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "stage")
        self.assertEqual(package.summary["selected_count"], 1)
        self.assertEqual(package.selected_sample_ids, ["sample-2"])
        self.assertIn("alpha strongest excerpt", package.rendered_context)
        self.assertNotIn("alpha first excerpt", package.rendered_context)
        self.assertNotIn("alpha middle excerpt", package.rendered_context)

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


if __name__ == "__main__":
    unittest.main()
