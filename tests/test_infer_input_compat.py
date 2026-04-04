import unittest

from lmbase.inference import InferBatchOutput, InferCost, InferInput, InferOutput

from finmy.builder.utils import run_single_inference


class _FakeBatchInference:
    def __init__(self):
        self.calls = []

    def run(self, infer_inputs, **kwargs):
        self.calls.append((infer_inputs, kwargs))
        return InferBatchOutput(
            outputs=[
                InferOutput(
                    prompt=[],
                    response="ok",
                    raw_response="ok",
                    cost=InferCost(
                        time_used=None,
                        prompt_tokens=1,
                        completion_tokens=1,
                    ),
                )
            ],
            total_time_used=0.01,
        )


class InferInputCompatTest(unittest.TestCase):
    def test_run_single_inference_wraps_single_input_for_batch_api(self):
        infer = _FakeBatchInference()
        infer_input = InferInput(system_msg="sys", user_msg="user")

        output = run_single_inference(infer, infer_input, Query="demo")

        self.assertEqual(output.response, "ok")
        self.assertEqual(len(infer.calls), 1)
        infer_inputs, kwargs = infer.calls[0]
        self.assertEqual(len(infer_inputs), 1)
        self.assertIs(infer_inputs[0], infer_input)
        self.assertEqual(kwargs, {"Query": "demo"})


if __name__ == "__main__":
    unittest.main()
