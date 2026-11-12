"""Offline checks for the shared research skill's source-index export."""
import csv
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'skills/plan-person-research/scripts/export_sources.py'
module = runpy.run_path(str(SCRIPT))
export_sources = module['export_sources']

HEADER = '''## 6. Source index

| Source ID | Original title and link | Publisher and publication date | Actual reading and locator | Supported judgment |
| --- | --- | --- | --- | --- |
'''
ROW = '| SRC-01 | [Company report](https://example.org/report) | Company; date unknown | Body read, p. 2 | Establishes the announcement only. |\n'


def plan(tmp_path, rows=ROW):
    path = tmp_path / 'research-plan.md'
    path.write_text('# Person\n\n' + HEADER + rows + '\n## 7. Handoff after confirmation\n', encoding='utf-8')
    return path


def test_preserves_text_ids_urls_and_reading_limits(tmp_path):
    path = plan(tmp_path, (
        '| SRC-01 | [公告 \\| "Terms" \\[draft\\]](<https://example.org/report_(2020)?a=1&b=2>) | Issuer A; reporter B; date unknown | Excerpt only, body blocked | A quotation, not an independent confirmation. |\n'
        '| SRC-08 | [Later report](https://example.org/report_(later)) | Issuer; undated | PDF pp. 2–3, not the full report | Context \\| attributed statement |\n'
    ))
    original = path.read_bytes()
    assert export_sources(path) == 2
    with path.with_name('sources.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0] == dict(source_id='SRC-01', title='公告 | "Terms" [draft]',
                          url='https://example.org/report_(2020)?a=1&b=2',
                          publication_info='Issuer A; reporter B; date unknown',
                          reading_note='Excerpt only, body blocked',
                          support_note='A quotation, not an independent confirmation.')
    assert rows[1]['source_id'] == 'SRC-08'  # Source IDs are not renumbered.
    assert rows[1]['url'] == 'https://example.org/report_(later)'
    assert rows[1]['support_note'] == 'Context | attributed statement'
    assert path.read_bytes() == original


def test_regeneration_removes_stale_rows_and_check_never_writes(tmp_path):
    path = plan(tmp_path, ROW + ROW.replace('SRC-01', 'SRC-02'))
    export_sources(path)
    output = path.with_name('sources.csv')
    before = output.read_bytes()
    assert export_sources(path, check=True) == 2
    plan(tmp_path)
    with pytest.raises(ValueError, match='stale'):
        export_sources(path, check=True)
    assert output.read_bytes() == before
    assert export_sources(path) == 1
    regenerated = output.read_bytes()
    export_sources(path)
    assert output.read_bytes() == regenerated
    assert b'SRC-02' not in regenerated


@pytest.mark.parametrize('bad_rows', [
    ROW + ROW,
    ROW.replace('https://example.org/report', 'file:///etc/passwd'),
    ROW.replace('[Company report](https://example.org/report)', 'Company report'),
    ROW.replace('Establishes the announcement only.', 'Unescaped | delimiter'),
])
def test_invalid_input_preserves_previous_export(tmp_path, bad_rows):
    path = plan(tmp_path)
    export_sources(path)
    output = path.with_name('sources.csv')
    original = output.read_bytes()
    plan(tmp_path, bad_rows)
    with pytest.raises(ValueError):
        export_sources(path)
    assert output.read_bytes() == original
    assert not list(tmp_path.glob('.sources-*'))


@pytest.mark.parametrize('body', ['# No source index\n', HEADER + ROW + '\n' + HEADER + ROW])
def test_missing_or_duplicate_index_does_not_generate_a_file(tmp_path, body):
    path = tmp_path / 'research-plan.md'
    path.write_text(body)
    with pytest.raises(ValueError, match='exactly one'):
        export_sources(path)
    assert not path.with_name('sources.csv').exists()


def test_only_source_index_rows_are_exported_and_cli_checks(tmp_path):
    path = plan(tmp_path)
    path.write_text('| SRC-99 | unrelated table | x | y | z |\n' + path.read_text() + ROW.replace('SRC-01', 'SRC-77'))
    result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    checked = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path), '--check'], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    with path.with_name('sources.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    assert [r['source_id'] for r in rows] == ['SRC-01']
