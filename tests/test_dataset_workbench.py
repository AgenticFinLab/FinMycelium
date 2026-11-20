from dataclasses import asdict
from pathlib import Path
import socket

import pytest
from streamlit.testing.v1 import AppTest

from finmy.dataset import DatasetCatalog, save_dataset_root
from finmy.search.control import SearchController
from finmy.search.state import SearchConfig
from finmy.workbench.store import Store
from finmy.workbench.search_bridge import create_catalog_search
from finmy.workbench import search_page
from dataset_fixture import fixture_dataset, csv_file, EVENT_FIELDS

APP = Path(__file__).resolve().parents[1] / 'finmy/workbench/app.py'


def find(items, label):
    return next(item for item in items if item.label == label)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No real network'))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = fixture_dataset(tmp_path / 'dataset')
    workspace = tmp_path / 'workbench'
    monkeypatch.setenv('FINMY_WORKBENCH_HOME', str(workspace))
    store = Store(workspace)
    save_dataset_root(workspace, str(root))
    calls = []
    def transport(*args):
        calls.append('search')
        return {'data':{'webPages':{'value':[{'url':'https://example.org/a','name':'Synthetic source'}]}}}
    controller = SearchController(workspace / 'search', transport=transport,
        fetcher=lambda u:(b'An invented appointment occurred in 1995.', 'txt', 'utf-8'))
    monkeypatch.setattr(search_page, 'get_controller', lambda root: controller)
    return root, store, controller, calls


def test_scope_confirmation_required_before_creation(setup):
    root, store, controller, calls = setup
    selection = DatasetCatalog(root).select('EVENT-TEST')
    with pytest.raises(ValueError, match='确认'):
        create_catalog_search(store, controller, selection, {}, 'simple', period='2020',include='Closing',exclude='')
    assert not controller.tasks() and not store.events() and not calls
    tid = create_catalog_search(store, controller, selection, {}, 'simple', period='2020',include='Closing',exclude='',confirmed=True)
    task = controller.inspect(tid)['task']
    assert task['catalog']['event_id'] == 'EVENT-TEST'
    assert task['event_id'].startswith('CAT-')
    assert store.decision(task['event_id'], 'scope') == 'approved'
    assert store.decision(task['event_id'], 'evidence') is None
    assert controller.inspect(tid)['status'] == 'ready'
    assert calls == []


def test_person_task_never_uses_eventcascade_record(setup):
    root, store, controller, calls = setup
    selection = DatasetCatalog(root).select('PERSON-EVENT-TEST','PERSON-TEST')
    tid = create_catalog_search(store,controller,selection,{},'simple',period='1990s',include='Term',exclude='',confirmed=True)
    assert 'event_id' not in controller.inspect(tid)['task']
    assert store.events() == []
    assert not calls


def test_dataset_settings_save_does_not_import_or_call(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.sidebar.button, '设置').click().run()
    find(app.text_input, '数据集根目录').set_value(str(root))
    find(app.button, '保存数据集路径').click().run()
    assert not app.exception
    assert not controller.tasks() and not store.events() and not calls


def test_person_selection_save_then_start_offline(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.radio, '目录类型').set_value('人物事件').run()
    assert not app.exception
    assert not any(x.label == '保存检索任务' for x in app.button)
    find(app.button, '准备检索').click().run()
    assert find(app.text_input, '本次研究时期').value.startswith('1990s')
    find(app.text_input, '本次研究时期').set_value('1995')
    find(app.text_area, '本次纳入范围').set_value('Appointment in 1995')
    find(app.selectbox, '检索模式').set_value('simple')
    find(app.multiselect, '搜索服务').set_value(['bocha'])
    find(app.checkbox, '确认本次研究范围与保存目录').check()
    find(app.button, '保存检索任务').click().run(timeout=30)
    assert not app.exception
    tid = controller.tasks()[0]
    assert calls == []
    assert controller.inspect(tid)['task']['research_scope']['period'] == '1995'
    find(app.button, '开始／继续').click().run(timeout=30)
    controller.threads[tid].join(5)
    assert not controller.active(tid)
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.radio, '目录类型').set_value('人物事件').run()
    find(app.button, '打开检索任务').click().run()
    assert app.session_state['task-selected'] == tid
    assert not app.exception
    assert controller.inspect(tid)['status'] == 'finished'
    assert calls == ['search']
    assert not store.events()


def test_catalog_immediate_start_is_explicit(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.selectbox,'检索模式').set_value('simple')
    find(app.multiselect, '搜索服务').set_value(['bocha'])
    find(app.checkbox,'确认本次研究范围与保存目录').check()
    find(app.checkbox,'允许启动后调用外部搜索与模型').check()
    find(app.button,'确认并开始搜索').click().run(timeout=30)
    assert not app.exception
    tid = controller.tasks()[0]
    controller.threads[tid].join(5)
    assert controller.inspect(tid)['status'] == 'finished'
    assert calls == ['search']


def test_empty_catalog_shows_no_legacy_rows(setup):
    root, store, controller, calls = setup
    csv_file(root / 'event-epg/events.csv', EVENT_FIELDS, [])
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.sidebar.button,'数据集').click().run()
    assert not app.exception
    assert not any(x.label == '选择普通事件' for x in app.selectbox)
    assert not controller.tasks() and not calls


def test_existing_independent_search_and_date_filter_preserved(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.button(key='nav-任务').click().run()
    find(app.button, '独立与批量检索').click().run()
    find(app.text_input,'研究对象').set_value('Standalone synthetic event')
    find(app.text_area,'研究要求').set_value('Investigate the invented closing')
    find(app.text_input,'资料发表开始日期').set_value('2020-01-01')
    find(app.button,'保存检索任务').click().run()
    assert not app.exception
    data = controller.inspect(controller.tasks()[0])
    assert data['config']['publication_start'] == '2020-01-01'
    assert 'catalog' not in data['task'] and not calls


def test_dataset_history_can_be_filtered_in_task_center(setup):
    root,store,controller,calls = setup
    selection = DatasetCatalog(root).select('PERSON-EVENT-TEST','PERSON-TEST')
    tid=create_catalog_search(store,controller,selection,{},'simple',period='1995',include='Appointment',exclude='',confirmed=True)
    app=AppTest.from_file(str(APP)).run(timeout=30)
    find(app.sidebar.button,'任务中心').click().run()
    options=find(app.selectbox,'按事件筛选').options
    assert any('Example appointment' in x for x in options)
    # Streamlit's test Selectbox stores the underlying key, not the formatted label.
    from finmy.workbench.domain import digest
    key='catalog:'+digest([selection['root'],selection['kind'],selection['person_id'],selection['event_id']])[:20]
    find(app.selectbox,'按事件筛选').set_value(key).run()
    assert not app.exception and not calls
    assert controller.inspect(tid)['status']=='ready'


def test_home_defaults_and_new_task_after_override(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert find(app.selectbox, '选择普通事件').value == 'EVENT-TEST'
    assert find(app.expander, '调整配置')
    assert not controller.tasks() and not calls
    find(app.number_input, '交付材料字符总上限').set_value(12345)
    find(app.radio, '目录类型').set_value('人物事件').run()
    find(app.button, '准备检索').click().run()
    find(app.checkbox, '确认本次研究范围与保存目录').check()
    find(app.button, '保存检索任务').click().run()
    assert not app.exception
    tid, = controller.tasks()
    assert controller.inspect(tid)['config'] == asdict(SearchConfig())
    find(app.sidebar.button, '数据集').click().run()
    assert find(app.button, '打开检索任务')
    assert not any(b.label == '保存检索任务' for b in app.button)
    find(app.button, '重新检索').click().run()
    assert not find(app.checkbox, '确认本次研究范围与保存目录').value
    assert controller.tasks() == [tid] and not calls


def test_home_matches_build_to_catalog_and_opens_task(setup):
    from finmy.workbench.build_tasks import BuildController
    root, store, controller, calls = setup
    selection = DatasetCatalog(root).select('EVENT-TEST')
    tid = create_catalog_search(store, controller, selection, {}, 'simple', period='2020',
                                include='Closing', exclude='', confirmed=True)
    event_id = controller.inspect(tid)['task']['event_id']
    store.add_source(event_id, 'Example', text='An invented closing.')
    store.review(event_id, 'evidence', 'approved', 'Tester', '', store.target(event_id, 'evidence'))
    bid = BuildController(store).create(event_id, store.settings())
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.button, '打开构建任务').click().run()
    assert not app.exception and app.session_state['task-selected'] == bid
    assert not calls


def test_batch_scopes_and_independent_config_are_isolated(setup):
    _, store, controller, calls = setup
    ids = store.create_events([dict(event_name_en=name, description=name+' timeline', scope_include=name)
                               for name in ('First', 'Second')])
    for eid in ids:
        store.review(eid, 'scope', 'approved', 'Tester', '', store.target(eid, 'scope'))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.button(key='nav-任务').click().run()
    find(app.button, '独立与批量检索').click().run()
    find(app.number_input, '交付材料字符总上限').set_value(4321).run()
    find(app.radio, '任务来源').set_value('本机普通事件').run()
    assert not any(b.label == '保存检索任务' for b in app.button)
    find(app.multiselect, '选择本机事件（可批量）').set_value(ids).run()
    assert find(app.number_input, '交付材料字符总上限').value == SearchConfig().max_builder_material_chars
    find(app.button, '保存检索任务').click().run(timeout=30)
    assert not app.exception and not calls
    results = [controller.inspect(tid) for tid in controller.tasks()]
    assert {d['task']['event_id'] for d in results} == set(ids)
    for d in results:
        event = store.event(d['task']['event_id'])
        assert d['task']['query_text'] == event['description']
        assert d['task']['scope_include'] == event['scope_include']
        assert d['status'] == 'ready' and not d['config']['allow_network']


def test_open_task_directly_without_enumerating_other_searches(setup, monkeypatch):
    root, store, controller, calls = setup
    selection = DatasetCatalog(root).select('EVENT-TEST')
    tid = create_catalog_search(store, controller, selection, {}, 'simple',
        period='2020', include='Closing', exclude='', confirmed=True)
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.button, '打开检索任务').click().run()
    monkeypatch.setattr(controller, 'tasks', lambda: pytest.fail('Unrelated searches scanned'))
    app.run()
    assert not app.exception and app.session_state['task-selected'] == tid
    assert find(app.button, '返回任务列表') and find(app.button, '开始／继续') and not calls
