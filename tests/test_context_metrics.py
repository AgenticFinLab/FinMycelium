import unittest

from finmy.context.assets import build_evidence_assets, summarize_context_assets
from finmy.generic import DataSample, UserQueryInput


class ContextMetricsTest(unittest.TestCase):
    def test_summarize_context_assets_uses_current_bundle_fields(self):
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

        self.assertEqual(
            summary,
            {
                "evidence_card_count": 1,
                "sample_id_count": 1,
                "global_token_count": 6,
                "query_token_count": 3,
                "signal_card_count": 0,
                "time_hint_count": 0,
                "entity_hint_count": 0,
                "action_hint_count": 0,
                "money_hint_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
