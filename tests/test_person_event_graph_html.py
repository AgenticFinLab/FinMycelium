"""Test the standalone exporter without Streamlit, a model, or a browser."""
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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


class PersonEventGraphHtmlTests(unittest.TestCase):

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
        with patch('finmy.person_epg.event.graph_html._bundled_layout', return_value=layout):
            self.assertIsNone(embedded_data(render_graph_html(changed), 'epg-layout'))

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
