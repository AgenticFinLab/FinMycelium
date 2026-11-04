"""Natural time ranges survive validation, projection, review and Gantt export."""
import copy
import json
import unittest

from test_subject_graph_visualizer import fixture, vf
from finmy.subject_graph.validation import date_interval, validate_subject_graph
from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.time_display import time_label
from finmy.subject_graph.visualizer import render_subject_graph
from finmy.subject_graph.consistency_review import apply_event_corrections
from finmy.subject_graph.prompts import EVENT, EVENT_REVIEW, REPAIR, system_prompt


def window(start='2022-07-21', end='2022-07-31', original='2022年7月下旬', approximate=True):
    field = vf('2022-07', '2022年7月下旬，公司购入股份。')
    field['time_window'] = dict(start=start, end=end, original=original, approximate=approximate)
    return field


def graph_fixture():
    graph = fixture()
    graph['events'] = graph['events'][:1]
    graph['relations'] = []
    event = graph['events'][0]
    event['start_time'] = event['end_time'] = vf('2022-07')
    event['participations'][0]['start_time'] = event['participations'][0]['end_time'] = vf('2022-07')
    event['actions'][0]['timestamp'] = window()
    event['transactions'][0]['timestamp'] = window()
    return graph


def plot_payload(page):
    decoder = json.JSONDecoder()
    text = page.split('Plotly.newPlot(', 1)[1].lstrip()
    _, end = decoder.raw_decode(text)
    text = text[end:].lstrip(' ,')
    data, end = decoder.raw_decode(text)
    layout, _ = decoder.raw_decode(text[end:].lstrip(' ,'))
    return data, layout


class TimeWindowTests(unittest.TestCase):
    def test_examples_preserve_bounds_and_wording(self):
        examples = [
            ('2022-07-21', '2022-07-31', '2022年7月下旬', True),
            ('2024-02-21', '2024-02-29', '2024年2月下旬', True),
            ('2026-10-14', '2026-11-13', '今年俄历十月', True),
            ('2023-07-01', '2023-07-31', '民国112年7月', True),
            ('2023-04-09', '2023-04-09', '2023年复活节', False),
        ]
        for start, end, original, approximate in examples:
            with self.subTest(original=original):
                field = window(start, end, original, approximate)
                bounds = date_interval(field)
                self.assertEqual(bounds[0].date().isoformat(), start)
                self.assertEqual(bounds[1].date().isoformat(), end)
                self.assertEqual(time_label(field), original + ('（约）' if approximate else ''))

    def test_unknown_scalar_does_not_hide_available_window(self):
        graph = graph_fixture()
        graph['events'][0]['actions'][0]['timestamp']['value'] = 'unknown'
        self.assertTrue(validate_subject_graph(graph)['valid'])
        cascade = to_event_cascade(graph)
        action = cascade['stages'][0]['episodes'][1]
        self.assertEqual(action['start_time']['value'], '2022-07-21')
        self.assertEqual(action['end_time']['value'], '2022-07-31')

    def test_invalid_inverted_and_outside_ranges_are_rejected(self):
        for start, end in [('2022-07-40', '2022-07-31'), ('2022-07-31', '2022-07-21'),
                           ('2023-07-21', '2023-07-31')]:
            graph = graph_fixture()
            graph['events'][0]['actions'][0]['timestamp'] = window(start, end)
            self.assertFalse(validate_subject_graph(graph)['valid'])

    def test_approximate_flag_requires_boolean(self):
        graph = graph_fixture()
        graph['events'][0]['actions'][0]['timestamp']['time_window']['approximate'] = 'true'
        self.assertFalse(validate_subject_graph(graph)['valid'])

    def test_window_does_not_bypass_source_requirement(self):
        graph = graph_fixture()
        field = graph['events'][0]['actions'][0]['timestamp']
        field.update(value='unknown', evidence_source_contents=[])
        report = validate_subject_graph(graph, ['2022年7月下旬，公司购入股份。'])
        self.assertTrue(any(e['path'].endswith('/actions/0/timestamp') for e in report['errors']))

    def test_native_graph_preserved_and_event_bounds_projected(self):
        graph = graph_fixture()
        graph['events'][0]['start_time'] = graph['events'][0]['end_time'] = window()
        original = copy.deepcopy(graph)
        stage = to_event_cascade(graph)['stages'][0]
        self.assertEqual(graph, original)
        self.assertEqual(stage['start_time']['value'], '2022-07-21')
        self.assertEqual(stage['end_time']['value'], '2022-07-31')
        self.assertEqual(stage['episodes'][1]['end_time']['value'], '2022-07-31')

    def test_html_keeps_original_wording_in_hover_only_and_preserves_range(self):
        page = render_subject_graph(graph_fixture())
        data, layout = plot_payload(page)
        annotations = [a['text'] for a in layout['annotations']]
        visible = '\n'.join(annotations + [str(t.get('text', '')) for t in data])
        self.assertNotIn('2022年7月下旬', visible)
        self.assertNotIn('（约）', visible)
        hover = '\n'.join(str(t.get('hovertext', '')) for t in data)
        self.assertIn('2022年7月下旬（约）', hover)
        self.assertIn('发生于该范围内，具体日期不详。', hover)
        self.assertIn('2022-07-21 — 2022-07-31', hover)
        activities = next(t for t in data if t.get('name') == 'Activities (S1)')
        self.assertEqual(activities['base'][0], '2022-07-21T00:00:00')
        self.assertEqual(activities['x'][0], 10 * 86400000)

    def test_review_can_replace_unknown_with_evidenced_window(self):
        graph = graph_fixture()
        graph['events'][0]['actions'][0]['timestamp'] = vf('unknown')
        # These fixtures test date routing; all existing facts use this provided excerpt.
        quote = '2022年7月下旬，公司购入股份。'
        def cite(value):
            if isinstance(value, dict):
                if 'value' in value: value['evidence_source_contents'] = [quote]
                else:
                    for child in value.values(): cite(child)
            elif isinstance(value, list):
                for child in value: cite(child)
        cite(graph)
        sources = [{'source_id': 's1', 'content': quote}]
        corrected, report = apply_event_corrections(graph, 'E2', [{'reason': 'Retain the supported late-month window',
            'patches': [{'op': 'replace', 'path': '/event/actions/A2/timestamp', 'value': window()}]}],
            {'E2': sources}, sources)
        self.assertTrue(report['accepted'], report)
        self.assertEqual(corrected['events'][0]['actions'][0]['timestamp'], window())

    def test_all_subject_passes_use_same_window_policy(self):
        for task in (EVENT, EVENT_REVIEW, REPAIR):
            prompt = system_prompt(task)
            self.assertIn('overrides the shared single-timestamp fallback', prompt)
            self.assertIn('"time_window"', prompt)
            self.assertNotIn('correct the single action timestamp to unknown', prompt)


if __name__ == '__main__':
    unittest.main()
