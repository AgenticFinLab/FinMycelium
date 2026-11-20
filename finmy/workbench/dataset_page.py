"""Dataset selection uses the common search form and controller."""
import json
import os
from pathlib import Path
import streamlit as st

from finmy.dataset import DatasetCatalog, dataset_root, save_dataset_root, output_directory, summary_directory
from finmy.workbench.ui import empty, local_timestamp, status
from finmy.workbench.workflow import navigate
from finmy.workbench.material_status import confirmations, confirmed_builds
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.build_page import build_status


def dataset_settings(store=None):
    from finmy.workbench.workspace import select_workspace
    from finmy.workbench.records import export_all
    st.subheader('EPG-dataset 本地路径')
    with st.form('dataset-settings'):
        root = st.text_input('数据集根目录', value=dataset_root(store.root) if store else '',
                             placeholder='/path/to/EPG-dataset', key='ui-dataset-root')
        st.caption('普通事件与人物事件共用。数据库和原始运行资料保存在 output/workbench/；共享任务记录保存在 workbench/。')
        if st.form_submit_button('保存数据集路径', icon=':material/folder:'):
            try:
                if store and os.environ.get('FINMY_WORKBENCH_HOME'):
                    save_dataset_root(store.root, root)
                else:
                    select_workspace(Path(__file__).resolve().parents[2], root,
                                     current=store.root if store else None)
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))

    if store is None:
        return
    root = dataset_root(store.root)
    if root:
        try:
            st.caption('构建输出：' + str(output_directory(root, 'builds')))
            st.caption('草稿和运行记录保存在 output/，审核后再收录到正式事件目录。')
            st.caption('共享任务记录：' + str(Path(root) / 'workbench'))
            if st.button('更新共享记录', icon=':material/sync:'):
                results = export_all(store.root)
                if any(r['status'] == 'failed' for r in results):
                    st.error('部分记录导出失败，原任务仍保留；请检查目录权限后重试。')
                else:
                    st.success('共享记录已更新；未启动任务，也未提交 Git。')
            failures = [p for p in (store.root / 'record-exports').glob('*.json')
                        if json.loads(p.read_text()).get('status') == 'failed']
            if failures:
                st.warning(f'{len(failures)} 项共享记录待重新导出；原任务与结果不受影响。')
        except ValueError as exc:
            st.warning(str(exc))


def _catalog_identity(record):
    return tuple(record.get(k) for k in ('root', 'kind', 'person_id', 'event_id'))


@st.cache_data(max_entries=2048, show_spinner=False)
def _search_identity(run_path, modified_ns):
    """Cache only routing metadata. Atomic run-file updates invalidate the entry."""
    run = json.loads(run_path.read_text(encoding='utf-8'))
    task = run['task']
    state = 'excluded' if run.get('build_disposition') == 'excluded' else run['status']
    return _catalog_identity(task.get('catalog', {})), task.get('event_id'), run['created_at'], state


def catalog_searches(controller):
    for tid in controller.tasks():
        path = controller.root / tid / 'runs/initial/run.json'
        yield tid, *_search_identity(path, path.stat().st_mtime_ns)


def event_tasks(store, controller, selection):
    identity = _catalog_identity(selection)
    records = []
    local_ids = set()
    for tid, ref, local_id, created, _ in catalog_searches(controller):
        if ref == identity:
            records.append((created, tid, '检索'))
            if local_id:
                local_ids.add(local_id)
    builds = BuildController(store)
    related = []
    for eid in {selection['event_id']} | local_ids:
        for row in builds.tasks(eid):
            ref = row['body'].get('catalog')
            if (ref and _catalog_identity(ref) == identity) or (not ref and eid in local_ids):
                related.append(row)
                records.append((row['created'], row['id'], '构建'))
    return sorted(records, reverse=True), related


def _open_task(task_id):
    navigate('任务', **{'task-selected': task_id, 'task_event_filter': ''})


def ordinary_catalog(store):
    from finmy.workbench.search_page import search_form, get_controller
    from finmy.workbench.workflow import search_status_label
    try:
        catalog = DatasetCatalog(dataset_root(store.root))
        rows = catalog.events()
        if not rows:
            empty('事件目录为空', '可在 event-epg/events.csv 登记普通事件，或打开本机事件记录。')
            return
        events = {r['event_id']: r for r in rows}
        key = 'ui-dataset-event-ordinary'
        if st.session_state.get(key) not in events: st.session_state.pop(key, None)
        event_id = st.selectbox('选择普通事件', list(events),
            format_func=lambda e: f"{events[e]['event_name']} · {events[e]['period']} · {events[e].get('status', '')}", key=key)
        selection = catalog.select(event_id)
        with st.expander('研究说明与来源线索'):
            st.caption(f"目录 ID：{event_id} · 检索汇总：{summary_directory(selection) / 'search-summary.md'}")
            st.markdown(selection.get('research_description') or selection['description'])
            if selection.get('source_leads'):
                for lead in selection['source_leads']:
                    st.write(lead['record'] if isinstance(lead, dict) else lead)
        controller = get_controller(str(store.root / 'search'))
        history, builds = event_tasks(store, controller, selection)
        if history:
            created, tid, kind = history[0]
            if kind == '构建':
                row = BuildController(store).reconcile(tid)
                label = build_status(row)[1]
            else:
                data = {**controller.inspect(tid), 'task_id': tid}
                label = search_status_label(data, confirmed_builds(tid, data, confirmations(builds)))
            st.subheader('继续工作')
            status(label, f'{kind} · {local_timestamp(created)} · {tid[:12]}')
            if st.button(f'打开{kind}任务', type='primary', key='catalog-open-'+tid):
                _open_task(tid)
            if len(history) > 1:
                with st.expander(f'其他任务（{len(history) - 1}）'):
                    for date, other, category in history[1:]:
                        if st.button(f'{category} · {local_timestamp(date)} · {other[:12]}', key='catalog-history-'+other):
                            _open_task(other)
            if not st.toggle('新建另一项检索', key='catalog-new-'+tid):
                return
        search_form(store, catalog=selection, previous_task=history[0][1] if history else '')
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.caption('请检查数据集路径、主表 ID 和研究计划对应章节。')
        if st.button('前往设置', icon=':material/settings:'):
            navigate('设置')
