"""Long-report focus without dropping attributed responses or changing saved runs."""
from copy import deepcopy
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search import budget
from finmy.search.evidence import record_passages
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))


@pytest.mark.parametrize('focus,noise,query', [
    ('Cedar scholarship commitment required community approval.',
     'Annual operations report 2024.', 'Cedar scholarship community approval annual report 2024'),
    ('林女士承诺资助社区图书馆，但须居民同意。',
     '年度运营报告2024。', '林女士 社区图书馆 资助 居民同意 年度报告 2024'),
    ('Mira announced caregiving leave to support her family.',
     'Annual activity report 2024.', 'Mira family caregiving leave annual report 2024'),
    ('Orion opened its regional laboratory following approval.',
     'Annual activity report 2024.', 'Orion regional laboratory approval annual report 2024'),
])
def test_broad_report_words_do_not_override_specific_question(focus, noise, query):
    document = {'blocks': [{'text': focus}] + [{'text': noise} for _ in range(35)]}
    entry = {'blocks': list(range(len(document['blocks'])))}
    current = budget.rank_blocks(entry, document, [query], focused=True,
                                 min_relative_score=.3, query_coverage=True)[0]['ranking']
    assert current[0][0] == 0
    assert len(current) == 1
    # Directed reading and v3 handoff assembly use ordinary BM25.
    assert budget.rank_blocks(entry, document, [query]) == budget.rank_blocks(
        entry, document, [query], query_coverage=False)


def test_single_term_and_unmatched_queries_keep_safe_fallbacks():
    doc = {'blocks': [{'text': 'Consent required.'}, {'text': 'Routine report.'}]}
    entry = {'blocks': [0, 1]}
    for query in ('consent', 'unmentioned', ''):
        assert budget.rank_blocks(entry, doc, [query], query_coverage=True) == budget.rank_blocks(
            entry, doc, [query])


def test_marked_response_and_context_survive_report_filtering_and_replay(tmp_path):
    state = SearchState(tmp_path, 'case', task=dict(
        target_type='event', target_name='Cedar community library',
        query_text='Trace the library commitment and community consent.'),
        config=SearchConfig(max_read_chars=100000))
    store = SourceStore(state)
    parts = ['Cedar community library commitment announced in the annual report.',
             'Only with community consent would the library open.']
    parts += ['Annual operations report 2024. ' * 80 + str(i) for i in range(8)]
    parts += ['An interviewer asked about the request.',
              'She declined it until residents agreed.',
              'No date was given and the account is retrospective.']
    parts += ['Routine maintenance report 2024. ' * 80 + str(i) for i in range(8)]
    sid = store.register('https://example.org/annual-report')
    doc = store.save_raw(sid, '\n\n'.join(parts).encode(), 'txt')
    store.read(sid)
    record_passages(state, [dict(source_id=sid, block=11, start=0, end=len(parts[11]))])
    _, complete = prepare_complete_sources(state, [sid])
    complete['reading_queries'] = [dict(source_id=sid, version=doc['version'],
        query='Cedar community library commitment annual report 2024')]
    complete.pop('complete_id'); complete['complete_id'] = digest(complete)
    frozen = deepcopy(complete)
    payload, record = derive_input(state, complete, max_chars=2000)
    content = payload['samples'][0]['content']
    for part in parts[:2] + parts[10:13]:
        assert part in content
    assert 'Routine maintenance' not in content
    assert record['material_chars'] <= 2000
    assert record['allocation']['priority_decisions'][0]['status'] == 'with_context'
    stages = record['allocation']['threshold_stages']
    assert [s['threshold'] for s in stages] == [.5, .4, .3]
    for before, after in zip(stages, stages[1:]):
        assert set(before['selected_blocks'][sid]) <= set(after['selected_blocks'][sid])
    assert record['budget_policy'] == 'evidence_priority_windows_v3'
    assert 'ranking_policy' not in record['allocation']
    old = deepcopy(complete); old['budget_policy'] = 'evidence_priority_windows_v4'
    old.pop('complete_id'); old['complete_id'] = digest(old)
    replay = derive_input(state, old, max_chars=2000)
    assert replay[1]['allocation']['ranking_policy'] == 'bm25_idf_query_coverage_shared'
    explicit = derive_input(state, complete, max_chars=2000,
                            allocation_policy=budget.QUERY_COVERAGE_POLICY)
    assert replay[0] == explicit[0]
    assert replay[1]['selected'] == explicit[1]['selected']
    assert replay[1]['complete_id'] == old['complete_id']
    assert record['allocation']['base_decisions'] == replay[1]['allocation']['base_decisions']
    assert complete == frozen and not (state.run_dir / 'builder_input.json').exists()
    assert state.data['usage'] == {'search': 0, 'model': 0}
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']:
        DataSample(**sample)
