"""Person-process search, readable evidence and unchanged handoff; no API calls."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.dataset import DatasetCatalog, search_task
from finmy.generic import DataSample, UserQueryInput
from finmy.search.agent import context_for, run_agent
from finmy.search.handoff import prepare_complete_sources, derive_input
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools
from dataset_fixture import fixture_dataset


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('No network or real model calls in person-process checks')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)


def task():
    return dict(target_type='event', target_name='Cedar education grant',
                query_text='Research the Cedar education grant; exclude other activities.',
                catalog=dict(kind='person_event', person_name='Ada Example',
                             event_name='Cedar education grant', storyline_name='Philanthropy'),
                research_scope=dict(include='The grant and its implementation', exclude='Other activities'))


def source(state, name, text, *, partial=False):
    store = SourceStore(state)
    sid = store.register('https://example.org/' + name, title=name)
    doc = store.save_raw(sid, text.encode(), 'txt', partial=partial)
    return sid, doc


@pytest.mark.parametrize('storyline,event,scope', [
    ('Philanthropy', 'Education grant', 'The commitment and its implementation'),
    ('Family', 'Marriage', 'Publicly documented decisions and responses'),
    ('Education', 'University studies', 'Enrollment and study choices'),
])
def test_catalog_automatically_carries_person_goal_without_changing_scope(tmp_path, storyline, event, scope):
    catalog = DatasetCatalog(fixture_dataset(tmp_path / 'dataset'))
    selection = catalog.select('PERSON-EVENT-TEST', 'PERSON-TEST')
    selection.update(storyline_name=storyline, event_name=event)
    before = deepcopy(selection)
    prepared = search_task(selection, period='1995', include=scope, exclude='Unrelated private life')
    assert 'event process' in prepared['query_text'] and 'evidenced actions' in prepared['query_text']
    assert event in prepared['query_text'] and storyline in prepared['query_text']
    assert prepared['research_scope'] == dict(period='1995', include=scope, exclude='Unrelated private life')
    assert prepared['catalog'] == before and selection == before
    assert prepared['seed_urls'] == before['seed_urls'] and prepared['target_type'] == 'event'
    ordinary = catalog.select('EVENT-TEST')
    assert 'focal person' not in search_task(ordinary, period='', include='Closing', exclude='')['query_text']


def test_short_query_read_keeps_qualifications_even_without_lexical_match(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_read_chars=1000))
    text = 'She agreed to fund the schools.\n\nThe promise depended on local consent.\n\nNo precise day was reported.'
    sid, doc = source(state, 'interview', text, partial=True)
    original = {p.name:p.read_bytes() for p in (state.root/'sources'/sid/doc['version']).iterdir()}
    tools = SearchTools(state)
    result = tools.read_source(sid, query='authorization')
    assert result['reading']['mode'] == 'full_saved_text' and result['status'] == 'partial'
    assert '\n\n'.join(s['text'] for s in result['spans']) == text
    assert result['at_end_of_saved_text']
    assert all(doc['blocks'][s['block']]['text'][s['start']:s['end']] == s['text'] for s in result['spans'])
    again = tools.read_source(sid, query='authorization')
    assert again['spans'] and again['reading']['match_status'] == 'already_read'
    assert again['reading']['replayed']
    assert again['spans'] == result['spans']
    assert tools.read_source(sid, location={'block':0})['spans']
    assert original == {p.name:p.read_bytes() for p in (state.root/'sources'/sid/doc['version']).iterdir()}
    assert state.data['read_sources'] == [sid] and state.data['usage'] == {'model':0, 'search':0}


def test_long_document_can_answer_a_different_question_after_matches_are_read(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_read_chars=650))
    text = ('Opening.\n\nGrant delivery was scheduled.\n\n' + 'Routine accounting. ' * 200
            + '\n\nShe negotiated local consent before committing funds.\n\nThe day is unknown.\n\n'
            + 'Routine inventory. ' * 200)
    sid, _ = source(state, 'report', text)
    tools = SearchTools(state)
    tools.read_source(sid, query='grant delivery scheduled')
    repeated = tools.read_source(sid, query='grant delivery scheduled')
    assert repeated['reading']['match_status'] == 'already_read'
    assert not repeated['at_end_of_saved_text']
    followup = tools.read_source(sid, query='negotiated local consent committing')
    assert 'She negotiated local consent' in '\n'.join(s['text'] for s in followup['spans'])
    assert sum(len(s['text']) for s in followup['spans']) <= 650
    assert context_for(state)['sources'][0]['unread_saved_chars'] > 0


def test_question_history_survives_recent_window_and_forced_finalization(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_model_calls=12))
    sid, _ = source(state, 'interview', 'She made a conditional commitment.')
    SourceStore(state).read(sid)
    state.data['actions'] = [dict(action='search', query='Cedar grant Ada contact', gap='Who contacted whom?'),
                             dict(action='read_source', source='https://example.org/interview#details', query='initial contact')]
    state.data['actions'] += [dict(action='read_source', source=sid, location={'block':0}) for _ in range(7)]
    state.data['usage']['model'] = 10
    c = context_for(state)
    assert c['prior_actions'] == [] and c['phase'] == 'finalize'
    assert c['finalization_reason'] == 'model_call_budget'
    assert c['search_attempts'][0]['gap'] == 'Who contacted whom?'
    assert c['sources'][0]['reading_questions_attempted'] == ['initial contact']
    assert c['sources'][0]['unread_saved_chars'] == 0
    state.data['usage']['model'] = 0
    assert context_for(state, finalize=True)['finalization_reason'] == 'context_limit'
    assert context_for(state)['finalization_reason'] is None


def test_handoff_queries_use_only_successful_reads_of_retained_versions(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_read_chars=200))
    kept, old = source(state, 'kept', 'She discussed the proposal.')
    omitted, _ = source(state, 'omitted', 'Other private activities.')
    tools = SearchTools(state)
    tools.read_source(kept, query='old question')
    tools.read_source(omitted, query='unrelated discarded material')
    current = SourceStore(state).save_raw(kept, ('She authorized the pledge.\n\n' + 'Routine accounts. ' * 200).encode(), 'txt')
    tools.read_source(kept, query='authorized pledge')
    tools.read_source(kept, query='absent-word-xyz')
    state.trace(dict(action='provider_started', provider='bocha', query='Cedar grant implementation'))
    _, complete = prepare_complete_sources(state, [kept])
    queries = complete['retrieval_queries']
    assert 'authorized pledge' in queries
    assert all(q not in queries for q in ('old question', 'unrelated discarded material', 'absent-word-xyz'))
    assert 'Ada Example. Cedar education grant. The grant and its implementation' in queries
    assert complete['reading_queries'] == [dict(source_id=kept, version=current['version'], query='authorized pledge')]
    assert complete['user_query']['query_text'] == task()['query_text']
    frozen = deepcopy(complete)
    first = derive_input(state, complete, max_chars=1000)
    tools.read_source(omitted, query='another later question')
    assert derive_input(state, complete, max_chars=1000) == first and complete == frozen
    assert old['version'] != current['version']


def test_actual_read_question_recovers_action_and_keeps_event_fact_and_provenance(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_read_chars=600))
    paragraphs = ['Cedar education grant was announced.', 'The grant would fund school buildings.']
    paragraphs += ['Routine accounting inventory. ' * 120 + str(i) for i in range(3)]
    action = 'She requested local consultation before authorizing disbursement.'
    paragraphs += ['An interview explained the sequence.', action, 'The exact day remains unknown.']
    paragraphs += ['Unrelated operations. ' * 150 + str(i) for i in range(3)]
    sid, doc = source(state, 'long-report', '\n\n'.join(paragraphs))
    notice, _ = source(state, 'notice', 'Local consent remained required.')
    store = SourceStore(state)
    store.read(sid); store.read(notice)
    _, old = prepare_complete_sources(state, [sid, notice])
    old_payload, _ = derive_input(state, old, max_chars=2400)
    SearchTools(state).read_source(sid, query='requested local consultation authorizing disbursement')
    full, complete = prepare_complete_sources(state, [sid, notice])
    payload, selected = derive_input(state, complete, max_chars=2400)
    content = '\n'.join(s['content'] for s in payload['samples'])
    assert action in content and action not in '\n'.join(s['content'] for s in old_payload['samples'])
    assert paragraphs[0] in content and 'Local consent remained required.' in content
    assert selected['material_chars'] == sum(len(s['content']) for s in payload['samples']) <= 2400
    assert complete['material_chars'] > 2400 and action in full['samples'][0]['content']
    assert derive_input(state, complete, max_chars=2400) == (payload, selected)
    for entry in selected['selected']:
        original = store.document(entry['source_id'], entry['version'])
        sample = next(s for s in payload['samples'] if s['raw_data_id'] == entry['source_id'])
        assert all(original['blocks'][i]['text'] in sample['content'] for i in entry['blocks'])
    UserQueryInput(**payload['user_query'])
    for sample in payload['samples']:
        DataSample(**sample)
    assert not (state.run_dir/'builder_input.json').exists()  # Offline preparation is read-only.


def test_final_call_retains_useful_context_with_unattempted_gap_and_no_extra_calls(tmp_path):
    state = SearchState(tmp_path, 'case', task=task(), config=SearchConfig(max_model_calls=1))
    sid, _ = source(state, 'notice', 'The foundation announced a grant; her private discussions were not disclosed.')
    SourceStore(state).read(sid)
    def decide(c):
        assert c['phase'] == 'finalize' and c['allowed_actions'] == ['finish']
        assert c['finalization_reason'] == 'model_call_budget'
        return dict(action='finish', source_ids=[sid], reason='supported',
                    gaps=['Not attempted: who initiated the personal discussion.'],
                    reason_detail='Model-call limit reached; grant announcement is supported, personal discussions remain unknown.')
    run_agent(state, SearchTools(state), decide)
    assert state.data['usage'] == {'model':1, 'search':0} and state.data['status'] == 'finished'
    assert 'limit' in state.data['stop_detail']
    complete = json.loads((state.run_dir/'complete_material.json').read_text())
    assert 'Not attempted' in complete['gaps'][0]
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert 'foundation announced' in payload['samples'][0]['content']


def test_empty_saved_body_is_not_reviewed_or_adopted(tmp_path):
    state = SearchState(tmp_path, 'case', task=task())
    sid, _ = source(state, 'empty', '')
    result = SearchTools(state).read_source(sid, query='personal decision')
    assert not result['spans'] and result['reading']['match_status'] == 'no_match'
    assert not context_for(state)['sources'][0]['reviewed']
    with pytest.raises(ValueError, match='Inspect this source'):
        prepare_complete_sources(state, [sid])
