"""Compatible details survive merging; changed review policies are not replayed."""
from copy import deepcopy
import json

from test_person_event_contract import payload, graph
from test_person_event_evidence_consolidation import case, ReviewModel, builder_for
from finmy.person_epg.event import evidence_consolidation as ec
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.runtime import Execution


def test_all_original_detail_statements_survive_with_both_source_quotes(case):
    payload, graph, facts, pair = case
    before = deepcopy(case)
    merged, merged_facts = ec.apply_mapping(graph, facts, {pair[1]:pair[0]}, payload)
    e = next(e for e in merged['evidence'] if e['evidence_id'] == pair[0])
    originals = [e for e in graph['evidence'] if e['evidence_id'] in pair]
    assert set(e['statement'].splitlines()) == {e['statement'] for e in originals}
    assert len(ec.source_ids(e)) == 2
    assert next(x for x in merged_facts['evidence'] if x['evidence_id'] == pair[0]) == e
    assert case == before


def test_old_all_different_policy_is_reviewed_again_then_new_policy_is_cached(case, tmp_path, monkeypatch):
    old = ReviewModel(())
    builder = builder_for(tmp_path, case, old)
    with monkeypatch.context() as prior:
        prior.setattr(ec, 'REVIEW_POLICY', 'strict-complete-claim-v1')
        prior.setattr(ec, 'SYSTEM', 'Old strict complete-claim review')
        builder.stage(ec.STAGE, lambda: ec.consolidate(builder))
    assert builder.run.state[ec.STAGE]['merged_records'] == 0
    model = ReviewModel(case[3])
    run = Execution(tmp_path, case[0], builder.run.config, model, resume=True)
    current = Construction(run)
    current.graph, current.facts = deepcopy(case[1]), deepcopy(case[2])
    current.stage(ec.STAGE, lambda: ec.consolidate(current))
    assert model.calls and run.state[ec.STAGE]['merged_records'] == 1
    report = json.loads((tmp_path / run.state[ec.STAGE]['path']).read_text())
    assert report['review_policy'] == ec.REVIEW_POLICY
    count = len(model.calls)
    current.graph, current.facts = deepcopy(case[1]), deepcopy(case[2])
    current.stage(ec.STAGE, lambda: ec.consolidate(current))
    assert run.state['stages'][ec.STAGE]['reused'] and len(model.calls) == count
