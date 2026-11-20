"""Run offline Event regression checks without the optional lmbase SDK suite."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == '__main__':
    import pytest
    sdk_tests = {'test_person_event_effort.py', 'test_person_event_json_mode.py'}
    files = [str(p) for p in sorted(Path('tests').glob('test_person_event_*.py')) if p.name not in sdk_tests]
    raise SystemExit(pytest.main(['-q', *files, *sys.argv[1:]]))
