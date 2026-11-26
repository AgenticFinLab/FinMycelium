"""Cached navigation and repeat-query control, without paid calls."""
import json
import socket

import pytest

from finmy.search.agent import execute_action, run_agent
from finmy.search.evidence import record_passages
from finmy.search.retrieval import cached_candidates
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))


def setup(tmp_path, **options):
    task = dict(target_type='event', target_name='Orion education program',
        query_text='Research the Orion program and Ada Vale decisions and conditions.',
        key_words=['Orion', 'Ada Vale', 'education', 'commitment'],
        catalog=dict(kind='person_event', person_name='Ada Vale', event_name='Orion education program'),
        research_scope=dict(include='education, commitment', period='2020'))
    config = dict(retrieval={'mode':'bm25'}, allow_network=True)
    config.update(options)
    state = SearchState(tmp_path, 'case', task=task, config=SearchConfig(**config))
    tools = SearchTools(state, fetcher=lambda url: pytest.fail('Use the cached original'))
    tools.sources.can_complete_partial = False  # These tests isolate cached selection.
    return state, tools


def saved(tools, name, text, *, read=False, scope=None):
    sid = tools.sources.register('https://example.org/'+name, title='Ada Vale on the Orion program')
    doc = tools.sources.save_raw(sid, text.encode(), 'txt', partial=not read,
        parsed=(dict(status='success', blocks=[dict(text=text, evidence_scope=scope)]) if scope else None))
    if read:
        result = tools.read_source(sid, location={'block':0})
        record_passages(tools.state, [dict(source_id=sid, **{k:s[k] for k in ('block','start','end')})
                                     for s in result['spans']])
    return sid, doc


def finish(ids, **extra):
    return dict(action='finish', source_ids=ids, gaps=[], reason='supported', **extra)


def test_finish_does_not_scan_generic_conditions_or_mark_unshown_cache(tmp_path):
    state, tools = setup(tmp_path)
    kept, _ = saved(tools, 'notice', 'The Orion education program launched in 2020.', read=True)
    condition, doc = saved(tools, 'interview',
        'ADA VALE: If local support failed, I would not fund the Orion program.')
    feedback=execute_action(state,tools,finish([kept]))
    assert state.data['status']=='finished' and 'candidates' not in feedback
    assert not state.data['sources'][condition].get('read_ranges')
    assert not state.data.get('finish_candidate_review')
    payload=json.loads((state.run_dir/'builder_input.json').read_text())
    assert [s['raw_data_id'] for s in payload['samples']]==[kept]
    assert tools.sources.document(condition)==doc


@pytest.mark.parametrize('options', [{'max_model_calls':1}, {'max_read_sources':1}])
def test_finish_review_respects_existing_limits(tmp_path, options):
    state, tools = setup(tmp_path, **options)
    kept, _ = saved(tools, 'notice', 'The Orion program launched in 2020.', read=True)
    candidate, _ = saved(tools, 'interview', 'Ada Vale stipulated that Orion needed consent.')
    run_agent(state, tools, lambda c: finish([kept]))
    assert state.data['usage']['model'] == 1 and state.data['status'] == 'finished'
    assert not state.data['sources'][candidate].get('read_ranges')


def test_review_has_bounded_sources_and_text_and_skips_metadata_conflicts(tmp_path):
    state, tools = setup(tmp_path, max_read_chars=200)
    state.data['task']['retrieval_constraints'] = {'event_id':'target'}
    for n in range(5):
        saved(tools, 'condition'+str(n), f'Ada Vale stipulated that Orion needed consent from district {n}.')
    bad, _ = saved(tools, 'wrong-event', 'Ada Vale stipulated conditions for the Orion program.', scope={'event_id':'other'})
    later, _ = saved(tools, 'retrospective', 'Ada Vale stipulated that Orion needed permission first.',
                     scope={'event_id':'target', 'published_at':'2025-01-01'})
    candidates = cached_candidates(state, finish([]))
    assert 0 < len(candidates) <= 3
    assert sum(len(s['text']) for c in candidates for s in c['spans']) <= 200
    assert bad not in {c['source_id'] for c in candidates}
    # Missing metadata and later publication are both eligible, not vetoed.
    for sid in list(state.data['sources']):
        if sid not in (bad, later): del state.data['sources'][sid]
    assert [c['source_id'] for c in cached_candidates(state, finish([]))] == [later]


def test_no_candidate_means_no_extra_model_call_and_bad_source_ids_still_fail(tmp_path):
    state, tools = setup(tmp_path)
    kept, _ = saved(tools, 'notice', 'The Orion program launched in 2020.', read=True)
    saved(tools, 'copy', 'The Orion program launched in 2020.')
    run_agent(state, tools, lambda c: finish([kept]))
    assert state.data['status'] == 'finished' and state.data['usage']['model'] == 1
    with pytest.raises(ValueError, match='Unknown source'):
        execute_action(state, tools, finish(['invented']))


def test_review_keeps_a_short_question_with_its_answer(tmp_path):
    state, tools = setup(tmp_path)
    question = 'INTERVIEWER: Would Orion proceed without local consent?'
    answer = 'ADA VALE: If that consent was missing, I would not proceed.'
    saved(tools, 'interview', question+'\n\n'+answer)
    candidates = cached_candidates(state, finish([]))
    assert len(candidates) == 1
    assert [s['text'] for s in candidates[0]['spans']] == [question, answer]


def repeated_reads(tmp_path):
    state, tools = setup(tmp_path, max_read_chars=85)
    text = '\n\n'.join(f'Orion program approval in 2020 needed community consent from district {i}.' for i in range(15))
    sid, _ = saved(tools, 'long', text)
    tools.sources.can_complete_partial = False
    q1 = 'Orion program approval 2020 community consent'
    q2 = 'Orion community consent program approvals 2020'
    first = tools.read_source(sid, query=q1, agent_feedback=True)
    second = tools.read_source(sid, query=q2, agent_feedback=True)
    assert first['progress']['new_chars'] > 0 and second['progress']['new_chars'] > 0
    return state, tools, sid, q1, first, second


def test_new_characters_without_evidence_do_not_allow_endless_rewording(tmp_path):
    state, tools, sid, query, _, _ = repeated_reads(tmp_path)
    before = list(state.data['sources'][sid]['read_ranges'])
    resumed = SearchState(tmp_path, 'case')
    result = SearchTools(resumed).read_source(sid, query=query, agent_feedback=True)
    assert result['reading']['match_status'] == 'no_evidence_gain' and result['spans'] == []
    assert resumed.data['sources'][sid]['read_ranges'] == before
    assert resumed.data['usage'] == {'model':0, 'search':0}


def test_new_marks_allow_useful_followup_and_other_source_marks_do_not(tmp_path):
    state, tools, sid, query, first, _ = repeated_reads(tmp_path)
    saved(tools, 'another', 'Ada Vale announced the Orion commitment.', read=True)
    assert tools.read_source(sid, query=query, agent_feedback=True)['reading']['match_status'] == 'no_evidence_gain'
    span = first['spans'][0]
    record_passages(state, [dict(source_id=sid, **{k:span[k] for k in ('block','start','end')})])
    assert tools.read_source(sid, query=query, agent_feedback=True)['spans']


@pytest.mark.parametrize('change', ['question', 'year', 'negation', 'location', 'version'])
def test_new_questions_locations_and_versions_are_readable(tmp_path, change):
    state, tools, sid, query, _, _ = repeated_reads(tmp_path)
    if change == 'version':
        tools.sources.save_raw(sid, b'Orion program approval changed after additional community consent.', 'txt')
    query = {'question':'Orion education funding donations', 'year':query.replace('2020','2021'),
             'negation':'not '+query}.get(change, query)
    if change == 'location':
        result = tools.read_source(sid, location={'block':8}, agent_feedback=True)
    else:
        result = tools.read_source(sid, query=query, agent_feedback=True)
    assert result.get('reading', {}).get('match_status') != 'no_evidence_gain'


def test_a_changed_day_or_amount_is_not_a_reworded_query(tmp_path):
    from finmy.search.progress import query_read_feedback, record_query_read
    state, tools, sid, _, first, _ = repeated_reads(tmp_path)
    state.data['sources'][sid]['query_read_attempts'] = []
    for query in ('Orion approval April 18 2020 $5.50 million', 'April 18 2020 Orion approval $5.5 million'):
        record_query_read(state, sid, query, first)
    assert query_read_feedback(state, sid, 'Orion approval April 18 2020 $5.50 million')
    assert query_read_feedback(state, sid, 'Orion approval April 19 2020 $5.50 million') is None
    assert query_read_feedback(state, sid, 'Orion approval April 18 2020 $6.50 million') is None
