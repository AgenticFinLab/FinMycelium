"""Offline conversion, validation and HTML rendering of Person EPG JSON."""

import argparse
import json
from pathlib import Path

from .validation import validate_person_epg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("convert", "validate", "export-legacy", "render"):
        sub = commands.add_parser(command)
        sub.add_argument("input", type=Path)
        if command != "validate":
            sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        if args.command == "validate":
            report = validate_person_epg(data)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["valid"] else 1
        if args.command == "render":
            from .visualizer import render_person_epg

            render_person_epg(data, args.output)
            print(args.output)
            return 0
        from .adapter import from_subject_graph, to_subject_graph

        converter = (
            from_subject_graph if args.command == "convert" else to_subject_graph
        )
        output = converter(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(args.output)
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
