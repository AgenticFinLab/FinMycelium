"""Invalid merge components cannot block independent valid components."""
from copy import deepcopy
import json

import pytest
from test_person_event_contract import payload, graph
from test_person_event_evidence_consolidation import case, ReviewModel, builder_for
from finmy.person_epg.event import evidence_consolidation as ec


def test_bad_component_is_retained_while_good_component_merges(case):
    payload, graph, facts, pair = case
    for package in (graph, facts):
        bad = deepcopy(package['evidence'][0])
        bad['evidence_id'] = 'EVD-BAD-A'
        bad['citations'][0]['quote'] = 'not the source text'
        other = deepcopy(bad)
        other['evidence_id'] = 'EVD-BAD-B'
        package['evidence'].extend([bad, other])
    original = deepcopy((graph, facts))
    result, result_facts, mapping, skipped = ec.apply_groups(graph, facts,
        {pair[1]: pair[0], 'EVD-BAD-B': 'EVD-BAD-A'}, payload)
    assert mapping == {pair[1]: pair[0]}
    assert len(skipped) == 1 and 'unverified' in skipped[0]['reason']
    assert skipped[0]['evidence_ids'] == ['EVD-BAD-A', 'EVD-BAD-B']
    for before, after in ((graph, result), (facts, result_facts)):
        assert [e for e in before['evidence'] if e['evidence_id'].startswith('EVD-BAD')] == [
            e for e in after['evidence'] if e['evidence_id'].startswith('EVD-BAD')]
    assert (graph, facts) == original


def test_offline_resume_after_failed_merge_uses_saved_decisions_only(case, tmp_path, monkeypatch):
    builder = builder_for(tmp_path, case, ReviewModel(case[3]))
    builder.finish('finished')
    model = ReviewModel(case[3])
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', lambda config: model)
    with monkeypatch.context() as failure:
        def fail(*args):
            raise ValueError('Original merge failed')
        failure.setattr(ec, 'apply_groups', fail)
        ec.main([str(tmp_path), '--allow-model'])
    state = json.loads((tmp_path / 'state.json').read_text())
    assert state['execution_status'] == 'failed'
    assert 'Original merge failed' in state['reason']
    calls = deepcopy(state['calls'])
    def forbidden(*args):
        pytest.fail('Offline replay must not construct a model')
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', forbidden)
    ec.main([str(tmp_path), '--saved-review-only'])
    after = json.loads((tmp_path / 'state.json').read_text())
    assert after['calls'] == calls
    assert after[ec.STAGE]['merged_records'] == 1
    assert after['visualization']['status'] == 'completed'


def test_missing_offline_checkpoint_fails_before_writing_state(case, tmp_path):
    builder = builder_for(tmp_path, case, ReviewModel(case[3]))
    builder.finish('finished')
    before = (tmp_path / 'state.json').read_bytes()
    with pytest.raises(ValueError, match='Missing matching saved review'):
        ec.main([str(tmp_path), '--saved-review-only'])
    assert (tmp_path / 'state.json').read_bytes() == before
