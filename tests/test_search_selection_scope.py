"""Selection remainders retain kept referents without adding reads or evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from finmy.search.agent import context_for, execute_action
from finmy.search.evidence import record_passages
from finmy.search.inspection import (accept_presentation, pending_passages,
                                     pending_preview, selected_prefix)
from finmy.search.review import record_checks
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools
from test_search_candidate_review import setup, finish, offline
from test_search_evidence_routing import check
from test_search_inspection import unselected, selected_text
from test_search_integrated_review import mark


def split_commitment(tmp_path, prefix=None, tail=None):
    state, tools = setup(tmp_path)
    prefix = prefix or 'Ada Vale committed funds to Orion and Cedar education programs.'
    tail = tail or (' To fund these commitments, I sold other assets.'
                    ' I kept a cash reserve to meet the remaining commitments.')
    sid, doc = unselected(tools, 'letter', prefix + tail)
    accept_presentation(state, context_for(state))
    record_checks(state, [check('What commitment was announced?', sid, mark(sid, 0, prefix))], mark_support=True)
    state.save()
    return state, tools, sid, doc, prefix, tail


def test_kept_referent_survives_resume_without_reopening_reading(tmp_path):
    state, tools, sid, doc, prefix, tail = split_commitment(tmp_path)
    restored = SearchState(tmp_path, 'case')
    before = deepcopy(restored.data)
    context = context_for(restored)
    row, = context['pending_evidence']
    assert row['text'] == tail
    assert row['selected_context_before'] == dict(block=0, start=0, end=len(prefix), text=prefix)
    assert restored.data == before  # Presentation context is read-only.
    assert row['version'] == doc['version']
    assert not context.get('cached_evidence')

    # The ordinary selection action can save the process facts without a reread;
    # the kept prefix itself does not create another pending decision or mark.
    accept_presentation(restored, context)
    assert restored.data['sources'][sid]['read_ranges'] == before['sources'][sid]['read_ranges']
    assert len(restored.data['priority_passages']) == 1
    location = {k: row[k] for k in ('source_id', 'version', 'block', 'start', 'end')}
    execute_action(restored, SearchTools(restored), finish([sid], fact_checks=[
        check('How were these commitments funded and constrained?', sid, location,
              detail='The shared commitments were funded by asset sales with a retained cash reserve.')]))
    assert not pending_passages(restored)
    assert prefix + tail in selected_text(restored)
    assert restored.data['usage'] == before['usage']
    assert tools.sources.document(sid) == doc


@pytest.mark.parametrize('change', ['source_id', 'version', 'block', 'gap', 'unselected'])
def test_prefix_never_bridges_unselected_text_or_other_originals(change):
    prefix = 'A target commitment was announced.'
    gap = ' An unselected claim intervened.' if change == 'gap' else ''
    text = prefix + gap + ' Its funding came from asset sales.'
    ref = dict(source_id='s', version='v', block=0, start=len(prefix + gap), end=len(text))
    saved = dict(source_id='s', version='v', block=0, start=0, end=len(prefix))
    if change in ('source_id', 'version'):
        saved[change] = 'another'
    if change == 'block':
        saved['block'] = 1
    state = SimpleNamespace(data=dict(priority_passages=[] if change == 'unselected' else [saved]))
    assert selected_prefix(state, ref, text) is None


@pytest.mark.parametrize('limit', [250, 500, 1000, 3200])
def test_prefix_shares_serialized_budget_and_never_displaces_pending_tail(tmp_path, limit):
    prefix = 'Ada Vale committed funds to Orion with a clearly documented purpose. ' * 8
    tail = ' To fund these commitments, I sold other assets.'
    state, tools, sid, doc, _, _ = split_commitment(tmp_path, prefix, tail)
    pending = pending_passages(state)
    before = deepcopy(state.data)
    rows = pending_preview(state, pending, limit)
    assert len(json.dumps(rows, ensure_ascii=False)) <= limit
    assert state.data == before
    without_prefix = deepcopy(state)
    without_prefix.data['priority_passages'] = []
    plain = pending_preview(without_prefix, pending, limit)
    assert [r['text'] for r in rows] == [r['text'] for r in plain]
    for row in rows:
        assert doc['blocks'][0]['text'][row['start']:row['end']] == row['text']
        if 'selected_context_before' in row:
            context = row['selected_context_before']
            assert context['text'] == prefix
            assert len(context['text']) <= 800
            assert len(json.dumps(context, ensure_ascii=False)) <= limit // 4
    if limit == 3200:
        assert rows[0]['selected_context_before']['text'] == prefix


def test_overlapping_kept_marks_form_one_exact_prefix_without_cutting_text():
    prefix = 'A target commitment was announced. It included a second project.'
    text = prefix + ' These commitments required asset sales.'
    ref = dict(source_id='s', version='v', block=0, start=len(prefix), end=len(text))
    shared = dict(source_id='s', version='v', block=0)
    state = SimpleNamespace(data=dict(priority_passages=[dict(shared, start=0, end=35),
        dict(shared, start=20, end=len(prefix)), dict(shared, start=0, end=len(prefix))]))
    assert selected_prefix(state, ref, text)['text'] == prefix
    long_prefix = 'Complete source sentence. ' * 40
    state.data['priority_passages'] = [dict(shared, start=0, end=len(long_prefix))]
    ref.update(start=len(long_prefix), end=len(long_prefix) + 5)
    assert selected_prefix(state, ref, long_prefix + ' Tail') is None
