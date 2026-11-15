"""Agent finish accounts for inspected sources without manual case-specific admission."""
import json
import socket

import pytest

from finmy.search.agent import run_agent
from finmy.search.evidence import record_passages, source_pool
from finmy.search.handoff import derive_input
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))


def setup(tmp_path, kind='person'):
    state = SearchState(tmp_path, 'case', task=dict(target_type=kind, target_name='Education program',
                        query_text='Research the education program and its participants.'))
    return state, SourceStore(state)


def saved(store, name, text, *, read=True):
    sid = store.register('https://example.org/'+name, title=name)
    doc = store.save_raw(sid, text.encode(), 'txt')
    if read:
        store.read(sid)
    return sid, doc


@pytest.mark.parametrize('kind', ['person', 'event', 'company'])
def test_finish_recovers_omitted_inspected_body_but_respects_explicit_exclusion(tmp_path, kind):
    state, store = setup(tmp_path, kind)
    notice, _ = saved(store, 'notice', 'The education program was announced.')
    letter, _ = saved(store, 'letter', 'I reallocated resources across several programs, including this one. Local consent remained required.')
    unrelated, _ = saved(store, 'unrelated', 'Unrelated sports results.')
    unread, _ = saved(store, 'unread', 'A lead that nobody has inspected.', read=False)
    calls = []
    def model(context):
        calls.append(context)
        # The omission itself is intentional: programmatic retention must recover it.
        return dict(action='finish', source_ids=[notice], source_exclusions={unrelated:'Outside the confirmed research scope'},
                    gaps=[], reason='supported')
    run_agent(state, SearchTools(state), model)
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    complete = json.loads((state.run_dir/'complete_material.json').read_text())
    selection = json.loads((state.run_dir/'selection.json').read_text())
    assert {x['raw_data_id'] for x in payload['samples']} == {notice, letter}
    assert 'Local consent remained required.' in str(payload['samples'])
    review = complete['source_review']
    assert review['automatically_retained'] == [letter]
    assert review['exclusions'] == {unrelated:'Outside the confirmed research scope'}
    assert selection['source_review'] == review
    assert unread not in review['inspected_versions']
    assert len(calls) == 1 and state.data['usage'] == {'model':1,'search':0}
    # Later state changes cannot alter a frozen source choice during reassembly.
    saved(store, 'later', 'A later source unrelated to the saved selection.')
    assert derive_input(state, complete)[0] == payload


def test_missing_marked_source_is_retained_but_explicit_rejection_is_recorded(tmp_path):
    state, store = setup(tmp_path)
    sid, doc = saved(store, 'letter', 'I accepted the invitation only after obtaining consent.')
    record_passages(state, [dict(source_id=sid, block=0, start=0, end=len(doc['blocks'][0]['text']))])
    retained, review = source_pool(state, [])
    assert retained == [sid] and review['automatically_retained'] == [sid]
    retained, review = source_pool(state, [], {sid:'The namesake is a different person'})
    assert retained == [] and review['exclusions'][sid]


def test_unread_new_version_and_failed_acquisition_are_not_promoted(tmp_path):
    state, store = setup(tmp_path)
    sid, old = saved(store, 'revised', 'An older inspected statement.')
    store.save_raw(sid, b'A different uninspected statement.', 'txt')
    failed = store.register('https://example.org/failed')
    state.data['sources'][failed]['status'] = 'fetch_failed'
    assert source_pool(state, [])[0] == []
    with pytest.raises(ValueError, match='Inspect'):
        source_pool(state, [sid])
    retained, review = source_pool(state, [], {sid:'Not relevant', failed:'Unavailable'})
    assert retained == [] and review['exclusions'] == {}
    assert set(review['uninspected_exclusions']) == {sid, failed}
    assert all(not note['evidence_reviewed'] for note in review['uninspected_exclusions'].values())


def test_invalid_or_conflicting_decisions_do_not_silently_change_retention(tmp_path):
    state, store = setup(tmp_path)
    sid, _ = saved(store, 'letter', 'The scope and its qualification.')
    for exclusions in ([], {sid:''}, {sid:7}, {sid:'x'*301}):
        with pytest.raises(ValueError, match='source_exclusions'):
            source_pool(state, [], exclusions)
    with pytest.raises(ValueError, match='both'):
        source_pool(state, [sid], {sid:'Outside scope'})
    with pytest.raises(ValueError, match='Unknown source'):
        source_pool(state, [], {'invented':'Outside scope'})


def test_duplicate_bodies_still_collapse_after_automatic_retention(tmp_path):
    state, store = setup(tmp_path)
    first, _ = saved(store, 'first', 'The same official statement and its qualifications.')
    second, _ = saved(store, 'copy', 'The same official statement and its qualifications.')
    run_agent(state, SearchTools(state), lambda c: dict(action='finish', source_ids=[first], gaps=[], reason='supported'))
    complete = json.loads((state.run_dir/'complete_material.json').read_text())
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert complete['source_review']['automatically_retained'] == [second]
    assert len(payload['samples']) == 1 and complete['duplicates'][0]['duplicate_of'] == first


def test_unread_exclusion_does_not_block_finish_or_claim_inspection(tmp_path):
    state, store = setup(tmp_path)
    read, _ = saved(store, 'statement', 'I accepted after community consent.')
    unread, _ = saved(store, 'candidate', 'Unread material.', read=False)
    calls = []
    def model(context):
        calls.append(context)
        return dict(action='finish', source_ids=[read], source_exclusions={unread:'Already inspected; unrelated'},
                    gaps=[], reason='supported')
    run_agent(state, SearchTools(state), model)
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    selection = json.loads((state.run_dir/'selection.json').read_text())
    assert len(calls) == 1 and state.data['status'] == 'finished'
    assert [s['raw_data_id'] for s in payload['samples']] == [read]
    review = selection['source_review']
    assert unread not in review['inspected_versions'] and unread not in review['exclusions']
    assert review['uninspected_exclusions'][unread]['status'] == 'uninspected'
    assert review['uninspected_exclusions'][unread]['evidence_reviewed'] is False
