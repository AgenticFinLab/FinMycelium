"""Single-call transport for the original AgentEventBuilder; no prompt changes."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.builder.sparse_build.inference import SparseAPIInference
from finmy.builder.sparse_build.runtime import (
    code_identity, digest, summarize_calls, validate_config, validate_input,
)


def validated_config(config):
    """Validate original-builder settings using the shared backend contract."""
    allowed = {"builder_type", "agents", "lm_type", "lm_name", "generation_config",
               "save_folder", "graph_config", "build_only_config"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("Unknown AgentEventBuilder config option")
    if config.get("builder_type") != "AgentEventBuilder":
        raise ValueError("Expected AgentEventBuilder")
    options = config.get("build_only_config", {})
    if not isinstance(options, dict) or set(options) - {"max_calls", "request_timeout_seconds"}:
        raise ValueError("build_only_config accepts max_calls and request_timeout_seconds only")
    graph = config.get("graph_config")
    if not isinstance(graph, dict) or set(graph) != {"recursion_limit"} or \
            type(graph["recursion_limit"]) is not int or graph["recursion_limit"] < 1:
        raise ValueError("graph_config requires a positive integer recursion_limit")
    normalized = deepcopy(config)
    normalized["sparse_builder_config"] = {
        "max_calls": options.get("max_calls", 40),
        "request_timeout_seconds": options.get("request_timeout_seconds", 900),
    }
    validate_config(normalized)
    for settings in config["agents"].values():
        if set(settings) - {"lm_type", "lm_name", "generation_config"}:
            raise ValueError("Unsupported per-role setting; use the shared model configuration")
    return normalized


def artifact_hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(directory).glob("*.json"))
            if p.name not in {"RunManifest.json", "GanttStatus.json"}}


class _SingleCallTransport(SparseAPIInference):
    def __init__(self, owner):
        self.owner = owner
        config = owner.build_config
        super().__init__(config["lm_name"], config["generation_config"],
                         timeout=owner.options["request_timeout_seconds"])

    def run(self, infer_input, **kwargs):
        owner = self.owner
        if len(owner.calls) >= owner.options["max_calls"]:
            raise RuntimeError("Request cap reached; no retry or implicit resume")
        # The original builder supplies escaped system text and a user template.
        # Format exactly once, including when evidence itself contains braces.
        messages = self._create_messages(infer_input, **kwargs)
        index = len(owner.calls) + 1
        record = {"index": index, "agent": owner.current_role, "attempt": 1,
                  "status": "pending", "prompt_tokens": None, "completion_tokens": None,
                  "reasoning_tokens": None, "cached_tokens": None, "elapsed_seconds": None}
        owner.save_traces(messages, f"request-{index:03d}", "json")
        owner.calls.append(record)
        owner.save_traces(owner.calls, "CallLedger", "json")
        started = time.perf_counter()
        try:
            output = self._inference(messages)
            owner.save_traces(output.to_dict(), f"response-{index:03d}", "json")
            record.update(status="response_received", prompt_tokens=output.cost.prompt_tokens,
                          completion_tokens=output.cost.completion_tokens,
                          reasoning_tokens=output.extras.get("reasoning_tokens"),
                          cached_tokens=output.extras.get("cached_tokens"),
                          finish_reason=output.extras.get("finish_reason"))
            if output.extras.get("finish_reason") != "stop" or output.extras.get("refusal") or \
                    output.extras.get("tool_calls") or not output.response.strip():
                raise ValueError("Incomplete or non-text response; no retry")
            return output
        except BaseException as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            record["elapsed_seconds"] = time.perf_counter() - started
            owner.save_traces(owner.calls, "CallLedger", "json")


class BuildOnlyAgentEventBuilder(AgentEventBuilder):
    """Opt-in adapter. Original graph, prompts, parsing and assembly are inherited."""

    def __init__(self, build_config):
        normalized = validated_config(build_config)
        self.options = normalized["sparse_builder_config"]
        self.calls = []
        self.current_role = None
        self._run_started = False
        super().__init__(build_config=deepcopy(build_config))

    def define_agent_models(self):
        self.agents_lm = _SingleCallTransport(self)

    def execute_agent(self, state, agent_name):
        self.current_role = agent_name
        return super().execute_agent(state, agent_name)

    def run(self, build_input):
        validate_input(build_input)
        if self._run_started:
            raise RuntimeError("Create a new builder for each run; implicit resume is not supported")
        self._run_started = True
        inputs = {"user_query": asdict(build_input.user_query),
                  "samples": [asdict(sample) for sample in build_input.samples]}
        config = deepcopy(self.build_config)
        config["build_only_config"] = self.options
        identity = code_identity()
        root = Path(__file__).resolve().parents[2]
        sources = list((root / "finmy/builder/agent_build").glob("*.py")) + [
            Path(__file__), root / "finmy/builder/base.py",
            root / "finmy/runner/build_only_runner.py", root / "finmy/runner/sparse_build_runner.py",
        ]
        identity["source_sha256"].update({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sources})
        manifest = {"status": "running", "builder_type": "AgentEventBuilder",
                    "quality_review": "required", "input_sha256": digest(inputs),
                    "effective_config": config, "config_sha256": digest(config), "code": identity,
                    "prompt_sha256": digest(self._get_agent_prompts())}
        self.save_traces(inputs, "BuildInput", "json")
        self.save_traces(manifest, "RunManifest", "json")
        started = time.perf_counter()
        try:
            output = super().run(build_input)
            manifest.update(status="completed", event_id=output.event_cascades["event_id"])
            return output
        except BaseException as exc:
            manifest.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            manifest.update(elapsed_seconds=time.perf_counter() - started,
                            usage=summarize_calls(self.calls), artifact_sha256=artifact_hashes(self.save_dir))
            self.save_traces(manifest, "RunManifest", "json")


def replay_original(directory):
    """Verify a completed local run and reassemble it without creating a client."""
    directory = Path(directory)
    manifest = json.loads((directory / "RunManifest.json").read_text(encoding="utf-8"))
    if manifest.get("builder_type") != "AgentEventBuilder" or manifest.get("status") != "completed":
        raise ValueError("Replay requires a completed AgentEventBuilder run")
    hashes = manifest.get("artifact_sha256", {})
    if not {"BuildInput.json", "FinalEventCascade.json", "CallLedger.json"} <= hashes.keys():
        raise ValueError("Incomplete run manifest")
    if any(p.is_symlink() for p in directory.glob("*.json")) or artifact_hashes(directory) != hashes:
        raise ValueError("Run artifacts changed or incomplete")
    builder = AgentEventBuilder.__new__(AgentEventBuilder)
    builder.save_dir = str(directory)
    return builder.integrate_from_files()
