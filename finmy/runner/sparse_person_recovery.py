"""Preflight or recover person organization from a verified failed extraction run."""

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
    parser.add_argument("--source-run", required=True, help="Failed person run with a complete FinalEventCascade")
    parser.add_argument("--config", default="configs/person_sparse.yml",
                        help="Defaults for agents/save_folder only; recorded subject and settings are retained")
    parser.add_argument("--output-root", help="New output parent outside the original run")
    parser.add_argument("--env-file", help="Optional local dotenv file; values are never printed")
    parser.add_argument("--execute", action="store_true", help="Allow new person organization model calls")
    args = parser.parse_args(argv)
    checkpoint = load_person_checkpoint(args.source_run)
    defaults = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    config = config_from_checkpoint(checkpoint, defaults, args.output_root)
    if args.env_file:
        from dotenv import load_dotenv
        if not Path(args.env_file).is_file():
            raise ValueError("Requested dotenv file does not exist")
        load_dotenv(args.env_file, override=False)
    report = preflight(config, checkpoint.build_input)
    historical_calls = len(checkpoint.historical_calls)
    from finmy.builder.sparse_build.runtime import sparse_options
    report.update(mode="person_organization_only", input_sha256=checkpoint.manifest["input_sha256"],
                  prior_calls=historical_calls,
                  remaining_calls=sparse_options(config).get("max_calls", 300) - historical_calls)
    print(json.dumps(report, ensure_ascii=False))
    if not args.execute:
        return 0
    if not report["credential_present"]:
        raise ValueError("The configured provider API key is missing")
    output = recover_person(config, args.source_run)
    print(json.dumps({"status": "completed", "run_directory": output.extras["run_directory"],
                      "new_calls": output.extras["usage"]["calls"]}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Person recovery failed ({type(exc).__name__}); inspect local checkpoints and run status.",
              file=sys.stderr)
        sys.exit(1)
