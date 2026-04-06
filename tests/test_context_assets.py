import unittest
from unittest.mock import patch

from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
    build_evidence_assets,
    summarize_context_assets,
)
from finmy.context.renderers import render_context_asset_summary, render_evidence_card
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

    def test_build_evidence_assets_adds_structured_signal_fields(self):
        user_query = UserQueryInput(
            query_text="What happened in Qian Zhimin's bitcoin laundering case?",
            key_words=["Qian Zhimin", "bitcoin", "money laundering"],
        )
        samples = [
            DataSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                content=(
                    "In July 2017, Zhimin Qian fled China. "
                    "She later tried to buy a £23.5 million London property "
                    "and police investigated the bitcoin proceeds."
                ),
                category="risk",
                knowledge_field="finance",
            )
        ]

        bundle = build_evidence_assets(user_query, samples)
        card = bundle.evidence_cards[0]

        self.assertTrue({"2017", "july 2017"}.issubset(set(card.time_hints)))
        self.assertIn("zhimin qian", card.entity_hints)
        self.assertIn("buy", card.action_hints)
        self.assertIn("£23.5 million", card.money_hints)
        self.assertIn("has_money_signal", card.quality_flags)

    def test_build_evidence_assets_populates_signal_counts_on_index(self):
        user_query = UserQueryInput(
            query_text="Track bitcoin laundering activity",
            key_words=["bitcoin", "laundering"],
        )
        samples = [
            DataSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                content="Police seized bitcoin in 2024 after a money laundering probe.",
                category="risk",
                knowledge_field="finance",
            )
        ]

        bundle = build_evidence_assets(user_query, samples)

        self.assertIn("sample-1", bundle.index.sample_signal_counts)
        self.assertEqual(bundle.index.sample_signal_counts["sample-1"]["money_hints"], 1)
        self.assertEqual(bundle.index.sample_signal_counts["sample-1"]["time_hints"], 1)

    def test_context_asset_summary_counts_signal_bearing_cards(self):
        user_query = UserQueryInput(
            query_text="What happened in Qian Zhimin's bitcoin laundering case?",
            key_words=["Qian Zhimin", "bitcoin", "money laundering"],
        )
        samples = [
            DataSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                content=(
                    "In July 2017, Zhimin Qian fled China. "
                    "She later tried to buy a £23.5 million London property "
                    "and police investigated the bitcoin proceeds."
                ),
                category="risk",
                knowledge_field="finance",
            ),
            DataSample(
                sample_id="sample-2",
                raw_data_id="raw-2",
                content="This background note is intentionally generic and signal-free.",
                category="background",
                knowledge_field="finance",
            ),
        ]

        bundle = build_evidence_assets(user_query, samples)
        summary = summarize_context_assets(bundle)

        self.assertEqual(summary["evidence_card_count"], 2)
        self.assertEqual(summary["signal_card_count"], 1)
        self.assertEqual(summary["time_hint_count"], 2)
        self.assertEqual(summary["entity_hint_count"], 2)
        self.assertEqual(summary["action_hint_count"], 2)
        self.assertEqual(summary["money_hint_count"], 2)
        self.assertEqual(summary["quality_flag_count"], 4)
        self.assertEqual(summary["query_signal_count"], 6)

    def test_render_evidence_card_includes_structured_hints(self):
        card = EvidenceCard(
            sample_id="sample-1",
            title="risk",
            excerpt="...",
            time_hints=["2017"],
            entity_hints=["zhimin qian"],
            action_hints=["flee"],
            money_hints=["£23.5 million"],
            quality_flags=["has_money_signal"],
        )

        rendered = render_evidence_card(card)

        self.assertIn("time_hints: 2017", rendered)
        self.assertIn("entity_hints: zhimin qian", rendered)
        self.assertIn("action_hints: flee", rendered)
        self.assertIn("money_hints: £23.5 million", rendered)
        self.assertIn("quality_flags: has_money_signal", rendered)

    def test_render_context_asset_summary_includes_signal_metrics(self):
        summary = {
            "evidence_card_count": 2,
            "sample_id_count": 2,
            "global_token_count": 10,
            "query_token_count": 3,
            "signal_card_count": 1,
            "time_hint_count": 2,
            "entity_hint_count": 1,
            "action_hint_count": 3,
            "money_hint_count": 2,
            "quality_flag_count": 4,
            "query_signal_count": 3,
        }

        rendered = render_context_asset_summary(summary)

        self.assertIn("signal_card_count=1", rendered)
        self.assertIn("time_hint_count=2", rendered)
        self.assertIn("query_signal_count=3", rendered)


if __name__ == "__main__":
    unittest.main()
