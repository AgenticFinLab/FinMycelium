"""Focused tests for sparse_build local context assets."""

import unittest

from finmy.generic import DataSample, UserQueryInput


class SparseContextAssetsTest(unittest.TestCase):
    def test_empty_samples_build_empty_bundle_without_crashing(self):
        from finmy.builder.sparse_build.context_assets import (
            build_evidence_assets,
            summarize_context_assets,
        )

        bundle = build_evidence_assets(
            UserQueryInput(query_text="alpha risk", key_words=["alpha"]),
            [],
        )
        summary = summarize_context_assets(bundle)

        self.assertEqual(bundle.evidence_cards, [])
        self.assertEqual(summary["evidence_card_count"], 0)
        self.assertEqual(summary["sample_id_count"], 0)
        self.assertGreater(summary["query_token_count"], 0)

    def test_query_terms_and_sample_content_generate_ranked_evidence_cards(self):
        from finmy.builder.sparse_build.context_assets import build_evidence_assets

        user_query = UserQueryInput(
            query_text="Blue Sky bitcoin laundering",
            key_words=["bitcoin", "laundering"],
        )
        samples = [
            DataSample(
                sample_id="s1",
                raw_data_id="r1",
                content=(
                    "In July 2017, Qian Zhimin used bitcoin to launder "
                    "Blue Sky fraud proceeds worth £23.5 million."
                ),
                category="case evidence",
                knowledge_field="finance",
            )
        ]

        bundle = build_evidence_assets(user_query, samples)
        card = bundle.evidence_cards[0]

        self.assertEqual(card.sample_id, "s1")
        self.assertGreater(card.score, 0)
        self.assertIn("bitcoin", card.money_hints)
        self.assertIn("has_money_signal", card.quality_flags)
        self.assertIn("2017", card.time_hints)

    def test_rendered_summary_and_card_are_stable_strings(self):
        from finmy.builder.sparse_build.context_assets import build_evidence_assets
        from finmy.builder.sparse_build.renderers import (
            render_context_asset_summary,
            render_evidence_card,
        )

        bundle = build_evidence_assets(
            UserQueryInput(query_text="alpha risk", key_words=["alpha"]),
            [
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content="alpha beta beta",
                    category="risk",
                    knowledge_field="finance",
                )
            ],
        )

        rendered_card = render_evidence_card(bundle.evidence_cards[0])
        rendered_summary = render_context_asset_summary(
            {
                "evidence_card_count": 1,
                "sample_id_count": 1,
                "global_token_count": 5,
                "query_token_count": 2,
                "signal_card_count": 0,
                "time_hint_count": 0,
                "entity_hint_count": 0,
                "action_hint_count": 0,
                "money_hint_count": 0,
            }
        )

        self.assertIn("sample_id: s1", rendered_card)
        self.assertIn("excerpt: alpha beta beta", rendered_card)
        self.assertIn("context_asset_summary:", rendered_summary)
        self.assertIn("evidence_card_count=1", rendered_summary)

    def test_local_context_builder_selects_matching_cards_with_length_boundary(self):
        from finmy.builder.sparse_build.context_assets import (
            EvidenceRetrievalPolicy,
            build_evidence_assets,
        )
        from finmy.builder.sparse_build.local_context_builder import (
            LocalContextBuilder,
            LocalContextRequest,
        )

        bundle = build_evidence_assets(
            UserQueryInput(query_text="bitcoin laundering", key_words=["bitcoin"]),
            [
                DataSample(
                    sample_id="s1",
                    raw_data_id="r1",
                    content="bitcoin laundering evidence " * 20,
                    category="target",
                    knowledge_field="finance",
                ),
                DataSample(
                    sample_id="s2",
                    raw_data_id="r2",
                    content="unrelated commodity update",
                    category="noise",
                    knowledge_field="finance",
                ),
            ],
            retrieval_policy=EvidenceRetrievalPolicy(max_cards=2, excerpt_char_limit=200),
        )

        package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EpisodeReconstructor",
                query_text="bitcoin laundering",
                key_words=["bitcoin"],
                target_stage="laundering stage",
                target_episode="bitcoin laundering episode",
                context_assets=bundle,
                max_context_chars=120,
            )
        )

        self.assertEqual(package.scope, "episode")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["s1"])
        self.assertLessEqual(len(package.rendered_context), 120)
        self.assertIn("used_card_count", package.budget_summary)


if __name__ == "__main__":
    unittest.main()
