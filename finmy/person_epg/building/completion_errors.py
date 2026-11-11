"""Typed completion status; truncated output is never accepted as a full result."""


class IncompleteCompletionError(ValueError):
    def __init__(self, agent_name, *, finish_reason=None, refusal=False,
                 tool_calls=False, completion_tokens=None, output_limit=None):
        self.finish_reason = finish_reason
        self.refusal = bool(refusal)
        self.tool_calls = bool(tool_calls)
        self.completion_tokens = completion_tokens
        self.output_limit = output_limit
        if finish_reason == "length" and not self.refusal and not self.tool_calls:
            detail = "output was truncated; no partial result was accepted"
        else:
            detail = "non-text or unsuccessful completion; no result was accepted"
        super().__init__(
            f"{agent_name}: incomplete completion (finish_reason={finish_reason!r}, "
            f"completion_tokens={completion_tokens}, output_limit={output_limit}, "
            f"refusal={self.refusal}, tool_calls={self.tool_calls}): {detail}"
        )
