"""Parse model JSON with bounded punctuation-only recovery."""
import json
import re


def parse_json_response(response_text):
    text = response_text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Start at the outer value. Never accept a valid inner object from a
    # truncated outer graph. Braces inside quoted evidence are ignored.
    start = next((i for i, c in enumerate(text) if c in "{["), None)
    if start is None:
        raise ValueError("Model response contains no JSON object or array")
    stack, quoted, escaped, end = [], False, False, None
    for i in range(start, len(text)):
        c = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
            continue
        if c == '"':
            quoted = True
        elif c in "{[":
            stack.append(c)
        elif c in "}]":
            if not stack or stack.pop() != ("{" if c == "}" else "["):
                raise ValueError("Model JSON has mismatched brackets")
            if not stack:
                end = i + 1
                break
    if end is None:
        raise ValueError("Model JSON is incomplete (possibly output token limit); regenerate the complete response")
    candidate = text[start:end]
    for _ in range(33):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            pos = exc.pos
            # Only delimiters outside strings are changed, never evidence text.
            if exc.msg == "Expecting ',' delimiter" and candidate[pos:pos+1] in ('"', '{', '[', '-', 't', 'f', 'n', *'0123456789'):
                candidate = candidate[:pos] + ',' + candidate[pos:]
                continue
            if exc.msg in ("Expecting property name enclosed in double quotes", "Expecting value") and candidate[pos:pos+1] in ('}', ']'):
                before = candidate[:pos].rstrip()
                if before.endswith(','):
                    candidate = before[:-1] + candidate[pos:]
                    continue
            raise ValueError(f"Invalid model JSON: {exc}") from exc
    raise ValueError("Model JSON exceeds punctuation repair limit")
