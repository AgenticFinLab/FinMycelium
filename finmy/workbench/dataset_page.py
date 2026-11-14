"""Dataset selection uses the common search form and controller."""
import json
import os
from pathlib import Path
import streamlit as st

from finmy.dataset import DatasetCatalog, dataset_root, save_dataset_root, output_directory, summary_directory
from finmy.workbench.ui import heading, empty
from finmy.workbench.workflow import navigate
from finmy.workbench.material_status import confirmed_builds, saved_confirmations


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


def dataset_page(store):
    from finmy.workbench.search_page import search_form, get_controller
    from finmy.workbench.workflow import search_status_label
    heading('数据集', '选择一个 event，确认本次范围后使用公共搜索。')
    try:
        catalog = DatasetCatalog(dataset_root(store.root))
        kind = st.radio('目录类型', ['普通事件', '人物事件'], horizontal=True, key='ui-dataset-kind')
        st.caption(str(catalog.root))
        person_id = None
        if kind == '人物事件':
            people = {r['person_id']: r for r in catalog.people()}
            if not people:
                empty('人物目录为空', '请先在 person-epg/people.csv 登记研究计划。')
                return
            if st.session_state.get('ui-dataset-person') not in people:
                st.session_state.pop('ui-dataset-person', None)
            person_id = st.selectbox('选择人物', list(people), format_func=lambda p: people[p]['name'], key='ui-dataset-person')
        rows = catalog.events(person_id)
        if not rows:
            empty('事件目录为空', '当前主表只有模板或没有记录；不会自动读取旧 data/ 目录。')
            return
        if person_id:
            stories = {r['storyline_id']: r['storyline_name'] for r in rows}
            key = 'ui-dataset-story-' + person_id
            if st.session_state.get(key, '') not in ['', *stories]: st.session_state.pop(key, None)
            story = st.selectbox('按 storyline 筛选（可选）', ['', *stories],
                                 format_func=lambda s: stories[s] if s else '全部 storyline', key=key)
            rows = [r for r in rows if not story or r['storyline_id'] == story]
        events = {r['event_id']: r for r in rows}
        key = 'ui-dataset-event-' + (person_id or 'ordinary')
        if st.session_state.get(key) not in events: st.session_state.pop(key, None)
        event_id = st.selectbox('选择 event', list(events),
            format_func=lambda e: f"{events[e]['event_name']} · {events[e]['period']} · {events[e].get('status', '')}", key=key)
        selection = catalog.select(event_id, person_id)
        st.caption(f"目录 ID：{event_id} · 检索汇总：{summary_directory(selection) / 'search-summary.md'}")
        if person_id:
            st.info('每次任务处理一条 event：先检索，确认材料后再创建人物构建任务。')
        with st.expander('研究说明与来源线索'):
            st.markdown(selection.get('research_description') or selection['description'])
            if selection.get('source_leads'):
                for lead in selection['source_leads']:
                    st.write(lead['record'] if isinstance(lead, dict) else lead)
        controller = get_controller(str(store.root / 'search'))
        history = []
        for tid in controller.tasks():
            run = controller.inspect(tid)
            ref = run['task'].get('catalog', {})
            if all(ref.get(k) == selection.get(k) for k in ('root', 'kind', 'event_id', 'person_id')):
                history.append((tid, run))
        if history:
            adopted = saved_confirmations(store.root)
            with st.expander(f'历史检索（{len(history)}）'):
                for tid, run in sorted(history, key=lambda r:r[1]['created_at'], reverse=True):
                    left, right = st.columns([4, 1])
                    left.write(f"{run['created_at'][:19]} · {search_status_label(run, confirmed_builds(tid, run, adopted))} · {tid[:12]}")
                    if right.button('查看任务', key='catalog-history-'+tid):
                        navigate('任务', **{'task-selected':tid, 'task_event_filter':''})
        search_form(store, catalog=selection)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.caption('请检查数据集路径、主表 ID 和研究计划对应章节。')
        if st.button('前往设置', icon=':material/settings:'):
            navigate('设置')
