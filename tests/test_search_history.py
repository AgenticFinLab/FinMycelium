"""Offline trace projection checks: no browser, API, or model calls."""
import json
from pathlib import Path
from finmy.workbench.search_history import read_trace, timeline, experiment_runs


def test_failed_handoff_and_timeout_are_separate_steps():
    rows = timeline([
        {'action':'model_response','response':json.dumps({'action':'search','query':'q','gap':'missing date'})},
        {'action':'search','query':'q','result':{'source_ids':['a','a'],'providers':[{'provider':'exa','status':'success'}]}},
        {'action':'action_error','error':{'error':'APITimeoutError'}},
        {'action':'model_response','response':json.dumps({'action':'finish','selections':[{}],'gaps':[]})},
        {'action':'action_error','error':{'error':'ValueError','hint':'Invalid selection offsets'}},
    ], {'status':'paused','selection':None})
    assert len(rows)==3
    assert rows[0]['new_count']==1 and rows[0]['gap']=='missing date'
    assert [r['model_call'] for r in rows]==[1,2,3]
    assert rows[2]['action']=='finish' and rows[2]['status']=='error'
    assert rows[1]['usage'] is None


def test_truncated_record_and_read_only_discovery(tmp_path):
    root=tmp_path/'.local-experiments/search-enhancement/test/runtime/task/runs/initial'
    root.mkdir(parents=True)
    record=root/'run.json';record.write_text(json.dumps({'task':{'target_name':'Case'}}))
    trace=root/'trace.jsonl';trace.write_text('{"action":"model_started","model_call":1}\n{"action":')
    before={p:p.read_bytes() for p in root.iterdir()}
    events,errors=read_trace(root)
    assert errors==1 and len(events)==1
    found=experiment_runs(tmp_path)
    assert found[0]['task_id']=='task' and found[0]['root']==root.parents[2]
    assert timeline(events,{'status':'paused'})[0]['status']=='unconfirmed'
    assert before=={p:p.read_bytes() for p in root.iterdir()}


def test_saved_policy_labels_preserve_original_records():
    import copy
    from finmy.workbench.search_history import budget_policy_label
    for policy, expected in (
        ('balanced_source_windows_v1', '材料预算分配（来源配额与共享余量）'),
        ('c2_base_shared_bm25_windows_v1', '材料预算分配（来源配额与共享余量）'),
        ('source_order_complete_paragraphs', '按来源顺序保留完整段落'),
        ('fair_source_quotas_bm25_windows', '按来源配额选取原文段落'),
    ):
        saved = {'mode': 'sources', 'budget_policy': policy, 'selected': [{'blocks': [2, 5]}]}
        before = copy.deepcopy(saved)
        assert budget_policy_label(saved) == expected
        assert saved == before
    assert budget_policy_label({'mode': 'spans'}) == '按片段组装'
