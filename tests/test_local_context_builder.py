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
            agent_name="episode-agent",
            query_text="alpha episode",
            key_words=["alpha"],
            target_stage="stage-1",
            target_episode="episode-1",
        )

        package = LocalContextBuilder().build(request, bundle)

        self.assertEqual(package.scope, "episode")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.summary["selected_count"], 1)
        self.assertEqual(package.selected_sample_ids, ["sample-1"])
        self.assertIn("alpha episode excerpt", package.rendered_context)

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
            agent_name="global-agent",
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
