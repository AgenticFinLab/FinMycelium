"""Offline request-contract and failure-diagnostic checks for event enrichment."""
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from finmy.runner.event_additions import empty_additions
from finmy.runner.event_enrichment import _failure_details, enrich_events


@pytest.mark.parametrize("api_style", ["single", "batch"])
@pytest.mark.parametrize("token_key", ["max_new_tokens", "max_tokens", "max_completion_tokens"])
def test_live_adapter_preserves_json_messages_and_bounded_options(api_style, token_key):
    # Isolate the dependency doubles from the rest of the suite. Run the real
    # SparseAPIInference and run_single_inference against a no-network client.
    program = textwrap.dedent('''
        import json
        import sys
        import types
        from types import SimpleNamespace

        mode, token_key = sys.argv[1:]
        calls, client_options = [], []
        modules = {name: types.ModuleType(name) for name in (
            "lmbase", "lmbase.inference", "lmbase.inference.base",
            "lmbase.inference.api_call", "dotenv")}
        sys.modules.update(modules)
        modules["dotenv"].load_dotenv = lambda *a, **k: None

        class Container:
            def __init__(self, **kwargs): self.__dict__.update(kwargs)

        for name in ("InferInput", "InferCost", "InferOutput"):
            cls = type(name, (Container,), {})
            setattr(modules["lmbase.inference.base"], name, cls)
            setattr(modules["lmbase.inference"], name, cls)

        class Client:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            def with_options(self, **kwargs):
                client_options.append(kwargs)
                return self
            def create(self, **params):
                assert params["response_format"] == {"type": "json_object"}
                # Match the provider's JSON-mode precondition for both roles.
                assert any("json" in m["content"].lower() for m in params["messages"])
                calls.append(params)
                response = SimpleNamespace(
                    usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
                    choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                        content='{"approved":true,"issues":[]}'))])
                response.model_dump = lambda **kw: {"choices": []}
                return response

        class Inference:
            def __init__(self, lm_name, generation_config):
                self.client = Client()
                self.model_name = lm_name.split("/", 1)[1]
                self.generation_config = generation_config
                self.max_tokens = 99999
            def execute(self, item):
                return self._inference([
                    {"role": "system", "content": item.system_msg},
                    {"role": "user", "content": item.user_msg}])

        if mode == "batch":
            def run(self, infer_inputs):
                return SimpleNamespace(outputs=[self.execute(x) for x in infer_inputs])
        else:
            def run(self, infer_input): return self.execute(infer_input)
        Inference.run = run
        modules["lmbase.inference.api_call"].LangChainAPIInference = Inference

        from finmy.runner.event_enrichment import (
            _live_completion, _completion_value, PROPOSAL_PROMPT, REVIEW_PROMPT)
        config = {"builder_config": {"lm_name": "deepseek/deepseek-chat",
                  "generation_config": {token_key: 16384, "temperature": 0.2}},
                  "event_followup": {"max_output_tokens": 8192,
                                     "request_timeout_seconds": 31}}
        complete = _live_completion(config)
        payload = {"event": {"event_id": "E1"},
                   "content": 'Literal {Query}, unmatched {, 中文 {"amount":123}'}
        for prompt in (PROPOSAL_PROMPT, REVIEW_PROMPT):
            record = {}
            result = complete(prompt, payload)
            assert json.loads(_completion_value(result, record))["approved"] is True
            assert record["finish_reason"] == "stop"
            assert calls[-1]["messages"] == [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        assert len(calls) == 2
        assert client_options == [{"max_retries": 0, "timeout": 31}]
        effective = "max_completion_tokens" if token_key == "max_completion_tokens" else "max_tokens"
        assert all(c[effective] == 8192 for c in calls)
        assert all("max_new_tokens" not in c for c in calls)
        if effective == "max_completion_tokens":
            assert all("max_tokens" not in c for c in calls)
        assert config["builder_config"]["generation_config"][token_key] == 16384
        print("request-contract-ok")
    ''')
    result = subprocess.run([sys.executable, "-c", program, api_style, token_key],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "request-contract-ok" in result.stdout


class BadRequestError(Exception):
    status_code = 400
    request_id = "request-123"
    code = "invalid_request_error"

    def __init__(self):
        # SDK str(exception) can contain whole request/response representations.
        super().__init__("RAW REQUEST MUST NOT BE LOGGED")
        self.body = {"error": {
            "code": "invalid_request_error",
            "message": "The messages must contain json for response_format=json_object.",
        }, "request": {"messages": ["PRIVATE SOURCE TEXT"]}}


def test_review_api_failure_is_auditable_without_accepting_candidate(tmp_path):
    package = json.loads((Path(__file__).parent / "fixtures/buffett_person_epg_preview.json").read_text())
    eid = package["event"][0]["event_id"]
    aid = next(row["activity_id"] for row in package["event_activity"] if row["event_id"] == eid)
    source = {"document_id": "EF_NEW", "event_ids": [eid],
              "content": "A separately documented meeting considered project ZX-17."}
    proposal = empty_additions()
    proposal["details"] = [{"activity_id": aid, "value": source["content"],
                            "citations": [{"document_id": "EF_NEW", "quote": source["content"]}]}]

    def complete(system, payload):
        if "proposal" in payload:
            raise BadRequestError()
        return json.dumps(proposal)

    config = {"builder_config": {"reconstruction": {"mode": "person", "subject": {
        "subject_id": "buffett", "name": "Warren Buffett", "coverage_start": "2022",
        "coverage_end": "2023"}}}, "event_followup": {"max_model_calls": 2}}
    candidate, report = enrich_events(package, [source], config, tmp_path, completion=complete)
    assert candidate == package
    assert report["model_calls"] == 2
    event = report["events"][0]
    ledger = json.loads((tmp_path / "CallLedger.json").read_text())
    for record in (event, ledger[1]):
        assert record["status"] == "failed"
        assert record["error_type"] == "BadRequestError"
        assert record["status_code"] == 400
        assert record["request_id"] == "request-123"
        assert record["error_code"] == "invalid_request_error"
        assert "must contain json" in record["error_message"]
        assert "RAW REQUEST" not in json.dumps(record)
        assert "PRIVATE SOURCE" not in json.dumps(record)
    assert not (tmp_path / "checkpoint_person_epg.json").exists()


def test_provider_diagnostics_redact_credentials_urls_and_request_payload(monkeypatch):
    monkeypatch.setenv("CUSTOM_PROVIDER_API_KEY", "custom-secret-value")
    error = BadRequestError()
    error.body["error"]["message"] = (
        "Invalid parameter custom-secret-value; Authorization: Bearer bearer-secret; "
        "api_key=another-secret; sk-secret-token; "
        "https://example.test/path?token=url-secret; messages=[PRIVATE_PAYLOAD]")
    result = _failure_details(error)
    text = json.dumps(result)
    for secret in ("custom-secret-value", "bearer-secret", "another-secret", "sk-secret-token",
                   "url-secret", "PRIVATE_PAYLOAD"):
        assert secret not in text
    assert "Invalid parameter" in result["error_message"]
    assert len(result["error_message"]) <= 400


def test_unstructured_error_does_not_dump_exception_or_body():
    error = RuntimeError("sensitive local input and whole request")
    error.body = "unstructured sensitive response"
    assert _failure_details(error) == {"error_type": "RuntimeError"}
