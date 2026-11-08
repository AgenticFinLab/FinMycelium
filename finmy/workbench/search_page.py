"""Search preparation and review in the existing local workbench."""
import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from finmy.search.control import SearchController
from finmy.search.state import SearchConfig, SearchState, write_json
from finmy.search.sources import SourceStore
from finmy.workbench.domain import display_name
from finmy.workbench.search_process import render_process
from finmy.workbench.search_history import budget_policy_label, experiment_runs


@st.cache_resource
def get_controller(root):
    return SearchController(root, env_file=Path(__file__).resolve().parents[2]/'.env')


STATUS={'ready':'待启动','running':'运行中','paused':'已暂停','finished':'待检查材料',
        'insufficient':'资料不足','limit':'达到运行上限','failed':'运行失败'}


@st.fragment(run_every='1s')
def task_panel(controller, task_id, store, read_only=False):
    data=controller.inspect(task_id)
    active=controller.active(task_id)
    st.subheader(data['task']['target_name'])
    st.caption(STATUS.get(data['status'],data['status'])+' · '+task_id)
    a,b,c=st.columns(3)
    a.metric('搜索请求',f"{data['usage']['search']} / {data['config']['max_search_requests']}")
    b.metric('阅读来源',f"{len(data['read_sources'])} / {data['config']['max_read_sources']}")
    c.metric('模型请求',f"{data['usage']['model']} / {data['config']['max_model_calls']}")
    if not read_only:
        a,b,c=st.columns(3)
        ended=data['status'] in {'finished','insufficient'}
        if a.button('开始／继续',disabled=active or ended,key='start-'+task_id,type='secondary' if ended else 'primary'):
            try:
                controller.start(task_id)
                st.rerun()
            except ValueError as exc:st.error(str(exc))
        if b.button('执行一步',disabled=active or ended or data.get('mode')=='simple',key='step-'+task_id):
            try:
                controller.start(task_id,steps=1)
                st.rerun()
            except ValueError as exc:st.error(str(exc))
        if c.button('暂停',disabled=not active,key='pause-'+task_id):
            controller.pause(task_id)
            st.info('已请求暂停；当前请求结束后保存状态。')
        st.caption('执行一步 = 一次模型决策及其工具执行；联合搜索可调用多家服务。暂停会等待当前请求结束。')
    if data.get('stop_reason'):
        reasons={'fixed_queries_completed':'固定查询已完成','user_pause':'手动暂停','checkpoint':'到达检查点','model_context_limit':'上下文达到长度上限','model_limit':'达到模型调用上限','repeated_invalid_action':'连续执行错误，任务已停止','supported':'已准备可供检查的材料','low_gain':'继续补搜收益较低','insufficient':'证据不足'}
        st.caption('停止原因：'+reasons.get(data['stop_reason'],data['stop_reason']))
    if not read_only:
        with st.expander('调整运行上限'):
            with st.form('limits-'+task_id):
                values={}
                for field,label in [('max_search_requests','搜索请求上限'),('max_read_sources','阅读来源上限'),
                                    ('max_model_calls','模型请求上限'),('max_model_context_chars','模型上下文字符上限'),
                                    ('timeout','单次请求超时（秒）')]:
                    values[field]=st.number_input(label,min_value=1,value=data['config'][field],key=task_id+field)
                enabled=st.checkbox('允许此任务调用外部接口',value=data['config']['allow_network'],key='enabled-'+task_id)
                if st.form_submit_button('保存运行上限',disabled=active):
                    try:
                        controller.configure(task_id,{**values,'allow_network':enabled})
                        st.success('配置已修订，累计调用次数保留。')
                    except ValueError as exc:st.error(str(exc))
    with st.expander('研究要求'):
        st.text(data['task']['query_text'])
        st.caption('运行模型：' + str(data['config'].get('lm_name') or '简单搜索无需模型'))
    render_process(controller, task_id, data, read_only=read_only)
    sources=data['sources']
    st.subheader('资料与交接')
    if not sources:st.info('尚未取得来源。')
    else:
        st.dataframe([{'标题':s['title'],'URL':s['url'],'状态':{'success':'已获取','partial':'部分正文','unread':'未读取','empty':'无正文','fetch_failed':'获取失败','parser_failed':'解析失败'}.get(s['status'],s['status']),
                       '发现记录':len(s['discoveries'])} for s in sources.values()],hide_index=True,width='stretch')
        with st.expander('查看原文与出处'):
            sid=st.selectbox('来源',list(sources),format_func=lambda k:sources[k]['title'] or sources[k]['url'],key='source-'+task_id)
            entry=sources[sid]
            st.text(entry['url'])
            if entry.get('version'):
                try:
                    doc=SourceStore(SearchState(controller.root,task_id)).document(sid)
                    st.caption('来源版本：'+doc['version'])
                    st.text_area('已保存原文','\n\n'.join(b['text'] for b in doc['blocks']),height=220,disabled=True,key='text-'+task_id+sid)
                except ValueError as exc:st.error(str(exc))
            else:st.caption('该来源尚无可用正文。')
    source_assembly_preview(controller, task_id, data, active)
    complete=data.get('complete_material')
    if complete:
        from finmy.search.handoff import materialize_complete
        st.caption(f"完整交接材料：{len(complete['selected'])} 份来源 · {complete['material_chars']} 字符；本次输入的遗漏仍保留在完整材料中。")
        try:
            full=materialize_complete(SearchState(controller.root,task_id),complete)
            st.download_button('下载完整交接正文',json.dumps(full,ensure_ascii=False,indent=2),file_name=task_id+'-complete-material.json',mime='application/json',key='complete-download-'+str(controller.root/task_id))
        except ValueError as exc:
            st.error(str(exc))
    selection=data['selection']
    if selection:
        st.caption('本次交接策略：' + budget_policy_label(selection))
        if selection.get('mode') == 'sources' and not selection['omitted']:
            st.caption('所选完整材料已全部放入预算，本次未裁减正文。')
        for gap in selection['gaps']:st.warning('简单搜索尚未评估过程证据覆盖，请检查所收集材料。' if gap=='Simple search has no semantic coverage assessment' else gap)
        unit = '份来源' if selection.get('mode') == 'sources' else '段'
        st.caption(f"采用 {len(selection['selected'])} {unit} · 遗漏记录 {len(selection['omitted'])} 项 · {selection['material_chars']} 字符")
        st.download_button('下载 Builder 输入',json.dumps(data['builder_input'],ensure_ascii=False,indent=2),
                           file_name=task_id+'-builder-input.json',mime='application/json',key='download-'+task_id)
        st.caption('审核材料后，可将下载的输入交给独立的 Agent／Sparse build-only 构建入口。')
        if not read_only and data['task'].get('event_id') and st.button('纳入事件待审资料',disabled=active,key='adopt-'+task_id):
            from finmy.workbench.search_bridge import adopt_sources
            try:
                added=adopt_sources(controller,task_id,store)
                st.success(f'新增 {added} 份待审资料；已有相同材料自动复用。')
            except ValueError as exc:st.error(str(exc))
        if not read_only:
            with st.expander('调整本次输入长度并重新组装'):
                length=st.number_input('本次 Builder 输入字符上限',min_value=1,value=selection['max_material_chars'],key='length-'+task_id)
                if st.button('重新组装',disabled=active,key='assemble-'+task_id):
                    controller.reassemble(task_id,length)
                    st.rerun()
        with st.expander('筛选与遗漏记录'):st.json(selection)


def source_assembly_preview(controller, task_id, data, active):
    from finmy.search.handoff import prepare_complete_sources, derive_input
    candidates = [sid for sid, entry in data['sources'].items() if any(
        r['version'] == entry.get('version') and r['end'] > r['start'] for r in entry.get('read_ranges', []))]
    if not candidates:
        return
    key = str(controller.root / task_id)
    with st.expander('按来源直接组装（不调用模型）'):
        st.caption('先完整组织所选来源正文，再生成本次预算输入。能够放入预算时保留全文；超出预算时为各来源分配基础配额并共享剩余空间，保留原文段落并记录遗漏。预览不会改写已保存材料。')
        with st.form('source-package-'+key):
            kept = st.multiselect('保留来源（按优先顺序选择）', candidates, default=candidates,
                                   format_func=lambda sid:data['sources'][sid]['title'] or data['sources'][sid]['url'])
            limit = st.number_input('本次 Builder 输入字符上限', min_value=1, value=data['config']['max_builder_material_chars'])
            if st.form_submit_button('组装预览', disabled=active):
                try:
                    state = SearchState(controller.root, task_id)
                    full, complete = prepare_complete_sources(state, kept, reason='manual_preview',
                        gaps=['人工选择来源的离线组装预览；尚未进行语义完整性验收'])
                    payload, record = derive_input(state, complete, max_chars=limit)
                    st.session_state['complete-package-result-'+key] = (payload, record, full, complete)
                except ValueError as exc:
                    st.error(str(exc))
        result = st.session_state.get('complete-package-result-'+key)
        if result:
            payload, record, full, complete = result
            st.markdown('**完整交接材料**')
            st.caption(f"{len(full['samples'])} 份来源 · {complete['material_chars']} 字符；仅清理和去重，未按输入预算裁减。")
            st.download_button('下载完整交接正文',json.dumps(full,ensure_ascii=False,indent=2),file_name=task_id+'-complete-preview.json',mime='application/json',key='complete-preview-download-'+key)
            st.markdown('**本次 Builder 输入**')
            st.caption(f"上次组装结果：{len(payload['samples'])} 份来源 · {record['material_chars']} 字符。修改选择后请重新组装。")
            if record['omitted']:
                st.warning(f"有 {len(record['omitted'])} 份来源的全部或部分正文未纳入本次输入；有正文的预算遗漏仍在完整材料中，请检查清单。")
            adopted = {item['source_id']:item for item in record['selected']}
            omitted = {item['source_id'] for item in record['omitted']}
            duplicate = {item['source_id'] for item in record['duplicates']}
            st.dataframe([{'来源':data['sources'][sid]['title'] or data['sources'][sid]['url'],
                           '保留情况':('部分段落' if sid in omitted else '全部已获取正文') if sid in adopted else ('重复来源复用' if sid in duplicate else '未纳入'),
                           '交接字符':adopted.get(sid,{}).get('material_chars',0)}
                          for sid in record['source_ids']],hide_index=True,width='stretch')
            if payload['samples']:
                st.download_button('下载本次组装输入', json.dumps(payload,ensure_ascii=False,indent=2),file_name=task_id+'-source-package.json',mime='application/json',key='source-package-download-'+key)
            st.download_button('下载来源与遗漏清单', json.dumps(record,ensure_ascii=False,indent=2),file_name=task_id+'-source-selection.json',mime='application/json',key='source-selection-download-'+key)
            with st.expander('核对保留与遗漏'):
                st.json(record)


def search_page(store):
    st.title('检索与证据')
    st.caption('选择研究范围，检索并检查资料，再交给构建器。')
    with st.expander('辅助工具', expanded=st.session_state.get('search-history-open', False)):
        show_history = st.checkbox('历史实验回看（只读）', key='search-history-open')
    if show_history:
        st.subheader('历史实验回看')
        st.caption('直接读取本机实验记录；不会调用 API、恢复任务或改写实验文件。')
        records=experiment_runs(Path(__file__).resolve().parents[2])
        if not records:
            st.info('尚无可回看的本地搜索实验。')
            return
        index=st.selectbox('选择实验',range(len(records)),format_func=lambda i:records[i]['label'])
        record=records[index]
        task_panel(get_controller(str(record['root'])),record['task_id'],store,read_only=True)
        return
    root=store.root/'search'
    controller=get_controller(str(root))
    profile=root/'profile.json'
    defaults=asdict(SearchConfig())
    if profile.exists():
        defaults.update(json.loads(profile.read_text()))  # Preserve saved choices; fill newly added defaults.
    events={e['event_id']:e for e in store.events()}
    event_id=st.selectbox('从主表选择事件',['']+list(events),format_func=lambda k:'手动填写研究对象' if not k else display_name(events[k]))
    event=events.get(event_id,{})
    with st.expander('新建检索任务',expanded=not controller.tasks()):
        with st.form('create-search'):
            a,b=st.columns(2)
            kind=a.selectbox('对象类型',['event','person','company'],format_func=lambda k:{'event':'事件','person':'人物','company':'公司'}[k])
            mode=b.selectbox('检索模式',['agent','simple'],format_func=lambda k:'增强搜索' if k=='agent' else '简单搜索（固定查询）')
            name=st.text_input('研究对象',display_name(event) if event else '')
            query=st.text_area('研究要求',event.get('description',''),height=100)
            providers=st.multiselect('搜索服务',['baidu','bocha','exa'],default=defaults['providers'])
            count=st.number_input('每次查询、每家服务的结果上限',min_value=1,max_value=50,value=defaults['max_results'])
            lm_name=st.text_input('搜索侧模型',defaults.get('lm_name') or '',placeholder='provider/model；简单搜索无需填写')
            output_tokens=st.number_input('模型答案 token 上限',min_value=1,value=defaults['generation_config'].get('max_tokens',4096))
            st.caption('对当前 Ark Seed 模型，该参数仅限制答案，不包含推理 token。')
            with st.expander('范围、来源和高级配置'):
                keywords=st.text_input('关键词（逗号分隔）',','.join(event.get('keywords',[])))
                seeds=st.text_area('已有来源 URL（每行一个）','\n'.join(x for x in event.get('source_hints',[]) if x.startswith(('https://','http://'))))
                fixed=st.text_area('简单搜索查询（每行一条；留空使用对象名称与关键词）')
                options={}
                for field,label in [('max_search_requests','累计搜索请求上限'),('max_read_sources','不同阅读来源上限'),
                                    ('max_model_calls','累计模型请求上限'),('max_read_chars','单次正文字符上限'),
                                    ('max_builder_material_chars','交付材料字符总上限'),
                                    ('max_model_context_chars','模型上下文字符上限'),
                                    ('timeout','单次请求超时（秒）')]:
                    options[field]=st.number_input(label,min_value=1,value=defaults[field])
                st.caption('单次请求超时适用于搜索、正文获取和模型调用；已保存配置沿用各自设置。')
                include=st.text_input('限定站点（逗号分隔）',','.join(defaults['include_domains']))
                exclude=st.text_input('排除站点（逗号分隔）',','.join(defaults['exclude_domains']))
                start=st.text_input('资料发表开始日期',defaults['publication_start'] or '',placeholder='YYYY-MM-DD；与事件发生时间不同')
                end=st.text_input('资料发表结束日期',defaults['publication_end'] or '',placeholder='YYYY-MM-DD')
                rewrite=st.checkbox('百度 query 改写',value=defaults['baidu_rewrite'])
            enabled=st.checkbox('允许启动后调用外部搜索与模型',value=False)
            if st.form_submit_button('保存检索任务',type='primary'):
                try:
                    config=SearchConfig(**{**defaults,**options,'providers':providers,'max_results':count,
                        'lm_name':lm_name or None,'generation_config':{'max_tokens':output_tokens},
                        'allow_network':enabled,'baidu_rewrite':rewrite,
                        'include_domains':[s.strip() for s in include.split(',') if s.strip()],
                        'exclude_domains':[s.strip() for s in exclude.split(',') if s.strip()],
                        'publication_start':start or None,'publication_end':end or None})
                    task=dict(target_type=kind,target_name=name,query_text=query,
                              key_words=[s.strip() for s in keywords.split(',') if s.strip()],
                              seed_urls=[s.strip() for s in seeds.splitlines() if s.strip()])
                    if fixed.strip():task['search_queries']=[s.strip() for s in fixed.splitlines() if s.strip()]
                    for key in ('coverage_start','coverage_end','scope_include','scope_exclude','aliases'):
                        if event.get(key):task[key]=event[key]
                    if event_id:task['event_id']=event_id
                    tid=controller.create(task,config,mode)
                    write_json(profile,{**asdict(config),'allow_network':False})
                    st.session_state['search-selected']=tid
                    st.success('任务已保存，尚未发起调用。')
                except (ValueError,TypeError) as exc:st.error(str(exc))
    tasks=controller.tasks()
    if tasks:
        selected=st.selectbox('选择检索任务',tasks,format_func=lambda k:controller.inspect(k)['task']['target_name']+' · '+k[:8],index=tasks.index(st.session_state.get('search-selected')) if st.session_state.get('search-selected') in tasks else 0)
        task_panel(controller,selected,store)
    else:st.info('尚无检索任务。')
