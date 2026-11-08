"""Build an EPG from prepared local text, without search or a database."""

import argparse
import copy
import json
from pathlib import Path
import sys

import yaml

from finmy.builder.agent_build_adapter import BuildOnlyAgentEventBuilder, replay_original, validated_config
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.runtime import digest
from finmy.runner.sparse_build_runner import load_inputs, preflight


def select_builder(config):
    if not isinstance(config, dict):
        raise ValueError("builder_config must be an object")
    config = copy.deepcopy(config)
    kind = config.setdefault("builder_type", "SparseRagBuilder")
    if kind == "AgentEventBuilder":
        return BuildOnlyAgentEventBuilder, validated_config(config)
    if kind == "SparseRagBuilder":
        if "build_only_config" in config:
            raise ValueError("Use sparse_builder_config for SparseRagBuilder limits")
        return SparseRagBuilder, config
    raise ValueError("builder_type must be AgentEventBuilder or SparseRagBuilder")


def replay(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "RunManifest.json").read_text(encoding="utf-8"))
    kind = manifest.get("builder_type", "SparseRagBuilder")
    if kind == "AgentEventBuilder":
        cascade = replay_original(directory)
    elif kind == "SparseRagBuilder":
        builder = SparseRagBuilder.__new__(SparseRagBuilder)
        builder.save_dir = str(directory)
        builder.build_config = {}
        cascade = builder.integrate_from_files(strict=True)
        if manifest.get("effective_config", {}).get("reconstruction", {}).get("mode") == "person":
            builder.integrate_person_from_files(strict=True)
    else:
        raise ValueError("Unsupported recorded builder_type")
    if cascade != json.loads((directory / "FinalEventCascade.json").read_text(encoding="utf-8")):
        raise ValueError("Replayed graph does not match FinalEventCascade.json")
    return {"status": "replay_pass", "builder_type": kind,
            "event_id": cascade["event_id"], "graph_sha256": digest(cascade)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/build_only_sparse.yml")
    parser.add_argument("--input", help="JSON containing user_query and samples")
    parser.add_argument("--env-file", help="Optional local dotenv file; never printed")
    parser.add_argument("--execute", action="store_true", help="Allow real model calls")
    parser.add_argument("--gantt", action="store_true", help="Render HTML after a successful build")
    parser.add_argument("--replay", help="Verify and reassemble a completed run offline")
    args = parser.parse_args(argv)
    if args.replay:
        if args.execute or args.input or args.env_file or args.gantt:
            parser.error("--replay cannot be combined with execution or input options")
        print(json.dumps(replay(args.replay)))
        return 0
    if not args.input:
        parser.error("--input is required unless --replay is used")
    if args.env_file:
        from dotenv import load_dotenv
        if not Path(args.env_file).is_file():
            raise ValueError("Requested dotenv file does not exist")
        load_dotenv(args.env_file, override=False)
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["builder_config"]
    config.setdefault("builder_type", "SparseRagBuilder")
    builder_class, checked_config = select_builder(config)
    build_input, input_hash = load_inputs(args.input)
    report = preflight(checked_config, build_input)
    report.update(builder_type=config["builder_type"], input_sha256=input_hash)
    print(json.dumps(report, ensure_ascii=False))
    if not args.execute:
        return 0
    if not report["credential_present"]:
        raise ValueError("The configured provider API key is missing")
    builder = builder_class(build_config=config)
    output = builder.run(build_input)
    if args.gantt:
        render = {"status": "completed"}
        try:
            person = (getattr(output, "extras", None) or {}).get("person_epg")
            if person is not None:
                from finmy.person_epg.visualizer import render_person_epg
                render_person_epg(person, Path(builder.save_dir) / "gantt.html")
            elif output.subject_graph is not None:
                from finmy.subject_graph.visualizer import render_subject_graph
                render_subject_graph(output.subject_graph, Path(builder.save_dir) / "gantt.html")
            else:
                from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
                EventCascadeGanttVisualizer().plot_cascade(
                    output.event_cascades, output_path=str(Path(builder.save_dir) / "gantt.html"))
        except Exception as exc:
            render = {"status": "failed", "error_type": type(exc).__name__}
        builder.save_traces(render, "GanttStatus", "json")
    print(json.dumps({"status": "completed", "builder_type": config["builder_type"],
                      "run_directory": builder.save_dir}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Build failed ({type(exc).__name__}); inspect local run status and inputs.", file=sys.stderr)
        sys.exit(1)
