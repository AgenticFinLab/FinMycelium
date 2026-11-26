import json
import socket
import pytest
from finmy.search.state import SearchState, SearchConfig
from finmy.search.retrieval import RetrievalSession, metadata_conflict, read_retrieved
from finmy.search.retrieval_eval import scores
from test_search_improvements import task, document


def state(tmp_path,mode='bm25',**extra):
    return SearchState(tmp_path,'x',task=task(),config=SearchConfig(
        retrieval=dict(mode=mode,top_k=1,**extra)))


def test_metadata_unknown_retrospective_and_known_conflict():
    scope=dict(entity_id='E1',event_id='X1',activity_start='2008-01-01',activity_end='2013-12-31')
    assert metadata_conflict(scope,{}) is None
    assert metadata_conflict(scope,dict(entity_id='E1',published_at='2025-01-01')) is None
    assert metadata_conflict(scope,dict(entity_id='E2'))=='entity_id'
    assert metadata_conflict(scope,dict(activity_start='2018-01-01',activity_end='2019-01-01'))=='activity_period'
    assert metadata_conflict(scope,dict(published_at='2025-01-01'),publication_end='2020-01-01')=='publication_filter'


def test_original_offsets_and_window_size(tmp_path):
    s=state(tmp_path,'bm25',window_chars=100)
    d=document('Orion Works delivery '+('details '*300))
    spans,reading=read_retrieved(RetrievalSession(s),d,'delivery',70,[])
    assert sum(len(x['text']) for x in spans)==70
    for x in spans: assert x['text']==d['blocks'][x['block']]['text'][x['start']:x['end']]
    assert scores(spans,[dict(block=0,start=0,end=20)])['evidence_char_recall']==1


def test_source_reader_uses_selected_mode_without_network(tmp_path):
    from finmy.search.sources import SourceStore
    s=state(tmp_path,'bm25');store=SourceStore(s)
    sid=store.register('https://example.org/notice')
    doc=store.save_raw(sid,b'Orion Works delivery occurred on 2013-10-04.','txt')
    result=store.read(sid,query='delivery 2013-10-04')
    assert result['reading']['mode']=='bm25'
    assert result['spans'] and s.data['usage']['model']==0
    ranges = list(s.data['sources'][sid]['read_ranges'])
    assert ranges[0]['version']==doc['version']
    replay = store.read(sid, query='delivery 2013-10-04')
    assert result['reading']['match_status'] == 'matched'
    assert replay['reading']['match_status'] == 'already_read'
    assert replay['spans'] == result['spans'] and s.data['sources'][sid]['read_ranges'] == ranges


def test_old_checkpoint_config_defaults_remain_resumable(tmp_path):
    s=SearchState(tmp_path,'x',task=task())
    s.data['config'].pop('retrieval');s.save()
    restored=SearchState(tmp_path,'x')
    assert restored.config.retrieval=={}
    assert SearchState(tmp_path,'x',config=s.data['config']).config == restored.config
    assert SearchState(tmp_path,'x',config=SearchConfig(retrieval={})).config == restored.config
    with pytest.raises(ValueError, match='retain saved configuration'):
        SearchState(tmp_path,'x',config=SearchConfig())


def test_unknown_metadata_survives_while_explicit_conflict_filters(tmp_path):
    s=state(tmp_path,'bm25')
    s.data['task']['retrieval_constraints']={'event_id':'target'}
    d=document('Delivery happened in this event.', 'Delivery happened in a different event.')
    d['blocks'][1]['evidence_scope']={'event_id':'other'}
    hits,report=RetrievalSession(s).rank(d,'delivery')
    assert [x['block'] for x in hits]==[0]
    assert report['metadata_exclusions'][0]['reason']=='event_id'


@pytest.mark.parametrize('mode',['hybrid','bm25_rerank','hybrid_rerank'])
def test_removed_modes_are_rejected(mode):
    with pytest.raises(ValueError,match='mode must be topic or bm25'):
        SearchConfig(retrieval={'mode':mode})


@pytest.mark.parametrize('option',['embedding_model_path','device','query_prefix',
                                  'passage_prefix','embedding_batch_size','rerank_batch_size'])
def test_removed_model_options_are_rejected(option):
    with pytest.raises(ValueError,match='accepts only'):
        SearchConfig(retrieval={'mode':'bm25',option:1})


def test_bm25_needs_no_network_model_or_model_cache(tmp_path,monkeypatch):
    from finmy.search.agent import LmbaseModel
    def forbidden(*args,**kwargs):
        pytest.fail('BM25 must not invoke a model or external service')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(LmbaseModel,'__call__',forbidden)
    s=state(tmp_path)
    d=document('Orion Works delivery occurred on 2013-10-04.', 'Unrelated operations.')
    before=dict(s.data['usage'])
    hits,report=RetrievalSession(s).rank(d,'delivery 2013-10-04')
    assert hits and [h['block'] for h in hits]==[0]
    assert report['ranked_ids']==report['bm25_ids']
    assert s.data['usage']==before
    assert not (s.run_dir/'retrieval-cache').exists()
    s.save()
    resumed=SearchState(tmp_path,'x')
    assert RetrievalSession(resumed).rank(d,'delivery 2013-10-04')==(hits,report)


def test_historical_costs_survive_without_empty_model_stage_reports(tmp_path):
    from finmy.search.eval import search_usage
    s=state(tmp_path)
    current=search_usage(s)
    assert 'reranking' not in current and 'embedding' not in current
    s.trace(dict(action='rerank_response',usage=dict(prompt_tokens=20,completion_tokens=3),duration_seconds=1))
    s.trace(dict(action='embedding_batch',count=2,duration_seconds=.5))
    historical=search_usage(s)
    assert historical['input_tokens']==20 and historical['output_tokens']==3
    assert historical['reranking']['calls']==1 and historical['embedding']['texts']==2
