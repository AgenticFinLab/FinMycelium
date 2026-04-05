import unittest
from unittest.mock import patch

from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)
from finmy.converter import convert_to_build_input
from finmy.generic import MetaSample, UserQueryInput


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


if __name__ == "__main__":
    unittest.main()
