import unittest

from finmy.context.assets import build_evidence_assets
from finmy.context.renderers import (
    render_context_asset_bundle,
    render_context_asset_summary,
)
from finmy.generic import DataSample, UserQueryInput
from finmy.pipeline import summarize_context_assets


class PromptCleanupTest(unittest.TestCase):
    def test_render_context_asset_summary_returns_string(self):
        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha"])
        samples = [
            DataSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                content="alpha beta beta",
                category="risk",
                knowledge_field="finance",
                tag="tag-1",
                method="method-1",
            )
        ]

        bundle = build_evidence_assets(user_query, samples)
        summary = summarize_context_assets(bundle)
        rendered = render_context_asset_summary(summary)

        self.assertIsInstance(rendered, str)
        self.assertIn("context_asset_summary", rendered)
        self.assertIn("evidence_card_count=1", rendered)

    def test_render_context_asset_bundle_returns_string(self):
        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha"])
        samples = [
            DataSample(
                sample_id="sample-1",
                raw_data_id="raw-1",
                content="alpha beta beta",
                category="risk",
                knowledge_field="finance",
                tag="tag-1",
                method="method-1",
            )
        ]

        bundle = build_evidence_assets(user_query, samples)
        rendered = render_context_asset_bundle(bundle)

        self.assertIsInstance(rendered, str)
        self.assertIn("context_asset_bundle", rendered)
        self.assertIn("sample-1", rendered)


if __name__ == "__main__":
    unittest.main()
