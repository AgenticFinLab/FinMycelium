"""Build a new person HTML from saved sources/facts, without running search."""

import argparse
import json
from pathlib import Path
import sys

import yaml

from finmy.builder.sparse_build.person_recovery import (
    config_from_checkpoint, load_person_checkpoint, recover_person,
)
from finmy.runner.sparse_build_runner import preflight


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True,
                        help="Saved completed/failed person run with facts or completed episode extraction")
    parser.add_argument("--config", default="configs/person_sparse.yml",
                        help="Agent/location defaults; the saved subject, sources and model settings are retained")
    parser.add_argument("--output-root", help="New output parent outside the original run")
    parser.add_argument("--env-file", help="Optional dotenv file; values are never printed")
    parser.add_argument("--max-new-calls", type=int,
                        help="Model-call limit for this invocation; historical calls are recorded separately")
    parser.add_argument("--reorganize", action="store_true",
                        help="Rebuild organization even if compatible organization replies were saved")
    parser.add_argument("--execute", action="store_true",
                        help="Run remaining fact normalization and organization calls; never searches again")
    args = parser.parse_args(argv)
    checkpoint = load_person_checkpoint(args.source_run)
    defaults = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    config = config_from_checkpoint(checkpoint, defaults, args.output_root, args.max_new_calls)
    if args.env_file:
        from dotenv import load_dotenv
        if not Path(args.env_file).is_file():
            raise ValueError("Requested dotenv file does not exist")
        load_dotenv(args.env_file, override=False)
    report = preflight(config, checkpoint.build_input)
    from finmy.builder.sparse_build.runtime import sparse_options
    canonical = checkpoint.canonical_checkpoint or {}
    report.update(mode=checkpoint.mode, input_sha256=checkpoint.manifest["input_sha256"],
                  prior_calls=len(checkpoint.historical_calls), search_calls=0,
                  facts_reused=checkpoint.fact_seed is not None,
                  canonical_phase_reused=(canonical.get("audit", {}).get("status") == "completed"
                                          and canonical.get("audit", {}).get("phase") == "completed"),
                  budget_scope="new_invocation", max_new_calls=sparse_options(config).get("max_calls", 300))
    print(json.dumps(report, ensure_ascii=False))
    if not args.execute:
        return 0
    if not report["credential_present"]:
        raise ValueError("The configured provider API key is missing")
    output = recover_person(config, args.source_run, reorganize=args.reorganize)
    root = Path(output.extras["run_directory"])
    html = root / "FinalPersonEPG.html"
    print(json.dumps({"status": "completed", "run_directory": str(root),
                      "html": str(html) if html.is_file() else None,
                      "new_calls": output.extras["usage"]["calls"], "search_calls": 0,
                      "organization_status": output.extras.get("person_acceptance", {}).get("status"),
                      "compat_projection": output.extras.get("compat_projection", {})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        message = {"status": "failed", "error_type": type(exc).__name__, "message": str(exc)}
        if getattr(exc, "run_directory", None):
            message["run_directory"] = exc.run_directory
            message["run_status"] = str(Path(exc.run_directory) / "RunManifest.json")
        print(json.dumps(message, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
