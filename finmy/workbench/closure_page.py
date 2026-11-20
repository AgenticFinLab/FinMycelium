"""Inspect a person build's outstanding work and save a version-bound offline decision."""
import json

import streamlit as st

from finmy.person_epg.event.closure import load_review, pending_items
from finmy.person_epg.event.closure_support import support_groups
from finmy.person_epg.event.records import pointer

NAMES = {'contexts': '背景', 'relation_candidates': '关系候选', 'actions': '行动'}
MODES = {'O': '原文件记载', 'A': '事实主张', 'I': '推断'}


def _passage(ev, sources):
    source = sources.get(ev['source_id'], {})
    st.caption(f"{source.get('title') or ev['source_id']} · {ev['sample_id']} · {ev['start']}–{ev['end']}")
    st.text(ev['quote'])


def _supports(supports, evidence, sources):
    seen = set()
    for support in supports:
        ids = support['evidence_ids']
        st.write(f"{support['target']} · {MODES.get(support['mode'], support['mode'])} · " + '、'.join(ids))
        for eid in ids:
            if eid in evidence and eid not in seen:
                _passage(evidence[eid], sources)
                seen.add(eid)


def _support_details(group, evidence, sources):
    repeated = group['kind'] == 'repeated_candidate'
    if repeated:
        st.write('抽取提案使用了已有记录的 ID。已核对事实字段，两版的差异仅涉及引证。')
    else:
        st.write('全文补读建议给已有事实追加引文。检查发现，拟追加引文与现有引证对该字段的支持方式不同。')
    st.caption(group['ref']['object_id'] + ' · 图中对应记录 ' + group['retained_id'])
    kept, extracted = group['retained'], group['record']
    st.write(kept.get('description') or kept.get('name') or group['retained_id'])
    current, proposed = st.columns(2)
    with current.expander('现有依据与已知缺口', expanded=True):
        _supports(kept.get('support', []), evidence, sources)
        for gap in kept.get('gaps', []):
            st.write(gap['target'] + ' · ' + gap['reason'])
        if group['ref']['collection'] == 'relation_candidates' and extracted.get('description') != kept.get('description'):
            st.caption('抽取阶段的关系候选')
            st.write(extracted['description'])
    with proposed.expander('拟追加的引证与原文', expanded=True):
        for change in group['changes']:
            if 'quote' in change:
                st.write(f"{change['target']} · {MODES[change['mode']]}")
                st.caption('该引文拟支持的字段内容')
                st.write(pointer(kept, change['target']))
                _passage(change['quote'], sources)
            else:
                _supports(change['supports'], evidence, sources)
    st.caption('关联的原始步骤：' + '、'.join(m['item']['task_id'] for m in group['members']))


def _checklist(review, items, groups):
    state = review['state']
    return json.dumps(dict(run_id=state['run_id'], state_sha256=review['state_sha256'],
        artifacts={field: dict(path=state[field], sha256=state[hash_key]) for field, hash_key in
                   [('facts', 'facts_sha256'), ('output', 'graph_sha256'), ('checks', 'checks_sha256')]},
        input_sha256=state['input_sha256'], coverage=state['coverage'], issues=review['checks']['issues'],
        unresolved_tasks=review['checks']['unresolved_tasks'], pending=[i['pending'] for i in items],
        support_groups=[dict(key=g['key'], ref=g['ref'], kind=g['kind'],
                             steps=[m['item']['task_id'] for m in g['members']]) for g in groups]),
        ensure_ascii=False, indent=2)


def closure_panel(controller, row):
    body = row['body']
    from .build_tasks import person_graph_version
    from finmy.person_epg.event.schema import GRAPH_VERSION
    if person_graph_version(body) != GRAPH_VERSION:
        return
    with st.expander('检查与收尾', expanded=row['status'] == 'partial'):
        try:
            review = load_review(body['artifact_directory'])
            items = pending_items(review)
            groups = support_groups(review, items)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            st.error(f'无法核对本次运行的图、事实或检查记录。请检查构建输出目录。{exc}')
            return
        state = review['state']
        if state['result_status'] == 'draft' and not items:
            st.success('结构收尾已完成。可到「数据集 → 人物事件」选择这份草稿送审。')
        for revision in state.get('offline_revisions', []):
            st.caption('已保存修订：' + revision['path'])
        if state['result_status'] == 'draft' and not items:
            return
        covered = {m['item']['key'] for group in groups for m in group['members']}
        gaps = [item for item in items if item['eligible']]
        others = [item for item in items if not item['eligible'] and item['key'] not in covered]
        choices = {g['key']: g for g in groups}
        choices.update((item['key'], item) for item in gaps)
        done = sum(c['body_status'] == 'processed' for c in state['coverage'])
        st.write(f"正文已读取 {done}/{len(state['coverage'])} 个区间 · 结构错误 {review['checks']['summary']['errors']} 项 · "
                 f"待处理记录 {len(items)} 条 · 可在此核对 {len(choices)} 项")
        st.download_button('下载本次收尾清单', _checklist(review, items, groups),
            row['id']+'-closure.json', mime='application/json', key='closure-list-'+row['id'], on_click='ignore')
        if others:
            with st.expander(f'需要单独复核的记录（{len(others)} 条）', expanded=not choices):
                for item in others:
                    st.write((item['task_id'] or '事实记录') + ' · ' + item['pending']['reason'])
        if not choices:
            st.info('此处没有可直接处置的提案。可将收尾清单交给离线复核，并从本次构建输出目录核对固定输入和检查记录。')
            return
        scope = row['id']+'-'+review['state_sha256'][:16]
        def label(key):
            choice = choices[key]
            if 'members' in choice:
                ref = choice['ref']
                return f"{NAMES[ref['collection']]} · {ref['object_id']} · {len(choice['members'])} 条记录"
            return f"保留背景并记录缺口 · {choice['task_id']} · {key[:8]}"
        key = st.selectbox('选择收尾事项', list(choices), format_func=label, key='closure-item-'+scope)
        choice = choices[key]
        evidence = {e['evidence_id']: e for package in (review['facts'], review['graph']) for e in package['evidence']}
        sources = {s['source_id']: s for package in (review['facts'], review['graph']) for s in package['sources']}
        token = scope+'-'+key
        if 'members' in choice:
            _support_details(choice, evidence, sources)
        else:
            st.write(choice['pending']['reason'])
            for eid in choice['pending']['evidence_ids']:
                if eid in evidence:
                    _passage(evidence[eid], sources)
        st.caption('保存后生成一份修订并重新检查。若要采纳新引证，或仍需核对，可保留此项并下载清单。')
        with st.form('close-'+token):
            if 'members' in choice:
                acknowledged = []
                for member in choice['members']:
                    if member.get('reported'):
                        item = member['item']
                        st.write(item['task_id']+' · '+item['pending']['reason'])
                        if st.checkbox('这条修正说明仅涉及本次补充引证，已逐条核对',
                                       key='ack-'+token+item['key']):
                            acknowledged.append(item['key'])
                confirmed = st.checkbox('保留已有记录及原有依据，退回上述补充引证', key='confirm-'+token)
                decision = dict(key=key, outcome='decline_support_change', acknowledged_pending=acknowledged)
            else:
                contexts = {c['context_id']: c for c in review['graph']['contexts']}
                cid = st.selectbox('对应记录', choice['context_ids'], key='context-'+token,
                    format_func=lambda k: k + ' · ' + contexts[k]['description'])
                confirmed = st.checkbox('保留该背景，并将尚缺的个人归属或其他信息记为缺口', key='confirm-'+token)
                decision = dict(key=key, context_id=cid)
            reason = st.text_area('处置理由', key='reason-'+token, help='说明已有材料支持什么、为什么这样处置。写入图的缺口建议用英文。')
            reviewer = st.text_input('处置人', key='reviewer-'+token)
            submit = st.form_submit_button('保存处置并重新检查', type='primary')
        if submit:
            if not confirmed or not reviewer.strip() or not reason.strip():
                st.warning('请勾选本项处置，填写处置理由和处置人。')
                return
            try:
                controller.close_person_pending(row['id'], [dict(decision, reason=reason)],
                                                expected_state_sha256=review['state_sha256'], reviewer=reviewer)
                st.session_state['notice'] = '已保存离线修订并重新检查。'
                st.rerun()
            except (ValueError, OSError, KeyError) as exc:
                st.error(str(exc))
