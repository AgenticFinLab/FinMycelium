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

    def test_build_selects_overlapping_cards_and_renders_selected_context(self):
        bundle = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="alpha risk excerpt",
                    tokens=["alpha", "risk"],
                ),
                EvidenceCard(
                    sample_id="sample-2",
                    title="sample-2",
                    excerpt="beta unrelated excerpt",
                    tokens=["beta"],
                ),
                EvidenceCard(
                    sample_id="sample-3",
                    title="sample-3",
                    excerpt="alpha signal excerpt",
                    tokens=["alpha", "signal"],
                ),
            ],
        )
        request = LocalContextRequest(
            agent_name="agent-alpha",
            query_text="alpha risk",
            key_words=["alpha"],
            context_assets=bundle,
        )

        package = LocalContextBuilder().build(request)

        self.assertEqual(package.scope, "agent-alpha")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.summary["selected_count"], 2)
        self.assertEqual(
            [card.sample_id for card in package.selected_cards],
            ["sample-1", "sample-3"],
        )
        self.assertIn("alpha risk excerpt", package.rendered_context)
        self.assertIn("alpha signal excerpt", package.rendered_context)
        self.assertNotIn("beta unrelated excerpt", package.rendered_context)

    def test_build_falls_back_when_no_cards_overlap(self):
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
            agent_name="agent-beta",
            query_text="alpha risk",
            key_words=["alpha"],
            context_assets=bundle,
        )

        package = LocalContextBuilder().build(request)

        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_cards, [])
        self.assertEqual(package.rendered_context, "")


if __name__ == "__main__":
    unittest.main()
