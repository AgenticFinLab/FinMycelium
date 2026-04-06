import unittest

from finmy.context import (
    LocalContextBuilder,
    LocalContextRequest,
)
from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


QUERY_TEXT = "What is the case involving fraud and money laundering by Qian Zhimin?"

MIXED_BUNDLE = EvidenceAssetBundle(
    retrieval_policy=EvidenceRetrievalPolicy(),
    index=EvidenceIndex(),
    evidence_cards=[
        EvidenceCard(
            sample_id="signal-1",
            title="signal-1",
            excerpt="Qian Zhimin ran the Blue Sky scheme and fled to Britain with bitcoin proceeds.",
            tokens=[
                "qian",
                "zhimin",
                "blue",
                "sky",
                "scheme",
                "fled",
                "britain",
                "bitcoin",
                "proceeds",
            ],
        ),
        EvidenceCard(
            sample_id="signal-2",
            title="signal-2",
            excerpt=(
                "Investigators linked laundering attempts and luxury property purchases to "
                "the same fraud."
            ),
            tokens=[
                "investigators",
                "linked",
                "laundering",
                "attempts",
                "luxury",
                "property",
                "purchases",
                "same",
                "fraud",
            ],
        ),
        EvidenceCard(
            sample_id="chrome-1",
            title="chrome-1",
            excerpt="Skip to main content Search for Careers Contact About us International edition",
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
            ],
        ),
    ],
)

NOISE_BUNDLE = EvidenceAssetBundle(
    retrieval_policy=EvidenceRetrievalPolicy(),
    index=EvidenceIndex(),
    evidence_cards=[
        EvidenceCard(
            sample_id="noise-1",
            title="noise-1",
            excerpt="Skip to main content Search for Careers Contact About us International edition",
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
            ],
        ),
        EvidenceCard(
            sample_id="noise-2",
            title="noise-2",
            excerpt="Latest headlines Related stories Sign up for newsletters",
            tokens=[
                "latest",
                "headlines",
                "related",
                "stories",
                "sign",
                "up",
                "for",
                "newsletters",
            ],
        ),
    ],
)


class GlobalShadowReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = LocalContextBuilder()
        cls.request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text=QUERY_TEXT,
            key_words=["fraud", "money laundering"],
        )

    def test_mixed_bundle_selects_small_signal_set_and_excludes_chrome(self):
        package = self.builder.build(self.request, MIXED_BUNDLE)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertGreater(package.summary["selected_count"], 0)
        self.assertLessEqual(package.summary["selected_count"], 3)
        self.assertIn("signal-1", package.selected_sample_ids)
        self.assertIn("signal-2", package.selected_sample_ids)
        self.assertNotIn("chrome-1", package.selected_sample_ids)
        self.assertIn("Qian Zhimin ran the Blue Sky scheme", package.rendered_context)
        self.assertNotIn("Skip to main content", package.rendered_context)

    def test_all_noise_bundle_falls_back_to_fulltext(self):
        package = self.builder.build(self.request, NOISE_BUNDLE)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")


if __name__ == "__main__":
    unittest.main()
