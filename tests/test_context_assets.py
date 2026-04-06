import unittest
from unittest.mock import patch

from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
)
from finmy.converter import convert_to_build_input
from finmy.generic import DataSample, MetaSample, UserQueryInput


class ConvertToBuildInputContextAssetsTest(unittest.TestCase):
    def test_preserves_supplied_context_assets_bundle(self):
        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha"])
        meta_samples = [
            MetaSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                location="meta-1",
                time="2025-01-01 00:00:00 UTC",
                category="risk",
                knowledge_field="finance",
                tag="tag-1",
                method="method-1",
            )
        ]
        context_assets = EvidenceAssetBundle(
            retrieval_policy=EvidenceRetrievalPolicy(),
            index=EvidenceIndex(token_counts={"alpha": 1}),
            evidence_cards=[
                EvidenceCard(
                    sample_id="sample-1",
                    title="sample-1",
                    excerpt="alpha excerpt",
                    tokens=["alpha"],
                )
            ],
        )

        with patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            build_input = convert_to_build_input(
                user_query=user_query,
                meta_samples=meta_samples,
                context_assets=context_assets,
            )

        self.assertIs(build_input.context_assets, context_assets)

    def test_build_evidence_assets_removes_skip_to_main_content_boilerplate(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Skip to main content Search for Careers Contact About us "
                "Qian Zhimin ran the Blue Sky Ponzi scheme and later laundered funds."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Skip to main content", excerpt)
        self.assertTrue(excerpt.startswith("Qian Zhimin"))
        self.assertIn("Blue Sky", excerpt)

    def test_build_evidence_assets_preserves_legitimate_leading_cnn_text(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Ad Feedback CNN analysis linked Qian Zhimin to laundering."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Ad Feedback", excerpt)
        self.assertTrue(excerpt.startswith("CNN analysis"))
        self.assertIn("Qian Zhimin", excerpt)

    def test_build_evidence_assets_preserves_legitimate_prose_starting_with_ad_feedback(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content="Ad Feedback is essential to this case study.",
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertEqual(excerpt, "Ad Feedback is essential to this case study.")

    def test_build_evidence_assets_removes_full_ad_feedback_chain(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Ad Feedback CNN values your feedback Video player was slow to load "
                "Qian Zhimin allegedly ran a large fraud scheme."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Ad Feedback", excerpt)
        self.assertNotIn("CNN values your feedback", excerpt)
        self.assertNotIn("Video player was slow to load", excerpt)
        self.assertTrue(excerpt.startswith("Qian Zhimin"))
        self.assertIn("fraud scheme", excerpt)

    def test_build_evidence_assets_removes_arrow_delimited_ad_feedback_chain(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Ad Feedback -> CNN values your feedback -> Video player was slow to load "
                "Qian Zhimin allegedly ran a large fraud scheme."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Ad Feedback", excerpt)
        self.assertNotIn("CNN values your feedback", excerpt)
        self.assertNotIn("Video player was slow to load", excerpt)
        self.assertNotIn("->", excerpt)
        self.assertTrue(excerpt.startswith("Qian Zhimin"))
        self.assertIn("fraud scheme", excerpt)

    def test_build_evidence_assets_preserves_legitimate_leading_cnn_reports_text(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content=(
                "Skip to main content CNN reports Qian Zhimin fled China."
            ),
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertNotIn("Skip to main content", excerpt)
        self.assertTrue(excerpt.startswith("CNN reports"))
        self.assertIn("Qian Zhimin", excerpt)

    def test_build_evidence_assets_strips_whitespace_for_non_noise_content(self):
        user_query = UserQueryInput(
            query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
            key_words=["fraud", "money laundering"],
            time_range=None,
            extras={},
        )
        sample = DataSample(
            sample_id="sample-1",
            raw_data_id="raw-1",
            content="   Qian Zhimin text   ",
            category="Financial Risk Control",
            knowledge_field="Artificial Intelligence",
            tag="url",
            method="URLParser",
        )

        bundle = build_evidence_assets(user_query, [sample])

        excerpt = bundle.evidence_cards[0].excerpt
        self.assertEqual(excerpt, "Qian Zhimin text")


if __name__ == "__main__":
    unittest.main()
