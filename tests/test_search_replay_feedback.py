"""Bound repeated payloads without losing verification, evidence or progressive reads."""
import json
from functools import partial
import socket

import pytest

from finmy.generic import DataSample, UserQueryInput
from finmy.search.agent import execute_action
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Replay checks must not call external services')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def agent_tools(state):
    tools = SearchTools(state)
    tools.read_source = partial(tools.read_source, agent_feedback=True)
    return tools


def setup(tmp_path, **config):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Education commitment',
                        query_text='Trace Ada public education commitment.'), config=SearchConfig(**config))
    tools = agent_tools(state)
    sid = tools.sources.register('https://example.org/interview', title='Public interview')
    text = 'Ada accepted the invitation.\n\nShe required local consent.\n\nLater she explained the commitment.'
    doc = tools.sources.save_raw(sid, text.encode(), 'txt')
    return state, tools, sid, doc


def mark(sid, doc, block=0):
    return dict(source_id=sid, block=block, start=0, end=len(doc['blocks'][block]['text']),
                reason='Keep the public statement and its condition')


@pytest.mark.parametrize('reader', ['topic', 'bm25'])
def test_interleaved_query_and_cursor_replays_stay_bounded_after_resume(tmp_path, reader):
    state, tools, sid, doc = setup(tmp_path, retrieval={'mode': reader})
    original = json.dumps(tools.sources.document(sid), sort_keys=True)
    first = tools.read_source(sid, query='invitation consent commitment')
    assert first['progress']['new_chars'] > 0
    verification = tools.read_source(sid, query='invitation consent commitment details')
    assert verification['spans'] == first['spans']
    assert verification['progress']['new_chars'] == 0
    other = tools.sources.register('https://example.org/other')
    tools.sources.save_raw(other, b'Another source reports a new public action.', 'txt')
    tools.read_source(other)
    # Reading elsewhere and restarting cannot make the same ranges new again.
    state = SearchState(tmp_path, 'case')
    tools = agent_tools(state)
    repeated = tools.read_source(sid, location={'block':1})
    assert repeated['spans'] == [] and repeated['reading']['replay_suppressed']
    assert repeated['progress']['new_chars'] == repeated['progress']['returned_chars'] == 0
    assert repeated['progress']['suppressed_chars'] > 0
    assert tools.read_source(sid, query='different words')['spans'] == []
    assert state.data['usage'] == {'search':0, 'model':0}
    assert json.dumps(tools.sources.document(sid), sort_keys=True) == original
    # Suppression affects tool feedback only; the inspected source and exact text survive handoff.
    execute_action(state, tools, dict(action='finish', source_ids=[sid], gaps=[], reason='supported'))
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']: DataSample(**sample)
    content = next(s['content'] for s in payload['samples'] if s['raw_data_id'] == sid)
    assert all(b['text'] in content for b in doc['blocks'])


def test_valid_new_source_marks_allow_verification_but_duplicates_do_not(tmp_path):
    state, tools, sid, doc = setup(tmp_path)
    tools.read_source(sid)
    tools.read_source(sid)
    assert tools.read_source(sid)['reading']['replay_suppressed']
    action = dict(action='read_source', source=sid, location={'block':0},
                  priority_passages=[mark(sid, doc)])
    result = execute_action(state, tools, action)
    assert result['spans'] and result['progress']['new_chars'] == 0
    assert len(state.data['priority_passages']) == 1
    changed_reason = dict(action, priority_passages=[dict(mark(sid, doc), reason='Another explanation')])
    result = execute_action(state, tools, changed_reason)
    assert result['reading']['replay_suppressed'] and len(state.data['priority_passages']) == 1
    other = tools.sources.register('https://example.org/other')
    other_doc = tools.sources.save_raw(other, b'Another documented decision.', 'txt')
    tools.read_source(other)
    result = execute_action(state, tools, dict(action, priority_passages=[mark(other, other_doc)]))
    assert result['reading']['replay_suppressed'] and len(state.data['priority_passages']) == 2
    invalid = dict(mark(sid, doc), end=100000)
    result = execute_action(state, tools, dict(action, priority_passages=[invalid]))
    assert result['reading']['replay_suppressed'] and state.data['priority_feedback']['rejected']
    # A genuinely new inspected range can be marked, accepted and reviewed.
    result = execute_action(state, tools, dict(action, priority_passages=[mark(sid, doc, 1)]))
    assert result['spans'] and len(state.data['priority_passages']) == 3


def test_progressive_ranges_and_new_source_versions_are_not_blocked(tmp_path):
    state, tools, sid, _ = setup(tmp_path, max_read_chars=12)
    first = tools.read_source(sid, location={'block':0})
    assert first['progress']['new_chars'] == 12
    assert tools.read_source(sid, location={'block':0})['spans']
    assert tools.read_source(sid, location={'block':0})['reading']['replay_suppressed']
    progressed = tools.read_source(sid, location={'block':0,'offset':6})
    assert progressed['progress']['new_chars'] == 6 and progressed['spans']
    # This range has not yet had a complete verification replay.
    assert tools.read_source(sid, location={'block':0,'offset':6})['spans']
    assert tools.read_source(sid, location={'block':0,'offset':6})['reading']['replay_suppressed']
    tools.sources.save_raw(sid, b'Ada revised her public commitment after consultation.', 'txt')
    fresh = tools.read_source(sid, location={'block':0})
    assert fresh['version'] != first['version'] and fresh['progress']['new_chars'] == 12
    assert tools.read_source(sid, location={'block':0})['spans']


def test_existing_run_without_guard_keeps_one_verification_and_recorded_coverage(tmp_path):
    state, tools, sid, _ = setup(tmp_path)
    tools.read_source(sid)
    state.data['sources'][sid].pop('replay_guard')
    state.save()
    resumed = SearchState(tmp_path, 'case')
    tools = agent_tools(resumed)
    verification = tools.read_source(sid)
    assert verification['spans'] and verification['progress']['new_chars'] == 0
    assert tools.read_source(sid)['reading']['replay_suppressed']
