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
    FIELDS, MODELS, DEFAULT_COLUMNS, DERIVED_FIELDS, LANGUAGES, LIST_FIELDS, RELATIONS, TABLE_LABELS,
    date_bounds, digest, display_name, editable_fields, encoded, export_table,
    extract_text, graph_from_bytes, read_matrix, read_table, unwrap,
)
from finmy.workbench.store import Store


def notice(text):
    st.session_state["notice"] = text
    st.rerun()


def heading(title, subtitle=None):
    st.title(title)
    if subtitle:
        st.caption(subtitle)


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


def model_picker(default, key):
    names = list(MODELS) + ["自定义"]
    selected = next((k for k, v in MODELS.items() if v == default), "自定义")
    label = st.selectbox("模型", names, index=names.index(selected), key=key)
    if label == "自定义":
        return st.text_input("Ark 模型 / 接入点 ID", default if selected == "自定义" else "", key=key + "-custom")
    return MODELS[label]


def job_form(store, ids):
    defaults = store.settings()
    model = model_picker(defaults["model"], "job-model")
    with st.form("new-job"):
        stage = st.selectbox("任务阶段", ["完整流程", "检索与处理", "构建图"])
        a, b = st.columns(2)
        with a:
            methods = ["SparseRagBuilder", "AgentEventBuilder"]
            builder = st.selectbox("构建方法", methods, index=methods.index(defaults["builder"]))
        with b:
            concurrency = st.number_input("事件并发数", min_value=1, max_value=32, value=defaults["concurrency"], step=1)
            evidence_review = st.checkbox("人工检查资料", value=True)
            graph_review = st.checkbox("人工审核图", value=True)
        if st.form_submit_button("保存任务", icon=":material/add_task:", type="primary", disabled=not ids):
            try:
                mapping = {"完整流程": "full", "检索与处理": "search", "构建图": "build"}
                store.create_job(ids, mapping[stage], {"builder": builder, "model": model, "concurrency": concurrency}, evidence_review, graph_review)
                notice("任务已保存，执行器待接入")
            except ValueError as exc:
                st.error(str(exc))


def data_page(store):
    events = store.events()
    heading("事件数据", f"{len(events)} 个事件")
    a, b = st.columns(2)
    with a:
        with st.expander("新增事件", icon=":material/add:"):
            event_form(store)
    with b:
        with st.expander("导入主表", icon=":material/upload:"):
            import_events(store)
    st.subheader("事件主表")
    search, state = st.columns([3, 2])
    with search:
        query = st.text_input("搜索", placeholder="名称、别名、ID、主体", label_visibility="collapsed", disabled=not events)
    with state:
        filter_state = st.selectbox("状态", ["全部状态", "待整理", "待审核资料", "待构建", "待审核图", "待修订", "已收录"], label_visibility="collapsed", disabled=not events)
    rows = store.table_rows()
    domain, owner, scope = st.columns(3)
    with domain:
        domain_filter = st.selectbox("领域筛选", ["全部领域"] + sorted({e["domain"] for e in events if e["domain"]}), disabled=not events)
    with owner:
        owner_filter = st.selectbox("负责人筛选", ["全部负责人"] + sorted({e["owner"] for e in events if e["owner"]}), disabled=not events)
    with scope:
        scope_filter = st.selectbox("范围确认筛选", ["全部", "待确认", "需修订", "已确认"], disabled=not events)
    rows = [r for r in rows if (not query or query.casefold() in encoded(r).casefold())
            and (domain_filter == "全部领域" or r["domain"] == domain_filter)
            and (owner_filter == "全部负责人" or r["owner"] == owner_filter)
            and (scope_filter == "全部" or r["scope_review"] == scope_filter)
            and (filter_state == "全部状态" or r["status"] == filter_state)]
    with st.expander("显示列", icon=":material/view_column:"):
        columns = st.multiselect("列", list(TABLE_LABELS), default=DEFAULT_COLUMNS, format_func=TABLE_LABELS.get)
    columns = columns or DEFAULT_COLUMNS
    table_rows = [{**r, "classification": " / ".join(v for v in (r["domain"], r["category"]) if v),
                   "coverage": f"{r['coverage_start'] or '未知'} → {r['coverage_end'] or '未知'}"} for r in rows]
    display = pd.DataFrame([{k: encoded(v) if isinstance(v, (list, dict)) else v for k,v in r.items()} for r in table_rows], columns=columns)
    selection = st.dataframe(display.rename(columns=TABLE_LABELS), hide_index=True, width="stretch", height=176 if not rows else "auto",
                             on_select="rerun", selection_mode="single-row", key="master-" + digest([[r["event_id"] for r in rows], columns])[:12])
    if selection.selection.rows:
        st.session_state["detail_id"] = rows[selection.selection.rows[0]]["event_id"]
    if not events:
        st.caption("暂无事件")
        return
    if not rows:
        st.info("无匹配事件")
    else:
        ids = st.multiselect("批量选择", [r["event_id"] for r in rows], format_func=lambda eid: display_name(next(r for r in rows if r["event_id"] == eid)), key="event-selection")
        with st.expander("批量任务", icon=":material/play_arrow:"):
            job_form(store, ids)
        with st.expander("导出", icon=":material/download:"):
            selected = [e for e in rows if e["event_id"] in ids]
            if not selected:
                st.caption("未选择事件")
            else:
                a, b, c = st.columns(3)
                a.download_button("CSV", export_table(selected), "events.csv", icon=":material/download:")
                b.download_button("Excel", export_table(selected, "xlsx"), "events.xlsx", icon=":material/download:")
                c.download_button("事件包", store.export_zip(ids), "events.zip", icon=":material/folder_zip:")
    st.divider()
    options = [e["event_id"] for e in events]
    selected = st.session_state.get("detail_id")
    eid = selected if selected in options else options[0]
    st.session_state["detail_id"] = eid
    st.subheader(display_name(store.event(eid)))
    details(store, eid)


def source_panel(store, eid):
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
    sources = store.sources(eid)
    if not sources:
        st.caption("暂无资料")
        return
    st.subheader("来源清单")
    for source in sources:
        with st.expander(source["title"] + (" · 已纳入" if source["included"] else " · 未纳入")):
            st.caption(f"{source['id']} · {source['published'] or '日期未知'}")
            if source["url"]:
                st.link_button("原始来源", source["url"], icon=":material/open_in_new:")
            st.text(source["text"] or "尚无正文")
            included = st.checkbox("纳入构建输入", bool(source["included"]), disabled=not source["text"].strip(), key=f"inc-{source['id']}")
            if included != bool(source["included"]):
                store.include_source(eid, source["id"], included)
                st.rerun()
    with st.expander("构建输入", icon=":material/data_object:"):
        bundle = store.input_bundle(eid)
        st.json(bundle, expanded=False)
        st.download_button("下载输入", encoded(bundle), f"{eid}-input.json", icon=":material/download:")
    review_form(store, eid, "evidence")


def review_form(store, eid, kind):
    target = store.target(eid, kind)
    label = {"scope": "范围", "evidence": "资料", "graph": "图"}[kind]
    decision = store.decision(eid, kind)
    st.subheader(f"审核{label}")
    if decision:
        st.caption({"approved": "已通过", "returned": "已退回", "issue": "已记录问题"}[decision])
    with st.form(f"review-{eid}-{kind}-{target[:12]}"):
        name = st.text_input("审核人", key=f"reviewer-{eid}-{kind}-{target[:12]}")
        verdict = st.radio("结论", ["通过", "退回", "记录问题"], horizontal=True)
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
    if version == 0:
        review_form(store, eid, "graph")
    else:
        st.caption("历史版本 · 只读")


def details(store, eid):
    event = store.event(eid)
    st.caption(f"{eid} · {store.status(eid)} · 主表 v{event['revision']}")
    meta, sources, graphs, history = st.tabs(["基本信息", "资料与输入", "图与修订", "运行记录"])
    with meta:
        event_form(store, event)
        if event["related_events"]:
            known_ids = {r["event_id"] for r in store.events()}
            st.dataframe(pd.DataFrame([{**r, "relation_type": RELATIONS[r["relation_type"]], "位置": "本工作区" if r["event_id"] in known_ids else "外部／未导入"} for r in event["related_events"]]).rename(columns={"event_id": "关联事件 ID", "relation_type": "关系", "note": "说明"}), hide_index=True, width="stretch")
        review_form(store, eid, "scope")
    with sources:
        source_panel(store, eid)
    with graphs:
        graph_panel(store, eid)
    with history:
        jobs = [j for j in store.jobs() if any(e["event"]["event_id"] == eid for e in j["body"]["events"])]
        if not jobs:
            st.caption("暂无运行记录")
        for job in jobs:
            st.write(f"{job['id']} · {'已取消' if job['status']=='cancelled' else '执行器待接入'}")
        reviews = store.reviews(eid)
        if reviews:
            st.subheader("审核记录")
            st.dataframe(pd.DataFrame(reviews)[["kind", "decision", "reviewer", "note", "created"]].rename(columns={"kind": "对象", "decision": "结论", "reviewer": "审核人", "note": "备注", "created": "时间"}), hide_index=True, width="stretch")


def tasks_page(store):
    jobs = store.jobs()
    heading("任务", f"{len(jobs)} 个任务")
    st.caption("检索与构建执行器待接入")
    events = store.events()
    with st.expander("新建任务", icon=":material/add_task:"):
        ids = st.multiselect("事件", [e["event_id"] for e in events], format_func=lambda eid: f"{eid} · {display_name(next(e for e in events if e['event_id']==eid))}")
        job_form(store, ids)
    if not jobs:
        st.info("暂无任务")
    for job in jobs:
        body = job["body"]
        label = "已取消" if job["status"] == "cancelled" else "待接入"
        with st.expander(f"{job['id']} · {len(body['events'])} 个事件 · {label}", expanded=len(jobs) == 1):
            a, b, c = st.columns(3)
            a.write(body["config"]["builder"])
            b.write(body["config"]["model"])
            c.write(f"并发 {body['config']['concurrency']}")
            st.caption(job["created"][:19])
            st.dataframe(pd.DataFrame([{"事件 ID": e["event"]["event_id"], "事件名称": display_name(e["event"]), "状态": label} for e in body["events"]]), hide_index=True, width="stretch")
            a, b, c, d = st.columns(4)
            a.button("开始", icon=":material/play_arrow:", disabled=True, key="run-"+job["id"])
            b.button("暂停", icon=":material/pause:", disabled=True, key="pause-"+job["id"])
            c.button("重试失败项", icon=":material/replay:", disabled=True, key="retry-"+job["id"])
            if d.button("取消", icon=":material/close:", disabled=job["status"] == "cancelled", key="cancel-"+job["id"]):
                store.cancel_job(job["id"])
                notice("任务已取消")
            with st.expander("任务配置"):
                st.json({k: v for k, v in body.items() if k != "events"})
            st.caption("尚未运行 · 耗时、tokens 与费用暂无")


def review_page(store):
    heading("待审")
    events = store.events()
    pending = [e for e in events if store.decision(e["event_id"], "scope") != "approved" or store.status(e["event_id"]) in {"待审核资料", "待审核图", "待修订"}]
    if not pending:
        st.info("暂无待审事件")
        return
    st.dataframe(pd.DataFrame([{"事件 ID": e["event_id"], "事件名称": display_name(e), "状态": store.status(e["event_id"]), "负责人": e["owner"]} for e in pending]), hide_index=True, width="stretch")
    eid = st.selectbox("选择事件", [e["event_id"] for e in pending], format_func=lambda x: f"{x} · {display_name(next(e for e in pending if e['event_id']==x))}")
    details(store, eid)


def settings_page(store):
    heading("设置")
    settings = store.settings()
    st.subheader("默认构建配置")
    model = model_picker(settings["model"], "default-model")
    with st.form("settings"):
        methods = ["SparseRagBuilder", "AgentEventBuilder"]
        builder = st.selectbox("构建方法", methods, index=methods.index(settings["builder"]))
        concurrency = st.number_input("事件并发数", min_value=1, max_value=32, value=settings["concurrency"], step=1)
        if st.form_submit_button("保存设置", icon=":material/save:", type="primary"):
            try:
                store.save_settings({"builder": builder, "model": model, "concurrency": concurrency})
                notice("默认配置已保存")
            except ValueError as exc:
                st.error(str(exc))
    st.divider()
    st.subheader("接口状态")
    from dotenv import dotenv_values
    envfile = ROOT / ".env"
    env = dotenv_values(envfile) if envfile.is_file() else {}
    rows = []
    for name, key in [("Ark", "ARK_API_KEY"), ("Bocha", "BOCHA_API_KEY"), ("Baidu", "BAIDUSEARCH_API_KEY")]:
        configured = bool(os.environ.get(key, env.get(key)))
        rows.append({"服务": name, "配置": "已配置" if configured else "未配置", "连接": "未检查"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.button("检查连接", icon=":material/wifi:", disabled=True)
    st.caption("连接检查待接入 · 密钥通过 .env 维护")
    st.subheader("工作目录")
    st.code(str(store.root), language=None)
    st.caption("本地单用户 · 模型可用性尚未验证")


def main():
    st.set_page_config(page_title="FinMycelium | 事件工作台", page_icon=":material/account_tree:", layout="wide")
    st.markdown("""<style>
        :root {font-family:system-ui,sans-serif;letter-spacing:0;}
        .stApp {background:#fff;color:#22302d;}
        h1 {font-size:1.65rem!important;font-weight:650!important;letter-spacing:0!important;}
        h2,h3 {font-size:1.12rem!important;letter-spacing:0!important;}
        .block-container {padding-top:2rem;max-width:1440px;padding-bottom:3rem;}
        [data-testid=stSidebar] {background:#f4f6f5;border-right:1px solid #e1e7e4;}
        [data-testid=stSidebar] h2 {font-size:1.22rem!important;}
        .stButton button,.stDownloadButton button {border-radius:5px;}
        .stButton button[kind=primary],.stFormSubmitButton button[kind=primary] {background:#187968;border-color:#187968;color:white;}
        [data-testid=stMetricValue] {font-size:1.5rem;}
        p,label,button,span {letter-spacing:0;overflow-wrap:anywhere;}
        @media(max-width:640px){.block-container{padding:4rem 1rem 2rem;}h1{font-size:1.4rem!important;}}
        </style>""", unsafe_allow_html=True)
    store = Store(os.environ.get("FINMY_WORKBENCH_HOME", str(ROOT / "output/workbench")))
    with st.sidebar:
        st.header("FinMycelium")
        st.caption("事件工作台")
        page = st.radio("导航", ["数据", "任务", "待审", "设置"], label_visibility="collapsed")
        st.divider()
        st.caption("本地工作区")
    message = st.empty()
    if "notice" in st.session_state:
        message.success(st.session_state["notice"])
    {"数据": data_page, "任务": tasks_page, "待审": review_page, "设置": settings_page}[page](store)


if __name__ == "__main__":
    main()
