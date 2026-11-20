"""Browse person catalogs, local runs and formally collected event artifacts."""

from collections import defaultdict
from functools import partial

import streamlit as st

from finmy.dataset import DatasetCatalog, component, dataset_root, within
from finmy.search.state import digest
from finmy.workbench import search_page
from finmy.workbench.build_page import LABELS
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.catalog_actions import search_collection
from finmy.workbench.dataset_page import catalog_searches
from finmy.workbench.graph_collection import graph_collection, reviewed_artifacts
from finmy.workbench.person_build_page import person_build_form
from finmy.workbench.review_selection import select_for_review, selected_review, withdraw_selection
from finmy.workbench.ui import empty, local_timestamp
from finmy.workbench.workflow import SEARCH_STATUS, navigate


def _event_tasks(store, root, person_id):
    searches, builds = defaultdict(list), defaultdict(list)
    controller = search_page.get_controller(str(store.root / 'search'))
    for tid, ref, _, created, state in catalog_searches(controller):
        if ref[:3] == (str(root), 'person_event', person_id):
            searches[ref[3]].append((created, tid, SEARCH_STATUS.get(state, state)))
    for group in searches.values():
        group.sort(reverse=True)
    for row in BuildController(store).person_task_headers(root, person_id):
        builds[(row['storyline_id'], row['event_id'])].append(row)
    return searches, builds


def _collection_status(ref, row, category, fallback):
    try:
        if category == 'search':
            current = search_collection(ref)
        else:
            current = graph_collection(ref)
            if not current and (row.get('status') == 'accepted' or any(row.get(k) for k in ('epg_path', 'gantt_path', 'review_path'))):
                raise ValueError('主表登记的正式成果缺失')
        return ('已收录' if current else fallback), ''
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return '收录待核对', str(exc)


def _open_task(task_id):
    navigate('任务', **{'task-selected': task_id, 'task_event_filter': ''})


def _build_label(row):
    return '已舍弃' if row['disposition'] == 'discarded' else LABELS.get(row['status'], row['status'])


def _drafts(rows):
    return [row for row in rows if row['status'] == 'completed' and row['disposition'] != 'discarded']


def _material_section(store, ref, current, searches, scope):
    st.markdown('#### 检索材料')
    if current:
        manifest = current['manifest']
        st.write(f"已收录 · {manifest['input_sample_count']} 份材料 · {manifest['input_characters']:,} 字符")
        with st.popover('查看已收录材料'):
            for handoff in manifest['search_handoffs']:
                st.caption(f"检索 {handoff['search_task_id']} · 交接版本 {handoff['handoff_revision']}")
                for gap in handoff.get('gaps', []):
                    st.write(gap)
            for name, data in current['files'].items():
                st.download_button(name, data, name, key='person-material-'+name, on_click='ignore')
        if 'builder-input.json' in current['files']:
            key = 'collected-' + current['sha256']
            opened = st.session_state.get('person-build-form') == key
            button_label = '收起构建设置' if opened else '用已收录材料创建构建'
            if st.button(button_label, type='secondary' if opened else 'primary', key='open-'+key):
                st.session_state['person-build-form'] = None if opened else key
                st.rerun()
            if opened:
                save_task = partial(BuildController(store).create_person_from_collection, ref,
                                    expected_manifest=current['sha256'])
                person_build_form(store, key, save_task)
        else:
            st.caption('这份历史收录只有检索汇总和来源清单。完整正文可从原检索任务核对。')
    elif not searches:
        st.caption('尚无已收录的检索材料。')
    with st.container(horizontal=True):
        if searches and st.button('打开检索任务', help='查看本事件最近一次检索'):
            _open_task(searches[0][1])
        previous = searches[0][1] if searches else ''
        form_id = digest([ref, previous])
        opened = st.session_state.get('person-search-form') == form_id
        label = '收起检索设置' if opened else ('重新检索' if current or searches else '准备检索')
        if st.button(label, disabled=scope is None):
            st.session_state['person-search-form'] = None if opened else form_id
            st.rerun()
    if opened and scope:
        search_page.search_form(store, catalog=scope, previous_task=previous)


def _graph_section(store, ref, rows, material, accepted):
    st.markdown('#### 事件图')
    if accepted:
        with st.popover('查看成果', type='primary', icon=':material/folder_open:'):
            meta = accepted['review']
            st.caption(f"审核人 {meta['reviewer']} · 构建任务 {meta['build_task_id']}")
            for name, raw in accepted['files'].items():
                st.download_button(name, raw, name, key='person-result-'+name, on_click='ignore')
        return
    controller = BuildController(store)
    selected = selected_review(ref)
    if selected:
        st.write('已选送审版本 · ' + selected['binding']['build_task_id'])
        with st.container(horizontal=True):
            if st.button('查看待处理', key='pending-'+digest(selected)):
                navigate('任务', **{'ui-task-view': '待处理', 'review-queue-event': selected['binding']['build_task_id']})
            if st.button('撤回送审', key='withdraw-review-'+digest(selected)):
                try:
                    withdraw_selection(ref, expected_selection=digest(selected))
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
    drafts = _drafts(rows)
    if not drafts:
        if rows:
            st.caption('最近构建 · ' + _build_label(rows[0]))
            if st.button('打开构建任务'):
                _open_task(rows[0]['id'])
        elif not selected:
            st.caption('尚无本机构建任务。')
        return
    current_hash = material['manifest']['input_sha256'] if material else None
    exact = [r for r in drafts if current_hash and r['input_hash'] == current_hash]
    other = [r for r in drafts if not current_hash or r['input_hash'] != current_hash]
    if current_hash:
        st.caption(f'当前收录材料有 {len(exact)} 份草稿，其他材料版本有 {len(other)} 份。')
    versions = {r['id']: r for r in (*exact, *other)}
    def label(task_id):
        row = versions[task_id]
        model = (row['model'] or '').split('/')[-1]
        match = ('当前材料' if row['input_hash'] == current_hash else '其他材料') if current_hash else '未比对材料'
        return ' · '.join(filter(None, (match, model, local_timestamp(row['created']), task_id)))
    task_id = st.selectbox('选择待查看的草稿', list(versions), format_func=label, index=None,
                           placeholder='选择一个构建版本', key='person-review-draft-'+digest(ref))
    if not task_id:
        return
    if st.button('打开构建任务'):
        _open_task(task_id)
    try:
        binding = reviewed_artifacts(controller.inspect(task_id))['binding']
        header = versions[task_id]
        st.caption(f"输入 {header['input_hash'][:12]} · 图 {binding['graph_sha256'][:12]} · "
                   f"交接版本 {header['handoff_revision'] or '未记录'}")
        if selected and selected['binding'] == binding:
            st.caption('可在任务中心的「待处理」领取这一版。')
        else:
            key = 'select-review-'+digest([binding, selected])
            if st.button('将此版本送审' if not selected else '改送此版本', key=key, type='primary'):
                select_for_review(controller, ref, binding, expected_selection=digest(selected))
                st.rerun()
    except (ValueError, OSError, KeyError) as exc:
        st.warning(f'暂不能送审 · {exc}')


def _history(searches, builds):
    runs = [(created, tid, '检索', status) for created, tid, status in searches]
    runs.extend((r['created'], r['id'], '构建', _build_label(r)) for r in builds)
    if runs:
        with st.expander(f'历史任务（{len(runs)}）'):
            options = {tid: f'{kind} · {status} · {local_timestamp(created)} · {tid}'
                       for created, tid, kind, status in sorted(runs, reverse=True)}
            tid = st.selectbox('历史任务', options, format_func=options.get, label_visibility='collapsed')
            if st.button('查看历史任务'):
                _open_task(tid)


def _show_person(store, catalog, person):
    pid = person['person_id']
    plan = within(catalog.root / 'person-epg', person['research_plan'])
    rows = catalog.events(pid)
    stories = {r['storyline_id']: r['storyline_name'] for r in rows}
    st.caption(f"{pid} · {len(stories)} 条 storyline · {len(rows)} 个 event")
    if person.get('coverage'):
        st.write(person['coverage'])
    with st.container(horizontal=True):
        for path, label in [(plan, '研究计划'), (plan.with_name('sources.csv'), '来源索引')]:
            file = within(catalog.root / 'person-epg', path.relative_to(catalog.root / 'person-epg'))
            if file.is_file():
                st.download_button(label, file.read_bytes(), file.name, icon=':material/download:')
            else:
                st.caption(label + '尚未提供')
    if not rows:
        empty('尚无事件', '此人物的 events.csv 中还没有事件。')
        return
    story_key = 'ui-person-story-'+pid
    if st.session_state.get(story_key, '') and st.session_state[story_key] not in stories:
        st.session_state.pop(story_key, None)
    story = st.selectbox('按 storyline 筛选', ['', *stories], format_func=lambda k: stories.get(k, '全部 storyline'),
                         key=story_key)
    searches, builds = _event_tasks(store, catalog.root, pid)
    records, details = [], []
    for row in rows:
        if story and row['storyline_id'] != story:
            continue
        eid = row['event_id']
        relative = plan.parent.relative_to(catalog.root) / component(row['storyline_name']) / component(row['event_name'])
        ref = dict(kind='person_event', root=str(catalog.root), person_id=pid, event_id=eid,
                   storyline_id=row['storyline_id'], event_dir=str(relative))
        search, build = searches[eid], builds[(row['storyline_id'], eid)]
        material, material_error = _collection_status(ref, row, 'search', search[0][2] if search else '待检索')
        graph_fallback = _build_label(build[0]) if build else '待构建'
        if _drafts(build):
            graph_fallback = LABELS['completed']
        try:
            if selected_review(ref):
                graph_fallback = '已选稿，待内容审核'
        except (ValueError, OSError, KeyError, TypeError):
            graph_fallback = '送审记录待核对'
        graph, graph_error = _collection_status(ref, row, 'epg', graph_fallback)
        records.append({'Storyline': row['storyline_name'], 'Event': row['event_name'], '时期': row['period'],
                        '检索材料': material, '事件图': graph})
        details.append((ref, search, build, material_error, graph_error))

    # Row indices belong to exactly this filtered catalog and order.
    table_key = 'person-events-' + digest([str(catalog.root), pid, story, [r[0]['event_id'] for r in details]])[:16]
    table = st.dataframe(records, hide_index=True, width='stretch', height=min(425, 38 * len(records) + 42),
                         column_config={name: st.column_config.TextColumn(width=width)
                                        for name, width in [('Storyline', 150), ('Event', 240), ('时期', 165),
                                                            ('检索材料', 108), ('事件图', 130)]},
                         on_select='rerun', selection_mode='single-row', key=table_key)
    event_ids = [item[0]['event_id'] for item in details]
    focus_key = 'person-event-' + digest([str(catalog.root), pid, story])
    if table.selection.rows:
        st.session_state[focus_key] = event_ids[table.selection.rows[0]]
    focus = st.session_state.get(focus_key)
    index = event_ids.index(focus) if focus in event_ids else 0
    ref, search, build, material_error, graph_error = details[index]
    current = records[index]
    st.subheader(current['Event'])
    st.caption(f"{ref['event_id']} · {current['Storyline']} · {current['时期']}")
    scope = None
    with st.expander('研究范围与来源线索'):
        try:
            scope = catalog.select(ref['event_id'], pid)
            st.markdown(scope.get('research_description') or scope['description'])
            for lead in scope.get('source_leads', []):
                st.write(lead['record'])
        except (ValueError, OSError) as exc:
            st.caption(f'研究计划中的说明待核对 · {exc}')
    if material_error:
        st.warning(material_error)
    material = search_collection(ref) if current['检索材料'] == '已收录' else None
    _material_section(store, ref, material, search, scope)
    if graph_error:
        st.warning(graph_error)
    else:
        _graph_section(store, ref, build, material, graph_collection(ref) if current['事件图'] == '已收录' else None)
    _history(search, build)


def person_data_page(store):
    try:
        catalog = DatasetCatalog(dataset_root(store.root))
        people = {person['person_id']: person for person in catalog.people()}
        if not people:
            empty('人物目录为空', '请先在 person-epg/people.csv 登记人物。')
            return
        pid = st.selectbox('选择人物', list(people), format_func=lambda pid: people[pid]['name'], key='ui-person-data')
        _show_person(store, catalog, people[pid])
    except (OSError, ValueError) as exc:
        st.error(str(exc))
