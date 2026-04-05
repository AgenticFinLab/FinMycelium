import unittest
from types import SimpleNamespace
from unittest.mock import patch

from finmy.context.assets import EvidenceAssetBundle
from finmy.generic import MetaSample, UserQueryInput
from finmy.pipeline import FinmyPipeline


class PipelineContextAssetsTest(unittest.TestCase):
    def test_create_build_input_attaches_built_evidence_assets_when_enabled(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = SimpleNamespace(info=lambda *args, **kwargs: None)

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
        expected_bundle = EvidenceAssetBundle.empty()

        with patch(
            "finmy.pipeline.build_evidence_assets",
            return_value=expected_bundle,
        ) as build_assets, patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            build_input = pipeline.create_build_input(
                user_query,
                meta_samples,
                attach_context_assets=True,
            )

        self.assertIs(build_input.context_assets, expected_bundle)
        build_assets.assert_called_once_with(user_query, build_input.samples)

    def test_create_build_input_leaves_context_assets_empty_when_disabled(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = SimpleNamespace(info=lambda *args, **kwargs: None)

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

        with patch("finmy.pipeline.build_evidence_assets") as build_assets, patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            build_input = pipeline.create_build_input(
                user_query,
                meta_samples,
                attach_context_assets=False,
            )

        self.assertEqual(build_input.context_assets.evidence_cards, [])
        self.assertEqual(build_input.context_assets.index.token_counts, {})
        build_assets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
