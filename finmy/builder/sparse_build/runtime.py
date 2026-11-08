"""Local run provenance and configuration checks for sparse reconstruction."""

from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import subprocess

from .prompts import get_agent_prompts
from finmy.reconstruction_scope import read_reconstruction, render_scope


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def validate_input(build_input):
    query = build_input.user_query
    if not isinstance(query.query_text, str) or not query.query_text.strip():
        raise ValueError("query_text must be nonempty text")
    if not isinstance(query.key_words, list) or any(not isinstance(k, str) for k in query.key_words):
        raise ValueError("key_words must be a list of strings")
    if not isinstance(build_input.samples, list) or not build_input.samples:
        raise ValueError("samples must be a nonempty list")
    seen = set()
    for sample in build_input.samples:
        if not isinstance(sample.sample_id, str) or not sample.sample_id.strip() or sample.sample_id in seen:
            raise ValueError("sample_id must be nonempty and unique")
        seen.add(sample.sample_id)
        if not isinstance(sample.raw_data_id, str) or not sample.raw_data_id.strip():
            raise ValueError("raw_data_id must be nonempty")
        if not isinstance(sample.content, str) or not sample.content.strip():
            raise ValueError("sample content must be nonempty text")


def sparse_options(config):
    """Use the same explicit-option precedence for validation, execution and replay."""
    options = config.get("sparse_builder_config", config.get("event_builder_config", {}))
    if not isinstance(options, dict):
        raise ValueError("sparse_builder_config must be an object")
    return options


def validate_config(config):
    read_reconstruction(config)
    roles = set(get_agent_prompts()[0])
    required = {"agents", "lm_type", "lm_name", "generation_config", "save_folder"}
    if not required <= config.keys():
        raise ValueError(f"Missing builder config keys: {sorted(required - config.keys())}")
    if config["lm_type"] != "api" or not isinstance(config["lm_name"], str) or "/" not in config["lm_name"]:
        raise ValueError("Use lm_type: api and lm_name: provider/model")
    if not isinstance(config["save_folder"], str) or not config["save_folder"].strip():
        raise ValueError("save_folder must be nonempty")
    if not isinstance(config["agents"], dict) or set(config["agents"]) != roles:
        raise ValueError("agents must contain exactly the seven sparse roles")
    generation = config["generation_config"]
    if not isinstance(generation, dict):
        raise ValueError("generation_config must be an object")
    caps = [key for key in ("max_new_tokens", "max_tokens", "max_completion_tokens") if key in generation]
    if len(caps) != 1 or type(generation[caps[0]]) is not int or generation[caps[0]] < 1:
        raise ValueError("Specify one positive integer output token limit")
    # A single backend is used throughout the graph; reject silently ignored overrides.
    for role, settings in config["agents"].items():
        if not isinstance(settings, dict):
            raise ValueError(f"{role}: expected settings object")
        for key in ("lm_type", "lm_name", "generation_config"):
            if key in settings and settings[key] != config[key]:
                raise ValueError(f"{role}: per-role {key} overrides are not supported")
    forbidden = {"model", "messages", "stream", "tools", "tool_choice", "functions", "n",
                 "api_key", "base_url", "extra_headers"}
    if generation.keys() & forbidden:
        raise ValueError("generation_config contains transport, tool, credential or multi-output overrides")
    supported = {"max_new_tokens", "max_tokens", "max_completion_tokens", "temperature", "top_p",
                 "presence_penalty", "frequency_penalty", "stop", "seed", "response_format",
                 "reasoning_effort", "verbosity", "extra_body"}
    if generation.keys() - supported:
        raise ValueError("Unsupported generation_config parameter")
    extra = generation.get("extra_body", {})
    if not isinstance(extra, dict) or set(extra) - {"thinking", "enable_thinking", "thinking_budget"}:
        raise ValueError("extra_body only supports provider thinking controls")
    options = sparse_options(config)
    allowed = {"enable_sparse_routing", "enable_context_assets", "max_calls", "context_top_k",
               "max_context_chars", "excerpt_char_limit", "max_card_tokens", "max_json_attempts",
               "request_timeout_seconds", "evidence_policy", "output_language"}
    if set(options) - allowed:
        raise ValueError("Unknown sparse_builder_config option")
    for key in ("enable_sparse_routing", "enable_context_assets"):
        if key in options and type(options[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    for key, default in (("max_calls", 300), ("context_top_k", 8), ("max_context_chars", 6000),
                         ("excerpt_char_limit", 240), ("max_card_tokens", 48)):
        value = options.get(key, default)
        if type(value) is not int or value < 1:
            raise ValueError(f"{key} must be a positive integer")
    attempts = options.get("max_json_attempts", 3)
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("max_json_attempts must be in [1, 3]")
    timeout = options.get("request_timeout_seconds", 900)
    if type(timeout) not in (int, float) or not 0 < timeout <= 3600:
        raise ValueError("request_timeout_seconds must be in (0, 3600]")
    if options.get("evidence_policy", "report") not in {"report", "strict"}:
        raise ValueError("evidence_policy must be report or strict")
    if not isinstance(options.get("output_language", "English"), str) or not options.get("output_language", "English").strip():
        raise ValueError("output_language must be nonempty")
    digest(config)  # Reject non-JSON values and NaN before any request.


def code_identity():
    root = Path(__file__).resolve().parents[3]
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    sources = (list(Path(__file__).parent.glob("*.py"))
               + list((root / "finmy/person_epg").glob("*.py"))
               + [root / "finmy/builder/agent_build/structure.py",
                  root / "finmy/reconstruction_scope.py",
                  root / "finmy/person_epg/schema.json",
                  root / "finmy/person_epg/schema_model.json"])
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sources if p.is_file()}
    from lmbase.inference.api_call import LangChainAPIInference
    adapter = Path(inspect.getfile(LangChainAPIInference))
    return {"git_commit": head, "worktree_dirty": dirty, "source_sha256": hashes,
            "lmbase_api_adapter_sha256": hashlib.sha256(adapter.read_bytes()).hexdigest()}


def run_identity(build_input, config):
    inputs = {"user_query": asdict(build_input.user_query), "samples": [asdict(s) for s in build_input.samples]}
    # Never serialize arbitrary config sections, environment variables or endpoints.
    safe_config = {key: config.get(key) for key in ("lm_type", "lm_name", "generation_config",
                                                  "sparse_builder_config", "event_builder_config")}
    reconstruction = read_reconstruction(config)
    safe_config["reconstruction"] = reconstruction
    prompts = get_agent_prompts()
    if reconstruction["mode"] == "person":
        from .person_organization import ORGANIZATION_SYSTEM_PROMPT
        prompts = {"event_roles": prompts, "scope": render_scope(config),
                   "person_guidance": PERSON_SCOPE_GUIDANCE,
                   "organization": ORGANIZATION_SYSTEM_PROMPT}
    return inputs, {"status": "running", "input_sha256": digest(inputs),
                    "effective_config": safe_config, "config_sha256": digest(safe_config),
                    "code": code_identity(), "prompt_sha256": digest(prompts)}


PERSON_SCOPE_GUIDANCE = (
    "Reconstruct the named person's documented involvement within the requested scope. "
    "Keep company actions assigned to the company, and personal actions to their actual actor. "
    "Each episode should identify one concrete occurrence, not a topic spanning unrelated scenes. "
    "Distinguish the date of a statement from the historical action it recalls. "
    "Stages here are extraction candidates; later organization determines personal stages. "
    "Do not change the supplied output fields or quote task metadata as evidence."
)


def summarize_calls(records):
    summary = {"calls": len(records), "retries": sum(r["attempt"] > 1 for r in records)}
    for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens"):
        values = [r.get(field) for r in records]
        summary[field] = sum(values) if all(v is not None for v in values) else None
        summary[f"known_{field}"] = sum(v for v in values if v is not None)
        summary[f"unknown_{field}_calls"] = sum(v is None for v in values)
    summary["by_role"] = {}
    for role in sorted({r["agent"] for r in records}):
        group = [r for r in records if r["agent"] == role]
        role_summary = {"calls": len(group), "seconds": sum(r.get("elapsed_seconds") or 0 for r in group),
                        "retries": sum(r["attempt"] > 1 for r in group)}
        for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens"):
            values = [r.get(field) for r in group]
            role_summary[field] = sum(values) if all(v is not None for v in values) else None
            role_summary[f"known_{field}"] = sum(v for v in values if v is not None)
            role_summary[f"unknown_{field}_calls"] = sum(v is None for v in values)
        summary["by_role"][role] = role_summary
    return summary
