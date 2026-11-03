"""Exercise real lmbase formatting without credentials or network transport."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from lmbase.inference.api_call import LangChainAPIInference
from lmbase.inference.base import InferCost, InferOutput

from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput


class SparseMessageTransportTest(unittest.TestCase):
    def setUp(self):
        # Bypass client initialization, but retain real run/_create_messages.
        self.client = LangChainAPIInference.__new__(LangChainAPIInference)
        self.client._inference = Mock(side_effect=self._response)
        self.builder = SparseRagBuilder.__new__(SparseRagBuilder)
        self.builder.build_config = {}
        self.builder.agents_lm = self.client

    @staticmethod
    def _response(messages):
        return InferOutput(
            prompt=messages,
            response='{"participants": []}',
            raw_response='{"participants": []}',
            cost=InferCost(time_used=None, prompt_tokens=20, completion_tokens=5),
        )

    def test_formatted_messages_cross_actual_adapter_unchanged(self):
        for content in (
            '{"amount": 100, "nested": {"currency": "USD"}}',
            'Literal {Query}, unmatched { and closing }; line two\nnot a template',
            '\u4e2d\u6587\u8bc1\u636e {"name": "\u516c\u53f8"}',
        ):
            with self.subTest(content=content):
                inputs = SimpleNamespace(
                    user_query=UserQueryInput(query_text="Event", key_words=[]),
                    samples=[DataSample(sample_id="s1", raw_data_id="r1", content=content)],
                )
                kwargs = self.builder._build_prompt_kwargs(inputs, "ParticipantReconstructor")
                system, user = self.builder._format_agent_messages("ParticipantReconstructor", kwargs)
                result = self.builder._infer_and_parse_json(
                    "ParticipantReconstructor", system, user, kwargs, "participant"
                )
                self.assertEqual(result, {"participants": []})
                messages = self.client._inference.call_args.args[0]
                self.assertEqual(messages, [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ])
                self.assertIn(content, messages[1]["content"])

    def test_retry_preserves_original_formatted_content(self):
        attempts = []

        def transport(messages):
            attempts.append(messages)
            output = self._response(messages)
            if len(attempts) == 1:
                output.response = "invalid JSON"
            return output

        self.client._inference.side_effect = transport
        user = 'Source {"value": 123}; literal {Query}'
        result = self.builder._infer_and_parse_json(
            "ParticipantReconstructor", "system", user, {"Query": "do not replace"}, "participant"
        )
        self.assertEqual(result, {"participants": []})
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0][1]["content"], user)
        self.assertTrue(attempts[1][1]["content"].startswith(user))

    def test_transport_failure_is_not_retried_as_json_failure(self):
        self.client._inference.side_effect = TimeoutError("synthetic timeout")
        with self.assertRaises(TimeoutError):
            self.builder._infer_and_parse_json(
                "ParticipantReconstructor", "system", "user", {}, "participant"
            )
        self.assertEqual(self.client._inference.call_count, 1)


if __name__ == "__main__":
    unittest.main()
