"""Lazy JSON completion helpers for the optional legacy gap review."""
import json
import re
from pathlib import Path
from typing import Any, Callable
Completion = Callable[[str, dict[str, Any]], str]

def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value

def _live_completion(model: str, options: dict[str, Any]) -> Completion:
    """Reuse the project's inference adapter and the existing .env credentials."""
    engine = None

    def complete(system: str, payload: dict[str, Any]) -> str:
        nonlocal engine
        from dotenv import load_dotenv
        from lmbase.inference.api_call import LangChainAPIInference
        from lmbase.inference.base import InferInput
        from finmy.builder.utils import run_single_inference

        if engine is None:
            # Explicit path works in python -m and avoids find_dotenv stack guessing.
            load_dotenv(Path.cwd() / ".env", override=False)
            generation = {"temperature": 0.0, "max_new_tokens": 4096}
            if options.get("json_mode", True):
                generation["response_format"] = {"type": "json_object"}
            engine = LangChainAPIInference(lm_name=model, generation_config=generation)
            if hasattr(getattr(engine, "client", None), "with_options"):
                engine.client = engine.client.with_options(timeout=60.0, max_retries=1)
        output = run_single_inference(
            engine, InferInput(system_msg=system, user_msg=json.dumps(payload, ensure_ascii=False))
        )
        if not isinstance(output.response, str):
            raise ValueError("Model returned a non-text response")
        return output.response

    return complete
