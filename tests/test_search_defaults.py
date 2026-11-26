"""Defaults, request preview and stop reporting agree without executing services."""
from dataclasses import asdict
import json
from pathlib import Path
import socket

import pytest
import yaml

from finmy.search.state import SearchConfig, SearchState
from finmy.search.control import SearchController
from finmy.search.summary import render
from finmy.workbench.search_defaults import load_defaults, clear_search_controls, request_preview, finalization_label


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('No service during configuration'))


def test_yaml_python_and_new_form_share_the_ark_bm25_profile(tmp_path):
    expected=asdict(SearchConfig())
    profile = yaml.safe_load((Path(__file__).resolve().parents[1]/'configs/search.yml').read_text())
    assert profile == expected
    assert expected['retrieval'] == {'mode': 'bm25'} and expected['lm_name'] == 'ark/deepseek-v4-1-flash-261017'
    assert load_defaults(tmp_path/'missing-profile.json')==expected
    assert expected['providers']==['baidu','bocha','exa']
    assert (expected['max_read_sources'],expected['max_model_calls'],expected['max_model_context_chars'])==(40,80,180000)
    assert expected['max_read_chars']==16000 and expected['max_builder_material_chars']==90000
    assert expected['generation_config']=={'max_tokens':8192}
    assert not expected['allow_network']
    preview=request_preview(expected['lm_name'],expected['generation_config'])
    assert preview['max_tokens']==8192 and preview['reasoning_effort']=='high'
    assert preview['thinking']=={'type':'enabled'} and preview['response_format']=={'type':'json_object'}
    assert (preview['temperature'],preview['top_p'])==(1.0,0.95)

    local = tmp_path/'profile.json'
    local.write_text(json.dumps({'providers': ['bocha']}))
    assert load_defaults(local) == {**expected, 'providers': ['bocha']}


def test_saved_profile_and_tasks_stay_fixed_and_parameter_widgets_refresh(tmp_path):
    saved=asdict(SearchConfig(providers=['bocha'],max_model_calls=60,max_read_sources=30,
                 max_model_context_chars=120000,generation_config={'max_tokens':4096},retrieval={'mode':'topic'}))
    profile=tmp_path/'profile.json';profile.write_text(json.dumps(saved))
    task=dict(target_type='event',target_name='Example',query_text='Trace public decisions')
    state=SearchState(tmp_path/'tasks','case',task=task,config=SearchConfig(**saved))
    before=(state.run_dir/'run.json').read_bytes()
    assert load_defaults(profile)==saved
    assert (state.run_dir/'run.json').read_bytes()==before
    session={'ui-search-tokens':4096,'ui-search-max_model_context_chars':120000,
             'ui-search-max_read_chars':12000,'ui-search-timeout':120,
             'ui-search-count-exa':4,'ui-search-model-provider':'ark',
             'ui-search-draft-event-query':'Keep my scope','ui-search-history':True}
    clear_search_controls(session)
    assert session=={'ui-search-draft-event-query':'Keep my scope','ui-search-history':True}


def test_explicit_budget_increase_reopens_only_the_relevant_finalization(tmp_path):
    controller=SearchController(tmp_path)
    task=dict(target_type='event',target_name='Example',query_text='Trace public decisions')
    tid=controller.create(task,{'max_model_calls':10,'max_model_context_chars':9000})
    state=SearchState(tmp_path,tid);state.data.update(finalization_trigger='context_limit',status='paused')
    state.data['usage']['model']=3;state.save()
    controller.configure(tid,{'max_model_calls':15})
    assert controller.inspect(tid)['finalization_trigger']=='context_limit'
    controller.configure(tid,{'max_model_context_chars':12000})
    current=controller.inspect(tid)
    assert 'finalization_trigger' not in current and current['usage']['model']==3
    assert current['config_history'][-1]['config']['max_model_context_chars']==9000


def test_summary_does_not_confuse_program_limit_and_model_assessment(tmp_path):
    scope={'period':'2000–2005','include':'Public decision','exclude':'Private motive'}
    task=dict(target_type='event',target_name='Example',query_text='Trace public decisions',research_scope=scope,
              catalog={'kind':'event','event_id':'E1','event_name':'Example'})
    state=SearchState(tmp_path,'case',task=task)
    state.data.update(status='finished',stop_reason='supported',termination_trigger='context_limit')
    text,_=render(state.data,'case',{}, {'user_query':{'query_text':task['query_text']},'samples':[]})
    assert 'Program finalization trigger: context_limit' in text
    assert 'model assessment: supported' in text
    assert finalization_label(state.data)=='模型上下文达到上限'
    assert finalization_label({'stop_reason':'supported'})==''
