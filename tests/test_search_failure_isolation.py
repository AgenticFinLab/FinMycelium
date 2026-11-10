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
