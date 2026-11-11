from pathlib import Path
import socket

import pytest
from streamlit.testing.v1 import AppTest

from finmy.dataset import DatasetCatalog, save_dataset_root
from finmy.search.control import SearchController
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
    find(app.sidebar.button, '数据集').click().run()
    find(app.radio, '目录类型').set_value('人物事件').run()
    assert not app.exception
    assert find(app.text_input, '本次研究时期').value.startswith('1990s')
    find(app.text_input, '本次研究时期').set_value('1995')
    find(app.text_area, '本次纳入范围').set_value('Appointment in 1995')
    find(app.selectbox, '检索模式').set_value('simple')
    find(app.checkbox, '确认本次研究范围与保存目录').check()
    find(app.button, '保存检索任务').click().run(timeout=30)
    assert not app.exception
    tid = controller.tasks()[0]
    assert calls == []
    assert controller.inspect(tid)['task']['research_scope']['period'] == '1995'
    find(app.button, '开始／继续').click().run(timeout=30)
    controller.threads[tid].join(5)
    assert not controller.active(tid)
    app.run()
    assert not app.exception
    assert controller.inspect(tid)['status'] == 'finished'
    assert calls == ['search']
    assert not store.events()


def test_catalog_immediate_start_is_explicit(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.sidebar.button, '数据集').click().run()
    find(app.selectbox,'检索模式').set_value('simple')
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
    assert not any(x.label == '选择 event' for x in app.selectbox)
    assert not controller.tasks() and not calls


def test_existing_independent_search_and_date_filter_preserved(setup):
    root, store, controller, calls = setup
    app = AppTest.from_file(str(APP)).run(timeout=30)
    find(app.sidebar.button,'新建检索').click().run()
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
