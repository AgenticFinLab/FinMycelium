"""Shared-policy integration and lossless offline repair of dated Person facts."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from finmy.subject_graph.temporal_policy import (
    normalize_time_field, TEMPORAL_NORMALIZATION_POLICY, SUBJECT_TEMPORAL_POLICY,
)
from finmy.person_epg.time_normalization import normalize_person_times
from finmy.person_epg.validation import validate_person_epg

ROOT = Path(__file__).resolve().parents[1]


class TimeNormalizationTest(unittest.TestCase):
    def test_periods_and_ranges_keep_precision_and_original(self):
        cases = {
            '2024-Q1': ('2024-01-01', '2024-03-31'),
            '2023-H2': ('2023-07-01', '2023-12-31'),
            '2022-03-14 to 2022-03-16': ('2022-03-14', '2022-03-16'),
            '2024-02 to 2024-03': ('2024-02-01', '2024-03-31'),
        }
        for raw, bounds in cases.items():
            with self.subTest(raw=raw):
                field = {'value': raw, 'evidence_source_contents': ['Original quote']}
                saved = copy.deepcopy(field)
                out = normalize_time_field(field)
                self.assertEqual(field, saved)
                self.assertEqual((out['time_window']['start'], out['time_window']['end']), bounds)
                self.assertEqual(out['time_window']['original'], raw)
                self.assertTrue(out['time_window']['approximate'])
                self.assertEqual(out, normalize_time_field(out))
        for raw in ('2023', '2024-02', '2024-02-29', 'unknown'):
            self.assertEqual(normalize_time_field({'value': raw}), {'value': raw})
        self.assertEqual(normalize_time_field({'value': '2024-02-29 12:30'})['value'], '2024-02-29T12:30')

    def test_ambiguous_calendar_or_fiscal_context_never_guesses(self):
        for raw, quote in [('2023-Q1', 'first fiscal quarter'),
                           ('农历正月初一', '年份未记载'), ('Orthodox Easter', 'year unspecified'),
                           ('2024-02-30', 'invalid date')]:
            out = normalize_time_field({'value': raw, 'evidence_source_contents': [quote]})
            self.assertEqual(out['value'], 'unknown')
            self.assertEqual(out['time_normalization']['status'], 'unresolved')
            self.assertEqual(out['time_normalization']['original'], raw)
            self.assertEqual(out['evidence_source_contents'], [quote])
        # A model-supported conversion keeps its own window and exactness.
        window = {'start': '2024-02-10', 'end': '2024-02-10',
                  'original': 'source calendar expression', 'approximate': False}
        out = normalize_time_field({'value': 'source calendar expression', 'time_window': window})
        self.assertEqual(out['time_window'], window)
        self.assertEqual(out['value'], '2024-02-10')

    def test_both_model_phases_use_the_single_policy_and_validate_time_fields(self):
        from sparse_test_dependencies import install_missing_lmbase_containers
        install_missing_lmbase_containers()
        from finmy.builder.sparse_build.person_fact_pipeline import EXTRACTION_SYSTEM, RECONCILE_SYSTEM, _field
        for prompt in (EXTRACTION_SYSTEM, RECONCILE_SYSTEM):
            self.assertIn(TEMPORAL_NORMALIZATION_POLICY, prompt)
            self.assertIn(SUBJECT_TEMPORAL_POLICY, prompt)
        out = _field({'value': '2023-Q1', 'citations': [{'document_id': 'D', 'quote': 'Q1 2023'}]},
                     {'D': {'content': 'Q1 2023'}}, allow_unknown=True)
        self.assertEqual(out['time_window']['end'], '2023-03-31')
        self.assertEqual(out['_citations'][0]['quote'], 'Q1 2023')

    def test_offline_cli_preserves_graph_and_evidence_and_reports_unresolved(self):
        data = json.loads((ROOT / 'tests/fixtures/buffett_person_epg_preview.json').read_text())
        for i, value in enumerate(['2023-Q1', '2023-H1', 'calendar not identified']):
            data['time_value'][i] = {'time_id': data['time_value'][i]['time_id'], 'value': value}
        before = copy.deepcopy(data)
        repaired, audit = normalize_person_times(data)
        self.assertEqual(data, before)
        for key in data:
            if key not in {'time_value', 'evidence_set'}:
                self.assertEqual(repaired[key], data[key])
        self.assertEqual(audit['counts']['unresolved'], 1)
        self.assertTrue(validate_person_epg(repaired, require_normalized_times=True)['valid'])
        self.assertEqual(normalize_person_times(repaired)[0], repaired)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            output = Path(directory) / 'page.html'
            source.write_text(json.dumps(data))
            old_bytes = source.read_bytes()
            run = subprocess.run([sys.executable, '-m', 'finmy.person_epg', 'render', str(source),
                                  '--normalize-times', '--output', str(output)], cwd=ROOT,
                                 text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(source.read_bytes(), old_bytes)
            self.assertEqual(json.loads(output.with_suffix('.normalized.json').read_text()), repaired)
            self.assertTrue(output.with_suffix('.time_normalization.json').exists())
            self.assertIn('plotly.js', output.read_text())
