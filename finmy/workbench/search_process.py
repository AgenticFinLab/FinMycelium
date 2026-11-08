"""Streamlit views of recorded actions, separate from search execution."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import streamlit as st
from .search_history import LABELS, read_trace, timeline

STATES = {'waiting':'进行中', 'completed':'已执行', 'warning':'需注意', 'error':'失败', 'unconfirmed':'未确认完成'}
PROVIDERS = {'baidu':'百度', 'bocha':'博查', 'exa':'Exa'}


def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')
    except (TypeError, ValueError):
        return '未记录'


def description(row, sources):
    if row['action'] == 'search':
        return row.get('query', '等待搜索结果')
    if row['action'] == 'read_source':
        source = sources.get(row.get('source'), {})
        return source.get('title') or source.get('url') or row.get('source', '')
    if row['action'] == 'finish':
        return f"选择 {row.get('selected_count', 0)} {row.get('selection_unit', '段')}，交接校验" if row['status'] != 'completed' else '材料已组装，等待人工检查'
    return '请求下一步操作' if not row['errors'] else '模型请求或动作未成功'


def render_process(controller, task_id, data, *, read_only=False):
    run_dir = controller.root / task_id / 'runs' / 'initial'
    events, incomplete = read_trace(run_dir)
    rows = timeline(events, data)
    sources = data['sources']
    st.subheader('运行过程')
    if incomplete:
        st.caption('部分过程记录尚未写完或无法解析，当前跳过；下次刷新会重新读取。')
    if data['status'] == 'running':
        if rows and rows[-1]['status'] == 'waiting':
            row = rows[-1]
            doing = '等待模型决策' if row['action'] == 'model' else LABELS.get(row['action'], row['action'])
            if row.get('pending_provider'):
                doing = '等待' + PROVIDERS.get(row['pending_provider'], row['pending_provider']) + '搜索返回'
            since = row.get('pending_since') or row['time']
            st.info(f'当前：{doing} · 开始于 {local_time(since)}（北京时间）')
        else:
            st.info('任务标记为运行中，等待下一条过程记录。')
        if read_only:
            st.caption('历史回看仅呈现已保存状态，不据此确认原执行进程仍然存活。')
    if data.get('stop_reason') == 'model_context_limit':
        st.warning('已因模型上下文过长暂停，尚未成功交接。直接继续会再次检查同一上限；这不代表资料数量不足。')
    elif data.get('status') in {'failed', 'limit'}:
        st.warning('任务尚未成功交接；查看下面的失败步骤及停止原因。')
    if not rows:
        st.caption('保存任务不会启动调用。点击“执行一步”后，这里展示一次决策及其执行结果。')
    else:
        errors = sum(bool(r['errors']) for r in rows)
        a, b, c = st.columns(3)
        a.metric('不同候选 URL', len(sources))
        b.metric('已记录步骤', len(rows))
        c.metric('出错步骤', errors)
        st.caption('搜索请求按服务分别计数；一步联合搜索可产生三次请求。以下展示操作决定与执行结果。')
        key = str(run_dir)
        with st.expander('模型用量与运行配置'):
            usage = [r['usage'] for r in rows if isinstance(r.get('usage'), dict)]
            missing = max(0, data['usage']['model'] - len(usage))
            st.write(f"已返回用量：输入 {sum(u.get('prompt_tokens',0) or 0 for u in usage):,} · 输出 {sum(u.get('completion_tokens',0) or 0 for u in usage):,} tokens")
            st.caption(f'{missing} 次调用尚无用量记录（可能运行中、超时或历史记录缺失）；输出已包含推理 token，不重复相加。此处不估算完整账单。')
            st.json({k:data['config'].get(k) for k in ('providers','lm_name','max_results','max_search_requests','max_read_sources','max_model_calls','max_read_chars','max_builder_material_chars','max_model_context_chars','timeout')})
        view = st.radio('过程筛选', ['全部步骤','搜索','阅读来源','整理交接','失败与提醒'], horizontal=True, key='filter-'+key)
        filtered = [r for r in rows if view == '全部步骤' or LABELS.get(r['action']) == view or (view == '失败与提醒' and r['status'] in {'error','warning'})]
        if not filtered:
            st.caption('暂无符合条件的步骤。')
        else:
            st.dataframe([{'步骤':r['step'], '时间（北京时间）':local_time(r['time']),
                           '操作':LABELS.get(r['action'],r['action']), '状态':STATES[r['status']],
                           '内容':description(r,sources)} for r in reversed(filtered)],
                         hide_index=True, width='stretch', height=min(380, 38*len(filtered)+40))
            selected = st.selectbox('查看步骤详情', [r['step'] for r in reversed(filtered)],
                                    format_func=lambda n:f'第 {n} 步', key='detail-'+key+'-'+view)
            row = next(r for r in filtered if r['step'] == selected)
            st.markdown(f"**{LABELS.get(row['action'],row['action'])} · {STATES[row['status']]}**")
            if row.get('model_call'):
                timing = f" · 模型响应 {row['duration']:.1f} 秒" if row.get('duration') is not None else ''
                st.caption(f"模型调用 #{row['model_call']}{timing}")
            if row['action'] == 'search':
                st.text(row.get('query',''))
                st.markdown('**为什么搜索**')
                st.text(row.get('gap') or '本条记录未提供理由（可能是初始查询或简单搜索）。')
                st.caption('这是 Agent 当时给出的理由，尚不代表缺口判断正确。')
                if row['providers']:
                    st.dataframe([{'服务':PROVIDERS.get(p['provider'],p['provider']),
                                   '结果':{'success':'成功','cached':'缓存复用','no_results':'无结果','failed':'失败','limit':'达到上限'}.get(p.get('status'),p.get('status')),
                                   '返回条数':str(p['result_count']) if p.get('result_count') is not None else '未记录',
                                   '耗时（秒）':str(p['duration_seconds']) if p.get('duration_seconds') is not None else '未记录', '错误':p.get('error_type') or '—'}
                                  for p in row['providers']], hide_index=True, width='stretch')
                if 'candidate_count' in row:
                    st.caption(f"本轮去重候选 {row['candidate_count']} 个 · 首次在搜索结果中出现 {row['new_count']} 个；来源不等于有效证据。")
                    with st.expander('本轮发现的来源'):
                        st.dataframe([{'标题':sources.get(sid,{}).get('title',''), 'URL':sources.get(sid,{}).get('url',sid)} for sid in row['source_ids']], hide_index=True, width='stretch')
            elif row['action'] == 'read_source':
                source = sources.get(row.get('source'),{})
                st.text(source.get('title',''))
                st.text(source.get('url',row.get('source','')))
                if row.get('location'):
                    st.caption('读取位置：段落编号 ' + str(row['location'].get('block',0)) + '，字符起点 ' + str(row['location'].get('offset',0)) + '（从 0 开始）')
                if 'chars' in row:
                    st.caption(f"本次返回 {row['chars']:,} 字符、{row['span_count']} 个片段 · {'已到保存文本末尾' if row.get('at_end') else '可继续读取'}")
                    if row.get('read_status') == 'partial':
                        st.caption('部分正文：保存文本读完不代表原始文档完整。')
                    with st.expander('本次实际读到的文本'):
                        st.text_area('本次片段', '\n\n'.join(s.get('text','') for s in row.get('spans',[])),height=240,disabled=True,key='spans-'+key+'-'+str(selected))
            elif row['action'] == 'finish':
                if row.get('source_ids'):
                    st.dataframe([{'保留来源':sources.get(sid,{}).get('title',sid),'URL':sources.get(sid,{}).get('url','')} for sid in row['source_ids']],hide_index=True,width='stretch')
                if row.get('sample_count') is not None:
                    st.caption(f"实际组装 {row['sample_count']} 份材料；预算遗漏见资料与交接。")
                if row['status'] == 'completed':
                    st.success('交接已生成，内容和证据仍需审核。')
                else:
                    st.warning('这只是一次交接尝试，尚未成功通过校验。')
                st.caption('停止理由：' + {'supported':'认为关键过程已有支持','low_gain':'认为继续补搜收益较低','insufficient':'资料不足'}.get(row.get('reason'),str(row.get('reason','未记录'))))
                for gap in row.get('gaps',[]):
                    st.text('待确认：' + gap)
            for error in row['errors']:
                name = error.get('error','执行失败')
                hint = error.get('hint',error.get('kind',''))
                friendly = {'APITimeoutError':'模型请求超时；未返回用量不能当作零费用。',
                            'Invalid selection offsets':'选定片段的字符位置超出原文，交接被拒绝。',
                            'Unknown review evidence ID':'选择的证据编号不在本次可选范围内。'}.get(hint) or {'APITimeoutError':'模型请求超时；未返回用量不能当作零费用。'}.get(name)
                st.error(friendly or f'{name}：{hint}')
                if friendly:
                    st.caption(f'{name} · {hint}')
        # Export the display ledger, not raw API/model response bodies or credentials.
        ledger = [{k:v for k,v in r.items() if k not in {'spans','decision'}} for r in rows]
        st.download_button('下载过程记录', json.dumps(ledger,ensure_ascii=False,indent=2),
                           file_name=task_id+'-process.json',mime='application/json',key='process-export-'+key)
