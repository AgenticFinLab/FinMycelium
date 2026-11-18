"""Evidence-starved Actions must remain visible under bounded relation requests."""
from copy import deepcopy
from types import SimpleNamespace

from test_person_event_contract import graph, payload
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.context import sized_request
from finmy.person_epg.event.prompts import system_prompt
from finmy.person_epg.event.records import prompt_json
from finmy.person_epg.event.runtime import EventBuildConfig


def evidence_ids(request):
    return [r['record']['evidence_id'] for r in request['related_records'] if r['collection'] == 'evidence']


def base(graph):
    return dict(role='relations', assigned_action_ids=[a['action_id'] for a in graph['actions']],
        assigned_phase_ids=[], assigned_records=dict(actions=deepcopy(graph['actions']), phases=[]),
        relation_candidates=[])


def uneven(graph):
    """An early Action has many quotes; two later Actions have their own quotes."""
    action, evidence = deepcopy(graph['actions'][0]), deepcopy(graph['evidence'][0])
    graph['actions'], graph['evidence'] = [], []
    for n, count in enumerate((18, 3, 3)):
        a = deepcopy(action)
        a.update(action_id='A'+str(n), support=[], conflicts=[], gaps=[])
        for i in range(count):
            e = deepcopy(evidence)
            e.update(evidence_id=f'E{n}-{i:02}', quote=f'Exact quote {n}-{i}. ' + 'x' * 1400)
            graph['evidence'].append(e)
            a['support'].append(dict(target='/description', mode='A', evidence_ids=[e['evidence_id']]))
        graph['actions'].append(a)
    return graph


def test_uneven_action_evidence_rotates_before_candidates_and_context(graph):
    graph = uneven(graph)
    original = deepcopy(graph)
    request = sized_request(base(graph), graph, 30000, 4000)
    included = evidence_ids(request)
    # Initial delivery covers all owners, including those without candidates.
    assert included[:3] == ['E0-00', 'E1-00', 'E2-00']
    assert not request['context_selection']['uncovered_action_ids']
    assert request['context_selection']['evidence_by_owner'][0]['omitted_evidence_ids']
    assert len(prompt_json(dict(task=request, read_results=[]))) <= 26000
    assert graph == original
    for item in request['related_records']:
        if item['collection'] == 'evidence':
            e = next(e for e in graph['evidence'] if e['evidence_id'] == item['record']['evidence_id'])
            assert all(item['record'][k] == e[k] for k in ('quote', 'start', 'end', 'sample_id', 'source_id'))


def test_candidate_reordering_cannot_take_away_minimum_action_quotes(graph):
    graph = uneven(graph)
    request = base(graph)
    request['relation_candidates'] = [dict(candidate_id='C', from_action_id='A0', to_action_id='A1',
        support=[dict(evidence_ids=['E0-17'])])]
    first = sized_request(request, graph, 30000, 4000)
    request['assigned_action_ids'].reverse()
    request['assigned_records']['actions'].reverse()
    second = sized_request(request, graph, 30000, 4000)
    assert {'E0-00', 'E1-00', 'E2-00'} <= set(evidence_ids(first)) & set(evidence_ids(second))
    assert 'E0-17' not in evidence_ids(first)[:3]

def test_passage_about_link_is_delivered_before_extra_endpoint_passages(graph):
    graph = uneven(graph)
    request = base(graph)
    request['relation_candidates'] = [dict(candidate_id='C', from_action_id='A0', to_action_id='A1',
        support=[dict(target='/type', evidence_ids=['E0-17'])])]
    result = sized_request(request, graph, 30000, 4000)
    assert evidence_ids(result)[:4] == ['E0-00', 'E1-00', 'E2-00', 'E0-17']
    assert result['context_selection']['omitted_relation_evidence_ids'] == []
    graph['evidence'][17]['quote'] = 'long connecting passage ' * 4000
    result = sized_request(request, graph, 30000, 4000)
    assert result['context_selection']['omitted_relation_evidence_ids'] == ['E0-17']
    assert result['context_selection']['uncovered_action_ids'] == []


def test_shared_evidence_is_delivered_once_and_counts_for_each_owner(graph):
    graph = uneven(graph)
    for a in graph['actions']:
        a['support'] = [dict(target='/description', mode='A', evidence_ids=['E0-00'])]
    request = sized_request(base(graph), graph, 30000, 4000)
    assert evidence_ids(request).count('E0-00') == 1
    assert all(r['included'] == 1 and not r['omitted_evidence_ids']
        for r in request['context_selection']['evidence_by_owner'])


def test_no_support_is_reported_separately_from_budget_omission(graph):
    graph = uneven(graph)
    graph['actions'][1]['support'] = []
    request = sized_request(base(graph), graph, 30000, 4000)
    assert request['context_selection']['actions_without_evidence'] == ['A1']
    assert not request['context_selection']['uncovered_action_ids']


def test_long_quote_is_not_truncated_or_replaced_by_unrelated_evidence(graph):
    graph = uneven(graph)
    graph['actions'] = graph['actions'][:1]
    graph['actions'][0]['support'] = [dict(target='/description', mode='A', evidence_ids=['E0-00'])]
    graph['evidence'][0]['quote'] = 'unaltered ' * 10000
    request = sized_request(base(graph), graph, 30000, 4000)
    assert request['context_selection']['uncovered_action_ids'] == ['A0']
    assert 'E0-00' in request['context_selection']['evidence_by_owner'][0]['omitted_evidence_ids']
    assert 'E0-00' not in evidence_ids(request)


def test_batching_preserves_global_navigation_and_delivers_minimum_evidence(graph, payload):
    graph = uneven(graph)
    # With quotes this large, all three Actions cannot share one bounded request.
    for e in graph['evidence']:
        e['quote'] *= 6
    config = EventBuildConfig(max_context_chars=60000)
    builder = Construction(SimpleNamespace(payload=payload, config=config, state={'id_map': {}}))
    builder.graph = graph
    seen = []
    def receive(task, role, package, request, **scope):
        assert not request['context_selection']['uncovered_action_ids']
        assert {a['action_id'] for a in request['facts_index']['actions']} == {'A0', 'A1', 'A2'}
        assert len(system_prompt(role)) + len(prompt_json(dict(task=request, read_results=[]))) <= 45000
        seen.append(request['assigned_action_ids'])
        return package, {}
    builder.receive = receive
    builder.relate()
    assert [aid for batch in seen for aid in batch] == ['A0', 'A1', 'A2']
    assert sum(bool(batch) for batch in seen) > 1


def test_single_oversized_quote_keeps_read_fallback_instead_of_blocking(graph, payload):
    graph = uneven(graph)
    graph['actions'] = graph['actions'][:1]
    graph['actions'][0]['support'] = [dict(target='/description', mode='A', evidence_ids=['E0-00'])]
    graph['evidence'][0]['quote'] = 'unaltered ' * 10000
    builder = Construction(SimpleNamespace(payload=payload,
        config=EventBuildConfig(max_context_chars=60000), state={'id_map': {}}))
    builder.graph = graph
    seen = []
    def receive(task, role, package, request, **scope):
        if request['assigned_action_ids']:
            assert request['context_selection']['uncovered_action_ids'] == ['A0']
            assert any(e['evidence_id'] == 'E0-00' for e in request['facts_index']['evidence_index'])
            seen.extend(request['assigned_action_ids'])
        return package, {}
    builder.receive = receive
    builder.relate()
    assert seen == ['A0']
