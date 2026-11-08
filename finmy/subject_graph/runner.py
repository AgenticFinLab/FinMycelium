"""Build native subject graphs from saved text, without collecting/searching again."""
import argparse
import copy
import json
from pathlib import Path

from finmy.reconstruction_scope import read_reconstruction


SPARSE_ROLES = (
    "SkeletonReconstructor", "SkeletonChecker", "ParticipantReconstructor",
    "TransactionReconstructor", "EpisodeReconstructor",
    "StageDescriptionReconstructor", "EventDescriptionReconstructor",
)


def subject_builder_config(config):
    """Select the person default without mutating the caller's configuration.

    Explicit builder choices and explicit role settings remain authoritative.
    Older pipeline YAML put role settings beside a null ``agents`` key; only
    that unambiguous shape is normalized here.
    """
    build_config = copy.deepcopy(config.get("builder_config", config))
    scope = read_reconstruction(build_config)
    default = "AgentEventBuilder" if scope["mode"] == "company" else "SparseRagBuilder"
    build_config.setdefault("builder_type", default)
    if build_config["builder_type"] == "SparseRagBuilder" and build_config.get("agents") is None:
        build_config["agents"] = {
            role: build_config.pop(role, {}) for role in SPARSE_ROLES
        }
    return build_config


def build_from_contents(contents, query, keywords, config):
    """Return (BuildOutput, output_directory); dependencies load only for live build."""
    if read_reconstruction(config)["mode"] == "event":
        raise ValueError("This entry point requires person or company mode")
    if not isinstance(contents, list) or not contents or any(
        not isinstance(text, str) or not text.strip() for text in contents
    ):
        raise ValueError("Saved contents must be a nonempty list of nonempty strings")
    from finmy.generic import UserQueryInput, DataSample
    from finmy.builder.base import BuildInput
    build_config = subject_builder_config(config)
    if build_config["builder_type"] == "SparseRagBuilder":
        from finmy.builder.sparse_build.main_build import SparseRagBuilder
        builder_class = SparseRagBuilder
    else:
        from finmy.builder.agent_build.main_build import AgentEventBuilder
        builder_class = AgentEventBuilder
    user_query = UserQueryInput(query_text=query, key_words=keywords or [])
    samples = [DataSample(sample_id=f"saved_{i}", raw_data_id=f"saved_{i}", content=text)
               for i, text in enumerate(contents)]
    builder = builder_class(build_config=build_config)
    return builder.run(BuildInput(user_query=user_query, samples=samples)), builder.save_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Full pipeline YAML config")
    parser.add_argument("--scope-config", help="YAML overlay containing builder_config.reconstruction")
    parser.add_argument("--input", help="Saved builder_input_contents.json")
    parser.add_argument("--query", default="Reconstruct the subject's documented history within the configured period.")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--output-dir", help="New build parent directory, or render output directory")
    parser.add_argument("--render-only", help="Existing FinalSubjectGraph.json; no model or network needed")
    args = parser.parse_args(argv)
    if args.render_only:
        from finmy.subject_graph.validation import validate_subject_graph
        from finmy.subject_graph.visualizer import render_subject_graph
        path = Path(args.render_only)
        graph = json.loads(path.read_text(encoding="utf-8"))
        report = validate_subject_graph(graph)
        if not report["valid"]:
            parser.error("Invalid SubjectGraph: " + json.dumps(report["errors"], ensure_ascii=False))
        destination = Path(args.output_dir) if args.output_dir else path.parent
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / "FinalSubjectGraph.html"
        if target.exists():
            parser.error(f"Output exists; select a new --output-dir: {target}")
        render_subject_graph(graph, target)
        print(target)
        return
    if not args.config or not args.input:
        parser.error("--config and --input are required for model reconstruction")
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.scope_config:
        overlay = yaml.safe_load(Path(args.scope_config).read_text(encoding="utf-8"))
        config["builder_config"]["reconstruction"] = overlay["builder_config"]["reconstruction"]
    if args.output_dir:
        config["builder_config"]["save_folder"] = args.output_dir
    contents = json.loads(Path(args.input).read_text(encoding="utf-8"))
    _, output = build_from_contents(contents, args.query,
                                    [k.strip() for k in args.keywords.split(",") if k.strip()], config)
    print(output)


if __name__ == "__main__":
    main()
