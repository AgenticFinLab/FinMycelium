"""Provider result limits are independent of shared request and reading budgets."""
import socket
from collections import Counter
from dataclasses import asdict
import pytest
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools, request_payload

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('No network'))


def test_per_provider_payload_caps_shared_requests_and_cached_replay(tmp_path):
    cfg=SearchConfig(providers=['baidu','bocha','exa'])
    state=SearchState(tmp_path,'case',task=dict(target_type='event',target_name='Example',query_text='Research documented actions'),config=cfg)
    calls=[]
    def transport(provider,payload,config):
        calls.append(provider)
        query=payload.get('query') or payload['messages'][0]['content']
        items=[dict(url=f'https://example.org/{provider}/{query}/{i}',title='Original title') for i in range(10)]
        return {'references':items} if provider=='baidu' else {'data':{'webPages':{'value':items}}} if provider=='bocha' else {'results':items}
    tools=SearchTools(state,transport=transport)
    assert request_payload('baidu','query',cfg)['resource_type_filter'][0]['top_k']==4
    assert request_payload('bocha','query',cfg)['count']==4
    assert request_payload('exa','query',cfg)['numResults']==8
    for n in range(4):
        assert len(tools.search('q'+str(n))['source_ids'])==16
    assert state.data['usage']['search']==12 and Counter(calls)=={'baidu':4,'bocha':4,'exa':4}
    counts=Counter(s['discoveries'][0]['provider'] for s in state.data['sources'].values())
    assert counts=={'baidu':16,'bocha':16,'exa':32}
    assert len(tools.search('q0')['source_ids'])==16 and len(calls)==12
    assert all(p['status']=='limit' for p in tools.search('q4')['providers'])
    resumed=SearchState(tmp_path,'case')
    assert asdict(resumed.config)==asdict(cfg) and resumed.data['usage']['search']==12


def test_scalar_saved_settings_keep_their_original_limits(tmp_path):
    old=SearchConfig(providers=['baidu','bocha','exa'],max_results=5,max_read_sources=20,max_model_calls=40)
    state=SearchState(tmp_path,'old',task=dict(target_type='event',target_name='Example',query_text='Original request'),config=old)
    restored=SearchState(tmp_path,'old')
    assert asdict(restored.config)==asdict(old)
    assert [restored.config.results_for(p) for p in old.providers]==[5,5,5]
    for provider in old.providers:
        assert request_payload(provider,'原始查询 Original',old)


@pytest.mark.parametrize('value',[True,0,51,{}, {'bocha':True}, {'bocha':0}, {'bocha':4,'unknown':4}])
def test_invalid_result_limits_rejected(value):
    with pytest.raises(ValueError): SearchConfig(max_results=value)
