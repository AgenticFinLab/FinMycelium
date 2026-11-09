"""Offline workflow contracts: frozen input, execution gates and draft provenance."""
import io
import json
import socket
import zipfile

import pytest

from finmy.workbench.build_tasks import BuildController
from finmy.workbench.domain import digest
from finmy.workbench.store import Store
from finmy.workbench.workflow import progress


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("Unexpected network")
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def prepared(tmp_path):
    store = Store(tmp_path)
    eid = store.create_events([{"event_name_en":"Synthetic event", "description":"An offline transaction",
                                "scope_include":"The transaction and its closing"}])[0]
    store.review(eid, "scope", "approved", "Reviewer", "", store.target(eid, "scope"))
    store.add_source(eid, "Source", "The transaction closed after approval.")
    store.review(eid, "evidence", "approved", "Reviewer", "", store.target(eid, "evidence"))
    return store, eid


def graph():
    return {"event_id":"fixture", "title":{"value":"Transaction"}, "stages":[
        {"stage_id":"S1", "episodes":[{"episode_id":"E1", "participants":[]}]}]}


def queue(controller, tid):
    row = controller.inspect(tid)
    controller.save(tid, "queued", row["body"])


def test_input_approval_creates_immutable_snapshot(prepared):
    store,eid = prepared
    original = store.handoffs(eid)[0]
    store.add_source(eid,"New", "Later evidence.")
    assert store.handoffs(eid)[0] == original
    assert store.decision(eid,"evidence") is None
    assert progress(store,eid)[0] == 2
    with pytest.raises(ValueError,match="审核"):
        BuildController(store).create(eid,store.settings())


@pytest.mark.parametrize("kind", ["AgentEventBuilder", "SparseRagBuilder"])
def test_real_builder_offline_input_preflight(prepared, tmp_path, kind):
    from finmy.runner.build_only_runner import select_builder
    from finmy.runner.sparse_build_runner import load_inputs, preflight
    store,eid = prepared
    controller=BuildController(store)
    tid=controller.create(eid,{**store.settings(),"builder":kind})
    row=controller.inspect(tid)
    path=tmp_path/"preflight-input.json"
    path.write_text(json.dumps(row["body"]["input"]))
    inputs,_=load_inputs(path)
    _,config=select_builder(row["body"]["config"])
    assert preflight(config,inputs)["status"] == "offline_preflight_pass"
    assert not store.graphs(eid)
    assert row["status"]=="ready"


def test_build_imports_draft_without_approval_and_exports_trace(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    queue(controller,tid)
    controller.run(tid,executor=lambda body,path:{"graph":graph(),"usage":{"calls":3},"run_directory":str(path/"fake")})
    row=controller.inspect(tid)
    assert row["status"]=="completed"
    assert row["body"]["graph_id"]==store.graphs(eid)[0]["id"]
    assert store.graphs(eid)[0]["input_hash"]==row["body"]["input_hash"]
    assert store.decision(eid,"graph") is None
    assert progress(store,eid)[0]==4
    controller.run(tid,executor=lambda *a:pytest.fail("Do not run completed tasks twice"))
    assert len(store.graphs(eid))==1
    with zipfile.ZipFile(io.BytesIO(store.export_zip([eid]))) as z:
        assert eid+"/build_runs.json" in z.namelist()
        assert eid+"/handoffs.json" in z.namelist()
        assert eid+"/FinalEPG.json" not in z.namelist()
    store.review(eid,"graph","approved","Reviewer","",store.target(eid,"graph"))
    assert progress(store,eid)[0]==5


def test_build_result_keeps_original_input_when_materials_change(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    frozen=controller.inspect(tid)["body"]["input_hash"]
    def execute(body,path):
        store.add_source(eid,"Later", "Different evidence")
        return {"graph":graph()}
    queue(controller,tid)
    controller.run(tid,executor=execute)
    assert controller.inspect(tid)["status"]=="completed"
    assert store.graphs(eid)[0]["input_hash"]==frozen
    assert digest(store.input_bundle(eid))!=frozen
    with pytest.raises(ValueError, match="输入已变化"):
        store.review(eid,"graph","approved","Reviewer","",store.target(eid,"graph"))


def test_worker_rechecks_approval_before_spending(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    queue(controller,tid)
    store.review(eid,"evidence","returned","Reviewer","Recheck",store.target(eid,"evidence"))
    controller.run(tid,executor=lambda *a:pytest.fail("Must not execute stale approval"))
    assert controller.inspect(tid)["body"]["error_type"]=="InputOrApprovalChanged"


def test_start_requires_explicit_execution_and_cancel_is_final(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    with pytest.raises(ValueError,match="明确允许"):
        controller.start(tid)
    controller.cancel(tid)
    with pytest.raises(ValueError,match="仅可启动"):
        controller.start(tid,allow_network=True)
    assert not store.graphs(eid)


def test_failure_records_safe_type_and_preserves_data(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    queue(controller,tid)
    def execute(*args):
        raise RuntimeError("secret=do-not-persist")
    controller.run(tid,executor=execute)
    row=controller.inspect(tid)
    assert row["status"]=="failed"
    assert row["body"]["error_type"]=="RuntimeError"
    assert "do-not-persist" not in json.dumps(row)
    assert not store.graphs(eid)


def test_dead_worker_never_automatically_retries(prepared):
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    row=controller.inspect(tid)
    controller.save(tid,"running",row["body"])
    assert controller.reconcile(tid)["status"]=="interrupted"
    assert not store.graphs(eid)


def test_legacy_plans_remain_separate(prepared):
    store,eid=prepared
    jid=store.create_job([eid],"search",store.settings())
    assert BuildController(store).tasks()==[]
    assert store.jobs()[0]["id"]==jid
    assert store.jobs()[0]["status"]=="not_connected"


def test_edited_scope_invalidates_progress(prepared):
    from finmy.workbench.domain import FIELDS
    store,eid=prepared
    row=store.event(eid)
    values={k:row[k] for k in FIELDS}
    store.update_event(eid,{**values,"scope_include":"A different transaction"},row["revision"])
    assert progress(store,eid)[0]==0


def test_final_export_requires_current_scope_and_evidence(prepared):
    store,eid=prepared
    store.add_graph(eid,graph())
    store.review(eid,"graph","approved","Reviewer","",store.target(eid,"graph"))
    store.review(eid,"evidence","returned","Reviewer","Review again",store.target(eid,"evidence"))
    with zipfile.ZipFile(io.BytesIO(store.export_zip([eid]))) as z:
        assert eid+"/FinalEPG.json" not in z.namelist()
    with pytest.raises(ValueError,match="审核当前资料"):
        store.review(eid,"graph","approved","Reviewer","",store.target(eid,"graph"))


@pytest.mark.parametrize("shared", [False, True])
def test_revised_search_adoption_preserves_rows_without_duplicate_input(prepared, shared):
    from finmy.search.control import SearchController
    from finmy.search.state import SearchState
    from finmy.search.handoff import prepare_complete_sources
    from finmy.workbench.search_bridge import adopt_sources, save_preview
    store,eid=prepared
    c=SearchController(store.root/"search", transport=lambda *a:{"data":{"webPages":{"value":[{"url":"https://example.org/a"},{"url":"https://example.org/b"}]}}},
                       fetcher=lambda u:(("Original source passage "+u).encode(),"txt","utf-8"))
    tid=c.create({"target_type":"event","target_name":"Transaction","query_text":"Find closing","event_id":eid,
                  "scope_hash":store.target(eid,"scope")},{},"simple")
    c.start(tid);c.threads[tid].join(5)
    adopt_sources(c,tid,store)
    old_count=len(store.sources(eid))
    if shared:
        other=c.create({"target_type":"event","target_name":"Transaction","query_text":"Find closing","event_id":eid}, {}, "simple")
        c.start(other);c.threads[other].join(5)
        adopt_sources(c,other,store)
        shared_ids={s["id"] for s in store.sources(eid) if s["included"]}
    state=SearchState(c.root,tid)
    sid=next(iter(state.data["sources"]))
    _,complete=prepare_complete_sources(state,[sid])
    save_preview(c,tid,complete,60000)
    adopt_sources(c,tid,store)
    assert len(store.sources(eid))>=old_count
    if shared:
        assert shared_ids <= {s["id"] for s in store.sources(eid) if s["included"]}
    else:
        assert len(store.input_bundle(eid)["samples"])==2  # manual source + latest search passage
    assert store.decision(eid,"evidence") is None
    row=store.event(eid)
    from finmy.workbench.domain import FIELDS
    store.update_event(eid,{**{k:row[k] for k in FIELDS},"scope_include":"Changed"},row["revision"])
    with pytest.raises(ValueError,match="范围已变化"):
        adopt_sources(c,tid,store)


def test_explicit_start_queues_one_worker_and_cannot_start_twice(prepared, monkeypatch):
    from types import SimpleNamespace
    import finmy.workbench.build_tasks as module
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    calls=[]
    monkeypatch.setattr(module.subprocess,"Popen",lambda args,**kwargs:(calls.append(args) or SimpleNamespace(pid=123)))
    controller.start(tid,allow_network=True)
    assert len(calls)==1
    assert "finmy.workbench.build_tasks" in calls[0]
    assert controller.inspect(tid)["status"]=="queued"
    with pytest.raises(ValueError):
        controller.start(tid,allow_network=True)
    assert len(calls)==1


def test_code_change_blocks_worker_before_execution(prepared, monkeypatch):
    import finmy.workbench.build_tasks as module
    store,eid=prepared
    controller=BuildController(store)
    tid=controller.create(eid,store.settings())
    queue(controller,tid)
    monkeypatch.setattr(module,"code_version",lambda:{"commit":"different"})
    controller.run(tid,executor=lambda *a:pytest.fail("changed code must not execute"))
    assert controller.inspect(tid)["body"]["error_type"]=="CodeChangedSinceTaskCreation"
