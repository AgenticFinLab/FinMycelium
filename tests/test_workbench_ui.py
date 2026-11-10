from pathlib import Path

from streamlit.testing.v1 import AppTest

from finmy.workbench.store import Store
from finmy.workbench.build_tasks import BuildController

APP = Path(__file__).resolve().parents[1] / "finmy/workbench/app.py"


def find(elements, label):
    return next(e for e in elements if e.label == label)


def run(app):
    # AppTest 1.51 treats single-select segmented controls as list-valued widgets.
    # Supply its public list input so it serializes the same index as the browser.
    for group in app.get("button_group"):
        if isinstance(group.value, str):
            group.set_value([group.value])
    return app.run(timeout=30)


def test_empty_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    app = AppTest.from_file(str(APP))
    run(app)
    assert not app.exception
    assert not app.dataframe
    assert find(app.button, "新增事件")
    for page in ("任务", "待审", "设置", "数据"):
        app.button(key="nav-" + page).click()
        run(app)
        assert not app.exception
    assert Store(tmp_path).events() == []


def test_filtered_empty_table_preserves_events(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    store.create_events([{"event_name_en": "Existing event"}])
    app = AppTest.from_file(str(APP))
    run(app)
    find(app.text_input, "搜索事件").set_value("No matching event")
    run(app)
    assert not app.exception
    assert not app.dataframe
    assert any("暂无匹配事件" in item.value for item in app.markdown)
    assert len(store.events()) == 1


def test_alias_search_filters_and_column_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    store.create_events([{"event_id": "A", "event_name_en": "Alpha", "aliases": ["Special alias"], "domain": "Energy", "owner": "One"},
                         {"event_id": "B", "event_name_zh": "乙", "domain": "Transport", "owner": "Two"}])
    app = AppTest.from_file(str(APP))
    run(app)
    find(app.text_input, "搜索事件").set_value("special alias")
    run(app)
    master = app.dataframe[0].value
    assert list(master["事件名称"]) == ["Alpha"]
    find(app.multiselect, "显示列").set_value(["event_id", "event_name_zh", "aliases", "notes"])
    run(app)
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert list(master.columns) == ["事件 ID", "中文名称", "别名", "备注"]
    find(app.text_input, "搜索事件").set_value("")
    find(app.selectbox, "领域").set_value("Transport")
    run(app)
    master = next(frame.value for frame in app.dataframe if "中文名称" in frame.value.columns)
    assert list(master["事件 ID"]) == ["B"]
    find(app.selectbox, "负责人").set_value("One")
    run(app)
    assert not app.dataframe
    assert not app.exception


def test_scope_review_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Example", "description": "Description", "scope_include": "Scope"}])[0]
    app = AppTest.from_file(str(APP))
    run(app)
    app.session_state["detail_id"] = eid
    run(app)
    next(e for e in app.text_input if e.key and "-scope-" in e.key and e.key.startswith("reviewer-")).set_value("Tester")
    find(app.button, "保存范围确认").click()
    run(app)
    assert not app.exception
    assert store.decision(eid, "scope") == "approved"
    find(app.button, "返回事件列表").click()
    run(app)
    find(app.selectbox, "范围确认").set_value("待确认")
    run(app)
    assert not app.dataframe


def test_create_and_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    app = AppTest.from_file(str(APP))
    run(app)
    find(app.button, "新增事件").click()
    run(app)
    find(app.text_input, "英文名称").set_value("UI synthetic event")
    find(app.text_area, "事件简介").set_value("Fictional timeline")
    find(app.text_area, "纳入范围").set_value("January 2025")
    find(app.button, "保存事件").click()
    run(app)
    assert not app.exception
    store = Store(tmp_path)
    event = store.events()[0]["event_id"]
    store.review(event, "scope", "approved", "Tester", "", store.target(event, "scope"))
    store.add_source(event, "Source", "Synthetic evidence.")
    app.button(key="nav-待审").click()
    run(app)
    assert not app.exception
    next(group for group in app.get("button_group")
         if group.key == "ui-event-section-" + event).set_value(["资料与输入"])
    run(app)
    next(e for e in app.text_input if e.key and e.key.startswith("reviewer-") and "-evidence-" in e.key).set_value("Tester")
    find(app.button, "保存审核").click()
    run(app)
    assert not app.exception
    assert store.status(event) == "待构建"


def test_settings_and_task(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Synthetic", "description": "Example", "scope_include": "Example scope"}])[0]
    store.review(eid, "scope", "approved", "Tester", "", store.target(eid, "scope"))
    store.add_source(eid, "Evidence", "A documented activity.")
    store.review(eid, "evidence", "approved", "Tester", "", store.target(eid, "evidence"))
    app = AppTest.from_file(str(APP))
    run(app)
    app.button(key="nav-设置").click()
    run(app)
    find(app.selectbox, "模型").set_value("自定义")
    run(app)
    find(app.text_input, "Ark 模型 / 接入点 ID").set_value("test-model")
    find(app.button, "保存构建默认配置").click()
    run(app)
    assert not app.exception
    assert store.settings()["model"] == "test-model"
    app.button(key="nav-数据").click()
    run(app)
    app.session_state["detail_id"] = eid
    app.session_state["ui-event-section-" + eid] = "图与修订"
    run(app)
    find(app.button, "创建构建任务").click()
    run(app)
    assert not app.exception
    controller = BuildController(store)
    task = controller.tasks()[0]
    assert task["status"] == "ready"
    assert task["body"]["settings"]["model"] == "test-model"
    # A new page session can inspect and cancel the persisted, unstarted task.
    app = AppTest.from_file(str(APP))
    app.session_state["navigation"] = "任务"
    app.session_state["task-selected"] = task["id"]
    run(app)
    assert find(app.button, "开始构建").disabled
    find(app.button, "取消构建任务").click()
    run(app)
    assert controller.inspect(task["id"])["status"] == "cancelled"


def test_graph_field_edit_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMY_WORKBENCH_HOME", str(tmp_path))
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en": "Test"}])[0]
    store.add_source(eid, "Source", "Test content")
    original = {"event_id": "original", "title": {"value": "Before"}, "stages": [
        {"stage_id": "S1", "name": {"value": "Stage"}, "episodes": []}]}
    store.add_graph(eid, original)
    app = AppTest.from_file(str(APP))
    run(app)
    app.session_state["detail_id"] = eid
    app.session_state["ui-event-section-" + eid] = "图与修订"
    run(app)
    selector = find(app.selectbox, "修改字段")
    selector.set_value(selector.options.index("title / value"))
    run(app)
    find(app.text_area, "新内容").set_value("After")
    find(app.text_input, "修订说明").set_value("Correct title")
    find(app.button, "保存修订版").click()
    run(app)
    assert not app.exception
    assert store.graphs(eid)[0]["body"]["title"]["value"] == "After"
    assert store.graphs(eid)[1]["body"] == original
