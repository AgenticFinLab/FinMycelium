"""Transactional local records. No network access or builder execution."""

import hashlib
import io
import json
import re
import sqlite3
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from finmy.workbench.domain import DEFAULT_MODEL, SCOPE_FIELDS, digest, encoded, event_record, export_table, stored_record, validate_graph, validate_url


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def identifier(prefix):
    return prefix + uuid.uuid4().hex[:12]


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "workbench.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT NOT NULL,
                    revision INTEGER NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS event_history (event_id TEXT, revision INTEGER, body TEXT, updated TEXT,
                    PRIMARY KEY(event_id, revision));
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
                    title TEXT, url TEXT, published TEXT, text TEXT, sha256 TEXT, raw BLOB,
                    included INTEGER NOT NULL, created TEXT);
                CREATE TABLE IF NOT EXISTS graphs (id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
                    body TEXT, sha256 TEXT, parent_id TEXT, note TEXT, input_hash TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
                    kind TEXT, target TEXT, decision TEXT, reviewer TEXT, note TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS handoffs (id TEXT PRIMARY KEY, event_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL, body TEXT NOT NULL, review_id TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT, status TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def events(self):
        with self.connection() as db:
            return [{**stored_record(json.loads(row["body"])), "revision": row["revision"], "updated": row["updated"]}
                    for row in db.execute("SELECT * FROM events ORDER BY updated DESC, id")]

    def event(self, event_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("事件不存在")
        return {**stored_record(json.loads(row["body"])), "revision": row["revision"], "updated": row["updated"]}

    def create_events(self, records):
        rows = [event_record(r) for r in records]
        for row in rows:
            row["event_id"] = row["event_id"] or identifier("EVT-")
            event_record(row)
        if len({r["event_id"] for r in rows}) != len(rows):
            raise ValueError("导入文件包含重复的事件 ID")
        with self.connection() as db:
            for row in rows:
                if db.execute("SELECT 1 FROM events WHERE id=?", (row["event_id"],)).fetchone():
                    raise ValueError(f"事件 ID 已存在：{row['event_id']}")
            for row in rows:
                stamp = now()
                db.execute("INSERT INTO events VALUES(?,?,?,?)", (row["event_id"], encoded(row), 1, stamp))
                db.execute("INSERT INTO event_history VALUES(?,?,?,?)", (row["event_id"], 1, encoded(row), stamp))
        return [r["event_id"] for r in rows]

    def update_event(self, event_id, fields, expected_revision):
        row = event_record({**fields, "event_id": event_id})
        with self.connection() as db:
            stamp = now()
            result = db.execute("UPDATE events SET body=?, revision=revision+1, updated=? WHERE id=? AND revision=?",
                                (encoded(row), stamp, event_id, expected_revision))
            if result.rowcount != 1:
                raise ValueError("记录已更新，请刷新后再保存")
            db.execute("INSERT INTO event_history VALUES(?,?,?,?)", (event_id, expected_revision + 1, encoded(row), stamp))

    def add_source(self, event_id, title, text="", url="", published="", raw=b""):
        self.event(event_id)
        if not title.strip() or (not text.strip() and not url):
            raise ValueError("请填写来源标题，以及正文或 URL")
        if url:
            validate_url(url)
        if len(raw) > 20 * 1024 * 1024 or len(text) > 5_000_000:
            raise ValueError("资料过大")
        sid = identifier("SRC-")
        sha = hashlib.sha256(raw or text.encode()).hexdigest()
        with self.connection() as db:
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (sid, event_id, title, url, published, text, sha, raw, int(bool(text.strip())), now()))
        return sid

    def sources(self, event_id):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT id,event_id,title,url,published,text,sha256,included,created FROM sources WHERE event_id=? ORDER BY created,id", (event_id,))]

    def include_source(self, event_id, source_id, included):
        with self.connection() as db:
            row = db.execute("SELECT text FROM sources WHERE id=? AND event_id=?", (source_id, event_id)).fetchone()
            if not row or (included and not row["text"].strip()):
                raise ValueError("没有可用正文，不能纳入输入")
            db.execute("UPDATE sources SET included=? WHERE id=? AND event_id=?", (int(included), source_id, event_id))

    def input_bundle(self, event_id):
        event = self.event(event_id)
        sources = [s for s in self.sources(event_id) if s["included"] and s["text"].strip()]
        return {"user_query": {"user_query_id": event_id,
                "query_text": "\n".join(f"{k}: {encoded(event[k]) if isinstance(event[k], list) else event[k]}" for k in SCOPE_FIELDS if event[k]),
                "key_words": event["keywords"],
                "extras": {"search_language": event["search_language"], "source_hints": event["source_hints"],
                           "source_registry": {s["id"]: {k: s[k] for k in ("title", "url", "published", "sha256")} for s in sources}}},
                "samples": [{"sample_id": s["id"], "raw_data_id": s["id"], "content": s["text"]} for s in sources]}

    def graphs(self, event_id):
        with self.connection() as db:
            return [{**dict(r), "body": json.loads(r["body"])} for r in db.execute("SELECT * FROM graphs WHERE event_id=? ORDER BY created DESC,id", (event_id,))]

    def add_graph(self, event_id, graph, note="手动导入", parent_id=None):
        self.event(event_id)
        validate_graph(graph)
        gid = identifier("GRAPH-")
        input_hash = digest(self.input_bundle(event_id))
        with self.connection() as db:
            if parent_id:
                parent = db.execute("SELECT * FROM graphs WHERE id=? AND event_id=?", (parent_id, event_id)).fetchone()
                if not parent or json.loads(parent["body"])["event_id"] != graph["event_id"]:
                    raise ValueError("修订不能修改图身份")
                input_hash = parent["input_hash"]
            db.execute("INSERT INTO graphs VALUES(?,?,?,?,?,?,?,?)", (gid, event_id, encoded(graph), digest(graph), parent_id, note, input_hash, now()))
        return gid

    def target(self, event_id, kind):
        if kind == "scope":
            event = self.event(event_id)
            return digest({k: event[k] for k in SCOPE_FIELDS})
        bundle_hash = digest(self.input_bundle(event_id))
        if kind == "evidence":
            return bundle_hash
        graphs = self.graphs(event_id)
        if not graphs:
            raise ValueError("尚无图")
        return digest({"input": bundle_hash, "graph_id": graphs[0]["id"], "graph_sha": graphs[0]["sha256"]})

    def reviews(self, event_id):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM reviews WHERE event_id=? ORDER BY created DESC,id", (event_id,))]

    def review(self, event_id, kind, decision, reviewer, note, expected_target):
        if kind not in {"scope", "evidence", "graph"} or decision not in {"approved", "returned", "issue"}:
            raise ValueError("无效审核类型")
        if not reviewer.strip() or (decision != "approved" and not note.strip()):
            raise ValueError("请填写审核人；退回或问题记录还需填写原因")
        current = self.target(event_id, kind)
        if current != expected_target:
            raise ValueError("内容已更新，请重新检查")
        if decision == "approved" and kind == "scope":
            event = self.event(event_id)
            if not (event["event_name_zh"] or event["event_name_en"]) or not event["description"].strip() or not event["scope_include"].strip():
                raise ValueError("确认范围前，请补齐一种名称、事件简介和纳入范围")
        if decision == "approved" and kind != "scope" and not self.input_bundle(event_id)["samples"]:
            raise ValueError("请先纳入至少一份资料正文")
        if decision == "approved" and kind == "graph":
            if self.graphs(event_id)[0]["input_hash"] != digest(self.input_bundle(event_id)):
                raise ValueError("图对应的输入已变化，请基于当前输入重新导入或构建")
        if decision == "approved" and kind != "scope" and self.decision(event_id, "scope") != "approved":
            raise ValueError("请先确认研究范围")
        if decision == "approved" and kind == "graph" and self.decision(event_id, "evidence") != "approved":
            raise ValueError("请先审核当前资料与输入")
        with self.connection() as db:
            review_id = identifier("REV-")
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)", (review_id, event_id, kind, current, decision, reviewer.strip(), note.strip(), now()))
            if kind == "evidence" and decision == "approved":
                bundle = self.input_bundle(event_id)
                if digest(bundle) != current:
                    raise ValueError("资料已更新，请重新审核")
                db.execute("INSERT INTO handoffs VALUES(?,?,?,?,?,?)",
                           (identifier("INPUT-"), event_id, current, encoded(bundle), review_id, now()))

    def handoffs(self, event_id):
        with self.connection() as db:
            return [{**dict(r), "body": json.loads(r["body"])} for r in db.execute(
                "SELECT * FROM handoffs WHERE event_id=? ORDER BY created DESC,id", (event_id,))]

    def decision(self, event_id, kind):
        try:
            target = self.target(event_id, kind)
        except ValueError:
            return None
        return next((r["decision"] for r in self.reviews(event_id) if r["kind"] == kind and r["target"] == target), None)

    def accepted(self, event_id):
        return all(self.decision(event_id, kind) == "approved" for kind in ("scope", "evidence", "graph"))

    def status(self, event_id):
        if self.graphs(event_id):
            if self.decision(event_id, "graph") == "approved" and not self.accepted(event_id):
                return "待审核资料" if self.decision(event_id, "scope") == "approved" else "待整理"
            return {"approved": "已收录", "returned": "待修订", "issue": "待修订"}.get(self.decision(event_id, "graph"), "待审核图")
        if self.input_bundle(event_id)["samples"]:
            return "待构建" if self.decision(event_id, "evidence") == "approved" else "待审核资料"
        return "待整理"

    def table_rows(self):
        rows = []
        for event in self.events():
            eid = event["event_id"]
            graphs = self.graphs(eid)
            rows.append({**event,
                         "scope_review": {"approved": "已确认", "returned": "需修订", "issue": "需修订"}.get(self.decision(eid, "scope"), "待确认"),
                         "evidence_review": self.decision(eid, "evidence") or "pending",
                         "graph_review": self.decision(eid, "graph") or "pending",
                         "graph_version": graphs[0]["id"] if graphs else "",
                         "status": self.status(eid), "relation_count": len(event["related_events"])})
        return rows

    def settings(self):
        with self.connection() as db:
            row = db.execute("SELECT body FROM settings WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"model": DEFAULT_MODEL, "builder": "SparseRagBuilder", "concurrency": 1}

    @staticmethod
    def validate_configuration(config):
        if set(config) != {"model", "builder", "concurrency"} or config["builder"] not in {"SparseRagBuilder", "AgentEventBuilder"}:
            raise ValueError("无效的构建配置")
        if not isinstance(config["model"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", config["model"]):
            raise ValueError("模型 ID 格式不正确")
        if type(config["concurrency"]) is not int or not 1 <= config["concurrency"] <= 32:
            raise ValueError("并发数需在 1–32 之间")

    def save_settings(self, config):
        self.validate_configuration(config)
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (encoded(config),))

    def create_job(self, ids, stage, config, evidence_review=True, graph_review=True):
        self.validate_configuration(config)
        if not ids or len(ids) != len(set(ids)) or stage not in {"search", "build", "full"}:
            raise ValueError("请选择事件和有效任务阶段")
        snapshots = []
        for eid in ids:
            event = self.event(eid)
            bundle = self.input_bundle(eid)
            if self.decision(eid, "scope") != "approved":
                raise ValueError(f"{eid}：请先确认事件范围")
            if stage == "build" and not bundle["samples"]:
                raise ValueError(f"{eid}：尚无可用输入资料")
            snapshots.append({"event": event, "input": bundle, "input_sha256": digest(bundle)})
        jid = identifier("TASK-")
        body = {"config": config, "stage": stage, "events": snapshots,
                "review_evidence": bool(evidence_review), "review_graph": bool(graph_review)}
        with self.connection() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?)", (jid, encoded(body), "not_connected", now()))
        return jid

    def jobs(self):
        with self.connection() as db:
            return [{**dict(r), "body": json.loads(r["body"])} for r in db.execute("SELECT * FROM jobs ORDER BY created DESC,id")]

    def cancel_job(self, job_id):
        with self.connection() as db:
            if db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='not_connected'", (job_id,)).rowcount != 1:
                raise ValueError("仅可取消未启动的任务")

    def export_zip(self, event_ids):
        catalog = {row["event_id"]: row for row in self.table_rows()}
        rows = [catalog[eid] for eid in event_ids]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("events.csv", export_table(rows))
            manifest = []
            for row in rows:
                eid = row["event_id"]
                files = {"event.json": row, "input.json": self.input_bundle(eid), "sources.json": self.sources(eid),
                         "reviews.json": self.reviews(eid), "handoffs.json": self.handoffs(eid)}
                with self.connection() as db:
                    files["event_history.json"] = [{**dict(r), "body": json.loads(r["body"])} for r in db.execute(
                        "SELECT revision,body,updated FROM event_history WHERE event_id=? ORDER BY revision", (eid,))]
                graphs = self.graphs(eid)
                for graph in graphs:
                    files[f"graphs/{graph['id']}.json"] = graph
                from finmy.search.control import SearchController
                searches = SearchController(self.root / "search")
                files["search_runs.json"] = []
                for tid in searches.tasks():
                    data = searches.inspect(tid)
                    if data["task"].get("event_id") == eid:
                        files["search_runs.json"].append({"task_id": tid, **{k:data[k] for k in (
                            "task", "config", "status", "usage", "code_sha256", "input_sha256", "selection") if k in data}})
                files["runs.json"] = [{**job, "body": {**job["body"], "events": [e for e in job["body"]["events"] if e["event"]["event_id"] == eid]}}
                                     for job in self.jobs() if any(e["event"]["event_id"] == eid for e in job["body"]["events"])]
                with self.connection() as db:
                    present = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='build_tasks'").fetchone()
                    if present:
                        files["build_runs.json"] = [{**dict(r), "body": json.loads(r["body"])} for r in db.execute(
                            "SELECT * FROM build_tasks WHERE event_id=? ORDER BY created,id", (eid,))]
                if self.accepted(eid):
                    files["FinalEPG.json"] = graphs[0]["body"]
                for filename, payload in files.items():
                    content = encoded(payload).encode()
                    path = f"{eid}/{filename}"
                    zf.writestr(path, content)
                    manifest.append({"path": path, "sha256": hashlib.sha256(content).hexdigest()})
            zf.writestr("manifest.json", encoded(manifest))
        return out.getvalue()
