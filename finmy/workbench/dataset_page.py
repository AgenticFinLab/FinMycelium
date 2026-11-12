"""Dataset selection uses the common search form and controller."""
import streamlit as st

from finmy.dataset import DatasetCatalog, dataset_root, save_dataset_root
from finmy.workbench.ui import heading, empty
from finmy.workbench.workflow import navigate


def dataset_settings(store):
    st.subheader('EPG-dataset 本地路径')
    with st.form('dataset-settings'):
        root = st.text_input('数据集根目录', value=dataset_root(store.root),
                             placeholder='/path/to/EPG-dataset', key='ui-dataset-root')
        st.caption('填写运行工作台的机器上的目录。普通事件与人物事件共用，配置只保存在本地工作区。')
        if st.form_submit_button('保存数据集路径', icon=':material/folder:'):
            try:
                save_dataset_root(store.root, root)
                st.success('数据集路径已保存；未导入或改写主表')
            except (ValueError, OSError) as exc:
                st.error(str(exc))


def dataset_page(store):
    from finmy.workbench.search_page import search_form, get_controller, STATUS
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
        st.caption(f"目录 ID：{event_id} · 检索汇总：{selection['event_dir']}/search-summary.md")
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
            with st.expander(f'历史检索（{len(history)}）'):
                for tid, run in sorted(history, key=lambda r:r[1]['created_at'], reverse=True):
                    left, right = st.columns([4, 1])
                    left.write(f"{run['created_at'][:19]} · {STATUS.get(run['status'], run['status'])} · {tid[:12]}")
                    if right.button('查看任务', key='catalog-history-'+tid):
                        navigate('任务', **{'task-selected':tid, 'task_event_filter':''})
        search_form(store, catalog=selection)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.caption('请检查数据集路径、主表 ID 和研究计划对应章节。')
        if st.button('前往设置', icon=':material/settings:'):
            navigate('设置')
