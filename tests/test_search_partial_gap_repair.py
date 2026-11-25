"""Regression coverage for partial cache acquisition and stale finish-gap wording."""
from copy import deepcopy
import json

from finmy.search.agent import context_for, execute_action, prepare_context, run_agent
from finmy.search.evidence import record_passages
from finmy.search.review import record_checks, saved_gap_evidence
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline
from test_search_evidence_routing import check
from test_search_integrated_review import mark


def test_cached_partial_is_completed_before_its_first_presentation(tmp_path):
    state, tools = setup(tmp_path)
    head = 'Ada Vale said the Orion grant would be delivered subject to local'
    full = (head + ' consent. The committee confirmed the transfer on July 8. '
            'Ada Vale explained that the Orion allocation supported the agreed education '
            'program and that the local consent requirement remained in force.')
    sid, original = saved(tools, 'notice', head)
    calls = []
    def fetch(url):
        calls.append(url)
        return full.encode(), 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    before = deepcopy(state.data)
    context_for(state)  # A read-only preview must not fetch or mark anything.
    assert state.data == before and not calls
    contexts = []
    def decide(context):
        contexts.append(context)
        candidate = next(c for c in context['cached_evidence'] if c['source_id'] == sid)
        assert candidate['version'] != original['version']
        assert full in ' '.join(s['text'] for s in candidate['spans'])
        refs = [dict(source_id=sid, version=candidate['version'],
                     **{k:s[k] for k in ('block','start','end')}) for s in candidate['spans']]
        return finish([sid], priority_passages=refs)
    run_agent(state, tools, decide)
    assert len(calls) == len(contexts) == 1
    assert state.data['status'] == 'finished'
    assert state.data['usage'] == {'model':1, 'search':0}
    assert full in (state.run_dir/'builder_input.json').read_text()
    assert tools.sources.document(sid, original['version']) == original
    resumed = SearchState(tmp_path, 'case')
    SearchTools(resumed, fetcher=fetch).read_source(sid, query='Orion grant')
    assert len(calls) == 1


def test_failed_completion_keeps_partial_and_does_not_retry_after_resume(tmp_path):
    state, tools = setup(tmp_path)
    sid, original = saved(tools, 'notice', 'Ada Vale said the Orion grant would be delivered subject to local')
    calls = []
    def denied(url):
        calls.append(url)
        raise PermissionError('Blocked test source')
    tools = SearchTools(state, fetcher=denied)
    first = prepare_context(state, tools)
    assert first['cached_evidence'][0]['version'] == original['version']
    assert not state.data['sources'][sid].get('read_ranges')
    assert first['sources'][0]['acquisition']['status'] == 'kept_cached'
    resumed = SearchState(tmp_path, 'case')
    prepare_context(resumed, SearchTools(resumed, fetcher=denied))
    assert len(calls) == 1
    assert tools.sources.document(sid) == original


def test_newly_ranked_partial_waits_without_unbounded_fetches(tmp_path, monkeypatch):
    state, tools = setup(tmp_path)
    first, _ = saved(tools, 'first', 'Ada Vale approved the Orion program.')
    later, _ = saved(tools, 'later', 'Ada Vale funded Orion subject to local')
    from finmy.search import agent
    calls = []
    def fetch(url):
        calls.append(url)
        return b'Ada Vale approved the Orion program. More original detail.', 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    contexts = iter([dict(phase='research', cached_evidence=[dict(source_id=first)]),
                     dict(phase='research', cached_evidence=[dict(source_id=later)])])
    monkeypatch.setattr(agent, 'context_for', lambda state: next(contexts))
    context = prepare_context(state, tools)
    assert len(calls) == 1 and 'cached_evidence' not in context
    assert not state.data['sources'][later].get('read_ranges')
    assert not state.data['sources'][later].get('acquisition_attempts')


def test_gap_review_restores_saved_quantity_without_promoting_planned_receipt(tmp_path):
    state, tools = setup(tmp_path)
    text = 'The Orion committee will deliver 7,321 units to Ada Vale on July 8.'
    sid, _ = saved(tools, 'notice', text, read=True)
    announcement = check('What delivery was announced?', sid, mark(sid,0,text),
                         detail='7,321 units were announced for July 8.')
    record_checks(state, [announcement])
    old_gap = 'The exact number of Orion units to be delivered was not found.'
    contexts = []
    def decide(context):
        contexts.append(context)
        if len(contexts) == 1:
            action = finish([sid]); action['gaps'] = [old_gap]
            return action
        assert context['feedback']['kind'] == 'finish_gap_review'
        assert text in [p['text'] for p in context['saved_gap_evidence']]
        receipt = check('Were the announced units actually received?', sid, mark(sid,0,text),
            status='planned', detail='7,321 units were announced for July 8; actual receipt remains unconfirmed.')
        return finish([sid], fact_checks=[receipt])
    run_agent(state, tools, decide)
    assert len(contexts) == 2 and state.data['usage'] == {'model':2, 'search':0}
    report = json.loads((state.run_dir/'selection.json').read_text())
    assert old_gap not in report['gaps']
    assert any('7,321' in g and 'unconfirmed' in g for g in report['gaps'])
    assert report['fact_checks'][1]['status'] == 'planned'
    assert text in (state.run_dir/'builder_input.json').read_text()


def test_last_budget_call_has_saved_gap_evidence_without_an_extra_stage(tmp_path):
    state, tools = setup(tmp_path, max_model_calls=1)
    text = 'The Orion committee will deliver 7,321 units to Ada Vale on July 8.'
    sid, _ = saved(tools, 'notice', text, read=True)
    state.data['proposed_gap_notes'] = ['The exact number of Orion units was not found.']
    original = deepcopy(state.data['priority_passages'])
    def decide(context):
        assert context['phase'] == 'finalize'
        assert text in [p['text'] for p in context['saved_gap_evidence']]
        return finish([sid], fact_checks=[check('Were the announced units received?',
            sid, mark(sid,0,text), status='planned',
            detail='The notice specifies 7,321 units; actual receipt is not confirmed.')])
    run_agent(state, tools, decide)
    assert state.data['status'] == 'finished' and state.data['usage']['model'] == 1
    assert state.data['priority_passages'][0] == original[0]


def test_saved_gap_preview_is_bounded_exact_and_never_invents_a_sentence_tail(tmp_path):
    state, tools = setup(tmp_path)
    text = 'Ada Vale will receive 7,321 Orion units subject to'
    sid, doc = saved(tools, 'partial-notice', text)
    tools.read_source(sid, query='Orion')
    record_passages(state, [mark(sid,0,text)])
    assert not saved_gap_evidence(state, ['Orion units'], max_chars=40)
    rows = saved_gap_evidence(state, ['Orion units'], max_chars=1000)
    assert len(json.dumps(rows,ensure_ascii=False)) + 32 <= 1000
    assert rows[0]['text'] == text
    assert doc['blocks'][rows[0]['block']]['text'][rows[0]['start']:rows[0]['end']] == text
    assert not saved_gap_evidence(state, ['Orion units'], max_chars=1000, selected=[])


def test_gap_check_is_bounded_even_if_model_repeats_the_same_note(tmp_path):
    state, tools = setup(tmp_path)
    sid, _ = saved(tools, 'notice', 'Ada Vale will receive 7,321 Orion units.', read=True)
    action = finish([sid]); action['gaps'] = ['The number of Orion units was not found.']
    assert execute_action(state, tools, action)['kind'] == 'finish_gap_review'
    execute_action(state, tools, action)
    assert state.data['status'] == 'finished'
