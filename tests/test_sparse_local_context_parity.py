"""Local context parity tests adapted to sparse_build's private architecture."""

import unittest

from finmy.generic import DataSample, UserQueryInput


class SparseLocalContextParityTest(unittest.TestCase):
    def test_global_context_rejects_template_only_navigation_matches(self):
        from finmy.builder.sparse_build.context_assets import build_evidence_assets
        from finmy.builder.sparse_build.local_context_builder import (
            LocalContextBuilder,
            LocalContextRequest,
        )

        query_text = "latest article page search contact newsletters"
        bundle = build_evidence_assets(
            UserQueryInput(query_text=query_text, key_words=["article", "search"]),
            [
                DataSample(
                    sample_id="template",
                    raw_data_id="r-template",
                    content=(
                        "latest article page search contact site newsletters "
                        "related stories menu home edition"
                    ),
                    category="site navigation",
                    knowledge_field="finance",
                )
            ],
        )

        package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EventDescriptionReconstructor",
                query_text=query_text,
                key_words=["article", "search"],
                context_assets=bundle,
            )
        )

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.memory["selection_rationale"], [])
        self.assertEqual(package.budget_summary["candidate_card_count"], 0)

    def test_global_context_keeps_case_signal_card_and_filters_template_card(self):
        from finmy.builder.sparse_build.context_assets import build_evidence_assets
        from finmy.builder.sparse_build.local_context_builder import (
            LocalContextBuilder,
            LocalContextRequest,
        )

        bundle = build_evidence_assets(
            UserQueryInput(
                query_text="Blue Sky fraud latest article",
                key_words=["Blue Sky", "fraud"],
            ),
            [
                DataSample(
                    sample_id="template",
                    raw_data_id="r-template",
                    content="latest article page search contact site newsletters",
                    category="site navigation",
                    knowledge_field="finance",
                ),
                DataSample(
                    sample_id="case",
                    raw_data_id="r-case",
                    content=(
                        "Blue Sky fraud proceeds were converted into bitcoin "
                        "during the laundering scheme."
                    ),
                    category="case evidence",
                    knowledge_field="finance",
                ),
            ],
        )

        package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="EventDescriptionReconstructor",
                query_text="Blue Sky fraud latest article",
                key_words=["Blue Sky", "fraud"],
                context_assets=bundle,
            )
        )

        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertEqual(package.selected_sample_ids, ["case"])
        self.assertEqual(package.memory["selection_rationale"][0]["match_kind"], "strong")

    def test_transaction_context_prefers_stage_aligned_card_over_generic_money_card(self):
        from finmy.builder.sparse_build.context_assets import build_evidence_assets
        from finmy.builder.sparse_build.local_context_builder import (
            LocalContextBuilder,
            LocalContextRequest,
        )

        query_text = "bitcoin transfer proceeds money laundering crypto funds payment"
        bundle = build_evidence_assets(
            UserQueryInput(
                query_text=query_text,
                key_words=["bitcoin", "transfer", "money", "funds"],
            ),
            [
                DataSample(
                    sample_id="generic-money",
                    raw_data_id="r-generic",
                    content=(
                        "bitcoin transfer proceeds money laundering crypto funds "
                        "payment settlement records"
                    ),
                    category="money movement",
                    knowledge_field="finance",
                ),
                DataSample(
                    sample_id="stage-aligned",
                    raw_data_id="r-stage",
                    content="Late court filing confirms the bitcoin transfer.",
                    category="court record",
                    knowledge_field="finance",
                ),
            ],
        )

        package = LocalContextBuilder().build(
            LocalContextRequest(
                agent_name="TransactionReconstructor",
                query_text=query_text,
                key_words=["bitcoin", "transfer", "money", "funds"],
                target_stage="Late court",
                target_episode="Bitcoin transfer",
                context_assets=bundle,
            )
        )

        self.assertEqual(package.selected_sample_ids, ["stage-aligned"])
        self.assertEqual(package.budget_summary["budget_source"], "agent")
        self.assertIn("stage_name", package.memory["selection_rationale"][0]["matched_fields"])


if __name__ == "__main__":
    unittest.main()
