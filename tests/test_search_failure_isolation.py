"""A provider/model/source interruption cannot discard unrelated usable work."""
import copy
import json
from unittest.mock import Mock

import pytest
import requests

from finmy.search.agent import context_for, run_agent
from finmy.search.control import SearchController
from finmy.search.handoff import assemble_sources, materialize_complete, prepare_complete_sources
from finmy.search.sources import SourceIntegrityError, SourceStore, repair_saved_sources
from finmy.search.state import SearchConfig, SearchState, write_json
from finmy.search.tools import SearchTools


def fixture(tmp_path, *, calls=24):
    state = SearchState(tmp_path, 'event', task=dict(target_type='event', target_name='Investment',
        query_text='Buffett investment 2022-2023'),
        config=SearchConfig(providers=['bocha', 'baidu'], max_model_calls=calls))
    return state, SearchTools(state, transport=lambda *args: pytest.fail('Unexpected provider call'))


def source(state, name):
    store = SourceStore(state)
    sid = store.register('https://example.test/' + name, title=name)
    store.save_raw(sid, (name + ' original event text.').encode(), 'txt')
    store.read(sid)
    return sid


def finish(ids):
    return dict(action='finish', source_ids=ids, reason='supported', gaps=[])


def test_partial_checkpoint_without_resume_metadata_keeps_actual_usage(tmp_path):
    from dataclasses import asdict
    from finmy.runner.search_failures import read_task_usage
    state, tools = fixture(tmp_path)
    sid = source(state, 'valid')
    run_agent(state, tools, lambda _: finish([sid, 'unknown']), max_steps=1)
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'checkpoint'
    assert 'resume' not in state.data
    assert (state.run_dir / 'builder_input.json').exists()
    # Accept the nullable optional field in older saved checkpoints too.
    state.data['resume'] = None
    state.save()
    record = dict(status='paused', config=asdict(state.config))
    read_task_usage(record, state.run_dir / 'run.json')
    assert record['status'] == 'paused'
    assert record['usage'] == dict(search_calls=0, parse_calls=1, search_model_calls=1)
    assert 'resume' not in record


def unavailable(*, blocked=False):
    return dict(providers_available=[], all_providers_unavailable=True,
        retryable_providers=[] if blocked else ['baidu'],
        blocked_providers=['bocha'] if blocked else [],
        next_retry_at=None if blocked else 120,
        provider_health={'bocha': {'status': 'blocked'}} if blocked else {'baidu': {'status': 'cooldown'}})


def test_cooldown_pauses_empty_without_finish_call_and_resume_keeps_quota(tmp_path):
    state, tools = fixture(tmp_path)
    state.data['usage'] = dict(search=1, model=1)
    tools.begin_invocation = Mock(wraps=tools.begin_invocation)
    tools.search_availability = lambda: unavailable()
    run_agent(state, tools, lambda _: pytest.fail('Empty outage must not call model'))
    assert tools.begin_invocation.call_count == 1
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'provider_cooldown'
    assert state.data['resume']['next_retry_at'] == 120
    assert state.data['usage'] == dict(search=1, model=1)
    assert not (state.run_dir / 'builder_input.json').exists()
    restored = SearchState(tmp_path, 'event')
    sid = source(restored, 'recovered')
    run_agent(restored, SearchTools(restored), lambda _: finish([sid]))
    assert restored.data['status'] == 'finished'
    assert restored.data['usage'] == dict(search=1, model=2)


def test_recorded_403_429_pattern_does_not_finish_or_disable_sibling(tmp_path):
    """Replay the uploaded run's failure pattern without any external calls."""
    requests_made = []
    def rejected(provider, payload, config):
        requests_made.append(provider)
        response = requests.Response()
        response.status_code = 403 if provider == 'bocha' else 429
        response.headers['Retry-After'] = '4'
        response._content = b'{"message":"permission denied"}' if provider == 'bocha' else b'{"message":"rate limit"}'
        raise requests.HTTPError(response=response)
    state, tools = fixture(tmp_path)
    tools.transport = rejected
    tools.provider_health.clock = lambda: 100
    run_agent(state, tools, lambda _: dict(action='search', query='Buffett acquisition'))
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'provider_cooldown'
    assert state.data['resume']['next_retry_at'] == 104
    assert state.data['resume']['requires_action']  # Bocha still needs account action.
    assert state.data['usage'] == dict(search=2, model=1)
    sibling = SearchState(tmp_path, 'sibling', task=state.data['task'], config=state.config)
    sibling_tools = SearchTools(sibling, transport=rejected)
    sibling_tools.provider_health.clock = lambda: 100
    run_agent(sibling, sibling_tools, lambda _: dict(action='search', query='Buffett succession'))
    assert requests_made == ['bocha', 'baidu', 'bocha', 'baidu']
    assert sibling.data['usage'] == dict(search=2, model=1)
    # A later invocation can probe recovered service, and never erases old usage.
    restored = SearchState(tmp_path, 'event')
    restored_tools = SearchTools(restored, transport=lambda provider, *args:
        {'data': {'webPages': {'value': []}}} if provider == 'bocha' else {'references': []})
    restored_tools.provider_health.clock = lambda: 105
    replies = iter([dict(action='search', query='Buffett acquisition', gap='Timeline is still unsupported'), finish([])])
    run_agent(restored, restored_tools, lambda _: next(replies))
    assert restored.data['usage'] == dict(search=4, model=3)
    assert restored.data['status'] == 'insufficient'  # Actual no-results, not a service outage.


def test_blocked_access_pauses_with_manual_action_without_spending_model(tmp_path):
    state, tools = fixture(tmp_path)
    tools.search_availability = lambda: unavailable(blocked=True)
    run_agent(state, tools, lambda _: pytest.fail('No empty finish'))
    assert state.data['stop_reason'] == 'provider_blocked'
    assert state.data['resume']['requires_action']
    assert not state.data['resume']['retryable']
    assert state.data['usage']['model'] == 0


def test_outage_retains_explicit_partial_selection_and_reassemble_keeps_pause(tmp_path):
    state, tools = fixture(tmp_path)
    chosen, unused = source(state, 'chosen'), source(state, 'unused')
    tools.search_availability = lambda: unavailable()
    run_agent(state, tools, lambda _: finish([chosen]))
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'provider_cooldown'
    record = json.loads((state.run_dir / 'selection.json').read_text())
    assert record['source_ids'] == [chosen]
    assert record['reason'] == 'insufficient'
    old_resume = copy.deepcopy(state.data['resume'])
    SearchController(tmp_path).reassemble('event', 2000)
    restored = SearchState(tmp_path, 'event')
    assert restored.data['status'] == 'paused'
    assert restored.data['stop_reason'] == 'provider_cooldown'
    assert restored.data['resume'] == old_resume


def test_raw_integrity_error_quarantines_only_bad_source_and_good_handoff_survives(tmp_path):
    state, tools = fixture(tmp_path)
    bad, good = source(state, 'damaged'), source(state, 'valid')
    entry = state.data['sources'][bad]
    (state.root / 'sources' / bad / entry['version'] / 'raw').write_bytes(b'Altered evidence')
    context = context_for(state)
    assert context['eligible_source_ids'] == [good]
    assert [row['source_id'] for row in context['sources']] == [good]
    assert context['quarantined_sources'][0]['source_id'] == bad
    # An explicit selection containing a newly damaged sibling retains the good
    # model-selected subset without treating the bad bytes as evidence.
    run_agent(state, tools, lambda _: finish([bad, good]))
    assert state.data['status'] == 'insufficient'
    payload = json.loads((state.run_dir / 'builder_input.json').read_text())
    assert [row['raw_data_id'] for row in payload['samples']] == [good]
    assert 'Altered evidence' not in json.dumps(payload)
    assert state.data['usage']['model'] == 1
    with pytest.raises(SourceIntegrityError):
        prepare_complete_sources(state, [bad])


def test_source_repair_and_export_skip_one_bad_version_but_manifest_stays_strict(tmp_path):
    state, _ = fixture(tmp_path)
    bad, good = source(state, 'damaged'), source(state, 'valid')
    _, record = prepare_complete_sources(state, [bad, good])
    entry = state.data['sources'][bad]
    (state.root / 'sources' / bad / entry['version'] / 'parsed.json').unlink()
    errors = []
    payload = materialize_complete(state, record, source_errors=errors)
    assert [row['raw_data_id'] for row in payload['samples']] == [good]
    assert errors == [dict(source_id=bad, version=entry['version'],
                           error_type='SourceIntegrityError', stage='source_integrity')]
    repair_saved_sources(state)
    assert state.data['sources'][bad]['quarantine']['excluded_from_handoff']
    with pytest.raises(SourceIntegrityError):
        materialize_complete(state, record)
    record['selected'][0]['header'] = 'changed'
    with pytest.raises(ValueError, match='manifest integrity'):
        materialize_complete(state, record, source_errors=[])


def test_model_transport_error_pauses_once_and_resume_does_not_reset_budget(tmp_path):
    state, tools = fixture(tmp_path)
    sid = source(state, 'saved')
    assemble_sources(state, [sid], reason='insufficient')
    def failed(_):
        response = requests.Response()
        response.status_code = 429
        response._content = b'{"error":{"message":"rate limit"}}'
        raise requests.HTTPError('private-super-secret', response=response)
    run_agent(state, tools, failed)
    assert state.data['status'] == 'paused'
    assert state.data['stop_reason'] == 'model_unavailable'
    assert state.data['usage']['model'] == 1
    assert state.data.get('invalid_actions', 0) == 0
    assert 'private-super-secret' not in (state.run_dir / 'run.json').read_text()
    assert (state.run_dir / 'builder_input.json').exists()
    run_agent(state, tools, lambda _: finish([sid]))
    assert state.data['status'] == 'finished'
    assert state.data['usage']['model'] == 2


def test_user_pause_and_hard_model_limit_still_prevent_calls(tmp_path):
    state, tools = fixture(tmp_path, calls=2)
    (state.root / 'pause_requested').touch()
    run_agent(state, tools, lambda _: pytest.fail('User paused'))
    assert state.data['stop_reason'] == 'user_pause'
    (state.root / 'pause_requested').unlink()
    state.data['usage']['model'] = 2
    run_agent(state, tools, lambda _: pytest.fail('Budget exhausted'))
    assert state.data['status'] == 'limit'
    assert state.data['usage']['model'] == 2


def test_optional_inspection_damage_does_not_hide_task_or_prevent_resume(tmp_path):
    state, _ = fixture(tmp_path)
    (state.run_dir / 'selection.json').write_text('{broken')
    write_json(state.run_dir / 'builder_input.json', {'samples': []})
    data = SearchController(tmp_path).inspect('event')
    assert data['selection'] is None
    assert data['builder_input'] == {'samples': []}
    assert data['can_resume']
    assert data['inspection_errors'][0]['file'] == 'selection.json'


def test_legacy_empty_outage_controller_resume_reopens_without_reset(tmp_path):
    state, tools = fixture(tmp_path)
    state.data.update(status='insufficient', stop_reason='insufficient', usage=dict(search=1, model=3))
    state.trace(dict(action='provider_result', status='failed', error_details={'category': 'rate_limit'}))
    state.save()
    controller = SearchController(tmp_path, model=lambda _: {'action': 'list_sources', 'offset': 0})
    assert controller.inspect('event')['can_resume']
    controller.start('event', steps=1)
    controller.threads['event'].join(timeout=5)
    restored = SearchState(tmp_path, 'event')
    assert restored.data['status'] == 'paused'
    assert restored.data['usage'] == dict(search=1, model=4)
    assert restored.data['resume_history'][-1]['reason'] == 'legacy_provider_interruption'
