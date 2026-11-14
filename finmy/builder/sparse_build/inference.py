"""Preserve completion status and usage for the sparse builder only."""

from finmy.model_api import ModelAPIInference
from lmbase.inference.base import InferCost, InferOutput


class SparseAPIInference(ModelAPIInference):
    def __init__(self, lm_name, generation_config, timeout=900):
        super().__init__(lm_name=lm_name, generation_config=generation_config)
        # Account for every submission ourselves; SDK retries would be invisible.
        self.client = self.client.with_options(max_retries=0, timeout=timeout)

    def _inference(self, messages):
        params = dict(self.generation_config or {})
        if "max_new_tokens" in params:
            params["max_tokens"] = params.pop("max_new_tokens")
        if "max_completion_tokens" not in params:
            params.setdefault("max_tokens", self.max_tokens)
        params.update(model=self.model_name, messages=messages)
        response = self.client.chat.completions.create(**params)
        usage = response.usage
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice is not None else None
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        completion_details = getattr(usage, "completion_tokens_details", None)
        return InferOutput(
            prompt=messages,
            response=(content or "").strip(),
            raw_response=content,
            cost=InferCost(
                time_used=None,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
            ),
            extras={
                "finish_reason": getattr(choice, "finish_reason", None),
                "refusal": getattr(choice.message, "refusal", None) if choice else None,
                "tool_calls": bool(getattr(choice.message, "tool_calls", None)) if choice else False,
                "reasoning_tokens": getattr(completion_details, "reasoning_tokens", None),
                "cached_tokens": getattr(prompt_details, "cached_tokens", None),
                "provider_response": response.model_dump(mode="json"),
            },
        )
