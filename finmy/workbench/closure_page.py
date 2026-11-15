"""Small offline disposition form inside the existing person build task."""
import json
import streamlit as st
from finmy.person_epg.event.closure import load_review, pending_items


def closure_panel(controller, row):
    body = row['body']
    if body.get('graph_schema_version') != 'person-event-1.0':
        return
    try:
        review = load_review(body['artifact_directory'])
    except (ValueError, OSError, KeyError):
        return  # The main task panel reports missing/invalid or unfinished artifacts.
    items = pending_items(review)
    with st.expander('检查与收尾', expanded=row['status'] == 'partial'):
        st.caption('离线保存人工处置和修订，不调用模型。草稿完成仍需后续内容审核。')
        for revision in review['state'].get('offline_revisions', []):
            st.caption('已保存修订：' + revision['path'])
        if not items:
            st.info('没有待人工处置的 pending。其他未完成项或结构错误仍以检查结果为准。')
            return
        contexts = {c['context_id']: c for c in review['graph']['contexts']}
        evidence = {e['evidence_id']: e for e in review['graph']['evidence']}
        token = review['state_sha256'][:16]
        decisions = []
        with st.form('close-' + row['id'] + '-' + token):
            for number, item in enumerate(items, 1):
                pending = item['pending']; key = item['key']
                st.markdown(f'**{number}. {item["task_id"] or "事实记录中的待处理项"}**')
                st.write(pending['reason'])
                st.caption('涉及记录：' + json.dumps(pending['refs'], ensure_ascii=False))
                for eid in pending['evidence_ids']:
                    ev = evidence.get(eid)
                    if ev:
                        st.caption(eid + ' · ' + ev.get('source_id', ''))
                        st.write(ev['quote'])
                if not item['eligible']:
                    st.caption('继续保留待处理：此项没有符合条件的已采用 Context，或涉及实际未完成工作。')
                    continue
                resolve = st.checkbox('确认作为 Context 保留，个人归属或其他未知记为缺口', key='resolve-'+token+key)
                cid = st.selectbox('对应记录', item['context_ids'], key='context-'+token+key,
                    format_func=lambda value: value + ' · ' + contexts[value]['description'][:90])
                # Form selections do not rerender until submission; show all candidates
                # so the preview never describes a different selection.
                for candidate in item['context_ids']:
                    st.caption(candidate)
                    st.write(contexts[candidate]['description'])
                reason = st.text_area('缺口与处置说明（将写入图；建议使用英文）', key='reason-'+token+key,
                    help='说明材料已证明什么、仍不能证明什么，以及为什么当前事项已处理。未知不等于未发生。')
                if resolve:
                    decisions.append(dict(key=key, context_id=cid, reason=reason))
            reviewer = st.text_input('处置人', value='Local reviewer')
            submit = st.form_submit_button('保存处置并重新检查', type='primary')
        if submit:
            try:
                controller.close_person_pending(row['id'], decisions,
                    expected_state_sha256=review['state_sha256'], reviewer=reviewer)
                st.rerun()
            except (ValueError, OSError, KeyError) as exc:
                st.error(str(exc))
