import json
import pytest
from finmy.search.state import SearchState, SearchConfig
from finmy.search.hybrid import RetrievalSession, metadata_conflict, read_retrieved
from finmy.search.retrieval_eval import scores
from test_search_improvements import task, document


class Encoder:
    identity='test-semantic-v1'
    def __init__(self): self.calls=0
    def __call__(self, texts):
        self.calls+=1
        return [[1.,0.] if ('delivery' in t or 'handed over' in t) else [0.,1.] for t in texts]


def state(tmp_path,mode='hybrid',**extra):
    return SearchState(tmp_path,'x',task=task(),config=SearchConfig(
        retrieval=dict(mode=mode,embedding_model_path='fixture',top_k=1,**extra)))


def test_semantic_recall_adds_synonym_and_cache_survives_session(tmp_path):
    s=state(tmp_path);encoder=Encoder()
    d=document('Orion Works delivery instructions are on our unrelated jobs page.',
               'The crates were handed over to the purchaser yesterday.')
    a=RetrievalSession(s,encoder=encoder)
    hits,report=a.rank(d,'Orion Works delivery')
    assert len(report['bm25_ids'])==1
    # Semantic fixture focuses the query on handed-over, avoiding a lexical tie.
    class Specific(Encoder):
        identity='test-semantic-v2'
        def __call__(self,texts):
            self.calls+=1
            return [[1.,0.] if t=='Orion Works delivery' or 'handed over' in t else [0.,1.] for t in texts]
    encoder=Specific();a=RetrievalSession(s,encoder=encoder)
    hits,report=a.rank(d,'Orion Works delivery')
    assert {x['block'] for x in hits}=={0,1}
    n=encoder.calls
    again,_=RetrievalSession(s,encoder=encoder).rank(d,'Orion Works delivery')
    assert again==hits and encoder.calls==n
    assert s.data['usage']['model']==0


def test_metadata_unknown_retrospective_and_known_conflict():
    scope=dict(entity_id='E1',event_id='X1',activity_start='2008-01-01',activity_end='2013-12-31')
    assert metadata_conflict(scope,{}) is None
    assert metadata_conflict(scope,dict(entity_id='E1',published_at='2025-01-01')) is None
    assert metadata_conflict(scope,dict(entity_id='E2'))=='entity_id'
    assert metadata_conflict(scope,dict(activity_start='2018-01-01',activity_end='2019-01-01'))=='activity_period'
    assert metadata_conflict(scope,dict(published_at='2025-01-01'),publication_end='2020-01-01')=='publication_filter'


def test_rerank_checks_evidence_keeps_unknown_and_caches(tmp_path):
    s=state(tmp_path,'bm25_rerank');s.config.retrieval['top_k']=10
    d=document('Orion Works delivery is completed.', 'Other company delivery is completed.',
               'Delivery is reportedly planned; the actor is unclear.')
    calls=[]
    def model(payload):
        calls.append(payload)
        return dict(labels=[dict(id=c['id'],entity='mismatch' if c['block']==1 else 'match' if c['block']==0 else 'unknown',
            attribute='match',evidence='direct' if c['block']==0 else 'unknown',quote=c['text'],reason='fixture') for c in payload['candidates']])
    a=RetrievalSession(s,reranker=model);hits,r=a.rank(d,'delivery')
    assert [x['block'] for x in hits]==[0,2]
    assert s.data['usage']['model']==1
    assert RetrievalSession(s,reranker=model).rank(d,'delivery')[0]==hits
    assert len(calls)==1 and s.data['usage']['model']==1
    # Modified task invalidates a cached relevance judgment.
    s.data['task']['query_text']='A changed event scope'
    a.rank(d,'delivery');assert len(calls)==2


def test_failed_rerank_is_counted_and_not_cached(tmp_path):
    s=state(tmp_path,'bm25_rerank')
    def bad(payload): return dict(labels=[])
    with pytest.raises(ValueError):
        RetrievalSession(s,reranker=bad).rank(document('Orion Works delivery was completed.'),'delivery')
    assert s.data['usage']['model']==1
    assert not list((s.run_dir/'retrieval-cache').glob('rerank-*.json'))


def test_reserved_model_calls_leave_unknown_candidates(tmp_path):
    s=state(tmp_path,'bm25_rerank');s.data['usage']['model']=s.config.max_model_calls-2
    def forbidden(payload): raise AssertionError('no remaining rerank budget')
    hits,record=RetrievalSession(s,reranker=forbidden).rank(document('Orion Works delivery happened.'),'delivery')
    assert hits and not record['labels']


def test_original_offsets_and_window_size(tmp_path):
    s=state(tmp_path,'bm25',window_chars=100)
    d=document('Orion Works delivery '+('details '*300))
    spans,reading=read_retrieved(RetrievalSession(s),d,'delivery',70,[])
    assert sum(len(x['text']) for x in spans)==70
    for x in spans: assert x['text']==d['blocks'][x['block']]['text'][x['start']:x['end']]
    assert scores(spans,[dict(block=0,start=0,end=20)])['evidence_char_recall']==1


def test_invalid_embedding_configuration_and_dimensions(tmp_path):
    with pytest.raises(ValueError):SearchConfig(retrieval=dict(mode='hybrid'))
    from finmy.search.hybrid import unit_vectors
    with pytest.raises(ValueError):unit_vectors([[float('nan')]],1)
    with pytest.raises(ValueError):unit_vectors([[1,0],[1]],2)


def test_source_reader_uses_selected_mode_without_network(tmp_path):
    from finmy.search.sources import SourceStore
    s=state(tmp_path,'bm25');store=SourceStore(s)
    sid=store.register('https://example.org/notice')
    doc=store.save_raw(sid,b'Orion Works delivery occurred on 2013-10-04.','txt')
    result=store.read(sid,query='delivery 2013-10-04')
    assert result['reading']['mode']=='bm25'
    assert result['spans'] and s.data['usage']['model']==0
    assert s.data['sources'][sid]['read_ranges'][0]['version']==doc['version']


def test_old_checkpoint_config_defaults_remain_resumable(tmp_path):
    s=SearchState(tmp_path,'x',task=task())
    s.data['config'].pop('retrieval');s.save()
    restored=SearchState(tmp_path,'x',config=SearchConfig())
    assert restored.config.retrieval=={}


def test_unknown_metadata_survives_while_explicit_conflict_filters(tmp_path):
    s=state(tmp_path,'bm25')
    s.data['task']['retrieval_constraints']={'event_id':'target'}
    d=document('Delivery happened in this event.', 'Delivery happened in a different event.')
    d['blocks'][1]['evidence_scope']={'event_id':'other'}
    hits,report=RetrievalSession(s).rank(d,'delivery')
    assert [x['block'] for x in hits]==[0]
    assert report['metadata_exclusions'][0]['reason']=='event_id'


def test_rerank_resume_reuses_completed_batches_after_failure(tmp_path):
    s=state(tmp_path,'bm25_rerank',rerank_batch_size=1);s.config.retrieval['top_k']=3
    d=document('Orion Works delivery happened.', 'Orion Works delivery was confirmed.')
    calls=[]
    def flaky(payload):
        calls.append(payload)
        if len(calls)==2: raise RuntimeError('simulated interruption')
        return dict(labels=[dict(id=c['id'],entity='match',attribute='match',evidence='direct',
                                 quote=c['text'],reason='fixture') for c in payload['candidates']])
    with pytest.raises(RuntimeError):RetrievalSession(s,reranker=flaky).rank(d,'delivery')
    assert s.data['usage']['model']==2
    hits,_=RetrievalSession(s,reranker=flaky).rank(d,'delivery')
    assert len(calls)==3 and len(hits)==2
