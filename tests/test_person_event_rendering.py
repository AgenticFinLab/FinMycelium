from copy import deepcopy
import json

import pytest

from test_person_event_contract import graph, payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.build import run_event
from finmy.person_epg.event.records import unknown_time
from finmy.person_epg.event.rendering import event_view, render_event
from finmy.person_epg.rendering import read_gantt, render_saved_event


def test_new_view_has_all_levels_and_retains_unknowns(graph):
    before = deepcopy(graph)
    view = event_view(graph)
    assert {r['kind'] for r in view['rows']} == {'Event', 'Stage', 'Phase', 'Action'}
    assert any(r['kind'] == 'Context' for r in view['items'])
    assert any(r['kind'] == 'Relation' for r in view['items'])
    assert all(r['fields'].get('Effective Context') for r in view['items'] if r['kind'] == 'Action')
    assert graph == before
    action = graph['actions'][0]
    action['time'] = unknown_time()
    rows = event_view(graph)['rows']
    assert rows[-1]['key'] == 'actions:' + action['action_id'] and rows[-1]['interval'] is None


def test_plot_text_cannot_execute_source_instructions(graph):
    graph['event']['name'] = '</script><script>alert(1)</script>'
    html = render_event(graph)
    assert graph['event']['name'] not in html
    assert '\\u003c/script\\u003e' in html
    assert 'Event, Stage, Phase and Action' in html
    assert 'cdn.plot.ly' not in html.split('const model = ')[-1]


def test_new_render_failure_does_not_erase_graph_or_rebuild(tmp_path, payload, monkeypatch):
    from finmy.person_epg.event import graph_html as rendering
    model = SyntheticEventModel()
    original = rendering.render_graph_html
    monkeypatch.setattr(rendering, 'render_graph_html', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('plot failure')))
    state = run_event(payload, tmp_path, model=model)
    assert state['result_status'] == 'draft' and state['render_status'] == 'failed'
    calls, graph_hash = len(model.calls), state['graph_sha256']
    monkeypatch.setattr(rendering, 'render_graph_html', original)
    state = render_saved_event(tmp_path)
    assert state['render_status'] == 'completed' and len(model.calls) == calls
    assert state['graph_sha256'] == graph_hash
    assert graph_hash in read_gantt(tmp_path, state)
    path = tmp_path / state['output']
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='integrity'):
        read_gantt(tmp_path, state)


def test_rendered_graph_hash_binds_exact_bytes(tmp_path, payload):
    state = run_event(payload, tmp_path, model=SyntheticEventModel())
    assert state['visualization']['graph_sha256'] == state['graph_sha256']
    assert state['render_status'] == 'completed'
    html = read_gantt(tmp_path, state)
    assert f'content="{state["graph_sha256"]}"' in html
    assert 'id="epg-view"' in html and 'id="picker"' in html
    assert html == read_gantt(tmp_path, state, current_view=True)
    checks = json.loads((tmp_path / state['checks']).read_text())
    assert checks['graph_sha256'] == state['graph_sha256']


def test_historical_timeline_previews_current_graph_without_changing_receipts(tmp_path, payload):
    from finmy.person_epg.event.records import sha256
    from finmy.person_epg.event.runtime import write_json

    state = run_event(payload, tmp_path, model=SyntheticEventModel())
    graph = json.loads((tmp_path / state['output']).read_text())
    timeline = render_event(graph, state['graph_sha256'], result_status='draft')
    artifact = tmp_path / state['visualization']['output']
    artifact.write_text(timeline, encoding='utf-8')
    state['visualization'].pop('renderer')
    state['visualization']['html_sha256'] = sha256(artifact.read_bytes())
    write_json(tmp_path / 'state.json', state)
    snapshot = (tmp_path / 'state.json').read_bytes()
    assert read_gantt(tmp_path, state) == timeline
    preview = read_gantt(tmp_path, state, current_view=True)
    assert 'id="epg-view"' in preview and state['graph_sha256'] in preview
    assert artifact.read_text() == timeline and (tmp_path / 'state.json').read_bytes() == snapshot
    assert read_gantt(tmp_path, render_saved_event(tmp_path)) == preview
