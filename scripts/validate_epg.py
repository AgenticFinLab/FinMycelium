"""Validate an existing EventCascade JSON without a model or search request."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finmy.builder.agent_build.validation import validate_event_cascade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Existing FinalEventCascade.json")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Separate directory for validated output and report")
    parser.add_argument("--no-deduplicate", action="store_true",
                        help="Only report problems; preserve all transactions")
    args = parser.parse_args()
    source = args.input.resolve()
    targets = [args.output_dir / name for name in
               ("FinalEventCascade.json", "epg_validation_report.json")]
    for target in targets:
        if target.resolve() == source or target.exists():
            parser.error(f"Refusing to overwrite {target}; choose a new output directory")
    with source.open(encoding="utf-8") as handle:
        original = json.load(handle)
    corrected, report = validate_event_cascade(
        original, deduplicate=not args.no_deduplicate
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for target, value in zip(targets, (corrected, report)):
        with target.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Output: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
