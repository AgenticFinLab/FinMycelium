"""Read-only event progress and shared navigation for the workbench."""
from finmy.workbench.domain import digest

STEPS = ["确认范围", "检索资料", "检查材料", "构建草稿", "审核修订", "收录导出"]


def event_searches(store, controller, event_id):
    records = []
    for tid in controller.tasks():
        data = controller.inspect(tid)
        if data["task"].get("event_id") == event_id:
            records.append((tid, data))
    return records


def progress(store, event_id, controller=None):
    """Approvals and executions are separate; current input wins over old graphs."""
    if store.decision(event_id, "scope") != "approved":
        return 0, "待确认范围", "确认范围"
    bundle = store.input_bundle(event_id)
    if not bundle["samples"]:
        runs = event_searches(store, controller, event_id) if controller else []
        if any(controller.active(tid) for tid, _ in runs):
            return 1, "检索中", "查看任务"
        if any(d.get("builder_input", {}).get("samples") for _, d in runs if d.get("builder_input")):
            return 2, "待检查检索材料", "查看任务"
        return 1, "待检索／补充资料", "开始检索"
    if store.decision(event_id, "evidence") != "approved":
        return 2, "待检查材料", "检查材料"
    from finmy.workbench.build_tasks import BuildController
    builds = BuildController(store)
    for run in builds.tasks(event_id):
        current = builds.reconcile(run["id"])
        if current["status"] in {"queued", "running"} and builds.current(current):
            return 3, "构建中", "查看构建任务"
    graphs = store.graphs(event_id)
    if not graphs or graphs[0]["input_hash"] != digest(bundle):
        return 3, "待构建" if not graphs else "输入已更新，待重新构建", "创建构建任务"
    decision = store.decision(event_id, "graph")
    if decision == "approved":
        return 5, "已收录", "收录导出"
    return 4, "需修订" if decision in {"returned", "issue"} else "待审核图", "审核修订"


def navigate(page, **values):
    import streamlit as st
    st.session_state.update(values)
    st.session_state["navigate_to"] = page
    st.rerun()
