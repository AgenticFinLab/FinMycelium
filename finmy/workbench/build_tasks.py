"""Persistent, explicitly started build-only tasks. No search or automatic approval."""
from contextlib import contextmanager
import fcntl
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import yaml

from finmy.search.control import task_lock, task_path
from finmy.search.state import write_json
from finmy.workbench.domain import digest, encoded, graph_from_bytes, validate_graph
from finmy.workbench.store import Store, identifier, now

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def worker_lock(root, task_id):
    # Starting holds this same lock until the queued row and PID are persisted.
    with (task_path(root, task_id) / ".writer.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def code_version():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True)
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((ROOT / "finmy").rglob("*.py"))}
    return {"commit": result.stdout.strip() if result.returncode == 0 else None,
            "python_sources_sha256": digest(files)}


def build_config(settings, directory):
    Store.validate_configuration(settings)
    kind = settings["builder"]
    filename = "build_only_sparse.yml" if kind == "SparseRagBuilder" else "build_only_agent.yml"
    config = yaml.safe_load((ROOT / "configs" / filename).read_text())["builder_config"]
    config["lm_name"] = "ark/" + settings["model"]
    config["save_folder"] = str(Path(directory).resolve() / "output")
    return config


class BuildController:
    def __init__(self, store):
        self.store = store
        self.root = store.root / "builds"
        with store.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS build_tasks (id TEXT PRIMARY KEY, event_id TEXT NOT NULL, "
                       "body TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL)")

    def tasks(self, event_id=None):
        with self.store.connection() as db:
            rows = db.execute("SELECT * FROM build_tasks ORDER BY created DESC,id").fetchall()
        return [{**dict(row), "body": json.loads(row["body"])} for row in rows
                if event_id is None or row["event_id"] == event_id]

    def inspect(self, task_id):
        task_path(self.root, task_id)
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM build_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("构建任务不存在")
        return {**dict(row), "body": json.loads(row["body"])}

    def save(self, task_id, status, body):
        with self.store.connection() as db:
            db.execute("UPDATE build_tasks SET status=?,body=? WHERE id=?", (status, encoded(body), task_id))

    def create(self, event_id, settings):
        self.store.validate_configuration(settings)
        if self.store.decision(event_id, "scope") != "approved":
            raise ValueError("请先确认研究范围")
        if self.store.decision(event_id, "evidence") != "approved":
            raise ValueError("请先审核当前资料与实际输入")
        bundle = self.store.input_bundle(event_id)
        if not bundle["samples"]:
            raise ValueError("没有可用正文")
        input_hash = digest(bundle)
        task_id = identifier("BUILD-")
        directory = task_path(self.root, task_id)
        body = {"input": bundle, "input_hash": input_hash, "settings": settings,
                "event": self.store.event(event_id), "scope_hash": self.store.target(event_id, "scope"),
                "config": build_config(settings, directory), "code": code_version(),
                "evidence_review": next(r for r in self.store.reviews(event_id)
                    if r["kind"] == "evidence" and r["target"] == input_hash), "attempt": 1}
        with self.store.connection() as db:
            db.execute("INSERT INTO build_tasks VALUES(?,?,?,?,?)", (task_id, event_id, encoded(body), "ready", now()))
        return task_id

    def current(self, row):
        eid, body = row["event_id"], row["body"]
        return (digest(self.store.input_bundle(eid)) == body["input_hash"]
                and self.store.target(eid, "scope") == body["scope_hash"]
                and self.store.decision(eid, "scope") == "approved"
                and self.store.decision(eid, "evidence") == "approved")

    def start(self, task_id, *, allow_network=False):
        if not allow_network:
            raise ValueError("请明确允许本次构建调用模型接口")
        with task_lock(self.root, task_id):
            row = self.inspect(task_id)
            if row["status"] != "ready":
                raise ValueError("仅可启动待启动任务；失败后请创建新的构建任务")
            if not self.current(row):
                raise ValueError("输入或审核状态已变化，请重新确认并创建构建任务")
            body = row["body"]
            body.update(start_requested=now(), queued_at=time.time())
            self.save(task_id, "queued", body)
            try:
                # Separate worker survives page changes and Streamlit restarts.
                with (task_path(self.root, task_id) / "worker.log").open("ab") as log:
                    worker = subprocess.Popen([sys.executable, "-m", "finmy.workbench.build_tasks",
                        "--root", str(self.store.root), "--task", task_id], cwd=ROOT,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                body["pid"] = worker.pid
                self.save(task_id, "queued", body)
            except Exception as exc:
                body["error_type"] = type(exc).__name__
                self.save(task_id, "failed", body)
                raise ValueError("构建进程未能启动") from exc

    def cancel(self, task_id):
        with task_lock(self.root, task_id):
            row = self.inspect(task_id)
            if row["status"] != "ready":
                raise ValueError("只能取消尚未启动的构建任务")
            self.save(task_id, "cancelled", row["body"])

    def reconcile(self, task_id):
        """Interrupted workers are never silently rerun or charged again."""
        row = self.inspect(task_id)
        if row["status"] not in {"queued", "running"}:
            return row
        try:
            with task_lock(self.root, task_id):
                row = self.inspect(task_id)
                body = row["body"]
                if row["status"] not in {"queued", "running"}:
                    return row
                if row["status"] == "queued" and time.time()-body.get("queued_at", time.time()) < 60:
                    return row
                body["error_type"] = "WorkerInterrupted"
                body["finished"] = now()
                self.save(task_id, "interrupted", body)
        except ValueError:
            pass  # A live worker owns the lock.
        return self.inspect(task_id)

    def run(self, task_id, executor=None):
        task_path(self.root, task_id).mkdir(parents=True, exist_ok=True)
        with worker_lock(self.root, task_id):
            row = self.inspect(task_id)
            if row["status"] != "queued":
                return
            body = row["body"]
            directory = task_path(self.root, task_id)
            started = time.monotonic()
            try:
                if not self.current(row):
                    raise ValueError("InputOrApprovalChanged")
                if code_version() != body["code"]:
                    raise ValueError("CodeChangedSinceTaskCreation")
                body.update(started=now(), pid=os.getpid())
                self.save(task_id, "running", body)
                write_json(directory / "input.json", body["input"])
                write_json(directory / "config.json", {"builder_config": body["config"]})
                write_json(directory / "snapshot.json", body)
                result = (executor or execute_build)(body, directory)
                graph = result["graph"]
                validate_graph(graph)
                body.update(run_directory=result.get("run_directory"), usage=result.get("usage"),
                            elapsed_seconds=time.monotonic()-started, finished=now())
                # Binding to the frozen input is essential if materials changed during execution.
                gid = identifier("GRAPH-")
                with self.store.connection() as db:
                    db.execute("INSERT INTO graphs VALUES(?,?,?,?,?,?,?,?)",
                        (gid, row["event_id"], encoded(graph), digest(graph), None,
                         "构建草稿 · " + task_id, body["input_hash"], now()))
                    body["graph_id"] = gid
                    db.execute("UPDATE build_tasks SET status='completed',body=? WHERE id=?", (encoded(body), task_id))
            except Exception as exc:
                reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
                    "InputOrApprovalChanged", "CodeChangedSinceTaskCreation", "MissingProviderCredential"} else type(exc).__name__
                body.update(error_type=reason, elapsed_seconds=time.monotonic()-started, finished=now())
                # Do not write credential-bearing exception messages to the interface.
                self.save(task_id, "failed", body)


def execute_build(body, directory):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    from finmy.runner.build_only_runner import select_builder
    from finmy.runner.sparse_build_runner import load_inputs, preflight
    builder_class, config = select_builder(body["config"])
    inputs, _ = load_inputs(directory / "input.json")
    report = preflight(config, inputs)
    write_json(directory / "preflight.json", report)
    if not report["credential_present"]:
        raise ValueError("MissingProviderCredential")
    builder = builder_class(build_config=config)
    builder.run(inputs)
    run = Path(builder.save_dir)
    graph = graph_from_bytes((run / "FinalEventCascade.json").read_bytes())
    manifest = json.loads((run / "RunManifest.json").read_text())
    return {"graph": graph, "run_directory": str(run), "usage": manifest.get("usage")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    BuildController(Store(args.root)).run(args.task)
