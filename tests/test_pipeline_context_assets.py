import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from finmy.context.assets import EvidenceAssetBundle, summarize_context_assets
from finmy.context.renderers import render_context_asset_summary
from finmy.generic import MetaSample, UserQueryInput
from finmy.pipeline import FinmyPipeline


class PipelineContextAssetsTest(unittest.TestCase):
    def test_create_build_input_attaches_built_evidence_assets_when_enabled(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = Mock()

        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha", "shared"])
        summarized_query = SimpleNamespace(key_words=["shared", "beta", "alpha", "gamma"])
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
                summarized_query=summarized_query,
            )

        self.assertEqual(
            build_input.user_query.key_words, ["alpha", "shared", "beta", "gamma"]
        )
        self.assertIs(build_input.context_assets, expected_bundle)
        build_assets.assert_called_once()
        merged_query = build_assets.call_args.args[0]
        self.assertEqual(merged_query.key_words, ["alpha", "shared", "beta", "gamma"])
        pipeline.logger.info.assert_any_call(
            "Passive context assets attached: %s",
            render_context_asset_summary(summarize_context_assets(expected_bundle)),
        )

    def test_create_build_input_merges_dict_shaped_summarized_keywords(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = Mock()

        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha", "shared"])
        summarized_query = SimpleNamespace(key_words={"shared": 3, "beta": 2, "gamma": 1})
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
        ), patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            build_input = pipeline.create_build_input(
                user_query,
                meta_samples,
                attach_context_assets=True,
                summarized_query=summarized_query,
            )

        self.assertEqual(
            build_input.user_query.key_words, ["alpha", "shared", "beta", "gamma"]
        )

    def test_create_build_input_defaults_to_disabled_context_assets(self):
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
            build_input = pipeline.create_build_input(user_query, meta_samples)

        self.assertEqual(build_input.user_query.key_words, ["alpha"])
        self.assertEqual(build_input.context_assets.evidence_cards, [])
        self.assertEqual(build_input.context_assets.index.token_counts, {})
        build_assets.assert_not_called()

    def test_create_build_input_preserves_original_query_without_summary(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = Mock()

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

        self.assertIs(build_input.user_query, user_query)
        self.assertIs(build_assets.call_args.args[0], user_query)
        self.assertEqual(build_input.user_query.key_words, ["alpha"])

    def test_lm_build_pipeline_with_contents_leaves_context_assets_empty(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
        pipeline.data_manager = SimpleNamespace()
        pipeline.builder = SimpleNamespace(run=Mock(return_value="ok"))
        pipeline.db_config = {}
        pipeline.pdf_collector_config = {}
        pipeline.url_collector_config = {}
        pipeline.summarizer_config = {}
        pipeline.matcher_config = {"use_matcher": False}

        raw_data_records = [SimpleNamespace(location="raw-1")]
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

        with patch.object(
            pipeline, "create_raw_data_records", return_value=raw_data_records
        ), patch.object(pipeline, "store_raw_data"), patch.object(
            pipeline, "create_and_store_user_query", return_value=user_query
        ), patch.object(
            pipeline, "summarize_user_query", return_value=SimpleNamespace()
        ), patch.object(
            pipeline, "_process_matching", return_value=meta_samples
        ), patch.object(
            pipeline, "store_meta_samples"
        ), patch(
            "finmy.pipeline.build_evidence_assets"
        ) as build_assets, patch(
            "finmy.converter.read_text_data_from_block",
            return_value="alpha excerpt",
        ):
            result = pipeline.lm_build_pipeline_with_contents(
                contents=["alpha excerpt"],
                query_text="alpha risk",
                key_words=["alpha"],
            )

        self.assertEqual(result, "ok")
        build_assets.assert_not_called()
        build_input = pipeline.builder.run.call_args.args[0]
        self.assertEqual(build_input.context_assets.evidence_cards, [])
        self.assertEqual(build_input.context_assets.index.token_counts, {})

    def test_lm_build_pipeline_with_contents_passes_summarized_query_to_build_input(self):
        pipeline = FinmyPipeline.__new__(FinmyPipeline)
        pipeline.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
        pipeline.data_manager = SimpleNamespace()
        pipeline.builder = SimpleNamespace(run=Mock(return_value="ok"))
        pipeline.db_config = {}
        pipeline.pdf_collector_config = {}
        pipeline.url_collector_config = {}
        pipeline.summarizer_config = {}
        pipeline.matcher_config = {"use_matcher": False}

        raw_data_records = [SimpleNamespace(location="raw-1")]
        user_query = UserQueryInput(query_text="alpha risk", key_words=["alpha"])
        summarized_query = SimpleNamespace(key_words=["alpha", "beta"])
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

        with patch.object(
            pipeline, "create_raw_data_records", return_value=raw_data_records
        ), patch.object(pipeline, "store_raw_data"), patch.object(
            pipeline, "create_and_store_user_query", return_value=user_query
        ), patch.object(
            pipeline, "summarize_user_query", return_value=summarized_query
        ), patch.object(
            pipeline, "_process_matching", return_value=meta_samples
        ), patch.object(
            pipeline, "store_meta_samples"
        ), patch.object(
            pipeline, "create_build_input", return_value=SimpleNamespace()
        ) as create_build_input:
            pipeline.lm_build_pipeline_with_contents(
                contents=["alpha excerpt"],
                query_text="alpha risk",
                key_words=["alpha"],
            )

        create_build_input.assert_called_once()
        self.assertIs(
            create_build_input.call_args.kwargs["summarized_query"], summarized_query
        )


if __name__ == "__main__":
    unittest.main()
