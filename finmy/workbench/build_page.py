"""Explicit build submission and review links; rendering never starts a model."""
import streamlit as st

from finmy.workbench.build_tasks import BuildController
from finmy.workbench.domain import encoded, display_name
from finmy.workbench.workflow import navigate
from finmy.workbench.ui import status, stats
from finmy.workbench.model_picker import model_picker

LABELS = {"ready":"待启动", "queued":"启动中", "running":"构建中", "paused":"已暂停", "completed":"已生成草稿，待审核",
          "failed":"构建失败", "interrupted":"构建中断", "cancelled":"已取消", "partial":"部分完成，待处理", "limit":"达到调用上限", "insufficient":"材料不足"}


def create_build(store, event_id):
    controller = BuildController(store)
    st.subheader("构建 draft EPG")
    st.caption("使用已确认的输入快照；模型与搜索配置独立。创建任务不会调用模型。")
    defaults = store.settings()
    model = model_picker(defaults["model"], "ui-build-model-" + event_id, purpose="build", label="构建模型")
    with st.form("create-build-"+event_id):
        methods = ["SparseRagBuilder", "AgentEventBuilder"]
        builder = st.selectbox("构建方法", methods, index=methods.index(defaults["builder"]))
        st.caption("沿用对应 build-only 配置的调用上限；Sparse 保持 report 与局部检索。")
        if st.form_submit_button("创建构建任务", type="primary"):
            try:
                tid = controller.create(event_id, {"builder":builder, "model":model, "concurrency":1})
                navigate("任务", **{"task-selected": tid, "task_event_filter": event_id})
            except ValueError as exc:
                st.error(str(exc))


def build_panel(store, task_id, row=None):
    controller = BuildController(store)
    row = row or controller.reconcile(task_id)
    body = row["body"]
    if body.get('kind') == 'person_event':
        from .person_build_page import person_build_panel
        return person_build_panel(store, controller, row, LABELS)
    st.subheader(display_name(body["event"]))
    status(LABELS[row["status"]], "构建 · " + task_id)
    st.write(body["config"]["builder_type"] + " · " + body["config"]["lm_name"])
    st.caption('构建输出：' + str(body.get('artifact_directory') or controller.root / task_id))
    if not controller.current(row):
        st.warning("当前资料或审核已变化。此任务仍绑定旧输入；请重新确认资料，旧运行不会被改写。")
    stats([("输入条目", len(body["input"]["samples"]), "文档或来源片段"),
           ("输入正文字符", f"{sum(len(s['content']) for s in body['input']['samples']):,}", "实际构建输入"),
           ("运行耗时", f"{body['elapsed_seconds']:.1f} 秒" if body.get("elapsed_seconds") is not None else "—", "以运行记录为准")])
    if row["status"] == "ready":
        allowed = st.checkbox("允许本次构建调用模型接口", key="build-allow-"+task_id)
        a,b = st.columns(2)
        if a.button("开始构建", type="primary", disabled=not allowed, key="build-start-"+task_id):
            try:
                controller.start(task_id, allow_network=allowed)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if b.button("取消构建任务", key="build-cancel-"+task_id):
            controller.cancel(task_id)
            st.rerun()
    elif row["status"] in {"queued", "running"}:
        st.info("构建在独立进程中运行，可切换页面。当前不支持中途暂停；不会自动重复执行。")
    elif row["status"] in {"failed", "interrupted"}:
        st.error("本次未成功完成：" + body.get("error_type", "Unknown"))
        st.caption("先检查本次配置和运行记录；重新构建会创建新任务并可能产生新的模型费用。")
    if row["status"] == "completed":
        st.success("已保存 draft 图。运行完成不等于内容审核通过。")
    if st.button("打开事件与审核", key="build-review-"+task_id, type="primary" if row["status"] == "completed" else "secondary", icon=":material/fact_check:"):
        navigate("数据", detail_id=row["event_id"], **{"ui-event-section-"+row["event_id"]:"图与修订"})
    if body.get("elapsed_seconds") is not None:
        st.caption(f"运行耗时：{body['elapsed_seconds']:.1f} 秒")
    with st.expander("本次配置、输入和追溯记录"):
        st.json({k:v for k,v in body.items() if k not in {"input", "event"}}, expanded=False)
        st.download_button("下载本次实际输入", encoded(body["input"]), task_id+"-input.json", key="build-input-"+task_id)
    st.caption("调用与 token 以运行记录为准；未提供的金额不按零费用显示。")
