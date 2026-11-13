from copy import deepcopy
import json
import socket

import pytest

from finmy.person_epg.build import run_legacy_event as run_event
from finmy.person_epg.rendering import read_gantt, render_saved_event
from finmy.person_epg.visualizer_gantt import event_view, PersonEventGanttVisualizer, render_event
from test_person_event_build import payload, SyntheticModel


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Rendering must stay offline'))


@pytest.fixture
def native(tmp_path):
    model = SyntheticModel()
    directory = tmp_path/'run'
    state = run_event(payload(), directory, model=model)
    graph = json.loads((directory/state['output']).read_text())
    return graph, state, directory, model


def test_native_identity_evidence_and_transaction_direction(native):
    graph, state, directory, _ = native
    before = deepcopy(graph)
    assert state['status'] == 'completed'
    assert state['visualization']['status'] == 'completed', state['visualization']
    view = event_view(graph)
    assert view['event']['event_id'] == 'PERSON-TEST-E1'
    assert len(view['stages']) == 1
    action, transaction = view['activities']
    assert action['activity_id'] == 'A:A1' and transaction['activity_id'] == 'T:T1'
    assert transaction['edges'][0] == {'source':'PERSON-TEST','target':'foundation','label':'Transfer'}
    assert any(e['document_id'] == 'DOC_1' and e['url'] == 'https://example.org/notice' for e in action['evidence'])
    assert len(action['evidence']) == 1 and len(action['evidence'][0]['references']) > 1
    for item in view['items']:
        for e in item['evidence']:
            doc = next(d for d in graph['source_document'] if d['document_id'] == e['document_id'])
            assert doc['content'][e['char_start']:e['char_end']] == e['quote']
    html = read_gantt(directory, state)
    assert state['graph_sha256'] in html and 'Draft · content review pending' in html
    assert '<script src=' not in html and '<details' not in html
    assert graph == before  # No EventCascade conversion or date rewriting.


def test_precision_unknowns_and_unassigned_facts(native):
    graph, *_ = native
    times = {t['time_id']:t for t in graph['time_value']}
    times[graph['action'][0]['timestamp_time_id']]['value'] = '2025'
    times[graph['financial_transaction'][0]['timestamp_time_id']]['value'] = 'unknown'
    view = event_view(graph)
    assert view['activities'][0]['time_label'] == '2025'
    assert view['activities'][0]['interval'][2] == 'year'
    assert view['activities'][1]['interval'] is None
    fig = PersonEventGanttVisualizer().plot_event(view)
    plotted = [t for t in fig.data if t.xaxis != 'x2']
    assert any(t.line.dash == 'dot' for t in plotted)
    assert not any('activity:T:T1' in (t.customdata or []) for t in plotted)
    assert any(a.text == 'Time not placed' for a in fig.layout.annotations)
    graph['event_activity'] = graph['event_activity'][:1]
    view = event_view(graph)
    retained = next(x for x in view['items'] if x['key'] == 'activity:T:T1')
    assert retained['fields']['Placement'].startswith('Retained fact')
    assert not retained['assigned']


def test_all_unknown_times_never_use_today_as_a_date(native):
    graph, *_ = native
    for row in graph['time_value']:
        row['value'] = 'unknown'
    view = event_view(graph)
    fig = PersonEventGanttVisualizer().plot_event(view)
    assert fig.layout.xaxis.type == 'linear' and not fig.layout.xaxis.showticklabels
    assert not any(t.xaxis != 'x2' for t in fig.data)
    assert len([a for a in fig.layout.annotations if a.text == 'Time not placed']) == 3


def test_native_relations_remain_inspectable_without_known_dates(native):
    graph, *_ = native
    graph['activity_relation'] = [dict(link_id='R1',from_activity_id='A:A1',to_activity_id='T:T1',
                                        relation_type='precedes',basis='inferred',description='Review this inference')]
    graph['entity_relation'] = [dict(relation_id='ER1',from_entity_id='PERSON-TEST',to_entity_id='foundation',
                                    relation_type='supporter',sort_order=0)]
    graph['relation_occurrence'] = [dict(relation_id='ER1',occurrence_id='O1',sort_order=0)]
    for row in graph['time_value']:
        row['value'] = 'unknown'
    view = event_view(graph)
    rel = next(i for i in view['items'] if i['key'] == 'activity-relation:R1')
    assert rel['fields']['basis'] == 'inferred'
    assert any(e['label'] == 'supporter' for e in view['activities'][0]['edges'])
    PersonEventGanttVisualizer().plot_event(view)


def test_input_script_text_cannot_escape_html(native):
    graph, *_ = native
    value = '</script><script>window.INJECTED=true</script>'
    graph['event'][0]['label'] = value
    graph['entity'][0]['name'] = '<img src=x onerror=alert(1)>'
    html = render_event(graph)
    assert value not in html and '<img src=x' not in html
    assert '\\u003c/script\\u003e' in html


def test_multiple_events_are_not_silently_collapsed(native):
    graph, *_ = native
    graph['event'].append({**graph['event'][0], 'event_id':'another', 'sort_order':1})
    with pytest.raises(ValueError, match='exactly one event'):
        render_event(graph)


def test_render_failure_keeps_json_and_rerender_needs_no_calls(tmp_path, monkeypatch):
    import finmy.person_epg.visualizer_gantt as renderer
    original = renderer.render_event
    def fail(*args):
        raise RuntimeError('Synthetic rendering failure')
    monkeypatch.setattr(renderer, 'render_event', fail)
    model = SyntheticModel(); directory = tmp_path/'run'
    state = run_event(payload(), directory, model=model)
    assert state['status'] == 'completed' and state['visualization']['status'] == 'failed'
    draft = (directory/state['output']).read_bytes()
    calls = deepcopy(state['calls'])
    monkeypatch.setattr(renderer, 'render_event', original)
    resumed = render_saved_event(directory)
    assert resumed['visualization']['status'] == 'completed'
    assert resumed['status'] == 'completed' and resumed['review_required']
    assert calls == resumed['calls'] and len(model.calls) == len(calls)
    assert (directory/state['output']).read_bytes() == draft
    assert read_gantt(directory, resumed)


def test_rendered_html_and_graph_must_match(native):
    graph, state, directory, _ = native
    html_path = directory/state['visualization']['output']
    html_path.write_text('unexpected')
    with pytest.raises(ValueError, match='integrity'):
        read_gantt(directory, state)
    state = render_saved_event(directory)
    assert read_gantt(directory, state)
    graph['event'][0]['label'] = 'changed'
    (directory/state['output']).write_text(json.dumps(graph))
    with pytest.raises(ValueError, match='integrity'):
        read_gantt(directory, state)
    with pytest.raises(ValueError, match='integrity'):
        render_saved_event(directory)
