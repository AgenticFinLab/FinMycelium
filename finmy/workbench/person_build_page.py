"""Material confirmation and native person-event drafts in the shared workbench."""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from finmy.dataset import within
from finmy.search.state import digest
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.domain import encoded
from finmy.workbench.workflow import navigate
from finmy.workbench.ui import stats, status


def create_person_build(store, controller, task_id, data):
    st.subheader('构建本条人物 event')
    st.caption('确认当前实际材料和已知缺口，保存为独立构建任务；模型与检索侧独立。')
    with st.form('person-build-create-'+task_id):
        model=st.text_input('人物构建 Ark 模型／接入点 ID',value=store.settings()['model'])
        with st.expander('构建上限'):
            calls=st.number_input('累计模型调用上限',min_value=1,value=40)
            tokens=st.number_input('每次输出 token 上限',min_value=1,value=12288)
            context=st.number_input('单次模型上下文字符上限',min_value=1,value=160000)
            batch=st.number_input('连续正文抽取批次字符数',min_value=401,value=12000)
            local_reads=st.number_input('局部读取累计次数上限',min_value=0,value=24)
            local_chars=st.number_input('局部读取累计字符上限',min_value=1,value=48000)
            repair=st.checkbox('允许最多一轮最终定向修正',value=True)
            st.caption('沿用当前检索交接正文；此处不会扩大材料预算或启动补搜。')
        confirmed=st.checkbox('我已检查本次实际材料与缺口，确认用于这条 event 的构建')
        if st.form_submit_button('保存人物构建任务',type='primary'):
            try:
                tid=BuildController(store).create_person(controller,task_id,
                    dict(lm_name=model if '/' in model else 'ark/'+model,max_calls=calls,max_new_tokens=tokens,max_context_chars=context,
                         extraction_chars=batch,max_read_calls=local_reads,max_read_chars=local_chars,final_repair_rounds=int(repair)),
                    confirmed=confirmed)
                navigate('任务',**{'task-selected':tid,'task_event_filter':''})
            except (ValueError,OSError) as exc:
                st.error(str(exc))


def person_build_panel(store, controller, row, labels):
    tid=row['id'];body=row['body'];event=body['input']['user_query']['extras']['person_event']
    st.subheader(event['event_name']+' — '+event['person_name'])
    status(labels[row['status']], '人物 event 构建 · '+tid)
    st.caption(event['storyline_name']+' · '+event['event_id']+' · '+body['person_config']['lm_name'])
    st.caption('构建输出：' + body['artifact_directory'])
    run=body.get('run_state',{})
    runtime=Path(body['artifact_directory'])/'state.json'
    if runtime.is_file():
        try:
            run=json.loads(runtime.read_text())
        except (OSError, ValueError):
            st.caption('运行记录正在更新，请稍后刷新。')
    stats([('输入正文字符',f"{sum(len(s['content']) for s in body['input']['samples']):,}",'已确认的原文输入'),
           ('累计模型调用',len(run.get('calls',[])),f"上限 {body['person_config']['max_calls']}"),
           ('尝试次数',run.get('attempts',0),'恢复复用有效检查点')])
    if run.get('calls'):
        last=run['calls'][-1]
        st.caption('最近阶段：'+last.get('task_id',last.get('phase','unknown'))+' · '+last['status'])
    if run.get('execution_status'):
        st.caption('执行：'+run['execution_status']+' · 结果：'+run['result_status']+' · 绘图：'+run['render_status'])
        coverage=run.get('coverage',[])
        if coverage:
            done=sum(r['status']=='processed' for r in coverage)
            st.caption(f'正文区间处理：{done}/{len(coverage)}；部分采用或未处理的区间保留在检查结果中。')
    if row['status']=='ready':
        allowed=st.checkbox('允许本次构建调用模型接口',key='person-allow-'+tid)
        a,b=st.columns(2)
        if a.button('开始人物构建',disabled=not allowed,type='primary',key='person-start-'+tid):
            try:
                controller.start(tid,allow_network=allowed)
                st.rerun()
            except ValueError as exc:st.error(str(exc))
        if b.button('取消构建任务',key='person-cancel-'+tid):
            controller.cancel(tid);st.rerun()
    elif row['status'] in {'running','queued'}:
        st.info('构建在后台运行；阶段结果与用量会保存在本次运行目录。')
    elif row['status']=='completed':
        st.success('已保存本条 event 的原生人物 JSON 草稿，待内容与证据审核。')
    else:
        st.warning('本次尚未完整完成：'+run.get('reason',run.get('error_type',body.get('error_type',row['status']))))
        if row['status'] in {'partial','failed','interrupted','limit'}:
            if body.get('graph_schema_version') != 'person-event-1.0':
                st.info('这是历史协议任务，可查看保存的产物或重新绘图；重新构建请建立新任务。')
            cap=st.number_input('恢复后的累计调用上限',min_value=body['person_config']['max_calls'],
                                value=body['person_config']['max_calls'],key='person-resume-cap-'+tid)
            st.caption('计数保留；准备恢复不会调用模型，仍需明确启动。')
            if st.button('准备恢复构建',key='person-resume-'+tid,disabled=body.get('graph_schema_version')!='person-event-1.0'):
                try:
                    controller.prepare_person_resume(tid,max_calls=cap);st.rerun()
                except (ValueError,OSError) as exc:st.error(str(exc))
    if run.get('output'):
        try:
            graph_path=within(body['artifact_directory'],run['output'])
            graph=json.loads(graph_path.read_text())
            current=graph.get('schema_version')=='person-event-1.0'
            if (digest(graph_path.read_bytes()) if current else digest(graph))!=run['graph_sha256']:raise ValueError('Saved graph integrity mismatch')
            st.caption('已保存的草稿：'+str(graph_path))
            if current:
                stats([('Event',1,'固定当前事项'),('Stage',len(graph['stages']),'局面阶段'),
                       ('Phase',len(graph['phases']),'行为模式'),('Action',len(graph['actions']),'有依据的主体行动')])
            else:
                stats([('Event',len(graph['event']),'固定当前事项'),('活动',len(graph['activity']),'保留原始事实与证据'),
                       ('阶段',len(graph['stage']),'按已支持的过程组织')])
            st.download_button('下载人物 event JSON',encoded(graph),tid+'-epg.json',key='person-json-'+tid)
            st.subheader('本条 event 的 Gantt')
            st.caption('直接读取这份人物 JSON；全部展开。可点击图元查看原记录与证据。')
            from finmy.person_epg.rendering import read_gantt
            try:
                html = read_gantt(body['artifact_directory'], run)
                st.download_button('下载独立 Gantt HTML', html, tid+'-gantt.html', 'text/html', key='person-gantt-'+tid)
                components.html(html, height=850, scrolling=True)
            except (OSError, ValueError, KeyError):
                st.info('这份 JSON 暂无可用的配套 Gantt，可单独生成；构建草稿已保留。')
            if st.button('从已保存 JSON 重新生成 Gantt', disabled=row['status'] in {'ready','queued','running'}, key='person-render-'+tid):
                try:
                    result = controller.render_person(tid)
                    if result['status'] == 'completed':
                        st.rerun()
                    else:
                        st.error('绘图未完成（'+result.get('error_type','unknown')+'），JSON 与模型用量保持不变。')
                except (OSError, ValueError) as exc:
                    st.error(str(exc))
            st.caption('重新绘图只读取已保存 JSON，不调用搜索或模型。')
            with st.expander('原生图内容与检查结果'):
                st.json(graph,expanded=False)
                checks=within(body['artifact_directory'],run['checks'])
                st.json(json.loads(checks.read_text()),expanded=False)
        except (OSError,ValueError,KeyError) as exc:st.error(str(exc))
    elif run.get('facts'):
        with st.expander('已保存事实与未完成项'):
            facts_path=within(body['artifact_directory'],run['facts'])
            if digest(facts_path.read_bytes()) == run.get('facts_sha256'):
                st.json(json.loads(facts_path.read_text()),expanded=False)
                if run.get('checks'):
                    st.json(json.loads(within(body['artifact_directory'],run['checks']).read_text()),expanded=False)
    st.caption('JSON 和 Gantt 均为待内容审核的草稿；当前不启动审核 Skill，也不会自动收录到正式数据集。')
    with st.expander('本次范围、输入与运行记录'):
        st.json(event,expanded=False)
        st.write('运行目录：'+body['artifact_directory'])
        st.json(run,expanded=False)
        st.download_button('下载已确认构建输入',encoded(body['input']),tid+'-input.json',key='person-input-'+tid)
        st.download_button('下载来源交接记录',encoded(body['provenance']),tid+'-provenance.json',key='person-provenance-'+tid)
