from copy import deepcopy
import json
import os

import pytest

from test_person_event_contract import graph, payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.build import run_event
from finmy.person_epg.event.records import unknown_time
from finmy.person_epg.event.rendering import event_view, render_event
from finmy.person_epg.rendering import SCROLLABLE_VIEW, read_gantt, render_saved_event, save_gantt


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


def test_workbench_evidence_view_from_saved_input(tmp_path, graph, payload, monkeypatch):
    from finmy.person_epg.event import graph_html
    from finmy.person_epg.event.records import sha256
    from test_person_event_graph_html import embedded_data

    frozen = tmp_path / 'input.json'
    frozen.write_text(json.dumps(payload))
    graph_path = tmp_path / 'epg.json'
    graph_path.write_text(json.dumps(graph))
    state = dict(output='epg.json', result_status='draft', input_sha256=sha256(frozen.read_bytes()),
                 graph_sha256=sha256(graph_path.read_bytes()))
    (tmp_path / 'state.json').write_text(json.dumps(state))
    state['visualization'] = save_gantt(graph, tmp_path, graph_path, result_status='draft')
    assert state['visualization']['renderer'] == SCROLLABLE_VIEW
    html = read_gantt(tmp_path, state, current_view=True)
    assert html == (tmp_path / 'gantt.html').read_text()
    assert embedded_data(html, 'epg-data') == graph
    view = embedded_data(html, 'epg-view')
    assert view['checked_input'] and not view['passage_issues']
    assert {c['kind'] for page in view['pages'] for c in page['cards']} >= {'action', 'context', 'party', 'evidence', 'source'}

    with monkeypatch.context() as patch:
        patch.setattr(graph_html, 'render_graph_html', lambda *a, **kw: pytest.fail('downgraded the saved viewer'))
        state['visualization']['renderer'] = 'person-event-scrollable-v10'
        assert read_gantt(tmp_path, state, current_view=True) == html

    # The workbench can display an earlier renderer's receipt without rewriting it.
    state['visualization']['renderer'] = 'person-event-scrollable-v4'
    assert read_gantt(tmp_path, state, current_view=True) == html
    frozen.write_text(frozen.read_text() + ' ')
    with pytest.raises(ValueError, match='input integrity'):
        read_gantt(tmp_path, state, current_view=True)


def test_running_renderer_keeps_its_matching_template(tmp_path, graph, monkeypatch):
    from finmy.person_epg.event import graph_html

    html = graph_html.render_graph_html(graph)
    (tmp_path / 'graph.html').write_text('asset from another deployment')
    monkeypatch.setattr(graph_html, '_ASSETS', tmp_path)
    assert graph_html.render_graph_html(graph) == html


@pytest.mark.skipif(not os.getenv('FINMY_TEST_CHROMIUM'), reason='Set FINMY_TEST_CHROMIUM for the offline viewport check')
def test_phase_overview_and_reading_size_in_browser(tmp_path, graph):
    from playwright.sync_api import sync_playwright
    from finmy.person_epg.event.graph_html import render_graph_html
    from test_person_event_graph_html import sample_graph

    for i in range(7):
        graph['actions'].append(dict(graph['actions'][0], action_id=f'EXTRA-{i}'))
    output = tmp_path / 'viewer.html'
    output.write_text(render_graph_html(graph), encoding='utf-8')
    fits = """() => {
        const diagram = document.querySelector('#diagram-scroll');
        const viewport = document.querySelector('#viewport'), box = viewport.getBoundingClientRect();
        const nodes = [...document.querySelectorAll('.card')];
        return nodes.length && document.querySelector('#zoom-level').textContent === '100%' &&
          diagram.scrollWidth === diagram.clientWidth && viewport.scrollHeight <= viewport.clientHeight + 1 &&
          nodes.every(node => {
            const r = node.getBoundingClientRect();
            return r.left >= box.left - 1 && r.right <= box.right + 1 &&
                   r.top >= box.top - 1 && r.bottom <= box.bottom + 1;
        });
    }"""
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=os.environ['FINMY_TEST_CHROMIUM'])
        page = browser.new_page(viewport={'width': 1366, 'height': 768}, offline=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(output.as_uri())
        for width, height in [(1366, 768), (390, 844), (844, 390)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_function(fits)
            first = page.locator('.action').first
            first.click()
            page.wait_for_function(fits)
            before = [page.locator(s).bounding_box() for s in ['#heading', '#toolbar', '#inspector']]
            quote = page.locator('.card.evidence').first
            action_width = first.bounding_box()['width']
            page.locator('#plus').click()
            assert page.locator('#zoom-level').inner_text() == '110%'
            assert first.bounding_box()['width'] == pytest.approx(action_width * 1.1, abs=1)
            page.locator('#fit').click()
            page.wait_for_function(fits)
            page.locator('#zoom').click()
            assert first.bounding_box()['width'] > action_width
            assert first.evaluate('el => Math.abs(el.getBoundingClientRect().width - el.offsetWidth) < 1')
            card, viewport = first.bounding_box(), page.locator('#viewport').bounding_box()
            for axis, extent in [('x', 'width'), ('y', 'height')]:
                assert viewport[axis] - 1 <= card[axis]
                assert card[axis] + card[extent] <= viewport[axis] + viewport[extent] + 1
            assert before == [page.locator(s).bounding_box() for s in ['#heading', '#toolbar', '#inspector']]
            assert page.evaluate('document.documentElement.scrollWidth === innerWidth && document.documentElement.scrollHeight === innerHeight')
            page.locator('#fit').click()
            page.wait_for_function(fits)
            quote.click()
            assert page.locator('#inspection blockquote').is_visible()
            assert page.locator('#evidence-lines path').count() > 0
            page.locator('#inspection h3:text-is("Source") + button').click()
            assert page.locator('#inspection .inspection-meta').first.inner_text().startswith('SOURCE')
            page.locator('#inspection-back').click()
            assert page.locator('#inspection blockquote').is_visible()
            page.keyboard.press('Escape')
            page.locator('#plus').click()
            page.locator('#next').click()
            page.wait_for_function(fits)
            page.locator('#previous').click()
        background = sample_graph()
        background.update(sources=graph['sources'], evidence=graph['evidence'])
        background_file = tmp_path / 'background.html'
        background_file.write_text(render_graph_html(background), encoding='utf-8')
        page.goto(background_file.as_uri())
        assert page.locator('#diagram-scroll').is_hidden()
        page.wait_for_function(fits)
        page.locator('#minus').click()
        assert page.locator('#zoom-level').inner_text() == '90%'
        page.locator('.card.evidence').first.click()
        assert page.locator('#evidence-lines path').count() > 0
        assert not errors
        browser.close()


@pytest.mark.skipif(not os.getenv('FINMY_TEST_CHROMIUM'), reason='Set FINMY_TEST_CHROMIUM for the offline viewport check')
@pytest.mark.parametrize('pre_slot_layout', [False, True])
def test_cross_phase_action_navigation_from_both_endpoints(tmp_path, monkeypatch, pre_slot_layout):
    from playwright.sync_api import sync_playwright
    from finmy.person_epg.event import graph_html
    from test_person_event_graph_html import sample_graph

    graph = sample_graph()
    graph['phases'] = [{'phase_id': pid, 'name': pid} for pid in ('Planning', 'Decision', 'Execution')]
    graph['actions'] = [{'action_id': aid, 'phase_id': p['phase_id'], 'name': aid}
                        for aid, p in zip(('Proposal', 'Vote', 'Delivery'), graph['phases'])]
    graph['actions'].append({'action_id': 'Consent', 'phase_id': 'Planning', 'name': 'Consent'})
    graph['contexts'] = [{'context_id': 'terms', 'description': 'Shared condition'}]
    for action in graph['actions'][:2]:
        action['delta_context_refs'] = [{'context_id': 'terms', 'relation_type': 'condition'}]
    graph['sources'] = [{'source_id': 's', 'title': 'Minutes'}]
    graph['evidence'] = [{'evidence_id': 'e', 'source_id': 's', 'quote': 'The proposal enabled the vote.'}]
    graph['relations'] = [
        {'relation_id': 'r1', 'from_action_id': 'Proposal', 'to_action_id': 'Vote', 'type': 'enables',
         'support': [{'target': '/type', 'evidence_ids': ['e'], 'mode': 'A'}]},
        {'relation_id': 'r2', 'from_action_id': 'Vote', 'to_action_id': 'Delivery', 'type': 'overlaps', 'basis': 'inferred'},
        {'relation_id': 'r3', 'from_action_id': 'Proposal', 'to_action_id': 'Consent', 'type': 'order_unknown',
         'basis': 'asserted'},
    ]
    if pre_slot_layout:
        arrange = graph_html.arrange_graph

        def earlier_layout(*args):
            view = arrange(*args)
            for sheet in view['pages']:
                sheet.pop('relation_slots')
                inset = sheet['sections'][0]['box'][1] - 18 if sheet['sections'] else 0
                for item in [*sheet['cards'], *sheet['sections']]:
                    item['box'][1] -= inset
                for jump in sheet['jumps']:
                    jump.pop('action_id')
            view['pages'][1]['jumps'].append({'relation_id': None, 'id': 'terms', 'page': 2})
            return view

        monkeypatch.setattr(graph_html, 'arrange_graph', earlier_layout)
    path = tmp_path / 'navigation.html'
    html = graph_html.render_graph_html(graph)
    path.write_text(html, encoding='utf-8')
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=os.environ['FINMY_TEST_CHROMIUM'])
        for width, height in ((1366, 768), (390, 844)):
            tab = browser.new_page(viewport={'width': width, 'height': height}, offline=True)
            errors = []
            tab.on('pageerror', lambda exc: errors.append(str(exc)))
            if pre_slot_layout and width > 800:
                tab.set_content('<style>* {margin:0} iframe {width:100vw;height:100vh;border:0}</style><iframe></iframe>')
                iframe = tab.locator('iframe')
                iframe.evaluate('(el, html) => { el.srcdoc = html; }', html)
                page = tab.frame_locator('iframe')
            else:
                tab.goto(path.as_uri())
                page = tab
            page.locator('#links .edge-layer polyline').first.wait_for(state='attached')
            assert page.locator('#jumps').count() == 0
            assert not page.locator('.phase-link').count()
            assert page.locator('#outline').evaluate('el => el.open')
            label = page.locator('#links .edge-label[data-relation=r1]')
            assert label.text_content() == 'A01 enables A02'
            assert page.locator('#links .edge-label[data-relation=r3]').text_content() == 'A01 order unknown A04'
            bridge = page.locator('#phase-bridges .bridge[data-relation-id=r1]')
            assert bridge.get_attribute('data-page') == '2'
            assert bridge.get_attribute('marker-end') == 'url(#phase-arrow)'
            assert bridge.get_attribute('stroke-dasharray') == 'none'
            assert bridge.evaluate("""path => {
                const tab = document.querySelector('#navigation [data-page="2"]').getBoundingClientRect();
                const tip = path.getPointAtLength(path.getTotalLength()).matrixTransform(path.getScreenCTM());
                return tip.x >= tab.left && tip.x <= tab.right && Math.abs(tip.y - tab.bottom) < 1;
            }""")
            page.get_by_role('button', name='A01 enables A02').press('Enter')
            assert page.locator('#inspection-title').inner_text() == 'A01 enables A02'
            assert page.locator('#inspection [data-target="e"]').count() == 1
            page.locator('.phase-list .relation-destination').click()
            assert page.locator('.action[data-id=Vote]').evaluate('el => el === document.activeElement')
            assert bridge.get_attribute('data-page') == '1'
            assert bridge.get_attribute('marker-end') is None
            assert page.locator('#links .edge-label[data-relation=r2]').text_content() == 'A02 overlaps A03'
            label.click()
            page.get_by_role('button', name='Go to A01 · Phase 1').click()
            page.get_by_role('button', name='Back to A02 · Phase 2').click()
            page.get_by_role('button', name='Back to A01 · Phase 1').click()
            assert page.locator('.action[data-id=Proposal]').evaluate('el => el === document.activeElement')
            page.locator('#picker').select_option('3')
            symmetric = page.locator('#phase-bridges .bridge[data-relation-id=r2]')
            assert symmetric.get_attribute('marker-end') is None
            assert symmetric.get_attribute('stroke-dasharray') != 'none'
            page.locator('#links .edge-label[data-relation=r2]').click()
            assert page.locator('#inspection-title').inner_text() == 'A02 overlaps A03'
            assert not errors
            tab.close()
        browser.close()


@pytest.mark.skipif(not os.getenv('FINMY_TEST_CHROMIUM'), reason='Set FINMY_TEST_CHROMIUM for the offline viewport check')
def test_zoom_uses_spare_width_and_preserves_layout_rows(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    from finmy.person_epg.event import graph_html
    from test_person_event_graph_html import sample_graph

    graph = sample_graph()
    graph['phases'] = [{'phase_id': 'P', 'name': 'Phase'}]
    graph['actions'] = [{'action_id': f'A{i}', 'phase_id': 'P', 'name': f'Action {i}'} for i in range(6)]
    graph['sources'] = [{'source_id': f'S{i}', 'title': f'Source {i}'} for i in range(24)]
    graph['evidence'] = [{'evidence_id': f'E{i}', 'source_id': f'S{i}', 'quote': f'Quote {i}'} for i in range(24)]
    graph['actions'][0]['support'] = [{'target': '/name', 'evidence_ids': [e['evidence_id'] for e in graph['evidence']]}]
    graph['relations'] = [{'relation_id': 'R', 'from_action_id': 'A0', 'to_action_id': 'A1', 'type': 'precedes'}]
    arrange = graph_html.arrange_graph

    def arrange_two_rows(*args):
        view = arrange(*args)
        phase = next(p for p in view['pages'] if p['phase'] == 'P')
        actions = [c for c in phase['cards'] if c['kind'] == 'action']
        for i, card in enumerate(actions[4:]):
            card['box'][0] = actions[i + 1]['box'][0]
            card['box'][1] += 140
        next(s for s in phase['sections'] if s['title'] == 'Actions and their context')['box'][3] += 140
        return view

    monkeypatch.setattr(graph_html, 'arrange_graph', arrange_two_rows)
    output = tmp_path / 'two-rows.html'
    output.write_text(graph_html.render_graph_html(graph), encoding='utf-8')
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=os.environ['FINMY_TEST_CHROMIUM'])
        page = browser.new_page(viewport={'width': 2500, 'height': 1320}, offline=True)
        page.goto(output.as_uri())
        assert page.locator('#zoom-level').inner_text() == '100%'
        grids = page.locator('.reference-grid')

        def cards_in_first_rows():
            return grids.evaluate_all("""grids => grids.map(grid => [...grid.children].filter(
                card => card.offsetTop === grid.firstElementChild.offsetTop).length)""")

        def rows():
            return page.locator('.action').evaluate_all("""cards => {
                const rows = new Map();
                for (const card of cards) {
                    if (!rows.has(card.offsetTop)) rows.set(card.offsetTop, []);
                    rows.get(card.offsetTop).push(card);
                }
                return [...rows.entries()].sort((a,b) => a[0]-b[0]).map(([,row]) =>
                    row.sort((a,b) => a.offsetLeft-b.offsetLeft).map(c => c.dataset.id));
            }""")

        expected = [['A0', 'A1', 'A2', 'A3'], ['A4', 'A5']]
        assert rows() == expected
        at_full_size = cards_in_first_rows()
        for _ in range(3):
            page.locator('#minus').click()
        assert page.locator('#zoom-level').inner_text() == '70%'
        assert all(b > a for a, b in zip(at_full_size, cards_in_first_rows(), strict=True))
        assert rows() == expected
        fills = """() => {
            const area = document.querySelector('#diagram-scroll');
            const last = document.querySelector('.action[data-id="A3"]'), box = last.getBoundingClientRect();
            const gap = area.getBoundingClientRect().right - box.right;
            return area.scrollWidth === area.clientWidth && gap >= 0 && gap <= 45 * box.width / last.offsetWidth + 1;
        }"""
        page.wait_for_function(fills)
        page.locator('.action').first.click()
        page.wait_for_function(fills)
        assert rows() == expected
        page.keyboard.press('Escape')
        page.wait_for_function(fills)
        page.set_viewport_size({'width': 600, 'height': 750})
        page.locator('#zoom').click()
        page.wait_for_function("""() => {const s=document.querySelector('#diagram-scroll');
            return s.scrollWidth > s.clientWidth && document.documentElement.scrollWidth === innerWidth;}""")
        assert rows() == expected
        assert page.locator('[data-relation-id="R"]').count() == 1
        path = page.locator('[data-relation-id="R"]')
        path.focus()
        path.press('Enter')
        page.set_viewport_size({'width': 2500, 'height': 1320})
        # A Phase reset brings the relation into the full-width overview.
        page.locator('#fit').click()
        page.wait_for_function(fills)
        page.keyboard.press('Escape')
        page.wait_for_function(fills)
        assert path.evaluate('node => node === document.activeElement')
        browser.close()
