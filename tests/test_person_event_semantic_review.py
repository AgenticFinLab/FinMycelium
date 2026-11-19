from copy import deepcopy
import json

import pytest

from finmy.person_epg.event.closure import load_review
from finmy.person_epg.event.relation_experiment import run_relations
from finmy.person_epg.event.semantic_review import apply_review, review_relations
from finmy.person_epg.rendering import read_gantt
from finmy.search.state import digest
from finmy.workbench.graph_collection import reviewed_artifacts
from test_person_event_contract import graph, payload
from test_person_event_pipeline import SyntheticEventModel
from test_person_event_relation_experiment import baseline, files


def pair(graph, source=None, target=None):
    ids = [a['action_id'] for a in graph['actions']]
    return dict(from_action_id=source or ids[0], to_action_id=target or ids[-1],
                type='continues', basis='inferred', reason='The cited passage describes the later resumption.',
                evidence_ids=[graph['evidence'][0]['evidence_id']])


def decisions(graph):
    return dict(existing=[dict(relation_id=r['relation_id'], decision='keep',
        evidence_ids=[graph['evidence'][0]['evidence_id']], reason='The cited passage supports the named endpoints.')
        for r in graph['relations']], additions=[], context_findings=[])


def test_scoped_changes_leave_original_and_unrelated_records_intact(payload, graph):
    original = deepcopy(graph)
    first, other = graph['relations'][0], graph['relations'][1]
    answer = decisions(graph)
    answer['existing'][0].update(decision='revise',
        replacement=pair(graph, first['to_action_id'], first['from_action_id']))
    answer['existing'][1]['evidence_ids'] = ['unlocated']
    edited, audit = apply_review(graph, payload, answer)
    assert graph == original and all(edited[k] == graph[k] for k in graph if k != 'relations')
    assert next(r for r in edited['relations'] if r['relation_id'] == other['relation_id']) == other
    replacement = next(r for r in edited['relations'] if r['relation_id'] == first['relation_id'])
    assert replacement['from_action_id'] == first['to_action_id']
    assert not audit['complete'] and audit['missing_relation_ids'] == [other['relation_id']]


def test_duplicate_verdicts_do_not_remove_real_edges(payload, graph):
    answer = decisions(graph)
    duplicate = dict(answer['existing'][0], decision='withdraw')
    answer['existing'].append(duplicate)
    edited, audit = apply_review(graph, payload, answer)
    assert edited == graph and not audit['complete']
    assert sum(x['status'] == 'rejected' for x in audit['decisions']) == 2


def test_cross_phase_addition_and_related_context_withdrawal_are_audited(payload, graph):
    answer = decisions(graph)
    added = pair(graph, 'ACTION-3', 'ACTION-1')
    answer['additions'] = [added]
    answer['context_findings'] = [dict(owner_id='ACTION-1', context_ref_id='CREF-3', decision='withdraw',
        evidence_ids=added['evidence_ids'], reason='The cited disclosure describes a later public statement.')]
    edited, audit = apply_review(graph, payload, answer)
    assert audit['complete'] and len(edited['relations']) == len(graph['relations']) + 1
    assert edited['actions'][0]['delta_context_refs'] == [] and graph['actions'][0]['delta_context_refs']
    assert edited['contexts'] == graph['contexts'] and edited['phases'] == graph['phases']


def test_blind_discovery_and_named_comparison_share_original_without_rebuilding(tmp_path, baseline):
    _, snapshot = baseline
    parent = tmp_path / 'joint'
    state = run_relations(snapshot, parent, model=SyntheticEventModel())
    graph = json.loads((parent/state['output']).read_text())
    before = files(parent)
    called = []

    def model(system, user, task):
        request = json.loads(user)['task']
        called.append(task)
        if task == 'review.discover':
            assert 'existing_edges' not in request and 'relation_candidates' not in request
            assert graph['relations'][0]['relation_id'] not in user
            assert request['evidence'][0]['statement']
            assert request['evidence'][0]['citations'][0]['quote']
            return {'pairs': []}
        assert request['independent'] == [] and request['existing_edges'][0]['from_name'] in {
            a['name'] for a in graph['actions']}
        return decisions(graph)

    output = tmp_path / 'review'
    reviewed = review_relations(parent, output, model=model)
    assert called == ['review.discover', 'review.compare']
    assert reviewed['result_status'] == 'draft' and all(c['reasoning_effort']=='high' for c in reviewed['calls'])
    assert json.loads((output/reviewed['output']).read_text()) == graph
    active = load_review(output)
    assert active['semantic_review']['parent']['parent_graph_sha256'] == state['graph_sha256']
    assert active['state']['facts_sha256'] == state['facts_sha256']
    assert active['state']['coverage'] == state['coverage']
    assert active['discovery'] == load_review(parent)['discovery']
    assert 'Draft' in read_gantt(output, reviewed)
    catalog = active['payload']['user_query']['extras']['person_event']
    row = dict(id=reviewed['run_id'], event_id=catalog['event_id'], status='completed',
               body=dict(kind='person_event', artifact_directory=str(output), catalog=catalog,
                         input_hash=digest(active['payload'])))
    assert reviewed_artifacts(row)['binding']['graph_sha256'] == reviewed['graph_sha256']
    resumed = review_relations(parent, output, model=model, resume=True)
    assert len(called) == 2 and resumed['calls'] == reviewed['calls'] and files(parent) == before
    with pytest.raises(ValueError, match='separate'):
        review_relations(parent, parent/'revision', model=model)
    (output / resumed['review']).write_text('{}')
    with pytest.raises(ValueError, match='独立关系复核'):
        load_review(output)


def test_failed_independent_call_retains_original_and_reports_partial(tmp_path, baseline):
    _, snapshot = baseline
    parent = tmp_path / 'joint'
    state = run_relations(snapshot, parent, model=SyntheticEventModel())
    output = tmp_path / 'review'
    reviewed = review_relations(parent, output, model=lambda *args: {'pairs': [{'reason':'unlocated'}]})
    assert reviewed['execution_status'] == 'invalid' and reviewed['result_status'] == 'partial'
    assert len(reviewed['calls']) == 1 and reviewed['graph_sha256'] == state['graph_sha256']
