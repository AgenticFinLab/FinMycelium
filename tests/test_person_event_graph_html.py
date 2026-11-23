"""Test the standalone exporter without Streamlit, a model, or a browser."""
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from finmy.person_epg.event.graph_html import render_graph_html
from finmy.person_epg.event.records import fingerprint
from finmy.person_epg.event.schema import GRAPH_VERSION


def sample_graph():
    return {
        'schema_version': GRAPH_VERSION,
        'event': {'event_id': 'TEST-E1', 'name': '示例'},
        'person': {'name': 'Test Person'},
        **{name: [] for name in (
            'stages', 'phases', 'actions', 'contexts', 'entities', 'sources', 'evidence', 'relations'
        )},
    }


def embedded_data(html, script_id):
    match = re.search(rf'<script id="{script_id}" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(match[1])


def record_sequence(graph, pairs):
    """Give each test precedence claim its own located, asserted passage."""
    graph['sources'].append(dict(source_id='sequence', title='Minutes'))
    for i, (a, b) in enumerate(pairs):
        quote = f'{a} preceded {b}.'
        eid = f'sequence-{i}'
        graph['evidence'].append(dict(evidence_id=eid, source_id='sequence', quote=quote,
                                      location_status='matched', start=0, end=len(quote)))
        graph['relations'].append(dict(relation_id=f'order-{i}', type='precedes', basis='asserted',
                                       from_action_id=a, to_action_id=b,
                                       support=[dict(target='', mode='A', evidence_ids=[eid])]))


def context_graph():
    graph = sample_graph()
    def ref(cid, kind, **fields):
        return dict(context_id=cid, relation_type=kind, **fields)
    graph.update(
        entities=[dict(entity_id='pat', name='Pat'), dict(entity_id='org', name='Foundation')],
        phases=[dict(phase_id='P1', name='Appointment', time=dict(start='2020-01-01', end='2020-12-31'),
                     baseline_context_refs=[ref('roles', 'participation', entity_id='org', role='Host',
                                                context_ref_id='shared')]),
                dict(phase_id='P2', name='Follow-up')],
        actions=[dict(action_id='A1', name='Accept', phase_id='P1', actor=dict(entity_id='pat'),
                      delta_context_refs=[ref('roles', 'participation', entity_id='org', role='Adviser'),
                                          ref('roles', 'participation', entity_id='org', role='Sponsor',
                                              qualification='Only for the appointment.'),
                                          ref('briefing', 'knowledge-source', entity_id='pat'),
                                          ref('terms', 'result'),
                                          ref('roles', 'participation')],
                      baseline_context_exclusions=[dict(context_ref_id='shared', reason='Acting independently.')]),
                 dict(action_id='A2', name='Sign', phase_id='P1', delta_context_refs=[ref('terms', 'condition')]),
                 dict(action_id='A3', name='Report', phase_id='P2', actor=dict(entity_id='pat'),
                      delta_context_refs=[ref('briefing', 'condition')])],
        contexts=[dict(context_id='roles', category='relations', perspective='world', description='Foundation roles'),
                  dict(context_id='briefing', category='person_state', perspective='belief', description='Briefing'),
                  dict(context_id='terms', category='environment', perspective='world', description='Terms'),
                  dict(context_id='report', category='environment', perspective='post_hoc', description='Later report',
                       time=dict(start='2020-07-01', end='2020-07-01'))])
    return graph


class PersonEventGraphHtmlTests(unittest.TestCase):

    def test_context_of_an_unassigned_action_stays_with_its_owner(self):
        graph = context_graph()
        graph['actions'].append(dict(action_id='outside', name='Unassigned action', phase_id=None,
                                     delta_context_refs=[dict(context_id='report', relation_type='trigger')]))
        for time in [dict(start='2020-07-01', end='2020-07-01'), dict(text='In 2020')]:
            with self.subTest(time=time):
                graph['contexts'][-1]['time'] = time
                pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
                self.assertEqual([p['phase'] for p in pages if any(c['id'] == 'report' for c in p['cards'])], [None])
                self.assertTrue(any(e['from'] == 'report' and e['to'] == 'outside' for e in pages[0]['edges']))

    def test_context_placement_and_edges_follow_scoped_references(self):
        graph = context_graph()
        html = render_graph_html(graph)
        self.assertEqual(embedded_data(html, 'epg-data'), graph)
        _, first, second = embedded_data(html, 'epg-view')['pages']
        roles = [(e['from'], e['to'], e['record']['role']) for e in first['edges'] if e['type'] == 'participation']
        self.assertCountEqual(roles, [('org', 'P1', 'Host'), ('org', 'A1', 'Adviser'), ('org', 'A1', 'Sponsor')])
        edges = [(e['from'], e['to'], e['type']) for e in first['edges'] if e['kind'] == 'context']
        self.assertIn(('briefing', 'pat', 'knowledge-source'), edges)
        self.assertIn(('A1', 'terms', 'result'), edges)
        self.assertIn(('terms', 'A2', 'condition'), edges)
        self.assertFalse(any(e['type'] == 'knowledge-source' for e in second['edges']))
        self.assertEqual(sum(c['id'] == 'terms' for c in first['cards']), 1)
        band = next(s['box'] for s in first['sections'] if s['title'] == 'Additional context')
        self.assertEqual([c['id'] for c in first['cards'] if band[1] <= c['box'][1] < band[1] + band[3]], ['report'])
        self.assertFalse(any(s['title'] == 'Additional context' for s in second['sections']))

    def test_one_action_inherits_a_condition_and_keeps_phase_only_endpoints(self):
        graph = context_graph()
        phase = graph['phases'][1]
        base = dict(context_id='briefing', relation_type='condition', context_ref_id='base')
        phase['baseline_context_refs'] = [base]
        page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][2]
        cards = {c['id']: c for c in page['cards']}
        self.assertTrue(cards['briefing']['phase_inline'])
        self.assertLess(cards['briefing']['box'][1], cards['A3']['box'][1])
        self.assertNotIn('Shared phase context', [s['title'] for s in page['sections']])
        wire, = [e for e in page['edges'] if e['kind'] == 'context']
        self.assertEqual((wire['from'], wire['to'], wire['owner'], wire['ref_path'], wire['direct_paths']),
                         ('briefing', 'A3', 'P2', '/baseline_context_refs/0', ['/delta_context_refs/0']))

        phase['baseline_context_refs'].extend(
            dict(context_ref_id=kind, relation_type=kind, context_id='roles', **extra)
            for kind, extra in [('trigger', {}), ('result', {}), ('participation', {'entity_id': 'org'}),
                                ('knowledge-source', {'entity_id': 'pat'})])
        graph['actions'][-1]['delta_context_refs'][0]['qualification'] = 'Only after receipt.'
        page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][2]
        wires = [e for e in page['edges'] if e['kind'] == 'context']
        self.assertCountEqual([(e['from'], e['type'], e['to']) for e in wires], [
            ('briefing', 'condition', 'A3'), ('briefing', 'condition', 'A3'),
            ('roles', 'trigger', 'P2'), ('P2', 'result', 'roles'), ('org', 'participation', 'P2'),
            ('roles', 'knowledge-source', 'pat')])
        self.assertEqual([e['owner'] for e in wires if e['type'] == 'condition'], ['P2', 'A3'])

    def test_empty_phase_preserves_the_original_context_endpoint(self):
        graph = context_graph()
        graph['actions'].pop()
        graph['phases'][1]['baseline_context_refs'] = [
            dict(context_id='briefing', relation_type='condition', context_ref_id='base')]
        page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][2]
        wires = [(e['from'], e['to']) for e in page['edges'] if e['kind'] == 'context']
        self.assertEqual(wires, [('briefing', 'P2')])
        self.assertFalse(any(c.get('phase_inline') for c in page['cards']))

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
        graph['sources'] = [{'source_id': 'S1', 'title': 'Shared source'}]
        graph['evidence'] = [{'evidence_id': 'E1', 'source_id': 'S1', 'quote': 'Exact evidence'}]
        record_sequence(graph, [(f'A{i}', f'A{i+1}') for i in range(11)] + [('A11', 'NEXT')])
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
        record_sequence(graph, [('A1', 'A2'), ('A2', 'A3')])
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
        self.assertEqual({card['id'] for card in phase['cards']}, {'A1', 'C1', 'E1', 'S1'})
        self.assertEqual(next(card for card in phase['cards'] if card['id'] == 'S1')['quotes'], ['E1'])
        self.assertEqual([section['title'] for section in phase['sections']],
                         ['Actions and their context', 'Evidence', 'Sources'])
        provenance = {(edge['from'], edge['to'], edge['type']) for edge in phase['edges'] if edge['kind'] == 'evidence'}
        self.assertEqual(provenance, {('S1', 'E1', 'contains'), ('E1', 'A1', 'supports')})
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
        for action in graph['actions'][:2]:
            action['delta_context_refs'] = [{'context_id': 'C1', 'relation_type': 'condition'}]
        graph['contexts'] = [{'context_id': 'C1', 'description': 'Undated context'}]
        graph['sources'] = [{'source_id': 'S1', 'title': 'Unused source'}]
        graph['relations'] = [
            {'from_action_id': 'A1', 'to_action_id': 'A2', 'type': 'precedes'},
            {'from_action_id': 'A1', 'to_action_id': 'A3', 'type': 'continues'},
        ]
        pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
        shown = {card['id'] for page in pages for card in page['cards']}
        self.assertTrue({'A3', 'C1', 'S1'} <= shown)
        page = next(page for page in pages if any(card['id'] == 'A1' for card in page['cards']))
        jump = next(link for link in page['jumps'] if link['id'] == 'A2')
        self.assertEqual(jump['type'], 'precedes')
        reverse = next(link for link in pages[jump['page']]['jumps'] if link['id'] == 'A1')
        self.assertEqual(reverse['relation_id'], jump['relation_id'])
        self.assertEqual((reverse['from'], reverse['to']), (jump['from'], jump['to']))
        self.assertTrue(any(card['id'] == 'A2' for card in pages[jump['page']]['cards']))
        self.assertEqual([p['jumps'] for p in pages], [[], [jump], [reverse]])
        for item, aid in ((page, 'A1'), (pages[jump['page']], 'A2')):
            self.assertTrue(any(e['from'] == 'C1' and e['to'] == aid and e['type'] == 'condition'
                                for e in item['edges']))

    def test_field_support_and_documented_participation_stay_separate(self):
        graph = sample_graph()
        graph.update(
            entities=[dict(entity_id='p', name='Lee', type='person'),
                      dict(entity_id='org', name='Association', type='organization')],
            phases=[dict(phase_id='phase', name='Public statement')],
            actions=[dict(action_id='a', phase_id='phase', name='Statement',
                          actor=dict(entity_id='p', role='Chair', on_behalf_of='org'),
                          support=[dict(target='/actor/role', mode='O', evidence_ids=['e1']),
                                   dict(target='/description', mode='A', evidence_ids=['e1', 'e2', 'e3'])],
                          delta_context_refs=[dict(context_id='c', relation_type='participation',
                                                   entity_id='org', role='Party to agreement',
                                                   support=[dict(target='/context_id', mode='A', evidence_ids=['e3'])])])],
            contexts=[dict(context_id='c', description='The organization was named in an agreement.')],
            sources=[dict(source_id='s1', title='Interview'), dict(source_id='s2', title='Filing')],
            evidence=[dict(evidence_id='e1', source_id='s1', quote='Lee, chair of the association'),
                      dict(evidence_id='e2', source_id='s1', quote='Lee made the statement'),
                      dict(evidence_id='e3', source_id='s2', quote='The association signed the agreement')])
        view = embedded_data(render_graph_html(graph), 'epg-view')
        self.assertEqual(view['fields']['a']['/actor/role']['support'], ['/support/0'])
        self.assertEqual(view['fields']['a']['/delta_context_refs/0/context_id']['support'],
                         ['/delta_context_refs/0/support/0'])
        person, = view['party_uses']['p']
        self.assertEqual(person['fields'], ['/actor/role'])
        participation = next(u for u in view['party_uses']['org'] if u['label'] == 'Participation')
        self.assertEqual(participation['fields'], ['/delta_context_refs/0/context_id'])
        phase = next(p for p in view['pages'] if p['phase'] == 'phase')
        links = {(e['from'], e['to']) for e in phase['edges'] if e['kind'] == 'evidence'}
        self.assertTrue({('s1', 'e1'), ('s1', 'e2'), ('s2', 'e3'), ('e1', 'p'), ('e3', 'a')} <= links)
        self.assertNotIn(('e3', 'org'), links)
        self.assertNotIn(('e2', 'p'), links)

    def test_handoff_metadata_stays_in_the_archive_and_out_of_passage_cards(self):
        from finmy.person_epg.event.records import sha256

        fixtures = Path(__file__).parent / 'fixtures' / 'person_event'
        graph = json.loads((fixtures / 'graph.json').read_text())
        payload = json.loads((fixtures / 'input.json').read_text())
        sample = payload['samples'][0]
        sid = sample['raw_data_id']
        source = payload['user_query']['extras']['source_registry'][sid]
        line = 'Publication date (source/provider metadata): 2020-02-07'
        body = 'She addressed the question.'
        text = sample['content'] = f"[source={sid} version=v1 status=partial]\nhttps://example.org/story\n{source['title']}\n{line}\n{body}"
        def quoted(eid, quote):
            start = text.index(quote)
            return dict(evidence_id=eid, source_id=sid, sample_id=sample['sample_id'], quote=quote,
                        start=start, end=start + len(quote), sample_sha256=sha256(text.encode()), location_status='matched')
        graph['evidence'] = [quoted('header', line), quoted('body', body)]
        graph['actions'][0]['support'] = [dict(target='/description', mode='A', evidence_ids=['header', 'body'])]
        html = render_graph_html(graph, payload=payload)
        self.assertEqual(embedded_data(html, 'epg-data'), graph)
        view = embedded_data(html, 'epg-view')
        self.assertTrue(view['checked_input'])
        self.assertEqual(view['passage_issues'], {'header': 'handoff'})
        self.assertEqual({c['id'] for p in view['pages'] for c in p['cards'] if c['kind'] == 'evidence'}, {'body'})
        graph['event']['event_id'] = 'another-event'
        with self.assertRaisesRegex(ValueError, 'different person event'):
            render_graph_html(graph, payload=payload)

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
