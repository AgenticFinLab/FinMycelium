"""Protect located context and keep source admission distinct from allocation."""
from copy import deepcopy
import socket

import pytest

from finmy.search import budget
from finmy.search.evidence import record_passages
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))


def setup(tmp_path):
    s = SearchState(tmp_path, 'case', task=dict(target_type='person', target_name='Ada',
                   query_text='Ada accepted invitation'),
                   config=SearchConfig(max_read_chars=100000, max_read_sources=30))
    return s, SourceStore(s)


def saved(store, name, paragraphs):
    sid = store.register('https://example.org/' + name, title=name)
    doc = store.save_raw(sid, '\n\n'.join(paragraphs).encode(), 'txt')
    return sid, doc


def test_marked_passage_keeps_question_and_qualifications_without_recursive_fill(tmp_path):
    s, store = setup(tmp_path)
    background = ['Routine maintenance. '*120+str(i) for i in range(5)]
    parts = background + ['Several institutions requested support.',
                          'The interviewer asked which request she accepted.',
                          'Ada accepted the invitation.',
                          'The statement was made at a public meeting.',
                          'Only if the community agreed would implementation begin.']
    parts += ['Unrelated inventory. '*120+str(i) for i in range(10)]
    sid, doc = saved(store, 'interview', parts)
    SearchTools(s).read_source(sid, query='Ada accepted invitation')
    record_passages(s, [dict(source_id=sid, block=7, start=0, end=len(parts[7]))])
    _, complete = prepare_complete_sources(s, [sid])
    old, _ = derive_input(s, complete, max_chars=2200, allocation_policy=budget.SOURCE_QUERY_POLICY)
    payload, selection = derive_input(s, complete, max_chars=2200)
    body = payload['samples'][0]['content']
    for part in parts[5:10]:
        assert part in body
    assert parts[9] not in old['samples'][0]['content']
    assert 'Unrelated inventory.' not in body
    assert selection['material_chars'] <= 2200
    assert selection['allocation']['thresholds'] == [.5, .4, .3]
    # Replaying a saved previous policy still means its original context behavior.
    previous = deepcopy(complete); previous['budget_policy'] = budget.SOURCE_QUERY_POLICY
    previous.pop('complete_id'); previous['complete_id'] = digest(previous)
    assert derive_input(s, previous, max_chars=2200)[0] == old


def test_window_recovers_one_preceding_antecedent(tmp_path):
    s, store = setup(tmp_path)
    parts = ['Unrelated maintenance. '*150+str(i) for i in range(5)]
    parts += ['The proposed arrangement required independent local consent.',
              'At that point, the participants were discussing the conditions.',
              'Ada accepted the invitation.',
              'The exact day was not disclosed.']
    parts += ['Unrelated inventory. '*150+str(i) for i in range(10)]
    sid, _ = saved(store, 'statement', parts)
    SearchTools(s).read_source(sid, query='Ada accepted invitation')
    _, complete = prepare_complete_sources(s, [sid])
    old, _ = derive_input(s, complete, max_chars=1800, allocation_policy=budget.SOURCE_QUERY_POLICY)
    new, record = derive_input(s, complete, max_chars=1800)
    assert parts[5] not in old['samples'][0]['content']
    assert parts[5] in new['samples'][0]['content']
    assert record['material_chars'] <= 1800 and 'Unrelated inventory.' not in new['samples'][0]['content']


def test_spare_budget_accepts_more_retained_sources_but_not_unreviewed_candidates(tmp_path):
    s, store = setup(tmp_path)
    ids = []
    for i in range(22):
        sid, _ = saved(store, str(i), [f'Independent account {i}: Ada accepted an invitation with qualifications.'])
        store.read(sid)
        ids.append(sid)
    unread, _ = saved(store, 'unread', ['Unverified lead.'])
    _, narrow = prepare_complete_sources(s, ids[:18])
    limited, _ = derive_input(s, narrow, max_chars=20000)
    assert len(limited['samples']) == 18
    # Additional admitted originals participate in the same quota/shared pool.
    _, complete = prepare_complete_sources(s, ids)
    expanded, record = derive_input(s, complete, max_chars=20000)
    assert len(expanded['samples']) == 22 and record['material_chars'] <= 20000
    assert unread in record['unselected_sources']
    assert s.data['usage'] == {'search': 0, 'model': 0}
    with pytest.raises(ValueError, match='Inspect'):
        prepare_complete_sources(s, ids + [unread])
