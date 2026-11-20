"""Offline checks for source-range budgets and prompt compaction."""
from copy import deepcopy
import json

import pytest

from test_person_event_contract import payload
from test_person_event_runtime import Model, valid
from finmy.person_epg.event.read_dedup import compact_read_results, next_read_charge
from finmy.person_epg.event.records import seed_facts, fingerprint, json_bytes, sha256
from finmy.person_epg.event.runtime import Corpus, EventBuildConfig, Execution, LimitReached
from finmy.person_epg.event.scheduling import Task


def read(start=0, end=10, sid='SAMPLE-1'):
    return dict(tool='read_sample', sample_id=sid, start=start, end=end)


def entry(corpus, request):
    return dict(request=request, result=corpus.read(request))


def test_overlap_versions_and_legacy_history(payload):
    corpus = Corpus(payload, seed_facts(payload), EventBuildConfig())
    first = entry(corpus, read(0, 20))
    overlap = entry(corpus, read(10, 30))
    assert next_read_charge(corpus.samples, [first], **overlap) == (20, 10)
    assert next_read_charge(corpus.samples, [first, overlap], **first) == (30, 0)
    old = dict(first, sample_versions={'SAMPLE-1': 'older-source-version'})
    assert next_read_charge(corpus.samples, [old], **first) == (20, 20)
    changed = deepcopy(first)
    changed['result']['text'] = 'changed content'
    spent, added = next_read_charge(corpus.samples, [changed], **first)
    assert spent == len(json_bytes(changed['result']).decode()) and added == 20


def test_body_and_read_overlap_preserve_text_offsets_and_originals(payload):
    corpus = Corpus(payload, seed_facts(payload), EventBuildConfig())
    request = dict(body=corpus.read(read(10, 20)))
    entries = [entry(corpus, read(0, 30)), entry(corpus, read(5, 25)), entry(corpus, read(0, 30))]
    before = deepcopy((request, entries))
    compact = compact_read_results(request, entries, corpus.samples)
    texts = [r['result'] for r in compact if 'text' in r['result']]
    assert [(r['start'], r['end']) for r in texts] == [(0, 10), (20, 30)]
    for r in texts:
        assert r['text'] == corpus.samples[r['sample_id']]['content'][r['start']:r['end']]
    assert compact[-1]['result']['already_supplied']
    assert (request, entries) == before


def test_search_and_sample_share_ranges(payload):
    corpus = Corpus(payload, seed_facts(payload), EventBuildConfig())
    item = corpus.read(read(0, 20))
    search = dict(request={'tool': 'search', 'query': 'test'}, result=[item, item])
    assert next_read_charge(corpus.samples, [], **search) == (0, 20)
    assert next_read_charge(corpus.samples, [search], **entry(corpus, read(10, 30))) == (20, 10)
    compact = compact_read_results({}, [search, entry(corpus, read(0, 20))], corpus.samples)
    assert compact[0]['result'][0]['text'] == item['text']
    assert compact[0]['result'][1]['already_supplied']
    assert compact[1]['result']['already_supplied']


def test_parallel_tasks_share_budget_but_each_receives_text(tmp_path, payload):
    seen = []
    def model(system, user, name):
        user = json.loads(user)
        if not user['read_results']:
            return {'read_requests': [read()]}
        seen.append((name, user['read_results'][0]['result']['text']))
        return {'ok': True}
    run = Execution(tmp_path, payload, EventBuildConfig(max_read_chars=10, extraction_workers=3), model,
                    model_factory=lambda: model)
    facts = seed_facts(payload)
    outcomes = run.execute_tasks('relations', [Task(name, run.infer_steps(name, 's', {}, facts, valid))
                                             for name in ('a', 'b', 'c')])
    assert all(t.error is None and t.result == {'ok': True} for t in outcomes.values())
    assert len(seen) == 3 and all(text == payload['samples'][0]['content'][:10] for _, text in seen)
    assert [r['budget_chars'] for r in run.state['reads']] == [10, 0, 0]
    assert run.state['read_budget']['charged_chars'] == 10
    # Audit history remains intact and distinct from charged source characters.
    assert len(run.state['reads']) == 3 and all(r['chars'] > 10 for r in run.state['reads'])


def test_resume_rebuilds_old_budget_and_keeps_checks_and_round_limit(tmp_path, payload):
    cfg = EventBuildConfig(max_read_chars=10)
    model = Model([{'read_requests': [read()]}, {'ok': True}])
    run = Execution(tmp_path, payload, cfg, model)
    facts = seed_facts(payload)
    run.infer('a', 's', {}, facts, valid)
    for r in run.state['reads']:
        r.pop('budget_chars'); r.pop('sample_versions')
    run.state.pop('read_budget')
    run.persist()
    model = Model([{'read_requests': [read()]}, {'ok': True}, {'read_requests': [read(10, 20)]}])
    resumed = Execution(tmp_path, payload, cfg, model, resume=True)
    resumed.infer('a', 's', {}, facts, valid)  # Paid checkpoint, no model call.
    resumed.infer('b', 's', {}, facts, valid)
    with pytest.raises(LimitReached, match='read_chars'):
        resumed.infer('c', 's', {}, facts, valid)
    assert len(model.calls) == 3 and resumed.state['read_budget']['charged_chars'] == 10
    assert len(resumed.state['reads']) == 2


def test_paid_legacy_prefetched_response_survives_compaction(tmp_path, payload):
    cfg = EventBuildConfig()
    request = dict(body=Corpus(payload, seed_facts(payload), cfg).read(read()))
    facts = seed_facts(payload)
    run = Execution(tmp_path, payload, cfg, Model([{'read_requests': [read()]}, TimeoutError()]))
    with pytest.raises(TimeoutError):
        run.infer('a', 's', request, facts, valid)
    call = run.state['calls'][-1]
    task = next(iter(run.state['tasks'].values()))
    legacy = dict(task=request, read_results=task['read_results'])
    call.update(status='prefetched', request_fingerprint=fingerprint(dict(system='s', user=legacy)),
                prefetched_response=call['response_path'], prefetched_sha256=sha256(json_bytes({'ok': True})))
    (tmp_path / call['response_path']).write_text(json.dumps({'raw': {'ok': True}}))
    run.persist()
    model = Model([])
    resumed = Execution(tmp_path, payload, cfg, model, resume=True)
    assert resumed.infer('a', 's', request, facts, valid) == {'ok': True}
    assert not model.calls
