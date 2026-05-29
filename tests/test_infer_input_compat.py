import unittest

from lmbase.inference import InferBatchOutput, InferCost, InferInput, InferOutput

from finmy.builder.utils import run_single_inference


def _output(response="ok"):
    return InferOutput(
        prompt=[],
        response=response,
        raw_response=response,
        cost=InferCost(
            time_used=None,
            prompt_tokens=1,
            completion_tokens=1,
        ),
    )


class _FakeBatchInference:
    def __init__(self):
        self.calls = []

    def run(self, infer_inputs, **kwargs):
        self.calls.append((infer_inputs, kwargs))
        return InferBatchOutput(outputs=[_output()], total_time_used=0.01)


class _FakeSingleInference:
    def __init__(self):
        self.calls = []

    def run(self, infer_input, **kwargs):
        self.calls.append((infer_input, kwargs))
        return _output("single-ok")


class _FakeDuckTypedSingleInference:
    def run(self, infer_input, **kwargs):
        class _Output:
            response = "duck-ok"

            def to_dict(self):
                return {"response": self.response}

        return _Output()


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

    def test_run_single_inference_preserves_single_input_api(self):
        infer = _FakeSingleInference()
        infer_input = InferInput(system_msg="sys", user_msg="user")

        output = run_single_inference(infer, infer_input, Query="demo")

        self.assertEqual(output.response, "single-ok")
        self.assertEqual(infer.calls, [(infer_input, {"Query": "demo"})])

    def test_run_single_inference_accepts_response_like_single_output(self):
        infer_input = InferInput(system_msg="sys", user_msg="user")

        output = run_single_inference(
            _FakeDuckTypedSingleInference(),
            infer_input,
        )

        self.assertEqual(output.response, "duck-ok")

    def test_run_single_inference_rejects_empty_batch_output(self):
        class _EmptyBatchInference:
            def run(self, infer_inputs, **kwargs):
                return InferBatchOutput(outputs=[], total_time_used=0.01)

        with self.assertRaisesRegex(ValueError, "no outputs"):
            run_single_inference(
                _EmptyBatchInference(),
                InferInput(system_msg="sys", user_msg="user"),
            )


if __name__ == "__main__":
    unittest.main()
