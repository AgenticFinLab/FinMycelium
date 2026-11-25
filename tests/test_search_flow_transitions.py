"""Acquisition, inspection and finish share their contracts across entry points."""
from copy import deepcopy
import json

import pytest

from finmy.search.agent import context_for, execute_action, prepare_context, run_agent
from finmy.search.evidence import record_passages
from finmy.search.inspection import accept_presentation, pending_passages
from finmy.search.progress import record_progress
from finmy.search.review import lead_reviews
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, saved, finish, offline


HEAD = 'Ada Vale said the Orion education grant would be delivered subject to local'
TAIL = ' consent. The committee confirmed the transfer on July 8.'
FULL = HEAD + TAIL + ' Ada Vale described the Orion education program and its agreed funding terms.'
SEED = 'https://example.org/annual-letter'


@pytest.mark.parametrize('entrypoint', ['store', 'tool', 'agent'])
@pytest.mark.parametrize('cursor', [{'block': 1, 'offset': 0}, {'block': 0, 'offset': 5}])
def test_nonzero_first_read_completes_without_rebasing_old_cursor(tmp_path, entrypoint, cursor):
    state, tools = setup(tmp_path)
    sid, old = saved(tools, 'partial', HEAD)
    calls = []
    def fetch(url):
        calls.append(url)
        return FULL.encode(), 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    if entrypoint == 'store':
        result = tools.sources.read(sid, **cursor)
    elif entrypoint == 'tool':
        result = tools.read_source(sid, cursor, agent_feedback=True)
    else:
        result = execute_action(state, tools, dict(action='read_source', source=sid, location=cursor))
    assert result['kind'] == 'source_version_changed' and result['operation_deferred']
    assert result['previous_version'] == old['version'] != result['version']
    assert result['requested_location'] == cursor and not result['spans']
    entry = state.data['sources'][sid]
    assert not entry.get('read_ranges') and not entry.get('query_read_attempts')
    assert not state.data.get('priority_passages') and not pending_passages(state)
    assert tools.sources.document(sid, old['version']) == old
    state.data['research_progress'] = {'consecutive_no_gain': 5}
    record_progress(state, 'review_passages', result)
    assert state.data['research_progress']['consecutive_no_gain'] == 0
    assert state.data['research_progress']['new_chars'] == 0
    state.save()
    resumed = SearchState(tmp_path, 'case')
    result = SearchTools(resumed, fetcher=fetch).read_source(sid, result['next_location'], agent_feedback=True)
    assert ''.join(s['text'] for s in result['spans']) == FULL
    assert len(calls) == 1 and resumed.data['read_sources'] == [sid]
    assert all(r['version'] == result['version'] for r in resumed.data['sources'][sid]['read_ranges'])


@pytest.mark.parametrize('entrypoint', ['store_query', 'tool_zero', 'agent_query', 'preview'])
def test_other_first_read_paths_use_the_same_expanded_version(tmp_path, entrypoint):
    state, tools = setup(tmp_path)
    sid, old = saved(tools, 'partial', HEAD)
    calls = []
    def fetch(url):
        calls.append(url)
        return FULL.encode(), 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    if entrypoint == 'preview':
        context = prepare_context(state, tools)
        result = next(c for c in context['cached_evidence'] if c['source_id'] == sid)
        assert not state.data['sources'][sid].get('read_ranges')
        accept_presentation(state, context)
    elif entrypoint == 'store_query':
        result = tools.sources.read(sid, query='Orion grant')
    elif entrypoint == 'tool_zero':
        result = tools.read_source(sid, {'block': 0, 'offset': 0})
    else:
        result = execute_action(state, tools, dict(action='read_source', source=sid, query='Orion grant'))
    assert result['version'] != old['version']
    assert TAIL in ''.join(s['text'] for s in result['spans'])
    assert len(calls) == 1
    assert all(r['version'] == result['version'] for r in state.data['sources'][sid]['read_ranges'])


@pytest.mark.parametrize('response', ['blocked', 'same', 'unrelated', 'unparseable'])
def test_failed_nonzero_completion_keeps_original_cursor_and_is_not_retried(tmp_path, response):
    state, tools = setup(tmp_path)
    sid, old = saved(tools, 'partial', HEAD)
    calls = []
    def fetch(url):
        calls.append(url)
        if response == 'blocked':
            raise PermissionError('Test denial')
        if response == 'same':
            return HEAD.encode(), 'txt', 'utf-8'
        if response == 'unrelated':
            return b'Unrelated advertising. ' * 100, 'txt', 'utf-8'
        return b'not a PDF', 'pdf', 'utf-8'
    result = SearchTools(state, fetcher=fetch).read_source(sid, {'offset': 5})
    assert result['version'] == old['version'] and result['spans'][0]['start'] == 5
    assert result['spans'][0]['text'] == HEAD[5:]
    resumed = SearchState(tmp_path, 'case')
    SearchTools(resumed, fetcher=fetch).read_source(sid, {'offset': 5})
    assert len(calls) == 1
    assert resumed.data['sources'][sid]['acquisition_attempts'][old['version']]['status'] == 'kept_cached'


def seed_case(tmp_path, **options):
    state, tools = setup(tmp_path, **options)
    kept, doc = saved(tools, 'kept', 'Ada Vale approved the Orion program.', read=True)
    state.data['task']['seed_urls'] = [SEED]
    seed = tools.sources.register(SEED)
    return state, tools, kept, doc, seed


@pytest.mark.parametrize('reason', ['supported', 'low_gain', 'insufficient'])
@pytest.mark.parametrize('legacy', [False, True])
def test_all_voluntary_finish_variants_require_unread_supplied_leads(tmp_path, reason, legacy):
    state, tools, kept, doc, seed = seed_case(tmp_path)
    action = finish([kept]); action['reason'] = reason
    if legacy:
        action.pop('source_ids')
        action['selections'] = [dict(source_id=kept, version=doc['version'], block=0,
                                     start=0, end=len(doc['blocks'][0]['text']))]
    before = deepcopy(state.data['sources'])
    result = execute_action(state, tools, action)
    assert result['kind'] == 'source_leads_pending' and result['operation_deferred']
    assert result['next_steps'] == [dict(action='read_source', source=seed, location={'block': 0, 'offset': 0})]
    assert not (state.run_dir / 'builder_input.json').exists()
    assert state.data['status'] == 'ready' and state.data['sources'] == before
    assert state.data['usage'] == {'search': 0, 'model': 0}


def test_cached_body_is_not_a_read_and_unknown_seed_uses_its_url(tmp_path):
    state, tools, kept, _, seed = seed_case(tmp_path)
    tools.sources.save_raw(seed, FULL.encode(), 'txt')
    state.data['task']['seed_urls'].append('https://example.org/second-letter')
    result = execute_action(state, tools, finish([kept]))
    assert result['pending_count'] == 2
    assert [s['source'] for s in result['next_steps']] == [seed, 'https://example.org/second-letter']
    assert not state.data['sources'][seed].get('read_ranges')


@pytest.mark.parametrize('skip_key', ['id', 'url'])
def test_skip_decision_survives_pending_passages_and_resume(tmp_path, skip_key):
    state, tools, kept, doc, seed = seed_case(tmp_path)
    state.data['priority_passages'] = []
    accept_presentation(state, context_for(state))
    assert pending_passages(state)
    action = finish([kept], source_lead_decisions={seed if skip_key == 'id' else SEED: 'Duplicate edition.'})
    assert execute_action(state, tools, action)['kind'] == 'pending_evidence'
    resumed = SearchState(tmp_path, 'case')
    before = deepcopy(resumed.data)
    assert context_for(resumed)['source_leads'][0]['status'] == 'skipped'
    assert resumed.data == before
    record_passages(resumed, [dict(source_id=kept, block=0, start=0, end=len(doc['blocks'][0]['text']))])
    execute_action(resumed, SearchTools(resumed), finish([kept]))
    assert resumed.data['status'] == 'finished'
    assert resumed.data['source_lead_review'][0]['reason'] == 'Duplicate edition.'


def test_previous_finish_checkpoint_retains_explicit_skip(tmp_path):
    state, tools, kept, _, seed = seed_case(tmp_path)
    state.data['source_lead_review'] = [dict(url=SEED, source_id=seed, status='skipped', reason='Duplicate edition.')]
    state.save()
    resumed = SearchState(tmp_path, 'case')
    execute_action(resumed, SearchTools(resumed), finish([kept]))
    assert resumed.data['status'] == 'finished'
    assert resumed.data['source_lead_review'][0]['status'] == 'skipped'


@pytest.mark.parametrize('decisions', [[], {'unknown': 'Duplicate.'}, {SEED: ''}])
def test_invalid_skip_does_not_unlock_finish_or_persist(tmp_path, decisions):
    state, tools, kept, _, _ = seed_case(tmp_path)
    with pytest.raises(ValueError, match='source_lead_decisions'):
        execute_action(state, tools, finish([kept], source_lead_decisions=decisions))
    assert not state.data.get('source_lead_decisions')
    assert not (state.run_dir / 'builder_input.json').exists()


@pytest.mark.parametrize('failure', ['fetch_failed', 'parser_failed'])
def test_unavailable_seed_allows_low_gain_finish_without_looping(tmp_path, failure):
    state, tools, kept, _, seed = seed_case(tmp_path)
    def fetch(url):
        if failure == 'fetch_failed':
            raise PermissionError('Test denial')
        return b'not a PDF', 'pdf', 'utf-8'
    result = SearchTools(state, fetcher=fetch).read_source(seed)
    assert result['status'] == failure
    execute_action(state, tools, finish([kept]))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    row = state.data['source_lead_review'][0]
    assert row['status'] == 'unavailable' and failure in row['reason']
    selection = json.loads((state.run_dir / 'selection.json').read_text())
    assert any(SEED in gap and failure in gap for gap in selection['gaps'])


@pytest.mark.parametrize('trigger', ['model_call_budget', 'context_limit', 'no_reading_progress', None])
def test_forced_finalization_preserves_unread_seed_gap(tmp_path, trigger):
    state, tools, kept, _, _ = seed_case(tmp_path)
    if trigger:
        state.data['finalization_trigger'] = trigger
    else:
        state.data['usage']['model'] = state.config.max_model_calls
    execute_action(state, tools, finish([kept]))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    selection = json.loads((state.run_dir / 'selection.json').read_text())
    assert any(SEED in gap for gap in selection['gaps'])


def test_source_budget_blocks_only_new_sources_not_a_reserved_unread_source(tmp_path):
    state, tools, kept, _, seed = seed_case(tmp_path, max_read_sources=2)
    state.reading(seed)  # A cursor invalidation or interrupted acquisition reserved this slot.
    state.data['task']['seed_urls'].append('https://example.org/extra')
    result = execute_action(state, tools, finish([kept]))
    assert result['pending_count'] == 1 and result['next_steps'][0]['source'] == seed
    execute_action(state, tools, finish([kept], source_lead_decisions={seed: 'Duplicate edition.'}))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    assert 'budget exhausted' in state.data['source_lead_review'][1]['reason']


def test_inspected_seed_and_other_unread_candidates_do_not_block_finish(tmp_path):
    state, tools, kept, _, seed = seed_case(tmp_path)
    tools.sources.save_raw(seed, FULL.encode(), 'txt')
    tools.read_source(seed)
    saved(tools, 'unrequested', 'Unrequested background material.')
    execute_action(state, tools, finish([kept], source_exclusions={seed: 'The retained source already covers the needed facts.'}))
    assert state.data['status'] == 'finished' and lead_reviews(state)[0]['status'] == 'read'


def test_deferred_finish_resumes_reads_and_delivers_the_supplied_original(tmp_path):
    state, tools, kept, _, seed = seed_case(tmp_path)
    calls = []
    def fetch(url):
        calls.append(url)
        return FULL.encode(), 'txt', 'utf-8'
    tools = SearchTools(state, fetcher=fetch)
    run_agent(state, tools, lambda context: finish([kept]), max_steps=1)
    assert state.data['status'] == 'paused' and not state.data.get('actions')
    assert not (state.run_dir / 'builder_input.json').exists()
    resumed = SearchState(tmp_path, 'case')
    contexts = []
    def decide(context):
        contexts.append(context)
        if len(contexts) == 1:
            assert context['feedback']['kind'] == 'source_leads_pending'
            return context['feedback']['next_steps'][0]
        return finish([kept, seed], priority_passages=[dict(source_id=seed, block=0, start=0, end=len(FULL))])
    run_agent(resumed, SearchTools(resumed, fetcher=fetch), decide)
    assert resumed.data['status'] == 'finished' and resumed.data['usage']['model'] == 3
    assert len(calls) == 1 and FULL in (resumed.run_dir / 'builder_input.json').read_text()
    assert resumed.data['source_lead_review'][0]['status'] == 'read'
    assert [a['action'] for a in resumed.data['actions']] == ['read_source', 'finish']


def test_version_change_resume_and_finish_share_the_same_inspection_state(tmp_path):
    state, tools = setup(tmp_path)
    # This short unfinished heading offers no candidate paragraph. The first
    # explicit read therefore exercises acquisition inside the ordinary loop.
    head = 'Ada Vale said the Orion grant was conditional on local'
    text = head + TAIL + ' Ada Vale explained the agreed education funding terms.'
    sid, old = saved(tools, 'partial', head)
    state.data['task']['seed_urls'] = [state.data['sources'][sid]['url']]
    state.data['research_progress'] = {'consecutive_no_gain': 5}
    calls = []
    def fetch(url):
        calls.append(url)
        return text.encode(), 'txt', 'utf-8'
    run_agent(state, SearchTools(state, fetcher=fetch),
              lambda context: dict(action='read_source', source=sid, location={'offset': 5}), max_steps=1)
    assert state.data['status'] == 'paused'
    assert state.data['feedback']['kind'] == 'source_version_changed'
    assert state.data['research_progress']['consecutive_no_gain'] == 0
    assert not state.data.get('actions') and not state.data['sources'][sid].get('read_ranges')
    assert execute_action(state, tools, finish([]))['kind'] == 'source_leads_pending'
    resumed = SearchState(tmp_path, 'case')
    def decide(context):
        candidate = next(c for c in context['cached_evidence'] if c['source_id'] == sid)
        assert candidate['version'] != old['version']
        return finish([sid], priority_passages=[dict(source_id=sid, version=candidate['version'],
            block=s['block'], start=s['start'], end=s['end']) for s in candidate['spans']])
    run_agent(resumed, SearchTools(resumed, fetcher=fetch), decide)
    assert resumed.data['status'] == 'finished' and len(calls) == 1
    assert resumed.data['usage']['model'] == 2
    assert [a['action'] for a in resumed.data['actions']] == ['finish']
    assert text in (resumed.run_dir / 'builder_input.json').read_text()


def test_ignored_seed_feedback_is_bounded_by_existing_finalization(tmp_path):
    state, tools, kept, _, _ = seed_case(tmp_path)
    run_agent(state, tools, lambda context: finish([kept]))
    assert state.data['status'] == 'finished' and state.data['stop_reason'] == 'low_gain'
    assert state.data['termination_trigger'] == 'no_reading_progress'
    assert state.data['usage']['model'] == 7
    assert len(state.data['actions']) == 1
