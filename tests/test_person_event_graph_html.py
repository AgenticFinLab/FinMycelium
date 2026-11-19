"""Test the standalone exporter without Streamlit, a model, or a browser."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from finmy.person_epg.event.graph_html import render_graph_html
from finmy.person_epg.event.records import fingerprint
from finmy.person_epg.event.schema import GRAPH_VERSION, LEGACY_GRAPH_VERSION


def sample_graph():
    return {
        'schema_version': LEGACY_GRAPH_VERSION,
        'event': {'event_id': 'TEST-E1', 'name': '示例'},
        'person': {'name': 'Test Person'},
        **{name: [] for name in (
            'stages', 'phases', 'actions', 'contexts', 'entities', 'sources', 'evidence', 'relations'
        )},
    }


def embedded_data(html, script_id):
    match = re.search(rf'<script id="{script_id}" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(match[1])


class PersonEventGraphHtmlTests(unittest.TestCase):

    def test_fact_sources_are_many_to_many_without_duplicate_source_cards(self):
        graph = sample_graph()
        graph['schema_version'] = GRAPH_VERSION
        graph['phases'] = [{'phase_id': 'P1', 'name': 'Investment'}]
        graph['actions'] = [{'action_id': 'A1', 'name': 'Investment', 'phase_id': 'P1',
                             'support': [{'evidence_ids': ['E1', 'E2']}]}]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Announcement', 'publisher': 'Company'},
                            {'source_id': 'S2', 'title': 'Interview', 'upstream_source_ids': ['S1']}]
        graph['evidence'] = [
            {'evidence_id': 'E1', 'statement': 'An investment took place.', 'citations': [
                {'source_id': 'S1', 'quote': 'We received the investment.'},
                {'source_id': 'S2', 'quote': 'I made the investment.'}]},
            {'evidence_id': 'E2', 'statement': 'The investment was one million.', 'citations': [
                {'source_id': 'S1', 'quote': 'One million was invested.'}]},
        ]
        before = json.loads(json.dumps(graph))
        html = render_graph_html(graph)
        view = embedded_data(html, 'epg-view')
        self.assertIn('Publisher: Company', view['details']['S1']['paragraphs'])
        self.assertIn('Reports information from: Announcement', view['details']['S2']['paragraphs'])
        page = next(page for page in view['pages'] if page['phase'] == 'P1')
        sources = [card for card in page['cards'] if card['kind'] == 'source']
        self.assertEqual({card['id']: card['quotes'] for card in sources},
                         {'S1': ['E1', 'E2'], 'S2': ['E1']})
        self.assertEqual(len(sources), 2)
        self.assertEqual({(edge['from'], edge['to']) for edge in page['edges'] if edge['kind'] == 'evidence'},
                         {('S1', 'A1'), ('S2', 'A1')})
        self.assertEqual(embedded_data(html, 'epg-data'), before)
        self.assertEqual(graph, before)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed to execute renderer citation selection')
    def test_both_html_renderers_only_select_the_current_sources_quotations(self):
        assets = Path(__file__).parents[1] / 'finmy/person_epg/event'
        fact = {'statement': 'Investment completed.', 'citations': [
            {'source_id': 'S1', 'quote': 'Announcement passage'},
            {'source_id': 'S2', 'quote': 'Interview passage'},
            {'source_id': 'S1', 'quote': 'Another announcement passage'},
        ]}
        for template in ('graph.html', 'graph_authored.html'):
            text = (assets / template).read_text()
            function = re.search(r'^function sourceCitations\(.*?^}', text, re.M | re.S).group()
            script = function + '''
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const old = {source_id:'S2', quote:'Legacy quotation'};
console.log(JSON.stringify([sourceCitations(input, 'S1'), sourceCitations(input, 'S2'),
                           sourceCitations(old, 'S1'), sourceCitations(old, 'S2')]));
'''
            result = subprocess.run(['node', '-e', script], input=json.dumps(fact),
                                    text=True, capture_output=True, check=True)
            selected = json.loads(result.stdout)
            self.assertEqual([item['quote'] for item in selected[0]],
                             ['Announcement passage', 'Another announcement passage'])
            self.assertEqual([item['quote'] for item in selected[1]], ['Interview passage'])
            self.assertEqual(selected[2], [])
            self.assertEqual(selected[3][0]['quote'], 'Legacy quotation')

    def test_whole_phase_uses_one_wide_canvas_with_deduplicated_nodes(self):
        graph = sample_graph()
        graph['person'] = {'person_id': 'PERSON-X', 'name': 'Example Person'}
        graph['entities'] = [
            {'entity_id': 'PERSON-X', 'name': 'Example Person', 'type': 'person'},
            {'entity_id': 'ORG-X', 'name': 'Example Company', 'type': 'organization'},
        ]
        graph['phases'] = [{'phase_id': 'P1', 'name': 'Long phase'}, {'phase_id': 'P2', 'name': 'Next phase'}]
        graph['actions'] = [
            {'action_id': f'A{i}', 'phase_id': 'P1', 'name': f'Action {i}',
             'actor': {'entity_id': 'PERSON-X'}, 'object': {'entity_refs': ['ORG-X']},
             'delta_context_refs': [{'context_id': 'SHARED', 'relation_type': 'condition'}],
             'support': [{'evidence_ids': ['E1']}]}
            for i in range(12)
        ] + [{'action_id': 'NEXT', 'phase_id': 'P2', 'name': 'Next phase action'}]
        graph['contexts'] = [{'context_id': 'SHARED', 'description': 'Shared condition'}]
        graph['relations'] = [
            {'from_action_id': f'A{i}', 'to_action_id': f'A{i+1}', 'type': 'precedes'}
            for i in range(11)
        ] + [{'from_action_id': 'A11', 'to_action_id': 'NEXT', 'type': 'precedes'}]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Shared source'}]
        graph['evidence'] = [{'evidence_id': 'E1', 'source_id': 'S1', 'quote': 'Exact evidence'}]
        before = json.loads(json.dumps(graph))
        view = embedded_data(render_graph_html(graph), 'epg-view')
        phase_pages = [page for page in view['pages'] if page['phase'] == 'P1']
        self.assertEqual(len(phase_pages), 1)
        page = phase_pages[0]
        ids = [card['id'] for card in page['cards']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({'PERSON-X', 'ORG-X', 'SHARED', 'S1'} <= set(ids))
        self.assertTrue({f'A{i}' for i in range(12)} <= set(ids))
        self.assertGreater(page['width'], 3000)
        cards = {card['id']: card for card in page['cards']}
        edges = {(edge['from'], edge['to']) for edge in page['edges']}
        for i in range(11):
            self.assertIn((f'A{i}', f'A{i+1}'), edges)
            self.assertLess(cards[f'A{i}']['box'][0], cards[f'A{i+1}']['box'][0])
        self.assertEqual({jump['id'] for jump in page['jumps']}, {'NEXT'})
        self.assertEqual(graph, before)

    def test_background_context_and_uncited_evidence_are_not_paginated(self):
        graph = sample_graph()
        graph['contexts'] = [{'context_id': f'C{i}', 'description': f'Background {i}'} for i in range(31)]
        graph['sources'] = [{'source_id': f'S{i}', 'title': f'Source {i}'} for i in range(12)]
        graph['evidence'] = [
            {'evidence_id': f'E{i}', 'source_id': f'S{i%12}', 'quote': f'Passage {i}'}
            for i in range(36)
        ]
        view = embedded_data(render_graph_html(graph), 'epg-view')
        self.assertEqual(len(view['pages']), 1)
        page = view['pages'][0]
        self.assertEqual(sum(c['kind'] == 'context' for c in page['cards']), 31)
        self.assertEqual(sum(c['kind'] == 'source' for c in page['cards']), 12)
        passages = {eid for card in page['cards'] for eid in card.get('quotes', [])}
        self.assertEqual(passages, {f'E{i}' for i in range(36)})
        for card in page['cards']:
            x, y, width, height = card['box']
            self.assertLessEqual(x + width, page['width'])
            self.assertLessEqual(y + height, page['height'])

    def test_people_roles_and_explicit_sequence_survive_compact_layout(self):
        graph = sample_graph()
        graph['person'] = {'person_id': 'PERSON-X', 'name': 'Ada Example'}
        graph['entities'] = [
            {'entity_id': 'PERSON-X', 'name': 'Ada Example', 'aliases': ['Ada'], 'type': 'person'},
            {'entity_id': 'ORG-X', 'name': 'Example Company', 'type': 'organization'},
        ]
        graph['phases'] = [{'phase_id': 'P1', 'name': 'Decision'}]
        graph['actions'] = [
            {'action_id': 'A1', 'phase_id': 'P1', 'name': 'Ada reviews the proposal',
             'actor': {'entity_id': 'PERSON-X'}, 'object': {'entity_refs': ['ORG-X']}},
            {'action_id': 'UNRELATED', 'phase_id': 'P1', 'name': 'Other activity'},
            {'action_id': 'A2', 'phase_id': 'P1', 'name': 'Ada approves the proposal',
             'actor': {'entity_id': 'PERSON-X'}},
            {'action_id': 'A3', 'phase_id': 'P1', 'name': 'Ada records the decision',
             'actor': {'entity_id': 'PERSON-X'}},
        ]
        graph['relations'] = [
            {'from_action_id': 'A1', 'to_action_id': 'A2', 'type': 'precedes'},
            {'from_action_id': 'A2', 'to_action_id': 'A3', 'type': 'precedes'},
        ]
        original = json.loads(json.dumps(graph))
        view = embedded_data(render_graph_html(graph), 'epg-view')
        page = next(p for p in view['pages'] if p['phase'] == 'P1')
        cards = {card['id']: card for card in page['cards']}
        self.assertEqual(cards['PERSON-X']['kind'], 'party')
        self.assertEqual(cards['ORG-X']['entity_type'], 'organization')
        edges = {(e['from'], e['to'], e['type']) for e in page['edges']}
        self.assertIn(('PERSON-X', 'A1', 'actor'), edges)
        self.assertIn(('A1', 'ORG-X', 'object'), edges)
        self.assertEqual(cards['A1']['box'][1], cards['A3']['box'][1])
        self.assertLess(cards['A1']['box'][0], cards['A2']['box'][0])
        self.assertLess(cards['A2']['box'][0], cards['A3']['box'][0])
        self.assertFalse(any(a == 'UNRELATED' or b == 'UNRELATED' for a, b, _ in edges))
        self.assertEqual(cards['A1']['title'], 'Reviews the proposal')
        self.assertEqual(view['details']['A1']['title'], 'Ada reviews the proposal')
        self.assertEqual(graph, original)

    def test_compact_sources_keep_full_passages_and_unknown_order(self):
        graph = sample_graph()
        graph['actions'] = [
            {'action_id': 'A1', 'name': 'First report', 'support': [{'evidence_ids': ['E1', 'E2']}]},
            {'action_id': 'A2', 'name': 'Second report'},
        ]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Primary report', 'published_at': '2024-01-02'}]
        graph['evidence'] = [
            {'evidence_id': 'E1', 'source_id': 'S1', 'quote': 'First exact passage. ' * 30},
            {'evidence_id': 'E2', 'source_id': 'S1', 'quote': 'Second exact passage.'},
        ]
        graph['relations'] = [{'from_action_id': 'A1', 'to_action_id': 'A2', 'type': 'order_unknown'}]
        html = render_graph_html(graph)
        view = embedded_data(html, 'epg-view')
        source = next(c for p in view['pages'] for c in p['cards'] if c['id'] == 'S1')
        self.assertLess(source['box'][3], 100)
        self.assertNotIn('excerpt', source)
        self.assertEqual(source['quotes'], ['E1', 'E2'])
        self.assertEqual(embedded_data(html, 'epg-data')['evidence'], graph['evidence'])
        relation = next(e for p in view['pages'] for e in p['edges'] if e['kind'] == 'relation')
        self.assertEqual(relation['type'], 'order_unknown')

    def test_long_context_and_non_latin_text_stay_available(self):
        graph = sample_graph()
        text = '该参与者尚未同意投资，只有满足条件后才可能参与。' * 12
        graph['contexts'] = [{'context_id': 'C1', 'description': text}]
        view = embedded_data(render_graph_html(graph), 'epg-view')
        card = next(c for p in view['pages'] for c in p['cards'] if c['id'] == 'C1')
        self.assertLess(len(card['title']), len(text))
        self.assertIn('尚未', card['title'])
        self.assertEqual(view['details']['C1']['title'], text)

    def test_preserves_json_and_escapes_script_text(self):
        graph = sample_graph()
        graph['event']['name'] += '</script><script>alert(1)</script>__EPG_LAYOUT_JSON__'
        html = render_graph_html(graph)
        self.assertEqual(embedded_data(html, 'epg-data'), graph)
        self.assertIsNone(embedded_data(html, 'epg-layout'))
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertNotIn('<script src=', html)

    def test_layout_binding_is_independent_of_dictionary_key_order(self):
        graph = sample_graph()
        page = {'title': 'Overview', 'phase': 0, **{
            key: [] for key in ('cards', 'paths', 'labels', 'evidence', 'jumps')
        }}
        layout = {'digest': fingerprint(graph), 'pages': [page]}
        reordered = dict(reversed(list(graph.items())))
        self.assertEqual(embedded_data(render_graph_html(reordered, layout=layout), 'epg-layout'), [page])
        changed = {**graph, 'event': {**graph['event'], 'name': 'Edited'}}
        with self.assertRaisesRegex(ValueError, 'digest does not match'):
            render_graph_html(changed, layout=layout)
        self.assertIsNone(embedded_data(render_graph_html(changed), 'epg-layout'))

    def test_arbitrary_event_ids_use_the_same_generated_layout(self):
        graph = sample_graph()
        graph['phases'] = [{'phase_id': 'P1', 'name': 'First'}]
        graph['actions'] = [{
            'action_id': 'A1', 'phase_id': 'P1', 'name': 'Buy', 'description': 'Full text',
            'delta_context_refs': [{'context_id': 'C1', 'relation_type': 'condition'}],
            'support': [{'evidence_ids': ['E1']}],
        }]
        graph['contexts'] = [{'context_id': 'C1', 'description': 'Condition'}]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Letter'}]
        graph['evidence'] = [{'evidence_id': 'E1', 'source_id': 'S1', 'quote': 'Original words'}]
        original = json.loads(json.dumps(graph))
        first = embedded_data(render_graph_html(graph), 'epg-view')
        graph['event']['event_id'] = 'ANOTHER-EVENT'
        second = embedded_data(render_graph_html(graph), 'epg-view')
        phase = next(page for page in first['pages'] if page['phase'] == 'P1')
        other = next(page for page in second['pages'] if page['phase'] == 'P1')
        self.assertEqual(phase, other)
        self.assertEqual({card['id'] for card in phase['cards']}, {'A1', 'C1', 'S1'})
        self.assertEqual(next(card for card in phase['cards'] if card['id'] == 'S1')['quotes'], ['E1'])
        self.assertEqual([section['title'] for section in phase['sections']],
                         ['Actions and their context', 'Source evidence'])
        self.assertTrue(any(edge['from'] == 'S1' and edge['to'] == 'A1' for edge in phase['edges']))
        self.assertTrue(any(edge['from'] == 'C1' and edge['to'] == 'A1' for edge in phase['edges']))
        graph['event']['event_id'] = original['event']['event_id']
        self.assertEqual(graph, original)

    def test_generated_views_retain_unassigned_data_and_cross_phase_links(self):
        graph = sample_graph()
        graph['phases'] = [{'phase_id': 'P1', 'name': 'First'}, {'phase_id': 'P2', 'name': 'Second'}]
        graph['actions'] = [
            {'action_id': 'A1', 'phase_id': 'P1', 'name': 'First action'},
            {'action_id': 'A2', 'phase_id': 'P2', 'name': 'Second action'},
            {'action_id': 'A3', 'name': 'Unassigned action'},
        ]
        graph['contexts'] = [{'context_id': 'C1', 'description': 'Undated context'}]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Unused source'}]
        graph['relations'] = [{'from_action_id': 'A1', 'to_action_id': 'A2', 'type': 'precedes'}]
        pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
        shown = {card['id'] for page in pages for card in page['cards']}
        self.assertTrue({'A3', 'C1', 'S1'} <= shown)
        page = next(page for page in pages if any(card['id'] == 'A1' for card in page['cards']))
        jump = next(link for link in page['jumps'] if link['id'] == 'A2')
        self.assertEqual(jump['type'], 'precedes')
        self.assertTrue(any(card['id'] == 'A2' for card in pages[jump['page']]['cards']))

    def test_module_exports_offline_html_and_protects_input(self):
        with TemporaryDirectory() as directory:
            graph = Path(directory) / 'graph.json'
            output = Path(directory) / 'graph.html'
            graph.write_text(json.dumps(sample_graph()), encoding='utf-8')
            command = [sys.executable, '-m', 'finmy.person_epg.event.graph_html', str(graph), '-o']
            completed = subprocess.run([*command, str(output)], capture_output=True, text=True, check=True)
            self.assertIn('Wrote ', completed.stdout)
            self.assertEqual(embedded_data(output.read_text(encoding='utf-8'), 'epg-data'), sample_graph())
            rejected = subprocess.run([*command, str(graph)], capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn('output path must differ', rejected.stderr)
            self.assertEqual(json.loads(graph.read_text(encoding='utf-8')), sample_graph())


if __name__ == '__main__':
    unittest.main()
