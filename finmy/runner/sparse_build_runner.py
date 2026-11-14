"""Preflight or explicitly execute reconstruction from local source text."""

import argparse
import json
import os
from pathlib import Path
import sys

import yaml

from finmy.model_config import api_key_variable, model_name
from finmy.builder.base import BuildInput
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.runtime import digest, validate_config, validate_input
from finmy.generic import DataSample, UserQueryInput


def load_inputs(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"user_query", "samples"}:
        raise ValueError("Input must contain exactly user_query and samples")
    result = BuildInput(UserQueryInput(**payload["user_query"]),
                        [DataSample(**sample) for sample in payload["samples"]])
    validate_input(result)
    return result, digest(payload)


def preflight(config, build_input):
    validate_config(config)
    validate_input(build_input)
    provider = model_name(config["lm_name"]).split("/", 1)[0]
    target = Path(config["save_folder"]).resolve()
    parent = target
    while not parent.exists():
        parent = parent.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ValueError("Output directory is not writable")
    return {"status": "offline_preflight_pass", "model": config["lm_name"],
            "credential_present": bool(os.environ.get(api_key_variable(provider))),
            "online_compatibility_verified": False, "sample_count": len(build_input.samples),
            "source_characters": sum(len(s.content) for s in build_input.samples),
            "output_root": str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/sparse_pipeline.yml")
    parser.add_argument("--input", help="JSON containing user_query and samples")
    parser.add_argument("--env-file", help="Optional local dotenv file; values are never printed")
    parser.add_argument("--execute", action="store_true", help="Allow real model calls")
    parser.add_argument("--gantt", action="store_true", help="Save an optional HTML visualization after construction")
    parser.add_argument("--replay", help="Strict offline assembly of a completed run directory")
    args = parser.parse_args(argv)
    if args.replay:
        if args.execute or args.input or args.env_file or args.gantt:
            parser.error("--replay cannot be combined with execution or input options")
        builder = SparseRagBuilder.__new__(SparseRagBuilder)
        builder.save_dir = str(Path(args.replay).resolve())
        builder.build_config = {}
        cascade = builder.integrate_from_files(strict=True)
        saved = json.loads((Path(args.replay) / "FinalEventCascade.json").read_text(encoding="utf-8"))
        if cascade != saved:
            raise ValueError("Replayed graph does not match FinalEventCascade.json")
        print(json.dumps({"status": "replay_pass", "event_id": cascade["event_id"], "graph_sha256": digest(cascade)}))
        return 0
    if not args.input:
        parser.error("--input is required unless --replay is used")
    if args.env_file:
        from dotenv import load_dotenv
        if not Path(args.env_file).is_file():
            raise ValueError("Requested dotenv file does not exist")
        load_dotenv(args.env_file, override=False)
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["builder_config"]
    if config.get("builder_type") != "SparseRagBuilder":
        raise ValueError("This entry only accepts SparseRagBuilder")
    build_input, input_hash = load_inputs(args.input)
    report = preflight(config, build_input)
    report["input_sha256"] = input_hash
    print(json.dumps(report, ensure_ascii=False))
    if not args.execute:
        return 0
    if not report["credential_present"]:
        raise ValueError("The configured provider API key is missing")
    builder = SparseRagBuilder(build_config=config)
    output = builder.run(build_input)
    if args.gantt:
        render = {"status": "completed"}
        try:
            from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
            EventCascadeGanttVisualizer().plot_cascade(
                output.event_cascades, output_path=str(Path(builder.save_dir) / "gantt.html"))
        except Exception as exc:
            render = {"status": "failed", "error_type": type(exc).__name__}
        builder.save_traces(render, "GanttStatus", "json")
    print(json.dumps({"status": "completed", "run_directory": builder.save_dir}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Provider exceptions can contain request URLs/headers; keep raw errors out of console logs.
        print(f"Sparse build failed ({type(exc).__name__}); inspect local run status and inputs.", file=sys.stderr)
        sys.exit(1)
