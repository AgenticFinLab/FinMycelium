"""Offline recovery: one bounded loop and explicit retry after setup repair."""
from copy import deepcopy
import json

import pytest
import requests

from finmy.search.agent import LmbaseModel
from finmy.search.control import SearchController
from finmy.search.pipeline import run_search
from finmy.search.state import SearchConfig, SearchState, digest
from test_model_api import offline, transport


TASK = dict(target_type='event', target_name='Synthetic acquisition',
            query_text='Trace the announcement and closing of an invented acquisition.')
URL = 'https://example.org/announcement'
SID = digest(URL)[:24]
READ = dict(action='read_source', source=URL)
FINISH = dict(action='finish', source_ids=[SID], gaps=[], reason='supported')


def trace(root, task_id='case'):
    return [json.loads(line) for line in
            (root/task_id/'runs/initial/trace.jsonl').read_text().splitlines()]


def test_five_consecutive_correctable_errors_recover_without_restart(tmp_path):
    search = dict(action='search', query='x'*73, gap='Closing date remains unknown')
    responses = iter([READ, search, 'invalid', search, 'invalid', search, FINISH])
    seen, fetched = [], []
    def decide(context):
        seen.append(deepcopy(context))
        return next(responses)
    def fetch(url):
        fetched.append(url)
        return b'The fictional acquisition closed.', 'txt', 'utf-8'
    result = run_search(TASK, root=tmp_path, task_id='case',
        config={'providers':['baidu','bocha','exa'], 'max_model_calls':10},
        model=decide, fetcher=fetch, transport=lambda *a:pytest.fail('Invalid queries must not execute'))
    assert result['status']=='finished' and result['usage']=={'model':7,'search':0}
    assert fetched==[URL] and len(seen)==7
    assert '72' in seen[2]['feedback']['hint']
    assert 'No action was executed' in seen[3]['feedback']['hint']
    rows=trace(tmp_path)
    assert not any(row['action']=='retry_started' for row in rows)
    assert len([row for row in rows if row['action']=='action_error' and row['recoverable']])==5
    assert SearchState(tmp_path,'case').data['invalid_actions']==0


@pytest.mark.parametrize('status',[400,401,403,404,422])
def test_model_setup_rejection_stops_once_and_can_be_manually_retried(tmp_path,transport,status):
    transport['status']=status
    config=SearchConfig(lm_name='tokenhub/deepseek/deepseek-flash',allow_network=True,max_model_calls=4)
    result=run_search(TASK,root=tmp_path,task_id='case',config=config,model=LmbaseModel(config))
    assert result['status']=='failed' and result['usage']['model']==1
    state=SearchState(tmp_path,'case')
    assert state.data['stop_reason']=='configuration_error'
    assert str(status) in state.data['feedback']['hint']
    assert len(transport['requests'])==1
    assert trace(tmp_path)[-1]['recoverable'] is False
    original=(state.run_dir/'trace.jsonl').read_bytes()
    # Operator repairs access/settings; retry uses the same task and usage.
    transport['status']=200
    transport['content']=json.dumps(dict(action='finish',source_ids=[],gaps=['No evidence'],reason='insufficient'))
    retried=run_search(root=tmp_path,task_id='case',model=LmbaseModel(config))
    assert retried['status']=='insufficient' and retried['usage']['model']==2
    assert (state.run_dir/'trace.jsonl').read_bytes().startswith(original)
    assert 'synthetic-tokenhub-key' not in (state.run_dir/'trace.jsonl').read_text()
    assert any(row['action']=='retry_started' and row['previous_stop_reason']=='configuration_error'
               for row in trace(tmp_path))


@pytest.mark.parametrize('status',[429,500])
def test_temporary_model_api_errors_use_total_budget(tmp_path,transport,status):
    transport['status']=status
    config=SearchConfig(lm_name='tokenhub/deepseek/deepseek-flash',allow_network=True,max_model_calls=5)
    result=run_search(TASK,root=tmp_path,task_id='case',config=config,model=LmbaseModel(config))
    assert result['status']=='limit' and result['usage']['model']==5
    assert len(transport['requests'])==5  # No hidden SDK retries.
    assert result['builder_input_path'] is None


def test_missing_model_key_stops_without_requests_and_retry_cannot_grant_budget(tmp_path,transport,monkeypatch):
    monkeypatch.delenv('HUNYUAN_API_KEY')
    config=SearchConfig(lm_name='tokenhub/deepseek/deepseek-flash',allow_network=True,max_model_calls=1)
    result=run_search(TASK,root=tmp_path,task_id='case',config=config,model=LmbaseModel(config))
    assert result['status']=='failed' and result['usage']['model']==1
    assert transport['requests']==[]
    assert 'HUNYUAN_API_KEY' in SearchState(tmp_path,'case').data['feedback']['hint']
    monkeypatch.setenv('HUNYUAN_API_KEY','synthetic-new-key')
    result=run_search(root=tmp_path,task_id='case',model=LmbaseModel(config))
    assert result['status']=='limit' and result['usage']['model']==1
    assert transport['requests']==[]


def http_error(status):
    response=requests.Response()
    response.status_code=status
    return requests.HTTPError('synthetic-secret-must-not-leak',response=response)


def test_provider_key_repair_reuses_successes_and_preserves_cumulative_requests(tmp_path):
    repaired=False
    calls=[]
    def provider(name,payload,config):
        calls.append(name)
        if name=='exa' and not repaired:
            raise http_error(401)
        item=dict(url=URL,title='Announcement',name='Announcement',text='Fictional deal closed.')
        return {'references':[item]} if name=='baidu' else (
            {'data':{'webPages':{'value':[item]}}} if name=='bocha' else {'results':[item]})
    def decide(context):
        if not context['prior_actions']:
            return dict(action='search',query='fictional acquisition',gap='Need closing evidence')
        if not context['sources'][0]['reviewed']:
            return READ
        return FINISH
    controller=SearchController(tmp_path,model=decide,transport=provider,
        fetcher=lambda url:(b'Fictional deal closed.','txt','utf-8'))
    tid=controller.create(TASK,{'providers':['bocha','exa','baidu'],'max_search_requests':6})
    controller.start(tid);controller.threads[tid].join(5)
    failed=controller.inspect(tid)
    assert not controller.active(tid)
    assert failed['status']=='failed' and failed['stop_reason']=='configuration_error'
    assert failed['usage']=={'model':1,'search':2} and calls==['bocha','exa']
    assert len(failed['sources'])==1 and failed['cache']
    assert 'synthetic-secret' not in json.dumps(failed)
    assert 'synthetic-secret' not in (tmp_path/tid/'runs/initial/trace.jsonl').read_text()
    repaired=True
    controller.start(tid);controller.threads[tid].join(5)
    result=controller.inspect(tid)
    assert not controller.active(tid)
    assert result['status']=='finished' and result['usage']=={'model':4,'search':4}
    assert calls==['bocha','exa','exa','baidu']  # Successful Bocha request stayed cached.
    assert result['task']==failed['task'] and result['config']==failed['config']


def test_website_access_denied_is_a_source_failure_not_a_task_setup_failure(tmp_path):
    responses=iter([READ,dict(action='finish',source_ids=[],gaps=['Source blocked'],reason='insufficient')])
    def blocked(url):
        raise http_error(403)
    result=run_search(TASK,root=tmp_path,task_id='case',model=lambda c:next(responses),fetcher=blocked)
    assert result['status']=='insufficient' and result['usage']=={'model':2,'search':0}
    assert SearchState(tmp_path,'case').data['sources'][SID]['status']=='fetch_failed'


@pytest.mark.parametrize('provider,variable',[
    ('bocha','BOCHA_API_KEY'),('baidu','BAIDUSEARCH_API_KEY'),('exa','EXA_API_KEY')])
def test_missing_search_key_stops_before_network(tmp_path,monkeypatch,provider,variable):
    monkeypatch.delenv(variable,raising=False)
    result=run_search(TASK,root=tmp_path,task_id='case',
        config={'providers':[provider],'allow_network':True},
        model=lambda c:dict(action='search',query='fictional acquisition'))
    state=SearchState(tmp_path,'case')
    assert result['status']=='failed' and result['usage']=={'model':1,'search':1}
    assert state.data['stop_reason']=='configuration_error'
    assert variable in state.data['feedback']['hint']


def test_simple_mode_bocha_access_error_can_be_retried_after_repair(tmp_path):
    repaired=False
    def provider(*args):
        if not repaired:
            return {'code':401,'message':'synthetic-secret-must-not-leak'}
        return {'code':200,'data':{'webPages':{'value':[{'url':URL,'name':'Announcement'}]}}}
    controller=SearchController(tmp_path,transport=provider,
        fetcher=lambda url:(b'Fictional deal closed.','txt','utf-8'))
    tid=controller.create(TASK,{},mode='simple')
    controller.start(tid);controller.threads[tid].join(5)
    failed=controller.inspect(tid)
    assert not controller.active(tid)
    assert failed['status']=='failed' and failed['stop_reason']=='configuration_error'
    assert failed['usage']=={'model':0,'search':1}
    assert 'BOCHA_API_KEY' in failed['feedback']['hint']
    assert not (tmp_path/tid/'runs/initial/responses/1.json').exists()
    repaired=True
    controller.start(tid);controller.threads[tid].join(5)
    result=controller.inspect(tid)
    assert not controller.active(tid)
    assert result['status']=='finished' and result['usage']=={'model':0,'search':2}
    assert 'synthetic-secret' not in json.dumps(result)
