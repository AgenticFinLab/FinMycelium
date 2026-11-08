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


def test_new_trace_waiting_provider_and_reading():
    events=[{'action':'model_started','model_call':4,'time':'2026-11-08T00:00:00+00:00'},
            {'action':'model_response','response':{'action':'search','query':'q'},'duration_seconds':2},
            {'action':'provider_started','provider':'bocha','query':'q'}]
    rows=timeline(events,{'status':'running'})
    assert len(rows)==1 and rows[0]['pending_provider']=='bocha'
    events += [{'action':'provider_result','provider':'bocha','status':'success','result_count':2,'duration_seconds':1},
               {'action':'search','query':'q','result':{'source_ids':['a','b'],'providers':[{'provider':'bocha','status':'success'}]}},
               {'action':'action_completed','operation':'search'},
               {'action':'model_started','model_call':5},
               {'action':'model_response','response':{'action':'read_source','source':'a'}},
               {'action':'read_started','source':'a','location':{'block':0}},
               {'action':'read_source','source':'a','result':{'status':'partial','spans':[{'text':'abc'}],'at_end_of_saved_text':True}}]
    rows=timeline(events,{'status':'paused'})
    assert len(rows)==2 and rows[0]['providers'][0]['result_count']==2
    assert rows[1]['chars']==3 and rows[1]['at_end'] and rows[1]['read_status']=='partial'


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


def test_simple_search_and_successful_finish():
    rows=timeline([
        {'action':'provider_started','provider':'exa','query':'q'},
        {'action':'search','query':'q','result':{'source_ids':[],'providers':[{'provider':'exa','status':'no_results'}]}},
        {'action':'read_started','source':'a'},
        {'action':'read_source','source':'a','result':{'status':'fetch_failed','error_type':'HTTPError'}},
    ],{'status':'insufficient'})
    assert len(rows)==2 and rows[0]['model_call'] is None
    assert rows[1]['status']=='error'
    rows=timeline([{'action':'model_response','response':{'action':'finish','selections':[]}},
                   {'action':'action_completed','operation':'finish','sample_count':0}],{'status':'insufficient'})
    assert rows[0]['status']=='completed' and rows[0]['sample_count']==0


def test_old_unrecorded_action_is_not_shown_as_still_running():
    rows=timeline([
        {'action':'model_response','response':{'action':'search','query':'too long'}},
        {'action':'model_response','response':{'action':'read_source','source':'a'}},
    ],{'status':'paused'})
    assert all(r['status']=='unconfirmed' for r in rows)
    assert all(not r['errors'] for r in rows)  # Missing records do not prove a failure.


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
