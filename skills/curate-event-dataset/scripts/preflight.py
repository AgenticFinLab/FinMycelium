"""Read-only inventory and interface probes; never certifies event truth."""
import argparse
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone


def file_info(path):
    if not path.is_file():
        return {"exists": False}
    raw = path.read_bytes()
    return {"exists": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def version(root):
    result = {}
    for key, args in [("head", ["rev-parse", "HEAD"]), ("status", ["status", "--short"])]:
        try:
            run = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=30)
            result[key] = run.stdout.strip() if run.returncode == 0 else run.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            result[key] = str(exc)
    return result


def load_domain(root):
    spec = importlib.util.spec_from_file_location("curation_preflight_domain", root / "finmy/workbench/domain.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe(call):
    try:
        value = call()
        return {"result": "pass", "rows": len(value)}
    except Exception as exc:
        return {"result": "blocked", "error": f"{type(exc).__name__}: {exc}"}


def inspect(finmy, dataset, mode):
    files = ["event-epg/master-table-spec.md",
             "event-epg/events.template.csv", "event-epg/events.csv", "event-epg/sources.csv",
             "event-epg/event-sources.csv", "event-epg/curation-decisions.csv",
             "event-epg/research/checkpoint.json", "event-epg/README.md",
             "event-epg/research-plan.md", "event-epg/quality-report.md", "scripts/curate_events.py",
             "scripts/export_event_workbench.py"]
    code = ["finmy/workbench/domain.py", "finmy/workbench/store.py", "finmy/dataset.py",
            "finmy/workbench/dataset_page.py", "finmy/workbench/search_bridge.py"]
    result = {"executed_at_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "python": platform.python_version(), "finmy_root": str(finmy), "dataset_root": str(dataset),
              "versions": {"finmy": version(finmy), "dataset": version(dataset)},
              "dataset_files": {n: file_info(dataset / n) for n in files},
              "interface_code": {n: file_info(finmy / n) for n in code},
              "limitation": "Inventory and executable parsing probes only. No web research, semantic truth review, deduplication verdict, formal-file change or Workbench database write."}
    result["original_inputs"] = {
        "status": "retired_by_user",
        "required": False,
        "note": "Original working table, legacy registry and graph manifest were deleted intentionally. Do not restore, read or rehash them; use the current catalog and retained audit records."}
    checkpoint = dataset / "event-epg/research/checkpoint.json"
    if checkpoint.is_file():
        q = json.loads(checkpoint.read_text(encoding="utf-8-sig"))
        checked, mismatches = 0, []
        for n, expected in q.get("output_sha256", {}).items():
            path = (dataset / "event-epg" / n).resolve()
            if not path.is_relative_to((dataset / "event-epg").resolve()):
                mismatches.append({"path": n, "error": "checkpoint path escapes catalog"})
                continue
            actual = file_info(path).get("sha256")
            checked += 1
            if actual != expected:
                mismatches.append({"path": n, "expected": expected, "actual": actual})
        result["checkpoint"] = {"recorded_complete": q.get("complete"), "hashes_checked": checked,
                                "mismatches": mismatches, "note": "Recorded completion is historical, not a new audit."}
    master = dataset / "event-epg/events.csv"
    if master.is_file() and (finmy / "finmy/workbench/domain.py").is_file():
        raw = master.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        rows = list(reader)
        fields = reader.fieldnames or []
        domain = load_domain(finmy)
        result["master"] = {"rows": len(rows), "fields": fields, "bytes": len(raw),
                            "duplicate_ids": len(rows) - len({r.get("event_id") for r in rows}),
                            "catalog_columns_to_omit_for_upload": [k for k in fields if k not in domain.FIELDS]}
        def business_rows():
            if len(fields) != len(set(fields)) or any(None in r or any(v is None for v in r.values()) for r in rows):
                raise ValueError("Malformed CSV header or row")
            missing = set(domain.FIELDS) - set(fields)
            if missing:
                raise ValueError("Missing business fields: " + ", ".join(sorted(missing)))
            return [domain.event_record({k: r[k] for k in domain.FIELDS}) for r in rows]
        result["business_row_parser"] = probe(business_rows)
        result["whole_file_upload"] = probe(lambda: domain.read_table(
            raw, master.name, {k: k if k in domain.FIELDS else None for k in fields}))
        # Separate process prevents loading checkout modules from an earlier sys.path.
        query = ("import json,sys;from finmy.dataset import DatasetCatalog;"
                 "c=DatasetCatalog(sys.argv[1]);r=c.events();"
                 "s=c.select(r[0]['event_id']) if r else None;"
                 "print(json.dumps({'rows':len(r),'first_selection_checked':bool(s)}))")
        try:
            run = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", query, str(dataset)], cwd=finmy,
                                 capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            result["native_catalog"] = ({"result": "pass", **json.loads(run.stdout)} if run.returncode == 0
                                         else {"result": "blocked", "error": run.stderr.strip()[-2400:]})
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result["native_catalog"] = {"result": "blocked", "error": str(exc)}
        # Inventory source-level requirements even if the file-size gate fails first.
        import ast
        catalog_code = finmy / "finmy/dataset.py"
        tree = ast.parse(catalog_code.read_text(encoding="utf-8") if catalog_code.is_file() else "")
        literals = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "events":
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "required" for t in child.targets):
                        try:
                            value = ast.literal_eval(child.value)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(value, list) and all(isinstance(v, str) for v in value):
                            literals.extend(value)
        result["native_required_literal_columns_missing"] = sorted(set(literals) - set(fields))
        result["native_requirements_note"] = "Source-level literal assignment inventory only; actual call above is authoritative. Conditional or computed requirements may need code inspection."
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finmy-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--mode", choices=["resume", "rebuild", "review"], default="resume")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    finmy, dataset = args.finmy_root.resolve(), args.dataset_root.resolve()
    if not finmy.is_dir() or not dataset.is_dir():
        parser.error("Both repository roots must exist")
    if args.output:
        out = args.output.resolve()
        allowed = (dataset / "output").resolve()
        if not out.is_relative_to(allowed) or out == allowed:
            parser.error("Report output must be under EPG-dataset/output/")
    result = inspect(finmy, dataset, args.mode)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Preflight report: {out}; inventory only, inspect blockers before continuing.")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
