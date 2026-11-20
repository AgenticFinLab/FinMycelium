import csv
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dataset_fixture import csv_file, PROGRESS_FIELDS
from test_catalog_actions import approved, draft
from finmy.workbench.graph_collection import collect_graph
from test_event_collection import setup, offline, finish
from finmy.dataset import catalog_event_directory
from finmy.workbench.search_bridge import create_catalog_search

APP = Path(__file__).resolve().parents[1] / 'finmy/workbench/app.py'


def open_people(store, monkeypatch):
    monkeypatch.setenv('FINMY_WORKBENCH_HOME', str(store.root))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.radio(key='ui-dataset-kind').set_value('人物事件').run()
    assert not app.exception and not app.error
    return app


def table(app):
    return next(item.value for item in app.dataframe if '检索材料' in item.value.columns)


def test_filter_and_prepare_exact_event(setup, monkeypatch):
    root, store, search, calls = setup
    path = root / 'person-epg/Example Person/events.csv'
    with path.open() as stream:
        original, = csv.DictReader(stream)
    extra = dict(original, storyline_id='OTHER', storyline_name='Other storyline', event_id='OTHER-EVENT', event_name='Other event')
    csv_file(path, PROGRESS_FIELDS, [extra, original])
    app = open_people(store, monkeypatch)
    assert len(table(app)) == 2
    app.selectbox(key='ui-person-story-PERSON-TEST').set_value('STORY-TEST').run()
    assert list(table(app)['Event']) == ['Example appointment']
    next(b for b in app.button if b.label == '准备检索').click().run()
    assert not app.exception and not app.error
    assert not any(item.label == '选择普通事件' for item in app.selectbox)
    assert app.text_input and any(item.label == '本次研究时期' and item.value.startswith('1990s') for item in app.text_input)
    assert not search.tasks() and not calls


def test_multiple_runs_one_row_and_receipt_validation(setup, monkeypatch):
    from finmy.workbench.catalog_actions import confirm_search
    root, store, search, calls = setup
    tid, ref = finish(setup)
    confirm_search(search, tid, expected_revision=search.inspect(tid)['handoff_revision'], reviewer='Tester', confirmed=True)
    latest = create_catalog_search(store, search, ref, {}, 'simple', period='1995', include='Term',
                                   exclude='', confirmed=True)
    app = open_people(store, monkeypatch)
    assert list(table(app)['检索材料']) == ['已收录'] and list(table(app)['事件图']) == ['待构建']
    (catalog_event_directory(ref)/'search/sources.csv').write_text('changed')
    app.run()
    assert list(table(app)['检索材料']) == ['收录待核对']
    next(b for b in app.button if b.label == '打开检索任务').click().run()
    assert not app.exception and app.session_state['task-selected'] == latest


def test_draft_accepted_and_damaged_graph(setup, draft, monkeypatch):
    root, builds, bid, ref = draft
    app = open_people(builds.store, monkeypatch)
    assert list(table(app)['事件图']) == ['已生成草稿，待审核']
    collect_graph(builds, bid, approved(builds, bid), confirmed=True)
    app.run()
    assert list(table(app)['事件图']) == ['已收录']
    assert any(b.label == 'gantt.html' for b in app.get('download_button'))
    (catalog_event_directory(ref)/'epg/epg.json').write_text('{}')
    app.run()
    assert list(table(app)['事件图']) == ['收录待核对']
    assert not any(b.label == 'gantt.html' for b in app.get('download_button'))


def test_create_from_collected_material_in_fresh_checkout(setup, tmp_path, monkeypatch):
    import json
    import shutil
    import pytest
    from finmy.dataset import DatasetCatalog
    from finmy.search.state import digest
    from finmy.workbench.build_tasks import BuildController
    from finmy.workbench.catalog_actions import confirm_search, search_collection
    from finmy.workbench.records import find_build_record
    from finmy.workbench.store import Store
    from finmy.workbench.workspace import select_workspace

    root, _, search, calls = setup
    tid, ref = finish(setup)
    receipt = confirm_search(search, tid, expected_revision=search.inspect(tid)['handoff_revision'],
                             reviewer='Collector', confirmed=True)
    new_root = tmp_path/'another-checkout'
    for folder in ('person-epg', 'event-epg', 'workbench/collections'):
        shutil.copytree(root/folder, new_root/folder)
    store = Store(select_workspace(tmp_path/'other-code', new_root))
    builds = BuildController(store)
    catalog = DatasetCatalog(new_root).select(ref['event_id'], ref['person_id'])
    original = search_collection(catalog)
    fixed = json.loads(original['files']['builder-input.json'])
    with pytest.raises(ValueError, match='确认'):
        builds.create_person_from_collection(catalog, expected_manifest=original['sha256'])
    with pytest.raises(ValueError, match='变化'):
        builds.create_person_from_collection(catalog, expected_manifest='superseded', confirmed=True)
    assert not builds.tasks()
    app = open_people(store, monkeypatch)
    next(b for b in app.button if b.label == '用已收录材料创建构建').click().run()
    assert not builds.tasks() and not app.exception
    next(c for c in app.checkbox if '我已检查本次实际材料' in c.label).check()
    next(b for b in app.button if b.label == '保存人物构建任务').click().run(timeout=30)
    assert not app.exception and not app.error
    row, = builds.tasks()
    body = row['body']
    assert row['status'] == 'ready' and body['input'] == fixed and builds.current(row)
    assert body['input_hash'] == original['manifest']['input_sha256'] == digest(fixed)
    assert body['catalog']['root'] == str(new_root)
    assert not Path(body['artifact_directory']).exists() and not (store.root/'search'/tid).exists()
    assert body['provenance']['search_task_id'] == tid
    assert body['provenance']['collected_input']['receipt_id'] == receipt['action_id']
    shared = json.loads(find_build_record(new_root, row['id']).read_text())
    assert shared['search_handoff']['collected_input']['manifest_sha256'] == original['sha256']
    assert search_collection(catalog)['files'] == original['files'] and calls == ['search']


def test_one_selected_draft_per_event_with_exact_version_binding(draft):
    import json
    import pytest
    from finmy.search.state import digest
    from finmy.workbench.graph_collection import reviewed_artifacts
    from finmy.workbench.review_selection import select_for_review, selected_review, withdraw_selection, review_queue
    root, builds, first, ref = draft
    row = builds.inspect(first)
    second = 'PBUILD-second'
    (builds.root/second).mkdir(parents=True)
    with builds.store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)',
                   (second, ref['event_id'], json.dumps(row['body']), 'completed', row['created']))
    one = reviewed_artifacts(row)['binding']
    two = reviewed_artifacts(builds.inspect(second))['binding']
    assert review_queue(root) == ([], [])
    with pytest.raises(ValueError, match='草稿已变化'):
        select_for_review(builds, ref, {**one, 'graph_sha256': '0'*64}, expected_selection=digest(None))
    choice = select_for_review(builds, ref, one, expected_selection=digest(None))
    assert select_for_review(builds, ref, one, expected_selection=digest(None)) == choice
    assert review_queue(root) == ([choice], [])
    with pytest.raises(ValueError, match='送审选择已变化'):
        select_for_review(builds, ref, two, expected_selection=digest(None))
    with pytest.raises(ValueError, match='另一版本'):
        collect_graph(builds, second, approved(builds, second), confirmed=True)
    replaced = select_for_review(builds, ref, two, expected_selection=digest(choice))
    with pytest.raises(ValueError, match='已变化'):
        withdraw_selection(ref, expected_selection=digest(choice))
    assert review_queue(root) == ([replaced], [])
    assert not (catalog_event_directory(ref)/'epg').exists()
    withdraw_selection(ref, expected_selection=digest(replaced))
    assert not selected_review(ref)
    select_for_review(builds, ref, one, expected_selection=digest(None))
    builds.set_disposition(first, 'discarded', reason='Retire test draft')
    assert review_queue(root) == ([], [])
    with pytest.raises(ValueError, match='舍弃'):
        select_for_review(builds, ref, one, expected_selection=digest(None))
    select_for_review(builds, ref, two, expected_selection=digest(None))
    collect_graph(builds, second, approved(builds, second), confirmed=True)
    assert not selected_review(ref) and review_queue(root) == ([], [])


def test_older_input_remains_selectable_and_queue_contains_only_nomination(setup, draft, monkeypatch):
    from zipfile import ZipFile
    from io import BytesIO
    from finmy.search.state import digest
    from finmy.workbench.catalog_actions import confirm_search, search_collection
    from finmy.workbench.graph_collection import reviewed_artifacts
    from finmy.workbench.person_review_page import _review_bundle
    from finmy.workbench.review_selection import selected_review
    root, builds, bid, ref = draft
    _, store, search, calls = setup
    tid, _ = finish(setup)
    confirm_search(search, tid, expected_revision=search.inspect(tid)['handoff_revision'],
                   reviewer='Tester', confirmed=True)
    collection = search_collection(ref)
    assert collection['manifest']['input_sha256'] != builds.inspect(bid)['body']['input_hash']
    ordinary, = store.create_events([{'event_name_en': 'Ordinary event', 'description': 'A local event',
                                      'scope_include': 'Documented actions'}])
    app = open_people(store, monkeypatch)
    assert any('当前收录材料有 0 份草稿，其他材料版本有 1 份' in c.value for c in app.caption)
    next(s for s in app.selectbox if s.label == '选择待查看的草稿').set_value(bid).run()
    next(b for b in app.button if b.label == '将此版本送审').click().run()
    assert not app.exception and not app.error
    assert list(table(app)['事件图']) == ['已选稿，待内容审核']
    item = selected_review(ref)
    assert item['binding']['build_task_id'] == bid
    app.button(key='nav-任务').click().run()
    app.radio(key='ui-task-view').set_value('待处理').run()
    assert not app.exception and not app.error
    queue = app.selectbox(key='ui-review-selected')
    assert len(queue.options) == 2
    assert any('Example appointment' in label for label in queue.options)
    assert any('Ordinary event' in label for label in queue.options)
    app.selectbox(key='ui-review-kind').set_value('范围确认').run()
    assert app.selectbox(key='ui-review-selected').value == 'event:'+ordinary
    app.button(key='nav-数据集').click().run()
    next(b for b in app.button if b.label == '查看待处理').click().run()
    assert app.selectbox(key='ui-review-selected').value == bid
    assert app.selectbox(key='ui-review-kind').value == '全部'
    next(b for b in app.button if b.label == '打开送审构建').click().run()
    next(b for b in app.button if b.label == '返回待处理').click().run()
    assert app.selectbox(key='ui-review-selected').value == bid
    assert any(b.label == '下载审核包' for b in app.get('download_button'))
    artifacts = reviewed_artifacts(builds.inspect(bid))
    with ZipFile(BytesIO(_review_bundle(artifacts))) as archive:
        for name, field in [('epg.json', 'graph_sha256'), ('gantt.html', 'gantt_sha256'), ('input.json', 'input_sha256')]:
            assert digest(archive.read(name)) == item['binding'][field]
        assert 'decision: pending' in archive.read('review.md').decode()
    assert not (catalog_event_directory(ref)/'epg').exists() and calls == ['search']


def test_build_bound_collection_reuses_frozen_payload_without_republishing(setup, monkeypatch):
    from finmy.workbench.build_tasks import BuildController
    from finmy.workbench.catalog_actions import search_collection
    _, store, search, calls = setup
    tid, catalog = finish(setup)
    builds = BuildController(store)
    first = builds.create_person(search, tid, confirmed=True)
    current = search_collection(catalog)
    assert current['manifest']['format_version'] == 2
    def unexpected_freeze(*args, **kwargs):
        raise AssertionError('Expected to reuse the frozen catalog input')
    monkeypatch.setattr('finmy.person_epg.input.freeze_search_input', unexpected_freeze)
    second = builds.create_person_from_collection(catalog, expected_manifest=current['sha256'], confirmed=True)
    assert builds.inspect(second)['body']['input'] == builds.inspect(first)['body']['input']
    assert search_collection(catalog)['files'] == current['files']
    assert builds.inspect(second)['body']['provenance']['collected_input']['receipt_id'] == first
    assert calls == ['search']


def test_team_queue_in_checkout_without_original_build(draft, tmp_path, monkeypatch):
    import shutil
    from finmy.search.state import digest
    from finmy.workbench.graph_collection import reviewed_artifacts
    from finmy.workbench.review_selection import select_for_review
    from finmy.workbench.workspace import select_workspace
    from finmy.workbench.store import Store
    root, builds, bid, ref = draft
    select_for_review(builds, ref, reviewed_artifacts(builds.inspect(bid))['binding'], expected_selection=digest(None))
    other = tmp_path/'colleague'
    for folder in ('person-epg', 'event-epg', 'workbench/review'):
        shutil.copytree(root/folder, other/folder)
    colleague = Store(select_workspace(tmp_path/'reviewer-code', other))
    app = open_people(colleague, monkeypatch)
    next(b for b in app.button if b.label == '查看待处理').click().run()
    assert not app.exception and not app.error
    assert any('只有共享送审记录' in info.value for info in app.info)
    assert app.selectbox(key='ui-review-selected').value == bid
    assert not any(b.label == '下载审核包' for b in app.get('download_button'))
