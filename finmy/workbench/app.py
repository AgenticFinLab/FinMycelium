"""Run: python -m streamlit run finmy/workbench/app.py --server.address 127.0.0.1"""

import copy
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from finmy.workbench.domain import (
    FIELDS, LANGUAGES, RELATIONS, TABLE_LABELS,
    date_bounds, digest, display_name, editable_fields, encoded, export_table,
    extract_text, graph_from_bytes, read_matrix, read_table, unwrap,
)
from finmy.workbench.ui import heading, apply_style, status as show_status, table_status, stats, step_strip, empty, keep_ui_state, local_timestamp
from finmy.workbench.store import Store
from finmy.workbench.model_picker import model_picker
from finmy.workbench.search_page import search_page, get_controller, task_panel
from finmy.workbench.workflow import SEARCH_STATUS, STEPS, progress, navigate, current_page, open_local_event, event_searches, search_status_code, search_status_label
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.build_page import create_build, build_panel, build_status
from finmy.workbench.material_status import confirmations, confirmed_builds, saved_confirmations


def notice(text):
    st.session_state["notice"] = text
    st.rerun()


def event_form(store, event=None):
    suffix = event["event_id"] if event else "new"
    base = event or {}
    if base.get("legacy_fields"):
        st.caption("旧字段待确认")
        st.json(base["legacy_fields"], expanded=True)
    with st.form(f"event-{suffix}"):
        st.subheader("基本信息")
        left, right = st.columns(2)
        with left:
            values = {"event_name_zh": st.text_input("中文名称", base.get("event_name_zh", ""))}
        with right:
            values["event_name_en"] = st.text_input("英文名称", base.get("event_name_en", ""))
        values["aliases"] = st.text_area("别名", "\n".join(base.get("aliases", [])), height=80, placeholder="每行一项")
        values["description"] = st.text_area("事件简介", base.get("description", ""), height=100)
        left, right = st.columns(2)
        with left:
            values["domain"] = st.text_input("领域", base.get("domain", ""))
            values["participants"] = st.text_area("主要主体", "\n".join(base.get("participants", [])), height=80, placeholder="每行一项")
        with right:
            values["category"] = st.text_input("类别", base.get("category", ""))
            values["country_region"] = st.text_area("国家／地区", "\n".join(base.get("country_region", [])), height=80, placeholder="每行一项")
        st.subheader("范围")
        left, right = st.columns(2)
        with left:
            values["coverage_start"] = st.text_input("覆盖开始时间", base.get("coverage_start", ""), placeholder="YYYY / YYYY-MM / YYYY-MM-DD")
            values["scope_include"] = st.text_area("纳入范围", base.get("scope_include", ""), height=100)
        with right:
            values["coverage_end"] = st.text_input("覆盖结束时间", base.get("coverage_end", ""), placeholder="YYYY / YYYY-MM / YYYY-MM-DD")
            values["scope_exclude"] = st.text_area("排除范围", base.get("scope_exclude", ""), height=100)
        st.subheader("检索准备")
        values["keywords"] = st.text_area("检索关键词", "\n".join(base.get("keywords", [])), height=80, placeholder="每行一项")
        values["search_language"] = st.selectbox("检索语言", list(LANGUAGES), index=list(LANGUAGES).index(base.get("search_language", "")), format_func=LANGUAGES.get)
        values["source_hints"] = st.text_area("来源线索", "\n".join(base.get("source_hints", [])), height=80, placeholder="机构、网站、文档或 URL，每行一项")
        st.subheader("关联与审核")
        links = pd.DataFrame([{**r, "relation_type": RELATIONS[r["relation_type"]]} for r in base.get("related_events", [])], columns=["event_id", "relation_type", "note"])
        links = st.data_editor(links, num_rows="dynamic", hide_index=True, width="stretch", key=f"relations-{suffix}", column_config={
            "event_id": st.column_config.TextColumn("关联事件 ID", required=True),
            "relation_type": st.column_config.SelectboxColumn("关系", options=list(RELATIONS.values()), required=True),
            "note": st.column_config.TextColumn("说明")})
        values["related_events"] = [{"event_id": r["event_id"], "relation_type": next((k for k,v in RELATIONS.items() if v == r["relation_type"]), ""), "note": r["note"]}
                                    for r in links.fillna("").to_dict("records") if any(r.values())]
        left, right = st.columns(2)
        with left:
            values["owner"] = st.text_input("负责人", base.get("owner", ""))
        with right:
            values["notes"] = st.text_input("备注", base.get("notes", ""))
        if st.form_submit_button("保存事件", icon=":material/save:", type="primary"):
            try:
                if event:
                    store.update_event(suffix, values, event["revision"])
                else:
                    st.session_state["detail_id"] = store.create_events([values])[0]
                    st.session_state.pop("data-action", None)
                notice("事件已保存")
            except ValueError as exc:
                st.error(str(exc))


def import_events(store):
    uploaded = st.file_uploader("事件主表", type=["csv", "xlsx"], key="table-upload")
    st.download_button("下载 CSV 模板", export_table([]), "events-template.csv", "text/csv", icon=":material/download:")
    if not uploaded:
        return
    try:
        raw = uploaded.getvalue()
        headers = [str(h).strip() for h in read_matrix(raw, uploaded.name)[0]]
        aliases = {label: key for key, label in FIELDS.items()}
        mapping = {h: aliases.get(h, h) if aliases.get(h, h) in FIELDS else None for h in headers}
        with st.expander("字段映射", expanded=any(v is None for v in mapping.values())):
            for i, header in enumerate(headers):
                options = [None] + list(FIELDS)
                mapping[header] = st.selectbox(header, options, index=options.index(mapping[header]), format_func=lambda k: FIELDS.get(k, "不导入"), key=f"map-{digest(headers)[:8]}-{i}")
        omitted = [h for h in headers if mapping[h] is None]
        allowed = True
        if omitted:
            allowed = st.checkbox("确认不导入这些列：" + "、".join(omitted), key="mapping-confirm-" + digest([headers, mapping])[:10])
        rows = read_table(raw, uploaded.name, mapping)
        existing = {e["event_id"] for e in store.events()}
        clashes = [r["event_id"] for r in rows if r["event_id"] in existing]
        st.caption(f"{len(rows)} 条记录")
        st.dataframe(pd.DataFrame(rows).rename(columns=FIELDS), hide_index=True, width="stretch", height=240)
        if clashes:
            st.error("ID 已存在：" + ", ".join(clashes[:10]))
        if st.button("确认导入", icon=":material/upload:", disabled=bool(clashes) or not allowed, type="primary"):
            store.create_events(rows)
            notice(f"已导入 {len(rows)} 个事件")
    except Exception as exc:
        st.error(f"导入检查未通过：{exc}")


def data_page(store):
    events = store.events()
    ids_all = {e["event_id"] for e in events}
    selected = st.session_state.get("detail_id")
    view = st.session_state.get("data-action")
    if selected in ids_all or view in {"new", "import"}:
        if st.button("返回事件列表", icon=":material/arrow_back:", type="tertiary"):
            st.session_state.pop("detail_id", None)
            st.session_state.pop("data-action", None)
            st.session_state.pop("return-to-review", None)
            st.session_state["master-epoch"] = st.session_state.get("master-epoch", 0) + 1
            st.rerun()
        if view == "new":
            heading("新增事件", "先明确对象与范围，再准备检索资料。")
            event_form(store)
        elif view == "import":
            heading("导入事件主表", "预览字段映射后确认导入，保留已有事件。")
            import_events(store)
        else:
            heading(display_name(store.event(selected)))
            details(store, selected)
        return
    title, actions = st.columns([3, 2], vertical_alignment="center")
    with title:
        heading("本机事件记录", f"{len(events)} 个普通事件 · 手工录入、导入及从目录检索保存的工作记录")
    with actions:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button("导入主表", icon=":material/upload:"):
                st.session_state["data-action"] = "import"
                st.rerun()
            if st.button("新增事件", icon=":material/add:", type="primary"):
                st.session_state["data-action"] = "new"
                st.rerun()
    search, state, filters, display_options = st.columns([4, 2, 1, 1], vertical_alignment="bottom")
    with search:
        query = st.text_input("搜索事件", placeholder="搜索名称、别名、ID 或主体", label_visibility="collapsed", key="ui-master-query")
    with state:
        filter_state = st.selectbox("流程状态", ["全部状态", "待确认范围", "待检索／补充资料", "检索中", "待检查检索材料", "待检查材料", "待构建", "构建中", "输入已更新，待重新构建", "待审核图", "需修订", "已收录"], label_visibility="collapsed", key="ui-master-status")
    with filters:
        with st.popover("筛选", icon=":material/filter_list:", width="stretch"):
            domain_filter = st.selectbox("领域", ["全部领域"] + sorted({e["domain"] for e in events if e["domain"]}), key="ui-master-domain")
            owner_filter = st.selectbox("负责人", ["全部负责人"] + sorted({e["owner"] for e in events if e["owner"]}), key="ui-master-owner")
            scope_filter = st.selectbox("范围确认", ["全部", "待确认", "需修订", "已确认"], key="ui-master-scope")
    labels = {"name": "事件名称", **TABLE_LABELS}
    with display_options:
        with st.popover("显示", icon=":material/view_column:", width="stretch"):
            columns = st.multiselect("显示列", list(labels), default=["name", "status", "coverage", "owner", "classification"], format_func=labels.get, key="ui-master-columns")
            batch = st.toggle("批量选择", key="ui-master-batch", help="开启后可多选事件，准备检索或导出。")
    columns = columns or ["name", "status", "coverage", "owner"]
    controller = get_controller(str(store.root / "search"))
    rows = store.table_rows()
    for row in rows:
        row["status"] = progress(store, row["event_id"], controller)[1]
    rows = [r for r in rows if (not query or query.casefold() in encoded(r).casefold())
            and (domain_filter == "全部领域" or r["domain"] == domain_filter)
            and (owner_filter == "全部负责人" or r["owner"] == owner_filter)
            and (scope_filter == "全部" or r["scope_review"] == scope_filter)
            and (filter_state == "全部状态" or r["status"] == filter_state)]
    active_filters = [v for v in (domain_filter, owner_filter, scope_filter) if v not in {"全部领域", "全部负责人", "全部"}]
    st.caption(f"显示 {len(rows)} / {len(events)} 个事件" + (" · " + " / ".join(active_filters) if active_filters else "") + (" · 勾选多个事件进行批量操作" if batch else " · 选择一行打开事件"))
    if not rows:
        empty("暂无匹配事件" if events else "从第一个事件开始", "调整筛选条件，或新增事件。" if events else "导入 CSV / Excel 主表，或新增事件来明确研究范围。")
        return
    table_rows = [{**r, "name": display_name(r), "status": table_status(r["status"]),
                   "classification": " / ".join(v for v in (r["domain"], r["category"]) if v),
                   "coverage": f"{r['coverage_start'] or '未知'} → {r['coverage_end'] or '未知'}"} for r in rows]
    frame = pd.DataFrame([{k: encoded(v) if isinstance(v, (list, dict)) else v for k,v in r.items()} for r in table_rows], columns=columns).rename(columns=labels)
    table_key = "master-" + digest([[r["event_id"] for r in rows], columns, batch, st.session_state.get("master-epoch", 0)])[:12]
    selection = st.dataframe(frame, hide_index=True, width="stretch", height=min(590, 38*len(rows)+40), row_height=38,
                             on_select="rerun", selection_mode="multi-row" if batch else "single-row", key=table_key,
                             column_config={"事件名称":st.column_config.TextColumn(width="large"), "流程状态":st.column_config.TextColumn(width="medium")})
    chosen = [rows[i]["event_id"] for i in selection.selection.rows]
    if chosen and not batch:
        st.session_state["detail_id"] = chosen[0]
        st.rerun()
    if chosen:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.write(f"已选择 **{len(chosen)}** 个事件")
            if st.button("准备批量检索", icon=":material/search:", type="primary"):
                navigate("任务", search_event_ids=chosen, **{"task-tool": "search", "ui-search-history": False})
            with st.popover("导出所选", icon=":material/download:"):
                records = [r for r in rows if r["event_id"] in chosen]
                st.download_button("事件主表 CSV", export_table(records), "events.csv")
                st.download_button("事件主表 Excel", export_table(records, "xlsx"), "events.xlsx")
                st.download_button("完整事件包", store.export_zip(chosen), "events.zip")


def source_panel(store, eid):
    sources = store.sources(eid)
    bundle = store.input_bundle(eid)
    included = [s for s in sources if s['included'] and s['text'].strip()]
    stats([("已登记资料", len(sources), "文档、片段或尚无正文的 URL"), ("当前输入条目", len(included), "同一来源可以包含多个片段"),
           ("输入正文字符", f"{sum(len(s['content']) for s in bundle['samples']):,}", "以实际输入为准")])
    material, review = st.columns([7, 3])
    with material:
        with st.expander("添加资料", expanded=not sources, icon=":material/add:"):
            upload_tab, url_tab = st.tabs(["上传资料", "添加来源"])
            with upload_tab:
                files = st.file_uploader("TXT / 文本 PDF", type=["txt", "pdf"], accept_multiple_files=True, key=f"sources-{eid}")
                if st.button("保存资料", icon=":material/upload:", disabled=not files, key=f"save-sources-{eid}"):
                    try:
                        parsed = [(f.name, extract_text(f.getvalue(), f.name), f.getvalue()) for f in files]
                        for name, text, raw in parsed:
                            store.add_source(eid, name, text, raw=raw)
                        notice(f"已保存 {len(parsed)} 份资料")
                    except Exception as exc:
                        st.error(f"资料未通过检查：{exc}")
            with url_tab:
                with st.form(f"source-url-{eid}"):
                    title = st.text_input("来源标题")
                    url = st.text_input("URL")
                    published = st.text_input("发布日期")
                    text = st.text_area("正文", height=150)
                    if st.form_submit_button("保存来源", icon=":material/add:"):
                        try:
                            store.add_source(eid, title, text, url, published)
                            notice("来源已保存" if text.strip() else "URL 已登记，抓取待接入")
                        except ValueError as exc:
                            st.error(str(exc))
        if sources:
            source_key = "ui-source-" + eid
            table_key = "source-list-" + eid
            def select_source():
                rows = st.session_state[table_key]['selection']['rows']
                if rows:
                    st.session_state[source_key] = sources[rows[0]]['id']
            st.dataframe([{"来源":s['title'], "输入":'已纳入' if s['included'] else '未纳入', "字符":len(s['text'])} for s in sources],
                         hide_index=True, width="stretch", height=min(250,38*len(sources)+40), row_height=38,
                         on_select=select_source, selection_mode="single-row", key=table_key,
                         column_config={"来源":st.column_config.TextColumn(width="large")})
            source = next((s for s in sources if s['id'] == st.session_state.get(source_key)), sources[0])
            st.markdown('**' + source['title'].replace('*','') + '**')
            st.caption('发布日期：' + (source['published'] or '未记录'))
            if source['url']:
                st.link_button('打开原始来源', source['url'], icon=':material/open_in_new:')
            use = st.checkbox('纳入构建输入', value=bool(source['included']), disabled=not source['text'].strip(), key='inc-'+source['id'])
            if use != bool(source['included']):
                store.include_source(eid, source['id'], use)
                st.rerun()
            with st.container(height=320, border=True):
                st.text(source['text'] or '尚无正文')
        else:
            empty('还没有资料', '可从检索任务纳入材料，也可直接上传已有证据。')
    with review:
        if sources:
            review_form(store, eid, 'evidence')
        st.download_button('下载当前实际输入', encoded(bundle), eid+'-input.json', icon=':material/download:')
        with st.expander('查看输入结构'):
            st.json(bundle, expanded=False)
        versions = store.handoffs(eid)
        if versions:
            with st.expander(f'已确认输入 · {len(versions)} 个版本'):
                for version in versions:
                    st.caption(version['created'][:19])
                    st.download_button('下载确认版输入', encoded(version['body']), version['id']+'.json', key=version['id'])


def review_form(store, eid, kind):
    target = store.target(eid, kind)
    label = {"scope": "范围", "evidence": "资料", "graph": "图"}[kind]
    decision = store.decision(eid, kind)
    prerequisite = (kind == "evidence" and store.decision(eid, "scope") != "approved") or (
        kind == "graph" and (store.decision(eid, "scope") != "approved" or store.decision(eid, "evidence") != "approved"))
    if prerequisite:
        st.warning("请先确认范围与当前资料，再审核后续产物。")
        return
    st.subheader(f"审核{label}")
    if decision:
        show_status({"approved": "已通过", "returned": "已退回", "issue": "已记录问题"}[decision])
    with st.form(f"review-{eid}-{kind}-{target[:12]}"):
        name = st.text_input("审核人", key=f"reviewer-{eid}-{kind}-{target[:12]}")
        verdict = st.selectbox("审核结论", ["通过", "退回", "记录问题"])
        note = st.text_area("审核备注", height=90)
        if st.form_submit_button("保存范围确认" if kind == "scope" else "保存审核", icon=":material/fact_check:", type="primary"):
            try:
                store.review(eid, kind, {"通过": "approved", "退回": "returned", "记录问题": "issue"}[verdict], name, note, target)
                notice("审核已保存")
            except ValueError as exc:
                st.error(str(exc))


def timeline(graph):
    rows, missing = [], 0
    for stage in graph["stages"]:
        for node, category in [(stage, "阶段")] + [(ep, "情节") for ep in stage["episodes"]]:
            start, end = str(unwrap(node.get("start_time"))), str(unwrap(node.get("end_time")))
            try:
                a = date_bounds(start[:10] if "T" in start or " " in start else start)
                b = date_bounds(end[:10] if "T" in end or " " in end else end)
            except (ValueError, TypeError):
                a = b = None
            if not a or not b or a[0] > b[1]:
                missing += 1
                continue
            try:
                lo, hi = datetime.combine(a[0], datetime.min.time()), datetime.combine(b[1] + timedelta(days=1), datetime.min.time())
            except OverflowError:
                missing += 1
                continue
            identity = node.get("stage_id", node.get("episode_id", ""))
            rows.append({"name": f"{identity} · {unwrap(node.get('name'))}", "start": lo, "end": hi, "kind": category, "date": f"{start} → {end}"})
    if not rows:
        st.info("暂无可绘制的时间区间")
        return
    fig = go.Figure()
    for kind, color in [("阶段", "#198376"), ("情节", "#5d86ad")]:
        selected = [r for r in rows if r["kind"] == kind]
        fig.add_trace(go.Bar(name=kind, y=[r["name"] for r in selected], base=[r["start"].isoformat() for r in selected],
                             x=[(r["end"] - r["start"]).total_seconds() * 1000 for r in selected], orientation="h", marker_color=color,
                             customdata=[r["date"] for r in selected], hovertemplate="%{y}<br>%{customdata}<extra></extra>"))
    fig.update_layout(height=max(260, min(900, 90 + len(rows) * 38)), margin=dict(l=0, r=10, t=25, b=15),
                      paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Arial", size=12), barmode="overlay",
                      legend=dict(orientation="h", y=1.12), xaxis=dict(type="date", gridcolor="#edf0f2"),
                      yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=[r["name"] for r in rows]))
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    st.caption(f"按原始时间精度显示区间 · {missing} 项时间缺失或不可解析")


def graph_panel(store, eid):
    with st.expander("导入图", icon=":material/upload:"):
        upload = st.file_uploader("FinalEventCascade JSON", type=["json"], key=f"graph-{eid}")
        confirmed = st.checkbox("确认此图属于当前事件，并对应当前输入资料", key=f"confirm-{eid}")
        if upload:
            try:
                graph = graph_from_bytes(upload.getvalue())
                st.write(unwrap(graph["title"]))
                st.caption(f"原图 ID：{graph['event_id']} · {len(graph['stages'])} 个阶段 · 基础结构检查通过")
                if st.button("保存原始图", disabled=not confirmed, icon=":material/save:", key=f"save-graph-{eid}"):
                    store.add_graph(eid, graph)
                    notice("原始图已保存")
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                st.error(f"图检查未通过：{exc}")
    graphs = store.graphs(eid)
    if not graphs:
        st.info("暂无图")
        return
    version = st.selectbox("图版本", range(len(graphs)), format_func=lambda i: f"v{len(graphs)-i} · {graphs[i]['note']} · {graphs[i]['created'][:19]}", key=f"version-{eid}")
    current = graphs[version]
    graph = current["body"]
    content, review = st.columns([7, 3])
    with content:
        gantt, fields, evidence = st.tabs(["Gantt", "结构与修订", "证据片段"])
        with gantt:
            timeline(graph)
        with fields:
            st.json(graph, expanded=False)
            options = list(editable_fields(graph))
            if options:
                path = st.selectbox("修改字段", range(len(options)), format_func=lambda i: " / ".join(map(str, options[i][0])), key=f"edit-path-{current['id']}")
                with st.form(f"graph-edit-{current['id']}"):
                    value = st.text_area("新内容", value=options[path][1], height=100, key=f"edit-value-{current['id']}-{path}")
                    reason = st.text_input("修订说明")
                    if st.form_submit_button("保存修订版", icon=":material/save:", disabled=version != 0):
                        try:
                            if not reason.strip():
                                raise ValueError("请填写修订说明")
                            revised = copy.deepcopy(graph)
                            cursor = revised
                            field_path = options[path][0]
                            for key in field_path[:-1]:
                                cursor = cursor[key]
                            cursor[field_path[-1]] = value
                            store.add_graph(eid, revised, reason, current["id"])
                            notice("修订版已保存，需重新审核")
                        except ValueError as exc:
                            st.error(str(exc))
        with evidence:
            quotes = [(path, value) for path, value in editable_fields(graph) if "evidence_source_contents" in path]
            if not quotes:
                st.caption("图中暂无证据片段")
            for path, value in quotes:
                st.caption(" / ".join(map(str, path)))
                st.text(value)
            st.caption("来源正文见“资料与输入”")
        st.download_button("下载此版本 JSON", encoded(graph), f"{eid}-{current['id']}.json", icon=":material/download:")
    with review:
        if version == 0:
            review_form(store, eid, "graph")
        else:
            st.caption("历史版本 · 只读")


def details(store, eid):
    controller = get_controller(str(store.root / "search"))
    step, state, action = progress(store, eid, controller)
    event = store.event(eid)
    info, primary = st.columns([3, 2], vertical_alignment="center")
    with info:
        show_status(state, f"主表 v{event['revision']} · {event['owner'] or '未指定负责人'}")
    section_key = "ui-event-section-" + eid
    if section_key not in st.session_state:
        st.session_state[section_key] = "基本信息" if step < 2 else "资料与输入" if step == 2 else "图与修订"
    with primary:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if step >= 2 and st.button("补充检索", icon=":material/search:", key="supplement-"+eid):
                navigate("任务", search_event_ids=[eid], **{"task-tool": "search", "ui-search-history": False})
            if action in {"开始检索", "查看任务", "查看构建任务"}:
                if st.button(action, key="next-"+eid, type="primary"):
                    if action == "开始检索":
                        navigate("任务", search_event_ids=[eid], **{"task-tool": "search", "ui-search-history": False})
                    else:
                        navigate("任务", task_event_filter=eid, **{"ui-task-view": "运行记录"})
            elif action == "收录导出":
                st.download_button("导出已审核事件包", store.export_zip([eid]), eid+".zip", key="final-export-"+eid, type="primary")
            else:
                label = "配置构建任务" if action == "创建构建任务" else action
                if st.button(label, type="primary", key="next-"+eid):
                    st.session_state[section_key] = "基本信息" if step == 0 else "资料与输入" if step == 2 else "图与修订"
                    st.rerun()
    step_strip(STEPS, step)
    st.caption(eid + " · 流程位置随当前范围、材料和审核状态更新")
    section = st.radio("事件详情", ["基本信息", "资料与输入", "图与修订", "运行记录"],
                       key=section_key, horizontal=True, label_visibility="collapsed")
    with st.container(key="event-body"):
        if section == "基本信息":
            summary, review = st.columns([7, 3])
            with summary:
                st.subheader("研究范围")
                st.write(event['description'] or '尚未填写事件简介')
                st.markdown('**纳入范围**')
                st.write(event['scope_include'] or '尚未填写')
                if event['scope_exclude']:
                    st.markdown('**排除范围**')
                    st.write(event['scope_exclude'])
                st.caption(f"事件覆盖时间：{event['coverage_start'] or '未限定'} → {event['coverage_end'] or '未限定'}")
                if event['keywords']:
                    st.caption('关键词：' + ' / '.join(event['keywords']))
                with st.expander("编辑事件与范围", expanded=not event['scope_include']):
                    event_form(store, event)
                if event["related_events"]:
                    known_ids = {r["event_id"] for r in store.events()}
                    st.dataframe(pd.DataFrame([{**r, "relation_type": RELATIONS[r["relation_type"]], "位置": "本工作区" if r["event_id"] in known_ids else "外部／未导入"} for r in event["related_events"]]).rename(columns={"event_id": "关联事件 ID", "relation_type": "关系", "note": "说明"}), hide_index=True, width="stretch")
            with review:
                review_form(store, eid, "scope")
        elif section == "资料与输入":
            source_panel(store, eid)
        elif section == "图与修订":
            if store.decision(eid, "evidence") == "approved" and store.decision(eid, "scope") == "approved":
                with st.expander("构建 draft EPG", expanded=action == "创建构建任务"):
                    create_build(store, eid)
            graph_panel(store, eid)
        elif section == "运行记录":
            runs = event_searches(store, controller, eid)
            adopted = saved_confirmations(store.root)
            for tid, data in runs:
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.write("检索 · " + search_status_label(data, confirmed_builds(tid, data, adopted)))
                    if st.button("打开任务", key="open-"+tid):
                        navigate("任务", **{"task-selected": tid, "task_event_filter": eid})
            for build in BuildController(store).tasks(eid):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.write("构建 · " + build_status(build)[1])
                    if st.button("查看构建记录", key="history-build-"+build["id"]):
                        navigate("任务", **{"task-selected": build["id"], "task_event_filter": eid})
            reviews = store.reviews(eid)
            if reviews:
                st.subheader("审核记录")
                st.dataframe(pd.DataFrame(reviews)[["kind", "decision", "reviewer", "note", "created"]].rename(columns={"kind": "对象", "decision": "结论", "reviewer": "审核人", "note": "备注", "created": "时间"}), hide_index=True, width="stretch")
            if not runs and not reviews and not BuildController(store).tasks(eid):
                empty("暂无运行与审核记录", "检索、构建与确认材料后，记录会保存在这里。")


def dataset_workspace(store):
    from finmy.dataset import dataset_root
    from finmy.workbench.dataset_page import ordinary_catalog
    from finmy.workbench.person_data_page import person_data_page
    if st.session_state.get('dataset-local'):
        if st.session_state.get('return-to-review'):
            if st.button('返回待处理', icon=':material/arrow_back:', type='tertiary'):
                navigate('任务', **{'ui-task-view': '待处理'})
        elif not st.session_state.get('detail_id') and not st.session_state.get('data-action'):
            if st.button('返回普通事件目录', icon=':material/arrow_back:', type='tertiary'):
                navigate('数据集')
        data_page(store)
        return
    heading('数据集')
    kinds, local = st.columns([3, 1], vertical_alignment='center')
    kind = kinds.radio('目录类型', ['普通事件', '人物事件'], horizontal=True, key='ui-dataset-kind',
                       label_visibility='collapsed')
    if kind == '普通事件' and local.button('本机事件记录', icon=':material/table_view:', width='stretch'):
        navigate('数据集', detail_id=None, **{'dataset-local': True, 'data-action': None,
                 'master-epoch': st.session_state.get('master-epoch', 0)+1})
    if not dataset_root(store.root):
        st.info('请在设置中选择 EPG-dataset，以打开正式事件目录。')
        if st.button('前往设置', icon=':material/settings:'):
            navigate('设置')
    elif kind == '人物事件':
        person_data_page(store)
    else:
        ordinary_catalog(store)


def tasks_page(store):
    if st.session_state.get('task-tool') == 'search':
        if st.button('返回任务列表', icon=':material/arrow_back:', type='tertiary'):
            navigate('任务', **{'ui-task-view': '运行记录'})
        search_page(store)
        return
    heading('任务中心')
    focused = st.session_state.get('task-detail-id')
    if focused:
        back = '返回待处理' if st.session_state.get('ui-task-view') == '待处理' else '返回任务列表'
        if st.button(back, icon=':material/arrow_back:'):
            navigate('任务')
        is_build = focused.startswith(("BUILD-", "PBUILD-"))
        if is_build:
            try:
                running = BuildController(store).inspect(focused)["status"] in {"queued", "running"}
            except ValueError:
                running = False
        else:
            running = get_controller(str(store.root / "search")).active(focused)
        if running:
            live_task(store, focused)
        else:
            focused_task(store, focused)
    else:
        modes, tools = st.columns([3, 1], vertical_alignment='center')
        view = modes.radio('任务视图', ['运行记录', '待处理'], horizontal=True,
                           label_visibility='collapsed', key='ui-task-view')
        if tools.button('独立与批量检索', icon=':material/search:', width='stretch'):
            navigate('任务', **{'task-tool': 'search', 'ui-search-history': False})
        if view == '待处理':
            pending_reviews(store)
        else:
            task_workspace(store)


@st.fragment(run_every="2s")
def live_task(store, task_id):
    if not focused_task(store, task_id):
        st.rerun()


def focused_task(store, task_id):
    build = task_id.startswith(("BUILD-", "PBUILD-"))
    try:
        if build:
            row = BuildController(store).reconcile(task_id)
        else:
            controller = get_controller(str(store.root / "search"))
            row = controller.inspect(task_id)
    except (ValueError, FileNotFoundError):
        st.warning("无法读取这条任务记录，可返回列表重新选择。")
        return
    with st.container(key="task-detail"):
        if build:
            build_panel(store, task_id, row=row)
        else:
            task_panel(controller, task_id, store, data=row)
    return row["status"] in {"queued", "running"} if build else controller.active(task_id)


def task_workspace(store):
    controller = get_controller(str(store.root / "search"))
    builds = BuildController(store)
    events = {e["event_id"]:e for e in store.events()}
    search_runs = [(tid, controller.inspect(tid)) for tid in controller.tasks()]
    labels = {eid: display_name(event) for eid, event in events.items()}
    def catalog_key(task):
        ref = task.get('catalog')
        return 'catalog:' + digest([ref['root'], ref['kind'], ref.get('person_id'), ref['event_id']])[:20] if ref else ''
    build_runs = builds.tasks()
    adopted = confirmations(build_runs)
    for build in build_runs:
        key = catalog_key(build['body'])
        if key: labels[key] = display_name(build['body']['event']) + ' · 数据集'
    for _, run in search_runs:
        key = catalog_key(run['task'])
        if key: labels[key] = run['task']['target_name'] + ' · 数据集'
    if "task_event_filter" in st.session_state:
        st.session_state["ui-task-event"] = st.session_state.pop("task_event_filter")
        st.session_state["ui-task-kind"] = "全部类型"
        st.session_state["ui-task-state"] = "全部状态"
    if st.session_state.get("ui-task-event", "") not in [""] + list(labels):
        st.session_state["ui-task-event"] = ""
    scope, kind, state = st.columns([3, 1, 1])
    with scope:
        eid = st.selectbox("按事件筛选", [""]+list(labels), format_func=lambda k:labels[k] if k else "全部事件与独立研究", key="ui-task-event", label_visibility="collapsed")
    with kind:
        kind_filter = st.selectbox("任务类型", ["全部类型", "检索", "构建"], key="ui-task-kind", label_visibility="collapsed")
    with state:
        state_filter = st.selectbox("运行状态", ["全部状态", "待启动", "运行中", "待检查", "已确认用于构建", "需处理", "不参与构建", "材料已收录", "已收录", "已舍弃", "已取消"], key="ui-task-state", label_visibility="collapsed")
    st.button("刷新任务列表", icon=":material/refresh:")
    records = []
    related_ids = {data['task'].get('event_id') for _, data in search_runs if catalog_key(data['task']) == eid}
    for tid, data in search_runs:
        data = {**data, "task_id": tid}
        if not eid or data["task"].get("event_id") == eid or catalog_key(data['task']) == eid:
            matched = confirmed_builds(tid, data, adopted)
            code = search_status_code(data, matched)
            records.append({"id":tid, "kind":"检索", "name":data["task"]["target_name"], "code":code,
                            "status":SEARCH_STATUS.get(code, code), "created":data.get("created_at", ""), "data":data})
    for build in build_runs:
        if eid in events and build["event_id"] != eid:
            continue
        if eid.startswith('catalog:') and build['event_id'] not in related_ids and catalog_key(build['body']) != eid:
            continue
        row = builds.reconcile(build["id"]) if build["status"] in {"running", "queued"} else build
        code, label = build_status(row)
        records.append({"id":row["id"], "kind":"构建", "name":display_name(row["body"]["event"]),
                        "code":code, "status":label, "created":row["created"], "data":row})
    buckets = {"待启动":{"ready"}, "运行中":{"running","queued"}, "待检查":{"finished","completed"}, "已确认用于构建":{"confirmed"},
               "需处理":{"failed","limit","insufficient","paused","interrupted","partial"}, "不参与构建":{"excluded"}, "材料已收录":{"collected"}, "已收录":{"accepted"}, "已舍弃":{"discarded"}, "已取消":{"cancelled"}}
    records = [r for r in records if (kind_filter == "全部类型" or r["kind"] == kind_filter)
               and (state_filter == "全部状态" or r["code"] in buckets[state_filter])]
    records.sort(key=lambda r:r["created"], reverse=True)
    if records:
        keys = [r["id"] for r in records]
        table_key = "tasks-" + digest(keys)[:12]
        def select_task():
            selected_rows = st.session_state[table_key]["selection"]["rows"]
            if selected_rows:
                st.session_state["task-selected"] = keys[selected_rows[0]]
                st.session_state["task-detail-id"] = keys[selected_rows[0]]
        st.dataframe([{"研究对象":r["name"], "类型":r["kind"], "状态":table_status(r["status"]),
                       "创建时间（北京时间）":local_timestamp(r["created"]), "任务 ID":r["id"][:12]} for r in records],
                     hide_index=True, width="stretch", height=min(240, 38*len(records)+40), row_height=38,
                     on_select=select_task, selection_mode="single-row", key=table_key,
                     column_config={"研究对象":st.column_config.TextColumn(width="large"), "状态":st.column_config.TextColumn(width="medium")})
        selected = st.session_state.get("task-selected")
        if selected not in keys:
            selected = keys[0]
        current = next(r for r in records if r["id"] == selected)
        st.caption(f"{len(records)} 个任务 · 当前选择 {current['name']} · {selected}")
        if st.button("打开任务", icon=":material/open_in_new:"):
            navigate("任务", **{"task-selected": selected})
    else:
        empty("暂无匹配任务", "从主表准备检索，或确认资料后创建构建任务；也可调整筛选条件。")
    jobs = store.jobs()
    if jobs:
        with st.expander(f"历史任务计划 · {len(jobs)} 条"):
            st.caption("旧版计划供查阅，不代表实际执行。")
            for job in jobs:
                st.write(job["id"] + " · " + ("已取消" if job["status"] == "cancelled" else "未执行"))
                st.json(job["body"], expanded=False)
                if st.button("取消计划", disabled=job["status"] == "cancelled", key="cancel-"+job["id"]):
                    store.cancel_job(job["id"])
                    st.rerun()


def pending_reviews(store):
    from finmy.dataset import dataset_root
    from finmy.workbench.person_review_page import person_review_panel
    from finmy.workbench.review_selection import review_queue
    items = {}
    root = dataset_root(store.root)
    if root:
        try:
            drafts, errors = review_queue(root)
            for error in errors:
                st.warning(error)
            for item in drafts:
                ref = item['catalog']
                name = ' / '.join(ref.get(key) or ref[fallback] for key, fallback in
                                  [('person_name', 'person_id'), ('storyline_name', 'storyline_id'), ('event_name', 'event_id')])
                tid = item['binding']['build_task_id']
                items[tid] = {'label': f"人物事件 · {name} · {ref['event_id']}", 'stage': '图审核', 'draft': item}
        except (ValueError, OSError) as exc:
            st.warning(str(exc))
    for event in store.events():
        eid = event['event_id']
        if store.decision(eid, 'scope') != 'approved':
            stage = '范围确认'
        else:
            bundle = store.input_bundle(eid)
            if not bundle['samples']:
                continue
            if store.decision(eid, 'evidence') != 'approved':
                stage = '材料审核'
            else:
                graphs = store.graphs(eid)
                if not graphs or graphs[0]['input_hash'] != digest(bundle) or store.decision(eid, 'graph') == 'approved':
                    continue
                stage = '图审核'
        items['event:'+eid] = {'label': f'普通事件 · {display_name(event)} · {eid}', 'stage': stage, 'event_id': eid}
    if not items:
        empty('当前没有待处理事项', '这里显示本机普通事件的范围、材料和图审核，以及人物事件明确选送的草稿。')
        return
    requested = st.session_state.pop('review-queue-event', None)
    if requested in items:
        st.session_state['ui-review-kind'] = '全部'
        st.session_state['ui-review-selected'] = requested
    stages = ['全部', *[stage for stage in ('范围确认', '材料审核', '图审核')
                       if any(item['stage'] == stage for item in items.values())]]
    if st.session_state.get('ui-review-kind') not in stages:
        st.session_state['ui-review-kind'] = '全部'
    group, choices = st.columns([1, 3], vertical_alignment='bottom')
    stage = group.selectbox('处理阶段', stages, key='ui-review-kind')
    keys = [key for key, item in items.items() if stage == '全部' or item['stage'] == stage]
    if st.session_state.get('ui-review-selected') not in keys:
        st.session_state['ui-review-selected'] = keys[0]
    selected = choices.selectbox('选择待处理事项', keys, key='ui-review-selected',
                                 format_func=lambda k: items[k]['label']+' · '+items[k]['stage'])
    item = items[selected]
    if 'draft' in item:
        person_review_panel(store, item['draft'])
    elif st.button('打开'+item['stage'], icon=':material/fact_check:', type='primary'):
        section = {'范围确认':'基本信息', '材料审核':'资料与输入', '图审核':'图与修订'}[item['stage']]
        open_local_event(item['event_id'], section, from_review=True)


def settings_page(store):
    heading("设置", "配置新任务的默认值。已经创建的任务保留各自的配置。")
    search, build, workspace = st.tabs(['搜索默认配置', '构建默认配置', '接口与工作区'])
    with search:
        from finmy.workbench.search_settings import search_settings
        search_settings(store)
    with build:
        settings = store.settings()
        model = model_picker(settings['model'], 'default-model', purpose='build', label='默认构建模型')
        with st.form('settings'):
            methods = ['SparseRagBuilder','AgentEventBuilder']
            builder = st.selectbox('构建方法', methods, index=methods.index(settings['builder']))
            st.caption('构建模型与搜索模型独立；每个事件单独创建构建任务。')
            if st.form_submit_button('保存构建默认配置', icon=':material/save:', type='primary'):
                try:
                    store.save_settings({'builder':builder,'model':model,'concurrency':settings['concurrency']})
                    notice('构建默认配置已保存')
                except ValueError as exc:
                    st.error(str(exc))
    with workspace:
        from finmy.workbench.dataset_page import dataset_settings
        dataset_settings(store)
        from dotenv import dotenv_values
        envfile = ROOT / '.env'
        env = dotenv_values(envfile) if envfile.is_file() else {}
        rows = []
        for name,key in [('Ark','ARK_API_KEY'),('TokenHub','HUNYUAN_API_KEY'),('Bocha','BOCHA_API_KEY'),('Baidu','BAIDUSEARCH_API_KEY'),('Exa','EXA_API_KEY')]:
            configured = bool(os.environ.get(key,env.get(key)))
            rows.append({'服务':name,'密钥配置':'已配置' if configured else '未配置','连接':'未检查'})
        st.subheader('接口状态')
        st.dataframe(rows,hide_index=True,width='stretch')
        st.caption('密钥通过 .env 维护。这里仅显示配置是否存在，不会发起连接或模型请求。')
        st.subheader('本地工作目录')
        st.code(str(store.root),language=None)
        st.caption('运行记录与数据库保存在本地工作区；自动批量构建调度尚未接入。')


def main():
    st.set_page_config(page_title="FinMycelium | 事件工作台", page_icon=":material/account_tree:", layout="wide")
    apply_style()
    keep_ui_state()
    from finmy.workbench.workspace import resolve_workspace
    from finmy.workbench.dataset_page import dataset_settings
    try:
        workspace = resolve_workspace(ROOT)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        dataset_settings(None)
        return
    if workspace is None:
        heading('工作区', '选择 EPG-dataset，保存工作台任务与运行记录。')
        dataset_settings(None)
        return
    store = Store(workspace)
    page = current_page(st.session_state)
    with st.sidebar:
        st.markdown('<div class="fm-brand"><strong>FinMycelium</strong><small>事件工作台 · EPG</small></div>', unsafe_allow_html=True)
        for value, label, icon in [('数据集', '数据集', 'folder_open'), ('任务', '任务中心', 'play_circle'), ('设置', '设置', 'tune')]:
            if st.button(label, icon=f':material/{icon}:', type='primary' if page == value else 'secondary',
                         width='stretch', key='nav-'+value):
                navigate(value)
        st.divider()
        st.caption("本地工作区 · 单用户")
        st.caption("范围 → 资料 → 草稿 → 审核")
    if "notice" in st.session_state:
        st.toast(st.session_state.pop("notice"), icon=":material/check_circle:")
    {'数据集': dataset_workspace, '任务': tasks_page, '设置': settings_page}[page](store)


if __name__ == "__main__":
    main()
