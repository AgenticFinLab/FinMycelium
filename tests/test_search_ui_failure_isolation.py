"""A damaged task or original must not hide other local search results."""
import io
import json
import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from finmy.search.control import SearchController
from finmy.workbench import search_page
from test_search_workbench import evidence_model


APP = Path(__file__).resolve().parents[1] / 'finmy/workbench/app.py'


def _page(tmp_path, monkeypatch, controller, task_id=None):
    monkeypatch.setenv('FINMY_WORKBENCH_HOME', str(tmp_path))
    monkeypatch.setattr(search_page, 'get_controller', lambda root: controller)
    app = AppTest.from_file(str(APP)).run(timeout=30)
    if task_id is not None:
        app.session_state['task-selected'] = task_id
    app.button(key='nav-任务').click().run()
    return app


def _finished(controller):
    task_id = controller.create(dict(target_type='event', target_name='Deal',
                                    query_text='Trace the documented closing'), {})
    controller.start(task_id)
    controller.threads[task_id].join(5)
    assert controller.inspect(task_id)['status'] == 'finished'
    return task_id


def _controller(tmp_path):
    return SearchController(tmp_path / 'search', model=evidence_model,
        transport=lambda *args: {'data': {'webPages': {'value': [
            {'url': 'https://example.org/closing', 'name': 'Closing announcement'}]}}},
        fetcher=lambda url: (b'The transaction closed after approval.', 'txt', 'utf-8'))


def test_corrupt_task_does_not_break_task_selector(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    healthy = _finished(controller)
    broken = controller.create(dict(target_type='event', target_name='Broken',
                                    query_text='Trace another event'), {})
    (controller.root / broken / 'runs/initial/run.json').write_text('{unfinished')
    app = _page(tmp_path, monkeypatch, controller, healthy)
    assert not app.exception
    assert any('事件归属' in warning.value for warning in app.warning)
    rows = next(frame.value for frame in app.dataframe if '任务 ID' in frame.value)
    assert len(rows) == 2
    assert not app.exception
    assert any(tab.label == '资料与交接' for tab in app.tabs)
    app.session_state['task-selected'] = broken
    app.run()
    assert not app.exception
    assert any('运行记录暂时无法读取' in error.value for error in app.error)


def test_missing_original_and_reassembly_error_keep_page_usable(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    task_id = _finished(controller)
    data = controller.inspect(task_id)
    source_id, source = next(iter(data['sources'].items()))
    (controller.root / task_id / 'sources' / source_id / source['version'] / 'raw').unlink()
    app = _page(tmp_path, monkeypatch, controller)
    assert not app.exception
    assert any('此来源无法校验' in error.value for error in app.error)
    next(button for button in app.button if button.label == '重新组装').click().run()
    assert not app.exception
    assert any('本次组装未完成' in error.value for error in app.error)
    assert controller.inspect(task_id)['usage'] == data['usage']


def test_malformed_complete_manifest_is_display_error_not_page_failure(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    task_id = _finished(controller)
    (controller.root / task_id / 'runs/initial/complete_material.json').write_text(json.dumps(['invalid']))
    app = _page(tmp_path, monkeypatch, controller)
    assert not app.exception
    assert app.error or app.warning
    assert any(tab.label == '资料与交接' for tab in app.tabs)


def test_invalid_optional_sidecar_keeps_task_and_resume_control_visible(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    task_id = controller.create(dict(target_type='event', target_name='Paused',
                                    query_text='Trace the event'), {})
    run_dir = controller.root / task_id / 'runs/initial'
    state = json.loads((run_dir / 'run.json').read_text())
    state.update(status='paused', stop_reason='provider_cooldown',
                 resume={'resumable': True, 'retryable': True})
    (run_dir / 'run.json').write_text(json.dumps(state))
    (run_dir / 'selection.json').write_text('{unfinished')
    app = _page(tmp_path, monkeypatch, controller)
    assert not app.exception
    assert any('部分交接记录无法读取' in warning.value for warning in app.warning)
    assert not next(button for button in app.button if button.label == '开始／继续').disabled


def test_legacy_empty_outage_has_resume_button_without_running_calls(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    task_id = controller.create(dict(target_type='event', target_name='Interrupted',
                                    query_text='Trace the event'), {})
    run_dir = controller.root / task_id / 'runs/initial'
    state = json.loads((run_dir / 'run.json').read_text())
    state.update(status='insufficient', stop_reason='insufficient')
    (run_dir / 'run.json').write_text(json.dumps(state))
    (run_dir / 'trace.jsonl').write_text(json.dumps({'action': 'provider_result',
        'provider': 'bocha', 'status': 'failed', 'error_details': {'http_status': 403}}) + '\n')
    app = _page(tmp_path, monkeypatch, controller)
    assert not app.exception
    assert not next(button for button in app.button if button.label == '开始／继续').disabled
    assert not controller.threads
    assert controller.inspect(task_id)['usage'] == state['usage']


def test_corrupt_search_keeps_event_progress_and_export(tmp_path):
    from finmy.workbench.store import Store
    from finmy.workbench.workflow import progress
    store = Store(tmp_path)
    eid = store.create_events([{'event_name_en': 'Deal', 'description': 'A transaction',
                                'scope_include': 'The closing'}])[0]
    store.review(eid, 'scope', 'approved', 'Reviewer', '', store.target(eid, 'scope'))
    controller = _controller(tmp_path)
    healthy = controller.create(dict(target_type='event', target_name='Deal',
        query_text='Trace the closing', event_id=eid), {})
    broken = controller.create(dict(target_type='event', target_name='Broken',
        query_text='Another event'), {})
    (controller.root / broken / 'runs/initial/run.json').write_text('{unfinished')
    errors = []
    assert progress(store, eid, controller, errors=errors)[0] == 1
    assert [row['task_id'] for row in errors] == [broken]
    with zipfile.ZipFile(io.BytesIO(store.export_zip([eid]))) as archive:
        saved = json.loads(archive.read(eid + '/search_runs.json'))
        assert [row['task_id'] for row in saved] == [healthy]
        diagnosis = json.loads(archive.read('search_record_errors.json'))
        assert diagnosis == {'scope': 'unattributed', 'errors': errors}
        assert eid + '/input.json' in archive.namelist()
    assert not controller.threads
