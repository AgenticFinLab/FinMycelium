"""Delivery merges keep original citations even when verification fails."""
from copy import deepcopy
import json

import pytest
from test_person_event_contract import payload, graph
from test_person_event_evidence_consolidation import case, ReviewModel, builder_for
from finmy.person_epg.event import evidence_consolidation as ec


def test_unverified_and_verified_components_both_merge(case):
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
    assert mapping == {pair[1]: pair[0], 'EVD-BAD-B': 'EVD-BAD-A'}
    assert skipped == []
    for after in (result, result_facts):
        records = [e for e in after['evidence'] if e['evidence_id'].startswith('EVD-BAD')]
        assert len(records) == 1
        assert records[0]['citations'][0]['quote'] == 'not the source text'
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


def test_offline_delivery_and_rerender_keep_invalid_citation(case, tmp_path, monkeypatch):
    from finmy.person_epg.event.deliver_evidence import main as deliver
    from finmy.person_epg.rendering import render_saved_event
    payload, graph, facts, pair = case
    for package in (graph, facts):
        next(e for e in package['evidence'] if e['evidence_id'] == pair[1])['citations'][0]['quote'] = 'unverified original'
    run_dir = tmp_path / 'run'
    builder = builder_for(run_dir, case, ReviewModel(pair))
    builder.finish('finished')
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', lambda config: ReviewModel(pair))
    ec.main([str(run_dir), '--allow-model'])
    state = json.loads((run_dir / 'state.json').read_text())
    assert state[ec.STAGE]['merged_records'] == 1
    attempt = (run_dir / state['evidence_postprocess']['input']).parent
    state_before = (run_dir / 'state.json').read_bytes()
    output = tmp_path / 'delivery'
    def forbidden(*args):
        pytest.fail('Offline delivery must not construct a model')
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', forbidden)
    deliver([str(attempt), '--output', str(output)])
    assert (run_dir / 'state.json').read_bytes() == state_before
    exported = json.loads((output / 'epg.json').read_text())
    assert any(c['quote'] == 'unverified original' for e in exported['evidence'] for c in e['citations'])
    assert (output / 'graph.html').is_file()
    rerendered = render_saved_event(run_dir)
    assert rerendered['visualization']['status'] == 'completed'
    assert rerendered['render_checks']['summary']['errors'] > 0
    assert rerendered['calls'] == state['calls']
