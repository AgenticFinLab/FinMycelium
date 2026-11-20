"""Cross-source semantic review -> reference rewrite -> JSON/HTML -> resume."""
from copy import deepcopy
import json
import re

import pytest

from test_person_event_contract import payload, graph
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event import evidence_consolidation as ec
from finmy.person_epg.event.evidence_support import upgrade_package_evidence
from finmy.person_epg.event.graph_html import render_graph_html
from finmy.person_epg.event.graph_view import build_views
from finmy.person_epg.event.records import IdMap, seed_facts, fingerprint
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, InvalidResponse
from finmy.person_epg.event.validation import check_graph


@pytest.fixture
def case(payload, graph):
    graph = upgrade_package_evidence(graph)
    original = graph['evidence'][0]
    citation = original['citations'][0]
    sample = deepcopy(next(s for s in payload['samples'] if s['sample_id'] == citation['sample_id']))
    sample.update(sample_id='SECOND-DOCUMENT', raw_data_id='SECOND-SOURCE')
    payload['samples'].append(sample)
    registry = payload['user_query']['extras']['source_registry']
    registry['SECOND-SOURCE'] = dict(registry[citation['source_id']], title='Second account of the same fact')
    copy = deepcopy(original)
    copy['evidence_id'] = 'EVD-Z-DUPLICATE'
    original['statement'] = 'The office imposed a disclosure restriction on Mina Lee.'
    copy['statement'] = 'Mina Lee was subject to the disclosure restriction imposed by the office.'
    copy['citations'][0].update(sample_id=sample['sample_id'], source_id=sample['raw_data_id'])
    graph['evidence'].append(copy)
    graph['sources'] = seed_facts(payload)['sources']
    # The common context supports retrieval even if the statements share little wording.
    graph['contexts'][0]['support'][0]['evidence_ids'] = [original['evidence_id'], copy['evidence_id']]
    facts = seed_facts(payload)
    for field in ('entities', 'actions', 'contexts', 'evidence'):
        facts[field] = deepcopy(graph[field])
    for action in facts['actions']:
        action['phase_id'] = None
        action['support'] = [s for s in action['support'] if s['target'] != '/phase_id']
    return payload, graph, facts, tuple(sorted([original['evidence_id'], copy['evidence_id']]))


class ReviewModel:
    last_usage = {'total_tokens': 12}
    def __init__(self, equivalent):
        self.equivalent = tuple(equivalent)
        self.calls = []
    def __call__(self, system, user, name):
        assert name.startswith('evidence_merge.'), 'Must not repeat any upstream stage'
        request = json.loads(user)['task']
        assert request['role'] == ec.STAGE
        self.calls.append(name)
        return {'decisions': [dict(pair_id=p['pair_id'],
            verdict='same_fact' if tuple(p['evidence_ids']) == self.equivalent else 'different_fact',
            reason='Same factual claim in two supplied accounts.' if tuple(p['evidence_ids']) == self.equivalent
                   else 'The supplied claims describe distinct facts.') for p in request['pairs']]}


def builder_for(tmp_path, case, model):
    payload, graph, facts, pair = case
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2), model)
    builder = Construction(run)
    builder.graph, builder.facts = deepcopy(graph), deepcopy(facts)
    return builder


def refs(value):
    if isinstance(value, list):
        for item in value: yield from refs(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == 'evidence_ids': yield from item
            elif key != 'lineage': yield from refs(item)


def test_semantic_merge_rewrites_refs_preserves_sources_and_renders(case, tmp_path):
    payload, graph, facts, pair = case
    original = deepcopy(case)
    model = ReviewModel(pair)
    builder = builder_for(tmp_path, case, model)
    assert builder.stage(ec.STAGE, lambda: ec.consolidate(builder))
    assert model.calls
    report = json.loads((tmp_path / builder.run.state[ec.STAGE]['path']).read_text())
    assert report['merged_records'] == 1 and report['multi_source_after'] == 1
    survivor, removed = pair
    merged = next(e for e in builder.graph['evidence'] if e['evidence_id'] == survivor)
    assert len(ec.source_ids(merged)) == 2
    assert removed not in set(refs(builder.graph)) | set(refs(builder.facts))
    assert len(builder.graph['evidence']) == len(graph['evidence']) - 1
    assert builder.graph['sources'] == graph['sources']
    assert builder.facts['lineage'][-1]['operation'] == 'merge'
    for e in graph['evidence']:
        if e['evidence_id'] in pair:
            assert all(c in merged['citations'] for c in e['citations'])
    before = check_graph(graph, payload, complete=False)
    after = check_graph(builder.graph, payload, complete=False)
    assert after['summary']['errors'] <= before['summary']['errors']
    html = render_graph_html(builder.graph)
    embedded = json.loads(re.search(r'<script id="epg-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert embedded == builder.graph
    view = build_views(builder.graph)
    # Both sources are represented by the existing graph renderer without source flattening.
    assert 'SECOND-SOURCE' in json.dumps(view)
    assert case == original


def test_different_and_uncertain_claims_are_not_merged(case):
    _, graph, _, pair = case
    pairs, _ = ec.candidate_pairs(graph)
    assert any(tuple(p['evidence_ids']) == pair for p in pairs)
    decisions = [dict(pair_id=p['pair_id'], verdict='uncertain', reason='Unresolved') for p in pairs]
    assert ec.merge_plan(graph, pairs, decisions)[0] == {}


def test_transitive_merge_cannot_override_explicit_disagreement():
    graph = dict(evidence=[{'evidence_id': x} for x in 'ABC'])
    pairs = [dict(pair_id=x+y, evidence_ids=[x,y]) for x,y in [('A','B'),('A','C'),('B','C')]]
    decisions = [dict(pair_id=p['pair_id'], verdict='different_fact' if p['pair_id']=='AC' else 'same_fact')
                 for p in pairs]
    mapping, conflicts = ec.merge_plan(graph, pairs, decisions)
    assert mapping == {'B':'A'} and conflicts


def test_reject_unknown_duplicate_and_missing_decisions(case):
    request = ec.batches(case[1], EventBuildConfig())[0]
    decisions = ReviewModel(case[3])('', json.dumps({'task': request}), 'evidence_merge.0')
    ec.validate_decisions(decisions, request)
    for malformed in ({'decisions': []}, {'decisions': decisions['decisions']*2},
                      {'decisions':[dict(pair_id='invented', verdict='same_fact', reason='x')]}):
        with pytest.raises(ValueError): ec.validate_decisions(malformed, request)


def test_read_requests_cannot_start_continuation_loop(case, tmp_path):
    calls = []
    def bad_model(*args):
        calls.append(1)
        return {'read_requests':[{'tool':'read_sample','sample_id':'invented','start':0,'end':1}]}
    builder = builder_for(tmp_path, case, bad_model)
    assert not builder.stage(ec.STAGE, lambda: ec.consolidate(builder))
    assert len(calls) == builder.run.config.max_json_attempts
    assert builder.run.state['reads'] == []
    assert builder.graph == case[1]
    assert not (tmp_path / 'checkpoints/stage-evidence_consolidation.json').exists()


def test_corrupted_quote_is_rejected_without_mutating_inputs(case):
    payload, graph, facts, pair = case
    original = deepcopy(graph)
    bad = deepcopy(graph)
    next(e for e in bad['evidence'] if e['evidence_id'] == pair[1])['citations'][0]['quote'] = 'invented'
    with pytest.raises(ValueError, match='unverified'):
        ec.apply_mapping(bad, facts, {pair[1]:pair[0]}, payload)
    assert graph == original


def test_cli_postprocess_and_resume_make_no_upstream_calls(case, tmp_path, monkeypatch, capsys):
    builder = builder_for(tmp_path, case, ReviewModel(case[3]))
    builder.run.config.stall_timeout = 180
    builder.run.config.max_transport_retries = 1
    builder.run.state['config'].update(stall_timeout=180, max_transport_retries=1)
    builder.finish('finished')
    input_before = (tmp_path / 'input.json').read_bytes()
    model = ReviewModel(case[3])
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', lambda config: model)
    ec.main([str(tmp_path), '--plan'])
    assert not model.calls
    ec.main([str(tmp_path), '--allow-model'])
    first_calls = list(model.calls)
    state = json.loads((tmp_path / 'state.json').read_text())
    assert state[ec.STAGE]['multi_source_after'] == 1
    assert state['config']['stall_timeout'] == 60 and state['config']['timeout'] == 900
    assert state['config']['max_transport_retries'] == 2
    assert state['visualization']['status'] == 'completed'
    graph_first = json.loads((tmp_path / state['output']).read_text())
    ec.main([str(tmp_path), '--allow-model'])
    state2 = json.loads((tmp_path / 'state.json').read_text())
    assert model.calls == first_calls
    assert state2['stages'][ec.STAGE]['reused']
    assert json.loads((tmp_path / state2['output']).read_text()) == graph_first
    assert (tmp_path / 'input.json').read_bytes() == input_before


def test_partial_budget_resume_reuses_successful_pair_reviews(case, tmp_path, monkeypatch):
    builder = builder_for(tmp_path, case, ReviewModel(case[3]))
    builder.run.config.max_calls = 1
    builder.run.state['config']['max_calls'] = 1
    builder.finish('finished')
    original_batches = ec.batches
    def two_batches(graph, config):
        request = original_batches(graph, config)[0]
        equivalent = next(p for p in request['pairs'] if tuple(p['evidence_ids']) == case[3])
        other = next(p for p in request['pairs'] if p != equivalent)
        return [dict(request, pairs=[p]) for p in (equivalent, other)]
    monkeypatch.setattr(ec, 'batches', two_batches)
    first_model = ReviewModel(case[3])
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', lambda config: first_model)
    ec.main([str(tmp_path), '--allow-model', '--extra-calls', '1'])
    first = json.loads((tmp_path / 'state.json').read_text())
    assert first['execution_status'] == 'limit'
    assert first[ec.STAGE]['merged_records'] == 1
    assert first[ec.STAGE]['reviewed_pairs'] == 1
    assert first_model.calls == ['evidence_merge.0']
    resumed = ReviewModel(case[3])
    monkeypatch.setattr('finmy.person_epg.event.guarded_transport.GuardedModel', lambda config: resumed)
    ec.main([str(tmp_path), '--allow-model', '--extra-calls', '3'])
    state = json.loads((tmp_path / 'state.json').read_text())
    assert state['stages'][ec.STAGE]['status'] == 'completed'
    assert state[ec.STAGE]['reviewed_pairs'] == 2
    assert resumed.calls == ['evidence_merge.1']
    assert len(state['calls']) == 2


def test_final_check_references_project_to_survivor_but_adoption_history_remains(case, tmp_path):
    builder = builder_for(tmp_path, case, ReviewModel(case[3]))
    item = dict(refs=[dict(collection='evidence', object_id=case[3][1], field='')],
                evidence_ids=[case[3][1]], reason='An unresolved historical review item')
    builder.reports = [dict(task_id='organize', role='organization',
                           report=dict(accepted=[], rejected=[], pending=[item]))]
    builder.stage(ec.STAGE, lambda: ec.consolidate(builder))
    state = builder.finish('finished')
    checks = json.loads((tmp_path / state['checks']).read_text())
    projected = checks['unresolved_tasks'][0]['report']['pending'][0]
    assert projected['evidence_ids'] == [case[3][0]]
    assert projected['refs'][0]['object_id'] == case[3][0]
    history = json.loads((tmp_path / state['facts']).with_name('adoption.json').read_text())
    assert history[0]['report']['pending'][0]['evidence_ids'] == [case[3][1]]
