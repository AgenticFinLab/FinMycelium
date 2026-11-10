"""Search preparation and review in the existing local workbench."""
import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from finmy.search.control import SearchController
from finmy.search.state import SearchConfig, SearchState
from finmy.search.sources import SourceStore
from finmy.workbench.domain import display_name
from finmy.workbench.workflow import navigate
from finmy.workbench.search_process import render_process, PROVIDERS
from finmy.workbench.ui import heading, status as show_status, stats, empty
from finmy.workbench.search_history import budget_policy_label, experiment_runs


@st.cache_resource
def get_controller(root):
    return SearchController(root, env_file=Path(__file__).resolve().parents[2]/'.env')


STATUS={'ready':'待启动','running':'运行中','paused':'已暂停','finished':'待检查材料',
        'insufficient':'资料不足','limit':'达到运行上限','failed':'运行失败'}
LOCAL_RECORD_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError)


def task_label(controller, task_id):
    try:
        return controller.inspect(task_id)['task']['target_name'] + ' · ' + task_id[:8]
    except LOCAL_RECORD_ERRORS:
        return '记录无法读取 · ' + task_id[:8]


def task_panel(controller, task_id, store, read_only=False, data=None):
    try:
        data = data if data is not None else controller.inspect(task_id)
    except LOCAL_RECORD_ERRORS as exc:
        st.error(f'此任务的运行记录暂时无法读取（{type(exc).__name__}）；其他任务仍可查看。')
        return
    active = controller.active(task_id)
    st.subheader(data['task']['target_name'])
    show_status(STATUS.get(data['status'], data['status']), '检索 · ' + task_id[:12])
    providers = ' / '.join(PROVIDERS.get(p, p) for p in data['config']['providers'])
    st.caption(providers + ' · ' + (data['config'].get('lm_name') or '使用默认模型'))
    if data.get('inspection_errors'):
        st.warning('部分交接记录无法读取，已单独列出；已保存来源和运行进度仍保留。')
        with st.expander('交接记录读取问题'):
            st.json(data['inspection_errors'])
    ended = not data.get('can_resume', data['status'] not in {'finished', 'insufficient'})
    if not read_only and not ended:
        if not data['config']['allow_network']:
            st.caption('此任务尚未允许外部调用，可在概览的“调整运行上限”中开启。')
        with st.container(horizontal=True, vertical_alignment='center'):
            if active:
                if st.button('暂停', key='pause-'+task_id):
                    controller.pause(task_id)
                    st.info('已请求暂停；当前请求结束后保存状态。')
            else:
                if st.button('开始／继续', key='start-'+task_id, type='primary'):
                    try:
                        controller.start(task_id)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                if st.button('执行一步', key='step-'+task_id):
                    try:
                        controller.start(task_id, steps=1)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    sources = data['sources']
    complete = data.get('complete_material')
    selection = data.get('selection')
    samples = (data.get('builder_input') or {}).get('samples', [])
    stats([
        ('候选来源', len(sources), '去重 URL'),
        ('已保存正文', sum(bool(s.get('version')) for s in sources.values()), '包含部分正文'),
        ('完整材料来源', len(complete.get('selected', [])) if complete else '—', '预算裁减前的选择' if complete else '当前记录未生成完整材料'),
        ('实际交接来源', len({s['raw_data_id'] for s in samples}) if selection else '—', '本次 Builder 输入'),
    ])
    overview, materials, process = st.tabs(['概览', '资料与交接', '运行记录'], default='资料与交接' if selection else '概览')
    with overview:
        st.markdown('**研究要求**')
        st.write(data['task']['query_text'])
        if data.get('stop_reason'):
            reasons={'fixed_queries_completed':'固定查询已完成', 'user_pause':'手动暂停', 'checkpoint':'到达检查点',
                     'model_context_limit':'上下文达到长度上限', 'model_limit':'达到模型调用上限',
                     'repeated_invalid_action':'连续执行错误，任务已停止', 'supported':'已准备可供检查的材料',
                     'low_gain':'继续检索收益较低', 'insufficient':'证据不足',
                     'provider_cooldown':'搜索服务暂时限流，等待后可继续',
                     'provider_blocked':'搜索服务拒绝访问，检查账户或凭据后可继续',
                     'provider_retry_exhausted':'本轮搜索服务重试已用完，稍后可继续',
                     'provider_unavailable':'搜索服务暂不可用，进度已保留',
                     'model_unavailable':'搜索模型暂不可用，进度已保留'}
            st.caption('停止原因：' + reasons.get(data['stop_reason'], data['stop_reason']))
        resume = data.get('resume')
        if data['status'] == 'paused' and isinstance(resume, dict) and resume.get('resumable'):
            st.info('任务已暂停，未判定为搜索完成。恢复后沿用已保存材料和累计额度。')
        st.markdown('**累计用量 / 上限**')
        stats([('搜索请求', f"{data['usage']['search']} / {data['config']['max_search_requests']}", '按每家服务计数'),
               ('阅读来源', f"{len(data['read_sources'])} / {data['config']['max_read_sources']}", '不同来源'),
               ('模型请求', f"{data['usage']['model']} / {data['config']['max_model_calls']}", '搜索侧模型')])
        st.caption('上限使用率不代表检索完成度。执行一步包含一次模型决策及工具执行。')
        with st.expander('范围、模型与原始配置'):
            st.json({'task_id':task_id, 'task':data['task'], 'config':data['config']}, expanded=False)
        if not read_only:
            with st.expander('调整运行上限'):
                with st.form('limits-'+task_id):
                    values = {}
                    cols = st.columns(2)
                    for i,(field,label) in enumerate([('max_search_requests','搜索请求上限'),('max_read_sources','阅读来源上限'),
                                      ('max_model_calls','模型请求上限'),('max_model_context_chars','模型上下文字符上限'),
                                      ('timeout','单次请求超时（秒）')]):
                        values[field] = cols[i%2].number_input(label, min_value=1, value=data['config'][field], key=task_id+field)
                    enabled = st.checkbox('允许此任务调用外部接口', value=data['config']['allow_network'], key='enabled-'+task_id)
                    if st.form_submit_button('保存运行上限', disabled=active):
                        try:
                            controller.configure(task_id, {**values,'allow_network':enabled})
                            st.success('配置已修订，累计调用次数保留。')
                        except ValueError as exc:
                            st.error(str(exc))
    with materials:
        material_panel(controller, task_id, store, data, active, read_only=read_only)
    with process:
        try:
            render_process(controller, task_id, data, read_only=read_only)
        except LOCAL_RECORD_ERRORS as exc:
            st.warning(f'部分过程记录无法展示（{type(exc).__name__}），材料仍可检查。')


def material_panel(controller, task_id, store, data, active, read_only=False):
    selection = data.get('selection')
    if selection:
        st.caption(f"实际交接 {selection['material_chars']:,} / {selection['max_material_chars']:,} 字符 · " + ("完整材料保留预算遗漏的原文" if data.get("complete_material") else "原始正文保存在来源记录中"))
        if not read_only and data['task'].get('event_id') and st.button('纳入事件待审资料',disabled=active,key='adopt-'+task_id,type='primary',icon=':material/fact_check:'):
            from finmy.workbench.search_bridge import adopt_sources
            try:
                added=adopt_sources(controller,task_id,store)
                navigate('数据', detail_id=data['task']['event_id'], **{'ui-event-section-'+data['task']['event_id']:'资料与输入'}, notice=f'新增 {added} 份待审资料，请在资料与输入页签检查并确认。')
            except ValueError as exc:st.error(str(exc))

    sources=data['sources']
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
                except LOCAL_RECORD_ERRORS as exc:
                    st.error(f'此来源无法校验（{type(exc).__name__}），请检查其他来源。')
            else:st.caption('该来源尚无可用正文。')
    source_assembly_preview(controller, task_id, data, active, read_only=read_only)
    complete=data.get('complete_material')
    if complete:
        from finmy.search.handoff import materialize_complete
        try:
            st.caption(f"完整交接材料：{len(complete['selected'])} 份来源 · {complete['material_chars']} 字符；本次输入的遗漏仍保留在完整材料中。")
            full=materialize_complete(SearchState(controller.root,task_id),complete)
            st.download_button('下载完整交接正文',json.dumps(full,ensure_ascii=False,indent=2),file_name=task_id+'-complete-material.json',mime='application/json',key='complete-download-'+str(controller.root/task_id))
        except LOCAL_RECORD_ERRORS as exc:
            st.error(f'完整交接材料无法校验（{type(exc).__name__}），已保存来源仍可逐项检查。')
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
        st.caption('当前保存的交接版本。纳入事件后，在资料页确认实际输入，再创建构建任务。')
        if not read_only:
            with st.expander('调整本次输入长度并重新组装'):
                length=st.number_input('本次 Builder 输入字符上限',min_value=1,value=selection['max_material_chars'],key='length-'+task_id)
                if st.button('重新组装',disabled=active,key='assemble-'+task_id):
                    try:
                        controller.reassemble(task_id,length)
                        st.rerun()
                    except LOCAL_RECORD_ERRORS as exc:
                        st.error(f'本次组装未完成（{type(exc).__name__}），原始材料仍保留。')
        with st.expander('筛选与遗漏记录'):st.json(selection)


def source_assembly_preview(controller, task_id, data, active, read_only=False):
    from finmy.search.handoff import prepare_complete_sources, derive_input
    candidates = [sid for sid, entry in data['sources'].items()
        if isinstance(entry, dict) and not entry.get('quarantine') and any(
            isinstance(r, dict) and r.get('version') == entry.get('version')
            and type(r.get('end')) is int and type(r.get('start')) is int
            and r['end'] > r['start'] for r in entry.get('read_ranges', []))]
    if not candidates:
        return
    key = str(controller.root / task_id)
    with st.expander('高级：人工选择来源与组装预览'):
        st.caption('先完整组织所选来源正文，再生成本次预算输入。能够放入预算时保留全文；超出预算时为各来源分配基础配额并共享剩余空间，保留原文段落并记录遗漏。预览不会改写已保存材料。')
        with st.form('source-package-'+key):
            kept = st.multiselect('保留来源', candidates, default=candidates,
                                   format_func=lambda sid:data['sources'][sid]['title'] or data['sources'][sid]['url'])
            limit = st.number_input('本次 Builder 输入字符上限', min_value=1, value=data['config']['max_builder_material_chars'])
            if st.form_submit_button('组装预览', disabled=active):
                try:
                    state = SearchState(controller.root, task_id)
                    full, complete = prepare_complete_sources(state, kept, reason='manual_preview',
                        gaps=['人工选择来源的离线组装预览；尚未进行语义完整性验收'])
                    payload, record = derive_input(state, complete, max_chars=limit)
                    st.session_state['complete-package-result-'+key] = (payload, record, full, complete)
                except LOCAL_RECORD_ERRORS as exc:
                    st.error(f'所选材料无法组装（{type(exc).__name__}）；请排除有问题的来源后重试。')
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
            if payload['samples'] and not read_only:
                if st.button('保存预览为当前交接版本', disabled=active, key='save-preview-'+key):
                    from finmy.workbench.search_bridge import save_preview
                    try:
                        save_preview(controller, task_id, complete, record['max_material_chars'])
                        st.session_state.pop('complete-package-result-'+key, None)
                        st.rerun()
                    except LOCAL_RECORD_ERRORS as exc:
                        st.error(f'预览交接未保存（{type(exc).__name__}），原始材料仍保留。')
            if payload['samples']:
                st.download_button('下载本次组装输入', json.dumps(payload,ensure_ascii=False,indent=2),file_name=task_id+'-source-package.json',mime='application/json',key='source-package-download-'+key)
            st.download_button('下载来源与遗漏清单', json.dumps(record,ensure_ascii=False,indent=2),file_name=task_id+'-source-selection.json',mime='application/json',key='source-selection-download-'+key)
            with st.expander('核对保留与遗漏'):
                st.json(record)


def search_page(store):
    title, auxiliary = st.columns([4, 1], vertical_alignment='center')
    with title:
        heading('新建检索', '明确研究要求，沿用默认配置，为每个对象保存独立任务。')
    with auxiliary:
        with st.popover('辅助工具', icon=':material/history:'):
            show_history = st.checkbox('历史实验回看（只读）', key='ui-search-history')
    if show_history:
        st.subheader('历史实验回看')
        st.caption('读取本机已有记录，不启动调用或改写实验文件。')
        records = experiment_runs(Path(__file__).resolve().parents[2])
        if not records:
            empty('暂无本地实验记录', '日常检索任务请在任务中心查看。')
            return
        index = st.selectbox('选择实验',range(len(records)),format_func=lambda i:records[i]['label'])
        record = records[index]
        task_panel(get_controller(str(record['root'])),record['task_id'],store,read_only=True)
        return
    root = store.root/'search'
    controller = get_controller(str(root))
    profile = root/'profile.json'
    defaults = asdict(SearchConfig())
    if profile.exists():
        defaults.update(json.loads(profile.read_text()))
    events = {e['event_id']:e for e in store.events()}
    if 'search_event_ids' in st.session_state:
        st.session_state['ui-search-events'] = [eid for eid in st.session_state.pop('search_event_ids') if eid in events]
    chosen = st.multiselect('从主表选择事件（可批量）',list(events),format_func=lambda k:display_name(events[k]),key='ui-search-events',placeholder='留空可创建独立研究任务')
    event_id = chosen[0] if chosen else ''
    event = events.get(event_id,{})
    case_key = 'ui-search-draft-' + ('batch' if len(chosen)>1 else event_id or 'independent') + '-'
    is_batch = len(chosen)>1
    left, right = st.columns([7, 3])
    with left:
        with st.container(border=True, key="search-fields"):
            st.subheader('研究对象与范围')
            if is_batch:
                st.info(f'已选择 {len(chosen)} 个事件，各自采用主表中的名称、研究要求与范围。')
            kind = st.selectbox('对象类型',['event','person'],format_func=lambda k:{'event':'事件','person':'人物'}[k],key=case_key+'kind',disabled=is_batch)
            name = st.text_input('研究对象',display_name(event) if event else '',key=case_key+'name',disabled=is_batch)
            query = st.text_area('研究要求',event.get('description',''),height=140,key=case_key+'query',disabled=is_batch,placeholder='描述需要查明的行动、参与者、交易和时间范围。')
            providers = st.multiselect('搜索服务',['baidu','bocha','exa'],default=defaults['providers'],format_func=lambda p:PROVIDERS[p]+' Search' if p=='exa' else PROVIDERS[p]+' Web Search',key='ui-search-providers')
            count = st.number_input('每次查询、每家服务的结果上限',min_value=1,max_value=50,value=defaults['max_results'],key='ui-search-count')
            if event and not is_batch:
                st.caption(f"事件覆盖：{event.get('coverage_start') or '未限定'} → {event.get('coverage_end') or '未限定'} · 资料发表时间可另行设置")
        with st.expander('范围与已有来源'):
            keywords = st.text_input('关键词（逗号分隔）',','.join(event.get('keywords',[])),key=case_key+'keywords',disabled=is_batch)
            seeds = st.text_area('已有来源 URL（每行一个）','\n'.join(x for x in event.get('source_hints',[]) if x.startswith(('https://','http://'))),key=case_key+'seeds',disabled=is_batch)
            include = st.text_input('限定站点（逗号分隔）',','.join(defaults['include_domains']),key='ui-search-include')
            exclude = st.text_input('排除站点（逗号分隔）',','.join(defaults['exclude_domains']),key='ui-search-exclude')
            a,b = st.columns(2)
            start = a.text_input('资料发表开始日期',defaults['publication_start'] or '',placeholder='YYYY-MM-DD',key='ui-search-start')
            end = b.text_input('资料发表结束日期',defaults['publication_end'] or '',placeholder='YYYY-MM-DD',key='ui-search-end')
            st.caption('留空可纳入事后报道和总结；与事件发生时间不同。')
        with st.expander('预算与模型参数'):
            lm_name = st.text_input('搜索侧模型',defaults.get('lm_name') or '',key='ui-search-model',help='provider/model；搜索模型与构建模型独立。')
            options = {}
            cols = st.columns(2)
            for i,(field,label) in enumerate([('max_search_requests','累计搜索请求上限'),('max_read_sources','不同阅读来源上限'),
                                  ('max_model_calls','累计模型请求上限'),('max_read_chars','单次正文字符上限'),
                                  ('max_builder_material_chars','交付材料字符总上限'),('max_model_context_chars','模型上下文字符上限'),
                                  ('timeout','单次请求超时（秒）')]):
                options[field] = cols[i%2].number_input(label,min_value=1,value=defaults[field],key='ui-search-'+field)
            output_tokens = st.number_input('模型答案 token 上限',min_value=1,value=defaults['generation_config'].get('max_tokens',4096),key='ui-search-tokens')
            st.caption('Ark Seed 的答案上限不包含推理 token；模型与构建侧独立配置。')
            rewrite = st.checkbox('百度 query 改写',value=defaults['baidu_rewrite'],key='ui-search-rewrite')
    with right:
        with st.container(border=True, key="search-summary"):
            st.subheader('本次任务')
            st.write(f"**{len(chosen) or 1}** 个独立检索任务")
            st.caption(' / '.join(PROVIDERS[p] for p in providers) or '请选择搜索服务')
            st.markdown('**实际交付预算**')
            st.write(f"{options['max_builder_material_chars']:,} 字符 / 事件")
            st.caption(f"累计搜索 {options['max_search_requests']} 次 · 阅读 {options['max_read_sources']} 个来源")
            st.caption(f"搜索模型：{lm_name or '未设置'}")
            enabled = st.checkbox('允许启动后调用外部搜索与模型',value=False,key='ui-search-allow')
            st.caption('保存后进入任务中心；点击开始才执行。')
            if st.button('保存检索任务',type='primary',icon=':material/add:',width='stretch'):
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
                    for key in ('coverage_start','coverage_end','scope_include','scope_exclude','aliases'):
                        if event.get(key):task[key]=event[key]
                    if event_id:task['event_id']=event_id
                    if chosen:
                        for eid in chosen:
                            if store.decision(eid, 'scope') != 'approved':
                                raise ValueError(display_name(events[eid]) + '：请先在数据页确认研究范围')
                    tids = []
                    for eid in chosen or [None]:
                        current = dict(task)
                        if len(chosen) > 1:
                            e = events[eid]
                            current = dict(target_type='event', target_name=display_name(e), query_text=e['description'],
                                           key_words=e['keywords'], seed_urls=[u for u in e['source_hints'] if u.startswith(('https://','http://'))])
                            for key in ('coverage_start','coverage_end','scope_include','scope_exclude','aliases'):
                                if e.get(key): current[key] = e[key]
                        if eid:
                            current['event_id'] = eid
                            current['scope_hash'] = store.target(eid, 'scope')
                        tids.append(controller.create(current, config))
                    tid = tids[0]
                    st.session_state['search-selected']=tid
                    navigate('任务', **{'task-selected':tid, 'task_event_filter':'', 'notice':f'已创建 {len(tids)} 个检索任务；点击开始后才发起调用。'})
                except (ValueError,TypeError) as exc:st.error(str(exc))
