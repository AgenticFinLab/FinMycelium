from pathlib import Path

from streamlit.testing.v1 import AppTest

from finmy.workbench.store import Store

APP = Path(__file__).resolve().parents[1] / 'finmy/workbench/app.py'


def find(elements, label):
    return next(e for e in elements if e.label == label)


def open_app(workspace, monkeypatch):
    monkeypatch.setenv('FINMY_WORKBENCH_HOME', str(workspace))
    return AppTest.from_file(str(APP)).run(timeout=30)


def local_records(app):
    find(app.button, '本机事件记录').click().run()
    assert not app.exception


def pending(app):
    app.button(key='nav-任务').click().run()
    app.radio(key='ui-task-view').set_value('待处理').run()
    assert not app.exception


def master(app):
    return next(frame.value for frame in app.dataframe if '事件名称' in frame.value.columns or '事件 ID' in frame.value.columns)


def test_empty_pages(tmp_path, monkeypatch):
    app = open_app(tmp_path, monkeypatch)
    assert [b.label for b in app.sidebar.button] == ['数据集', '任务中心', '设置']
    assert any('选择 EPG-dataset' in info.value for info in app.info)
    local_records(app)
    assert find(app.button, '新增事件') and find(app.button, '导入主表')
    pending(app)
    assert any('当前没有待处理事项' in m.value for m in app.markdown)
    app.button(key='nav-设置').click().run()
    assert find(app.text_input, '数据集根目录')
    app.button(key='nav-数据集').click().run()
    assert not app.exception and Store(tmp_path).events() == []


def test_filtered_empty_table_keeps_filters(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.create_events([{'event_name_en': 'Existing event'}])
    app = open_app(tmp_path, monkeypatch)
    local_records(app)
    assert list(master(app)['事件名称']) == ['Existing event']
    app.text_input(key='ui-master-query').set_value('No matching event').run()
    assert any('暂无匹配事件' in m.value for m in app.markdown)
    app.text_input(key='ui-master-query').set_value('').run()
    assert list(master(app)['事件名称']) == ['Existing event']
    assert not app.exception and len(store.events()) == 1


def test_alias_search_filters_and_column_selection(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.create_events([{'event_id': 'A', 'event_name_en': 'Alpha', 'aliases': ['Special alias'], 'domain': 'Energy', 'owner': 'One'},
                         {'event_id': 'B', 'event_name_zh': '乙', 'domain': 'Transport', 'owner': 'Two'}])
    app = open_app(tmp_path, monkeypatch)
    local_records(app)
    app.text_input(key='ui-master-query').set_value('special alias').run()
    app.multiselect(key='ui-master-columns').set_value(['event_id', 'event_name_zh', 'aliases', 'notes']).run()
    assert list(master(app).columns) == ['事件 ID', '中文名称', '别名', '备注']
    assert list(master(app)['事件 ID']) == ['A']
    app.text_input(key='ui-master-query').set_value('')
    app.selectbox(key='ui-master-domain').set_value('Transport').run()
    assert list(master(app)['事件 ID']) == ['B']
    app.selectbox(key='ui-master-owner').set_value('One').run()
    assert not app.exception and any('暂无匹配事件' in m.value for m in app.markdown)


def test_scope_review_ui(tmp_path, monkeypatch):
    store = Store(tmp_path)
    eid, = store.create_events([{'event_name_en': 'Example', 'description': 'Description', 'scope_include': 'Scope'}])
    app = open_app(tmp_path, monkeypatch)
    pending(app)
    assert app.selectbox(key='ui-review-selected').value == 'event:'+eid
    find(app.button, '打开范围确认').click().run()
    assert app.radio(key='ui-event-section-'+eid).value == '基本信息'
    find(app.text_input, '审核人').set_value('Tester')
    find(app.button, '保存范围确认').click().run(timeout=30)
    assert not app.exception and store.decision(eid, 'scope') == 'approved'
    find(app.button, '返回待处理').click().run()
    assert any('当前没有待处理事项' in m.value for m in app.markdown)


def test_create_and_review_queue(tmp_path, monkeypatch):
    app = open_app(tmp_path, monkeypatch)
    local_records(app)
    find(app.button, '新增事件').click().run()
    find(app.text_input, '英文名称').set_value('UI synthetic event')
    find(app.text_area, '事件简介').set_value('Fictional timeline')
    find(app.text_area, '纳入范围').set_value('January 2025')
    find(app.button, '保存事件').click().run(timeout=30)
    assert not app.exception
    store = Store(tmp_path)
    event = store.events()[0]['event_id']
    store.review(event, 'scope', 'approved', 'Tester', '', store.target(event, 'scope'))
    store.add_source(event, 'Source', 'Synthetic evidence.')
    pending(app)
    find(app.button, '打开材料审核').click().run()
    assert app.radio(key='ui-event-section-'+event).value == '资料与输入'
    find(app.text_input, '审核人').set_value('Tester')
    find(app.button, '保存审核').click().run(timeout=30)
    assert not app.exception and store.status(event) == '待构建'


def test_settings_and_historical_task(tmp_path, monkeypatch):
    store = Store(tmp_path)
    eid, = store.create_events([{'event_name_en': 'Synthetic', 'description': 'Example', 'scope_include': 'Example scope'}])
    store.review(eid, 'scope', 'approved', 'Tester', '', store.target(eid, 'scope'))
    store.create_job([eid], 'search', store.settings())
    app = open_app(tmp_path, monkeypatch)
    app.button(key='nav-设置').click().run()
    find(app.selectbox, '默认构建模型').set_value('自定义').run()
    find(app.text_input, '默认构建模型 ID').set_value('test-model')
    find(app.button, '保存构建默认配置').click().run()
    assert not app.exception and store.settings()['model'] == 'ark/test-model'
    app.button(key='nav-任务').click().run()
    assert store.jobs()[0]['status'] == 'not_connected'
    find(app.button, '取消计划').click().run()
    assert not app.exception and store.jobs()[0]['status'] == 'cancelled'


def test_graph_field_edit_preserves_original(tmp_path, monkeypatch):
    store = Store(tmp_path)
    eid, = store.create_events([{'event_name_en': 'Test', 'description': 'Example event', 'scope_include': 'Within scope'}])
    store.review(eid, 'scope', 'approved', 'Tester', '', store.target(eid, 'scope'))
    store.add_source(eid, 'Source', 'Test content')
    store.review(eid, 'evidence', 'approved', 'Tester', '', store.target(eid, 'evidence'))
    original = {'event_id': 'original', 'title': {'value': 'Before'}, 'stages': [
        {'stage_id': 'S1', 'name': {'value': 'Stage'}, 'episodes': []}]}
    store.add_graph(eid, original)
    app = open_app(tmp_path, monkeypatch)
    pending(app)
    find(app.button, '打开图审核').click().run()
    assert app.radio(key='ui-event-section-'+eid).value == '图与修订'
    selector = find(app.selectbox, '修改字段')
    selector.set_value(selector.options.index('title / value')).run()
    find(app.text_area, '新内容').set_value('After')
    find(app.text_input, '修订说明').set_value('Correct title')
    find(app.button, '保存修订版').click().run()
    assert not app.exception
    assert [g['body']['title']['value'] for g in store.graphs(eid)] == ['After', 'Before']
    store.add_source(eid, 'New source', 'Updated evidence')
    find(app.button, '返回待处理').click().run()
    assert app.selectbox(key='ui-review-kind').options == ['全部', '材料审核']
    store.review(eid, 'evidence', 'approved', 'Tester', '', store.target(eid, 'evidence'))
    app.run()
    assert any('当前没有待处理事项' in m.value for m in app.markdown)


def test_existing_navigation_resolves_to_current_view():
    from finmy.workbench.workflow import current_page
    for page, destination, view in [('人物', '数据集', '人物事件'), ('数据', '数据集', '普通事件'),
                                    ('检索', '任务', '运行记录'), ('待审', '任务', '待处理')]:
        state = {'navigation': page}
        assert current_page(state) == destination
        assert state.get('ui-task-view', state.get('ui-dataset-kind')) == view
        assert bool(state.get('dataset-local')) == (page == '数据')
        assert (state.get('task-tool') == 'search') == (page == '检索')
        assert current_page(state) == destination


def test_return_to_queue_keeps_selected_event(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.create_events([{'event_id': 'FIRST', 'event_name_en': 'First event'},
                         {'event_id': 'SECOND', 'event_name_en': 'Second event'}])
    app = open_app(tmp_path, monkeypatch)
    pending(app)
    queue = app.selectbox(key='ui-review-selected')
    other = next('event:'+eid for eid in ['FIRST', 'SECOND'] if 'event:'+eid != queue.value)
    queue.set_value(other).run()
    find(app.button, '打开范围确认').click().run()
    find(app.button, '返回待处理').click().run()
    assert app.selectbox(key='ui-review-selected').value == other
