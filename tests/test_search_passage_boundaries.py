"""Complete new annotations using only already-read originals, without extra calls."""
from copy import deepcopy
import json
import socket

import pytest

from finmy.search.agent import run_agent
from finmy.search.evidence import record_passages, sentence_bounds
from finmy.search.handoff import derive_input, prepare_complete_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.tools import SearchTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('No network'))


def setup(tmp_path, text):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Cedar payment',
        query_text='Trace the Cedar payment.', key_words=['Cedar', 'payment']),
        config=SearchConfig(max_model_calls=1))
    store = SourceStore(state)
    sid = store.register('https://example.org/payment')
    doc = store.save_raw(sid, text.encode(), 'txt')
    store.read(sid)
    return state, store, sid, doc


@pytest.mark.parametrize('text,sentence,fragment', [
    ('Earlier event. Dr. Ada said, “The U.S. unit paid $5.50 after approval.” Next event.',
     'Dr. Ada said, “The U.S. unit paid $5.50 after approval.”', 'unit paid $5.50 after app'),
    ('前事已结。她说：“批准后支付5.50元。”另一件事。', '她说：“批准后支付5.50元。”', '批准后支付5.50'),
    ('Old heading\n\nCedar paid only after approval. Other business.',
     'Cedar paid only after approval.', 'paid only after app'),
])
def test_sentence_bounds_keep_attribution_qualifications_and_paragraphs(text, sentence, fragment):
    start = text.index(fragment)
    left, right = sentence_bounds(dict(text=text), start, start+len(fragment))
    assert text[left:right] == sentence
    assert sentence_bounds(dict(text=text), left, right) == (left, right)


@pytest.mark.parametrize('block', [
    dict(text='Cedar paid $5.50. Other column.', table=1, cells=[{}]),
    dict(text='| Issuer | Payment |\n| Cedar | Paid $5.50. |'),
    dict(text='An unfinished source tail without its final words'),
])
def test_tables_and_unfinished_source_tails_keep_original_bounds(block):
    assert sentence_bounds(block, 5, 12) == (5, 12)


@pytest.mark.parametrize('coverage,expand', [('complete', True), ('partial', False), ('gap', False), ('old', False)])
def test_alignment_requires_current_contiguous_read_coverage(tmp_path, coverage, expand):
    text = 'Earlier event. Cedar paid $5.50 after approval. Other business.'
    state, _, sid, doc = setup(tmp_path, text)
    left, right = text.index('Cedar'), text.index(' Other business.')
    start, end = text.index('paid'), text.index('approval')+3
    ranges = [dict(version=doc['version'], block=0, start=start, end=end)]
    extras = {'complete':[(left,start+2),(end-2,right)], 'partial':[],
              'gap':[(left,start-1),(end+1,right)], 'old':[(left,right)]}[coverage]
    ranges += [dict(version='old' if coverage=='old' else doc['version'], block=0, start=a, end=z)
               for a,z in extras]
    state.data['sources'][sid]['read_ranges'] = ranges
    mark = dict(source_id=sid, block=0, start=start, end=end, fact_ids=['payment'])
    original = deepcopy(mark)
    assert record_passages(state, [mark])['accepted'] == 1
    result = state.data['priority_passages'][0]
    assert (result['start'], result['end']) == ((left,right) if expand else (start,end))
    assert mark == original and state.data['sources'][sid]['read_ranges'] == ranges
    assert state.data['usage'] == {'search':0, 'model':0}


def test_finish_completes_only_the_selected_sentence_and_respects_budget(tmp_path):
    text = ('Cedar repaid the principal. The redemption will reduce reported earnings by $0.04. '
            'Annual dividends were $500 million. Unrelated issuer profile.')
    state, _, sid, doc = setup(tmp_path, text)
    start, end = text.index('The redemption'), text.index('reported')+3
    right = text.index(' Annual dividends')
    mark = dict(source_id=sid, block=0, start=start, end=end, fact_ids=['earnings_effect'])
    action = dict(action='finish', source_ids=[sid], gaps=[], reason='supported', priority_passages=[mark])
    original = deepcopy(action)
    run_agent(state, SearchTools(state), lambda _: action)
    assert action == original and state.data['actions'][0] == original
    assert state.data['usage'] == {'search':0, 'model':1}
    accepted = state.data['priority_passages'][0]
    assert (accepted['start'],accepted['end']) == (start,right)
    assert record_passages(state, [mark])['accepted'] == 1
    assert len(state.data['priority_passages']) == 1
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert text[start:right] in payload['samples'][0]['content']
    assert 'Annual dividends' not in payload['samples'][0]['content']
    complete = json.loads((state.run_dir/'complete_material.json').read_text())
    _, selection = derive_input(state, complete)
    limited, report = derive_input(state, complete, max_chars=selection['material_chars']-1)
    assert not limited['samples'] and report['material_chars'] <= selection['material_chars']-1
    assert accepted['version'] == doc['version']


def test_later_reads_and_corrected_marks_do_not_change_a_frozen_handoff(tmp_path):
    text = 'Cedar paid only after approval. Other business.'
    state, store, sid, doc = setup(tmp_path, text)
    end = text.index('approval')+3
    entry = state.data['sources'][sid]
    entry['read_ranges'] = [dict(version=doc['version'], block=0, start=0, end=end)]
    mark = dict(source_id=sid, block=0, start=0, end=end, fact_ids=['payment'])
    record_passages(state, [mark])
    _, frozen = prepare_complete_sources(state, [sid])
    before = derive_input(state, frozen)
    # Re-validation of saved coordinates must not grow them after another read.
    store.read(sid)
    _, still_saved = prepare_complete_sources(state, [sid])
    assert still_saved['priority_passages'][0]['end'] == end
    record_passages(state, [dict(mark,end=text.index(' Other business.'))])
    assert len(state.data['priority_passages']) == 2
    record_passages(state, [mark])
    assert len(state.data['priority_passages']) == 1
    assert state.data['priority_passages'][0]['end'] == text.index(' Other business.')
    assert derive_input(state, frozen) == before
