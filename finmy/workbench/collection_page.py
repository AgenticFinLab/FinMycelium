"""Small explicit collection controls in the existing task panels."""
import streamlit as st

from .catalog_actions import collected_search, confirm_search, search_collection, withdraw_search
from .graph_collection import (build_collection, collect_graph, graph_collection,
                               review_template, withdraw_graph)


def search_collection_panel(controller, task_id, data, *, active=False, read_only=False):
    catalog = data['task']['catalog']
    with st.expander('确认交接与收录', expanded=False):
        st.caption('确认材料后即可收录到事件 search/；之后可另建构建任务。')
        try:
            current = search_collection(catalog)
        except (ValueError, OSError, KeyError) as exc:
            st.error(str(exc)); return
        matches = collected_search(data, task_id)
        if matches:
            st.success('当前交接版本已收录')
        elif current:
            st.info('此事件已有另一份确认材料；再次确认将采用当前版本，已有构建输入保留。')
        if read_only or active: return
        reviewer = st.text_input('确认人', key='search-collector-'+task_id)
        approved = st.checkbox('我已检查实际交接材料与已知缺口', key='search-confirm-'+task_id)
        if st.button('确认并收录检索材料', key='collect-search-'+task_id,
                     disabled=not approved or not reviewer.strip() or not data.get('builder_input') or bool(matches)):
            try:
                confirm_search(controller, task_id, expected_revision=data['handoff_revision'], reviewer=reviewer, confirmed=True)
                st.rerun()
            except (ValueError, OSError, KeyError) as exc: st.error(str(exc))
        if current:
            reason = st.text_input('撤回原因', key='withdraw-search-reason-'+task_id)
            st.caption('撤回移出正式目录并保留归档；原始检索和已创建构建的固定输入保留。')
            if st.button('撤回事件检索收录', key='withdraw-search-'+task_id, disabled=not reviewer.strip() or not reason.strip()):
                try:
                    withdraw_search(catalog, expected_manifest=current['sha256'], reviewer=reviewer, reason=reason)
                    for handoff in current['manifest']['search_handoffs']:
                        controller._sync_records(handoff['search_task_id'])
                    st.rerun()
                except (ValueError, OSError, KeyError) as exc: st.error(str(exc))


def disposition_panel(controller, row):
    if row['status'] in {'ready', 'running', 'queued'}: return
    with st.expander('草稿采用选择'):
        discarded = row['body'].get('disposition') == 'discarded'
        st.caption('舍弃表示本次草稿不进入后续审核收录；运行状态、产物、用量和历史保留，可恢复。')
        reason = st.text_input('原因', key='discard-reason-'+row['id'])
        if st.button('恢复待审核' if discarded else '舍弃本次草稿', key='discard-'+row['id'],
                     disabled=bool(build_collection(row)) or (not discarded and not reason.strip())):
            try:
                controller.set_disposition(row['id'], 'pending' if discarded else 'discarded', reason=reason)
                st.rerun()
            except (ValueError, OSError) as exc: st.error(str(exc))


def graph_collection_panel(controller, row):
    catalog = row['body'].get('catalog')
    if not catalog or row['status'] in {'ready', 'queued', 'running'}: return
    with st.expander('内容审核与成果收录', expanded=False):
        st.caption('在界面外审核这份图，填写 review.md；确认后收录 JSON、Gantt 与审核记录，并更新主表。')
        try:
            current = graph_collection(catalog)
        except (ValueError, OSError, KeyError) as exc:
            st.error(str(exc)); return
        if current:
            st.success('事件已有审核收录成果 · '+current['review']['build_task_id'])
            for name, raw in current['files'].items():
                st.download_button('下载已收录 '+name, raw, name, key='collected-'+row['id']+'-'+name)
            reviewer = st.text_input('撤回确认人', key='graph-withdrawer-'+row['id'])
            reason = st.text_input('撤回原因', key='graph-withdraw-reason-'+row['id'])
            if st.button('撤回事件图收录', key='withdraw-graph-'+row['id'], disabled=not reviewer.strip() or not reason.strip()):
                try:
                    withdraw_graph(catalog, expected_review=current['review_sha256'], reviewer=reviewer, reason=reason)
                    st.rerun()
                except (ValueError, OSError, KeyError) as exc: st.error(str(exc))
            return
        if row['status'] != 'completed' or row['body'].get('disposition') == 'discarded':
            st.caption('完成 draft 并恢复待审核后，才可提交内容审核记录。')
            return
        try:
            template = review_template(row)
        except (ValueError, OSError, KeyError) as exc:
            st.error(str(exc)); return
        st.download_button('下载本图审核记录模板', template, 'review.md', key='review-template-'+row['id'])
        review = st.file_uploader('已完成的 review.md', type=['md'], key='review-upload-'+row['id'])
        approved = st.checkbox('确认此版本已通过内容与证据审核，允许正式收录', key='accept-graph-'+row['id'])
        if st.button('收录审核通过的图', key='collect-graph-'+row['id'], disabled=not approved or review is None):
            try:
                raw = review.getvalue()
                if len(raw) > 2*1024*1024: raise ValueError('审核记录过大')
                collect_graph(controller, row['id'], raw, confirmed=True)
                st.rerun()
            except (ValueError, OSError, KeyError) as exc: st.error(str(exc))
