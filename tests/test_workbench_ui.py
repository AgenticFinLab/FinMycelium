from pathlib import Path

from streamlit.testing.v1 import AppTest

from finmy.workbench.store import Store
from finmy.workbench.domain import DEFAULT_COLUMNS, TABLE_LABELS

APP = Path(__file__).resolve().parents[1] / "finmy/workbench/app.py"


def find(elements, label):
    return next(e for e in elements if e.label == label)


def test_empty_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert master.empty
    assert list(master.columns) == [TABLE_LABELS[k] for k in DEFAULT_COLUMNS]
    assert find(app.text_input, "搜索").disabled
    for page in ("任务", "待审", "设置", "数据"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    assert Store(tmp_path).events() == []


def test_filtered_empty_table_keeps_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    store.create_events([{"event_name_en": "Existing event"}])
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.text_input, "搜索").set_value("No matching event").run()
    assert not app.exception
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert master.empty
    assert any(item.value == "无匹配事件" for item in app.info)
    assert len(store.events()) == 1


def test_alias_search_filters_and_column_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    store.create_events([{"event_id": "A", "event_name_en": "Alpha", "aliases": ["Special alias"], "domain": "Energy", "owner": "One"},
                         {"event_id": "B", "event_name_zh": "乙", "domain": "Transport", "owner": "Two"}])
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.text_input, "搜索").set_value("special alias").run()
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert list(master["事件 ID"]) == ["A"]
    find(app.multiselect, "列").set_value(["event_id", "event_name_zh", "aliases", "notes"]).run()
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert list(master.columns) == ["事件 ID", "中文名称", "别名", "备注"]
    find(app.text_input, "搜索").set_value("")
    find(app.selectbox, "领域筛选").set_value("Transport").run()
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert list(master["事件 ID"]) == ["B"]
    find(app.selectbox, "负责人筛选").set_value("One").run()
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert master.empty
    assert not app.exception


def test_scope_review_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Example", "description": "Description", "scope_include": "Scope"}])[0]
    app = AppTest.from_file(str(APP)).run(timeout=30)
    next(e for e in app.text_input if e.key and "-scope-" in e.key and e.key.startswith("reviewer-")).set_value("Tester")
    find(app.button, "保存范围确认").click().run()
    assert not app.exception
    assert store.decision(eid, "scope") == "approved"
    find(app.selectbox, "范围确认筛选").set_value("待确认").run()
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert master.empty


def test_create_and_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.text_input, "英文名称").set_value("UI synthetic event")
    find(app.text_area, "事件简介").set_value("Fictional timeline")
    find(app.text_area, "纳入范围").set_value("January 2025")
    find(app.button, "保存事件").click().run(timeout=30)
    assert not app.exception
    store = Store(tmp_path)
    event = store.events()[0]["event_id"]
    store.review(event, "scope", "approved", "Tester", "", store.target(event, "scope"))
    store.add_source(event, "Source", "Synthetic evidence.")
    app.sidebar.radio[0].set_value("待审").run(timeout=30)
    assert not app.exception
    next(e for e in app.text_input if e.key and e.key.startswith("reviewer-") and "-evidence-" in e.key).set_value("Tester")
    find(app.button, "保存审核").click().run(timeout=30)
    assert not app.exception
    assert store.status(event) == "待构建"


def test_settings_and_task(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Synthetic", "description": "Example", "scope_include": "Example scope"}])[0]
    store.review(eid, "scope", "approved", "Tester", "", store.target(eid, "scope"))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.sidebar.radio[0].set_value("设置").run()
    find(app.selectbox, "模型").set_value("自定义").run()
    find(app.text_input, "Ark 模型 / 接入点 ID").set_value("test-model")
    find(app.button, "保存设置").click().run()
    assert not app.exception
    assert store.settings()["model"] == "test-model"
    app.sidebar.radio[0].set_value("任务").run()
    find(app.multiselect, "事件").set_value([eid]).run()
    find(app.button, "保存任务").click().run()
    assert not app.exception
    assert store.jobs()[0]["status"] == "not_connected"
    assert find(app.button, "开始").disabled
    find(app.button, "取消").click().run()
    assert store.jobs()[0]["status"] == "cancelled"


def test_graph_field_edit_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Test"}])[0]
    store.add_source(eid, "Source", "Test content")
    original = {"event_id": "original", "title": {"value": "Before"}, "stages": [
        {"stage_id": "S1", "name": {"value": "Stage"}, "episodes": []}]}
    store.add_graph(eid, original)
    app = AppTest.from_file(str(APP)).run(timeout=30)
    selector = find(app.selectbox, "修改字段")
    selector.set_value(selector.options.index("title / value")).run()
    find(app.text_area, "新内容").set_value("After")
    find(app.text_input, "修订说明").set_value("Correct title")
    find(app.button, "保存修订版").click().run()
    assert not app.exception
    assert store.graphs(eid)[0]["body"]["title"]["value"] == "After"
    assert store.graphs(eid)[1]["body"] == original
