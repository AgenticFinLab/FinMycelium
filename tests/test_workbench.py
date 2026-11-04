import copy
import io
import json
import zipfile

import pytest

from finmy.workbench.domain import (
    DEFAULT_MODEL, DERIVED_FIELDS, FIELDS, date_bounds, display_name, editable_fields, event_record, export_table,
    extract_text, graph_from_bytes, read_matrix, read_table, validate_graph, validate_url,
)
from finmy.workbench.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "workspace")


@pytest.fixture
def event(store):
    eid = store.create_events([{"event_name_en": "Synthetic port reopening", "description": "A fictional port closes and reopens.",
                                 "scope_include": "The port response in January 2025", "coverage_start": "2025-01", "coverage_end": "2025-02"}])[0]
    store.review(eid, "scope", "approved", "Reviewer", "", store.target(eid, "scope"))
    return eid


@pytest.fixture
def graph():
    return {"event_id": "synthetic-port", "title": {"value": "Synthetic port reopening"},
            "event_type": {"value": "logistics"}, "descriptions": [],
            "stages": [{"stage_id": "S1", "name": {"value": "Response"}, "index_in_event": 0,
                        "start_time": {"value": "2025-01"}, "end_time": {"value": "2025-02"}, "descriptions": [],
                        "episodes": [{"episode_id": "E1", "name": {"value": "Reopening"}, "index_in_stage": 0,
                                      "start_time": {"value": "2025-01-03"}, "end_time": {"value": "2025-01-04"},
                                      "participants": [{"participant_id": "P_1", "name": {"value": "Port authority"},
                                                        "actions": [{"name": {"value": "Open", "evidence_source_contents": ["The port reopened."]}}]}],
                                      "participant_relations": [], "transactions": []}]}]}


def test_empty_and_persistent(store, event):
    assert Store(store.root).event(event)["event_name_en"] == "Synthetic port reopening"
    assert Store(store.root / "other").events() == []


@pytest.mark.parametrize("field,value", [("event_name_en", ""), ("event_id", "../../escape"), ("coverage_start", "2025-02-30"),
                                        ("coverage_start", "25"), ("coverage_start", "2025-13"), ("coverage_start", "0000")])
def test_invalid_event(field, value):
    with pytest.raises(ValueError):
        event_record({"event_name_en": "Example", field: value})


def test_dates():
    assert date_bounds("2024-02")[1].day == 29
    assert date_bounds("unknown") is None
    assert event_record({"event_name_en": "Partial", "coverage_start": "2025", "coverage_end": "2025-01"})["coverage_start"] == "2025"
    with pytest.raises(ValueError):
        event_record({"event_name_en": "Invalid", "coverage_start": "2026", "coverage_end": "2025"})


def test_atomic_duplicate_import(store, event):
    with pytest.raises(ValueError):
        store.create_events([{"event_name_en": "New", "event_id": "NEW"}, {"event_name_en": "Duplicate", "event_id": event}])
    assert len(store.events()) == 1
    with pytest.raises(ValueError):
        store.create_events([{"event_name_en": "One", "event_id": "X"}, {"event_name_en": "Two", "event_id": "X"}])
    assert len(store.events()) == 1


def test_edit_conflict_and_history(store, event):
    row = store.event(event)
    fields = {k: row[k] for k in FIELDS}
    store.update_event(event, {**fields, "event_name_en": "Updated"}, 1)
    with pytest.raises(ValueError):
        store.update_event(event, fields, 1)
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM event_history").fetchone()[0] == 2


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_table_roundtrip(kind):
    rows = [{"event_name_zh": "含逗号,\n换行", "event_id": "TEST-1", "coverage_start": "1900"}]
    out = read_table(export_table(rows, kind), "events." + kind)
    assert out[0]["event_name_zh"] == rows[0]["event_name_zh"]
    assert out[0]["coverage_start"] == "1900"


@pytest.mark.parametrize("raw", [b"title,title\na,b\n", b"wrong\na\n", b"title,owner\na\n", b"title\n\n"])
def test_table_reject(raw):
    with pytest.raises(ValueError):
        read_table(raw, "events.csv")


def test_formula_export():
    raw = export_table([{"event_name_zh": "=HYPERLINK(1)"}])
    assert b"'=HYPERLINK" in raw
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(export_table([{"event_name_zh": "=1+1"}], "xlsx")))
    assert book.active["B2"].data_type == "s"


def test_excel_formula_reject():
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["title"])
    book.active.append(["=1+1"])
    raw = io.BytesIO()
    book.save(raw)
    with pytest.raises(ValueError, match="公式"):
        read_table(raw.getvalue(), "events.xlsx")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "https://user:secret@example.org", "bad"])
def test_url_reject(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_evidence_originals_and_url(store, event):
    sid = store.add_source(event, "Source", "The port reopened.\n", raw=b"original")
    urlid = store.add_source(event, "Link", url="https://example.org/article")
    assert store.input_bundle(event)["samples"][0]["content"] == "The port reopened.\n"
    with pytest.raises(ValueError):
        store.include_source(event, urlid, True)
    store.include_source(event, sid, False)
    assert store.input_bundle(event)["samples"] == []
    with store.connection() as db:
        assert db.execute("SELECT raw FROM sources WHERE id=?", (sid,)).fetchone()[0] == b"original"


def test_extract_text():
    assert extract_text("文本".encode(), "input.txt") == "文本"
    with pytest.raises(ValueError):
        extract_text(b" ", "blank.txt")
    with pytest.raises(ValueError):
        extract_text(b"a", "input.exe")


def test_blank_pdf_rejected():
    from PyPDF2 import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    raw = io.BytesIO()
    writer.write(raw)
    with pytest.raises((ValueError, KeyError)):
        extract_text(raw.getvalue(), "scan.pdf")


def test_graph_revisions_and_review(store, event, graph):
    store.add_source(event, "Source", "The port reopened.")
    first = store.add_graph(event, graph)
    target = store.target(event, "graph")
    store.review(event, "graph", "approved", "Reviewer", "Checked", target)
    assert store.status(event) == "已收录"
    revised = copy.deepcopy(graph)
    revised["title"]["value"] = "Revised title"
    store.add_graph(event, revised, "Title correction", first)
    assert store.status(event) == "待审核图"
    assert store.graphs(event)[1]["body"] == graph
    with pytest.raises(ValueError, match="更新"):
        store.review(event, "graph", "approved", "Reviewer", "", target)


def test_changed_input_invalidates_approval(store, event, graph):
    sid = store.add_source(event, "Source", "The port reopened.")
    store.review(event, "evidence", "approved", "Reviewer", "", store.target(event, "evidence"))
    store.add_graph(event, graph)
    store.review(event, "graph", "approved", "Reviewer", "", store.target(event, "graph"))
    store.add_source(event, "Second source", "Another fact.")
    assert store.decision(event, "evidence") is None
    assert store.status(event) == "待审核图"
    with pytest.raises(ValueError, match="输入已变化"):
        store.review(event, "graph", "approved", "Reviewer", "", store.target(event, "graph"))


def test_empty_evidence_cannot_approve(store, event, graph):
    store.add_graph(event, graph)
    with pytest.raises(ValueError, match="资料正文"):
        store.review(event, "graph", "approved", "Reviewer", "", store.target(event, "graph"))


def test_dangling_reference(graph):
    graph["stages"][0]["episodes"][0]["participant_relations"] = [{"from_participant_id": "P_1", "to_participant_id": "P_2"}]
    with pytest.raises(ValueError, match="不存在"):
        validate_graph(graph)


def test_duplicate_ids(graph):
    graph["stages"].append(copy.deepcopy(graph["stages"][0]))
    with pytest.raises(ValueError):
        validate_graph(graph)


def test_edit_fields_protect_ids(graph):
    paths = [path for path, value in editable_fields(graph)]
    assert ("title", "value") in paths
    assert not any(str(part).endswith("_id") for path in paths for part in path)


def test_graph_envelope(graph):
    assert graph_from_bytes(json.dumps([graph]).encode()) == graph
    with pytest.raises(ValueError):
        graph_from_bytes(b'[{"event_id":"x"},{"event_id":"y"}]')


def test_job_has_no_execution(store, event):
    config = store.settings()
    jid = store.create_job([event], "search", config)
    assert store.jobs()[0]["status"] == "not_connected"
    assert store.jobs()[0]["body"]["review_evidence"] is True
    store.cancel_job(jid)
    assert store.jobs()[0]["status"] == "cancelled"
    with pytest.raises(ValueError):
        store.cancel_job(jid)


def test_missing_build_input(store, event):
    with pytest.raises(ValueError):
        store.create_job([event], "build", store.settings())


@pytest.mark.parametrize("config", [{"model": DEFAULT_MODEL, "builder": "SparseRagBuilder", "concurrency": 0},
                                    {"model": "a/b", "builder": "SparseRagBuilder", "concurrency": 1},
                                    {"model": DEFAULT_MODEL, "builder": "bad", "concurrency": 1}])
def test_config_reject(store, config):
    with pytest.raises(ValueError):
        store.save_settings(config)


def test_export_isolation_and_manifest(store, event, graph):
    store.add_source(event, "Source", "The port reopened.", raw=b"binary-original")
    store.add_graph(event, graph)
    store.review(event, "graph", "approved", "Reviewer", "", store.target(event, "graph"))
    other = store.create_events([{"event_name_en": "PRIVATE OTHER", "description": "Other", "scope_include": "Other"}])[0]
    store.review(other, "scope", "approved", "Reviewer", "", store.target(other, "scope"))
    store.create_job([event, other], "search", store.settings())
    with zipfile.ZipFile(io.BytesIO(store.export_zip([event]))) as archive:
        assert event + "/FinalEPG.json" in archive.namelist()
        assert not any(name.startswith(other) for name in archive.namelist())
        assert b"PRIVATE OTHER" not in archive.read(event + "/runs.json")
        assert b"binary-original" not in b"".join(archive.read(n) for n in archive.namelist())
        import hashlib
        for entry in json.loads(archive.read("manifest.json")):
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("names", [{"event_name_zh": "测试事件"}, {"event_name_en": "Example"},
                                  {"event_name_zh": "测试事件", "event_name_en": "Example"}])
def test_names_and_lists(names):
    row = event_record({**names, "aliases": "Example, Inc.\n另一个名称\n另一个名称",
                        "participants": ["Authority", "Operator"], "search_language": "zh-en"})
    assert row["aliases"] == ["Example, Inc.", "另一个名称"]
    assert row["participants"] == ["Authority", "Operator"]
    assert row["event_name_en"] == names.get("event_name_en", "")
    assert display_name(row) == names.get("event_name_zh", names.get("event_name_en"))


@pytest.mark.parametrize("field,value", [("aliases", [1]), ("participants", {}), ("search_language", "other"),
                                        ("related_events", {}), ("related_events", [{"event_id": "OTHER"}]),
                                        ("related_events", [{"event_id": "OTHER", "relation_type": [], "note": ""}])])
def test_bad_structured_fields(field, value):
    with pytest.raises(ValueError):
        event_record({"event_name_en": "Test", field: value})


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_full_table_roundtrip_and_derived_rejection(store, kind):
    row = event_record({"event_id": "A", "event_name_zh": "测试", "event_name_en": "Test",
                        "aliases": ["Alias, with comma", "别名"], "country_region": ["Region A", "Region B"],
                        "participants": ["Example, Inc."], "coverage_start": "2025", "coverage_end": "unknown",
                        "scope_include": "A response", "scope_exclude": "Earlier crisis", "description": "Test",
                        "keywords": ["search one", "search two"], "source_hints": ["https://example.org"],
                        "search_language": "en", "related_events": [
                            {"event_id": "EXTERNAL", "relation_type": "overlap", "note": "Shared response"}]})
    exported = export_table([{**row, "scope_review": "已确认", "graph_review": "approved", "status": "已收录"}], kind)
    assert read_matrix(exported, "events." + kind)[0] == list(FIELDS) + list(DERIVED_FIELDS)
    imported = read_table(exported, "events." + kind)
    assert imported == [row]
    eid = store.create_events(imported)[0]
    summary = store.table_rows()[0]
    assert summary["relation_count"] == 1
    assert summary["scope_review"] == "待确认"
    assert store.decision(eid, "graph") is None


def test_explicit_legacy_column_mapping():
    raw = b"legacy_id,title,start_time,scope_note,unused\nOLD-1,Example,2025,Response,old metadata\n"
    with pytest.raises(ValueError, match="映射"):
        read_table(raw, "events.csv")
    mapping = {"legacy_id": "event_id", "title": "event_name_en", "start_time": "coverage_start", "scope_note": "scope_include"}
    row = read_table(raw, "events.csv", mapping)[0]
    assert row["event_id"] == "OLD-1"
    assert row["event_name_en"] == "Example"
    assert row["event_name_zh"] == ""
    assert row["coverage_start"] == "2025"
    with pytest.raises(ValueError, match="映射"):
        read_table(raw, "events.csv", {**mapping, "unused": "event_name_en"})


def test_related_event_validation():
    link = {"event_id": "B", "relation_type": "contains", "note": "Shared scope"}
    with pytest.raises(ValueError, match="自引用"):
        event_record({"event_id": "B", "event_name_en": "Test", "related_events": [link]})
    with pytest.raises(ValueError, match="重复"):
        event_record({"event_id": "A", "event_name_en": "Test", "related_events": [link, link]})


def test_scope_is_required_and_cannot_approve_incomplete_event(store):
    eid = store.create_events([{"event_name_en": "Draft"}])[0]
    with pytest.raises(ValueError, match="先确认"):
        store.create_job([eid], "search", store.settings())
    with pytest.raises(ValueError, match="补齐"):
        store.review(eid, "scope", "approved", "Reviewer", "", store.target(eid, "scope"))
    store.review(eid, "scope", "returned", "Reviewer", "Define scope", store.target(eid, "scope"))
    assert store.table_rows()[0]["scope_review"] == "需修订"


@pytest.mark.parametrize("field,value", [("event_name_en", "Updated name"), ("aliases", ["Another name"]),
                                        ("scope_include", "Wider scope"), ("scope_exclude", "Another exclusion"),
                                        ("coverage_end", "2026"), ("participants", ["Another subject"])])
def test_scope_edits_invalidate_review(store, event, field, value):
    target = store.target(event, "scope")
    row = store.event(event)
    store.update_event(event, {**{k: row[k] for k in FIELDS}, field: value}, row["revision"])
    assert store.decision(event, "scope") is None
    with pytest.raises(ValueError, match="更新"):
        store.review(event, "scope", "approved", "Reviewer", "", target)
    with pytest.raises(ValueError, match="先确认"):
        store.create_job([event], "search", store.settings())


def test_coordination_edits_preserve_scope_and_input(store, event):
    bundle = store.input_bundle(event)
    row = store.event(event)
    store.update_event(event, {**{k: row[k] for k in FIELDS}, "owner": "New owner", "notes": "A note"}, row["revision"])
    assert store.decision(event, "scope") == "approved"
    assert store.input_bundle(event) == bundle
    row = store.event(event)
    store.update_event(event, {**{k: row[k] for k in FIELDS}, "keywords": ["One phrase", "Another phrase"]}, row["revision"])
    assert store.decision(event, "scope") == "approved"
    assert store.input_bundle(event)["user_query"]["key_words"] == ["One phrase", "Another phrase"]
    assert store.input_bundle(event) != bundle


def test_legacy_record_read_does_not_rewrite_history(store):
    original = json.dumps({"event_id": "OLD", "title": "Legacy title", "description": "Description",
                           "scope_note": "Old scope", "start_time": "2020", "end_time": "2021"})
    with store.connection() as db:
        db.execute("INSERT INTO events VALUES(?,?,?,?)", ("OLD", original, 1, "2025-01-01"))
        db.execute("INSERT INTO event_history VALUES(?,?,?,?)", ("OLD", 1, original, "2025-01-01"))
    row = store.event("OLD")
    assert display_name(row) == "Legacy title"
    assert row["event_name_zh"] == row["event_name_en"] == row["coverage_start"] == ""
    assert row["legacy_fields"]["scope_note"] == "Old scope"
    assert store.table_rows()[0]["scope_review"] == "待确认"
    with store.connection() as db:
        assert db.execute("SELECT body FROM events").fetchone()[0] == original
    store.update_event("OLD", {**{k: row[k] for k in FIELDS}, "event_name_en": "Legacy title"}, 1)
    with store.connection() as db:
        assert db.execute("SELECT body FROM event_history WHERE revision=1").fetchone()[0] == original
        assert db.execute("SELECT count(*) FROM event_history").fetchone()[0] == 2
