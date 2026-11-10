"""JSON -> HTML contract, complete membership coverage and offline UI routing."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from finmy.person_epg.visualizer import render_person_epg
from test_subject_graph_ui import load

history = load('person_epg_history_test', 'finmy/web_ui/utils/history_loader.py')
detect_build_mode = history.detect_build_mode
load_history_result = history.load_history_result
scan_history_files = history.scan_history_files

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/buffett_person_epg_preview.json'


def package():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


class PageData(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.payload = ''
        self.capture = False
        self.external_scripts = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.capture = attrs.get('id') == 'epg-data'
            if attrs.get('src'):
                self.external_scripts.append(attrs['src'])

    def handle_endtag(self, tag):
        if tag == 'script':
            self.capture = False

    def handle_data(self, text):
        if self.capture:
            self.payload += text


class PersonEPGVisualizerTest(unittest.TestCase):
    def test_cli_renders_complete_json_losslessly_without_network_assets(self):
        data = package()
        snapshot = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'nested' / 'timeline.html'
            command = subprocess.run([
                sys.executable, '-m', 'finmy.person_epg', 'render',
                str(FIXTURE), '--output', str(output),
            ], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(command.returncode, 0, command.stderr)
            page = output.read_text(encoding='utf-8')
        parsed = PageData(page)
        self.assertEqual(json.loads(parsed.payload), data)
        self.assertEqual(parsed.external_scripts, [])
        self.assertIn('plotly.js', page)
        self.assertEqual(len(data['event_activity']), 45)
        self.assertEqual(data, snapshot)

    def test_invalid_reference_is_rejected_before_writing(self):
        data = package()
        data['event_activity'][0]['activity_id'] = 'missing'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'bad.html'
            with self.assertRaisesRegex(ValueError, 'Foreign key'):
                render_person_epg(data, output)
            self.assertFalse(output.exists())

    def test_unorganized_conversion_does_not_silently_export_an_empty_chart(self):
        data = package()
        data['event_activity'] = []
        data['event_activity_detail'] = []
        with self.assertRaisesRegex(ValueError, 'Store domain/event organization'):
            render_person_epg(data)

    def test_script_and_template_text_roundtrip_safely(self):
        data = package()
        hostile = '</script><script>alert(1)</script>@@SCRIPT@@'
        data['graph']['title'] = hostile
        before = copy.deepcopy(data)
        page = render_person_epg(data)
        self.assertNotIn(hostile, page)
        self.assertEqual(json.loads(PageData(page).payload), before)
        self.assertEqual(data, before)

    def test_history_detects_named_examples_and_person_epg_directories(self):
        data = package()
        self.assertEqual(detect_build_mode(data), 'person_epg')
        self.assertEqual(load_history_result(str(FIXTURE)), data)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'build_output_example'
            folder.mkdir()
            (folder / 'FinalPersonEPG.json').write_text(json.dumps(data))
            (folder / 'FinalEventCascade.json').write_text('{}')
            self.assertEqual(load_history_result(str(folder)), data)
            self.assertEqual(len(scan_history_files(directory)), 1)
            data['event_activity'][0]['activity_id'] = 'missing'
            (folder / 'FinalPersonEPG.json').write_text(json.dumps(data))
            self.assertIsNone(load_history_result(str(folder)))


@unittest.skipUnless(shutil.which('node'), 'Node.js is optional, used only for renderer runtime tests')
class PersonEPGScriptTest(unittest.TestCase):
    def run_script(self, data):
        # Consume the payload actually exported to HTML, not a separate JS fixture.
        exported = json.loads(PageData(render_person_epg(data)).payload)
        result = subprocess.run([
            'node', str(ROOT / 'tests/person_epg_render_check.cjs')
        ], input=json.dumps({'data': exported, 'script': str(ROOT / 'finmy/person_epg/assets/timeline.js')}),
            text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_complete_memberships_details_hover_and_approximate_marks(self):
        data = package()
        result = self.run_script(data)
        traces = [t for t in result['data'] if t.get('meta', {}).get('kind') == 'activity']
        self.assertEqual(len(traces), 45)
        self.assertEqual({t['meta']['activity_id'] for t in traces},
                         {m['activity_id'] for m in data['event_activity']})
        self.assertEqual(sum(t['meta']['event_id'] == 'thread:oxy' for t in traces), 16)
        self.assertEqual(len(result['annotations']), len(data['domain']) + len(data['event']))
        for member in data['event_activity']:
            trace = next(t for t in traces if t['meta']['event_id'] == member['event_id']
                         and t['meta']['activity_id'] == member['activity_id'])
            selected = {d['detail_index'] for d in data['event_activity_detail']
                        if d['event_id'] == member['event_id'] and d['activity_id'] == member['activity_id']}
            for detail in data['activity_detail']:
                if detail['activity_id'] == member['activity_id'] and (
                    member['detail_mode'] == 'all' or detail['detail_index'] in selected
                ):
                    from html import escape
                    self.assertIn(escape(detail['value'], quote=True).replace('&#x27;', '&#39;'), result['hoverCards'][result['data'].index(trace)]['html'])
        uncertain = [s for s in result['shapes'] if s.get('type') == 'rect' and s.get('line', {}).get('dash') == 'dash']
        self.assertTrue(uncertain)
        self.assertTrue(all(s['fillcolor'] == 'rgba(0,0,0,0)' for s in uncertain))
        self.assertTrue(any(t.get('marker', {}).get('pattern', {}).get('shape') == '/' for t in result['data']))

    def test_hover_omits_evidence_wraps_and_preserves_full_formatted_text(self):
        from html import unescape
        import re
        data = package()
        for span in data['evidence_span']:
            if span['document_id'] is None:
                span['quote'] = 'HIDDEN_EVIDENCE_SENTINEL'
        for event, text in zip(data['event'], [
            'Long overview & context ' * 80, '中文没有空格' * 300, 'x' * 2000
        ]):
            event['summary'] = text
        result = self.run_script(data)
        previews = [h for t in result['data'] for h in t.get('hovertext', [])]
        self.assertTrue(any(len(h.split('<br>')) > 20 for h in previews))
        self.assertTrue(any('<b>' in h for h in previews))
        for trace, card in zip(result['data'], result['hoverCards']):
            if not card:
                continue
            # Ignore layout whitespace, but require every character of every
            # non-evidence field, including the final relationship, to survive.
            plain = lambda h: re.sub(r'\s+', '', unescape(re.sub(r'<[^>]*>', '', h)))
            for hover in trace.get('hovertext', []):
                self.assertEqual(plain(hover), plain(card['html']))
                for bold in re.findall(r'<b>(.*?)</b>', card['html']):
                    self.assertIn(plain(bold), [plain(x) for x in
                        re.findall(r'<b>(.*?)</b>', hover)])
        for preview in previews:
            self.assertNotIn('HIDDEN_EVIDENCE_SENTINEL', preview)
            self.assertNotIn('Evidence (', preview)
            lines = preview.split('<br>')
            self.assertNotIn('preview shortened', preview)
            for line in lines:
                self.assertLessEqual(sum(2 if ord(c) > 255 else 1
                                         for c in unescape(re.sub(r'<[^>]*>', '', line))), 68)

    def test_subject_years_and_unknown_time_are_not_hardcoded(self):
        data = package()
        focal = next(e for e in data['entity'] if e['entity_id'] == data['graph']['subject_entity_id'])
        focal['name'] = 'Example Person'
        data['graph'].update(title='Other history', coverage_start='2010', coverage_end='2030')
        result = self.run_script(data)
        self.assertEqual(result['title'], 'Example Person · Other history')
        self.assertGreater(int(result['scale']['max']), 7000)
        data['graph'].update(coverage_start=None, coverage_end=None)
        data['time_value'] = [{'time_id': t['time_id'], 'value': 'unknown'} for t in data['time_value']]
        result = self.run_script(data)
        self.assertFalse(result['xaxis']['visible'])
        self.assertTrue(result['scale']['disabled'])
        self.assertTrue(all(t['xaxis'] == 'x2' for t in result['data'] if t.get('meta', {}).get('kind') == 'activity'))


if __name__ == '__main__':
    unittest.main()
