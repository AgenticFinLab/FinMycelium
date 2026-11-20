"""Offline regression against an unchanged, extracted PBUILD-dee74d7e4a1d run.

Set PERSON_EVENT_REAL_RUN_DIR to the directory containing input.json and
attempts/0004/{epg,facts}.json. No test writes to that directory.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

import pytest

from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.validation import check_graph


ORIGINAL_INPUT_SHA256 = 'ef910ea7c1905fa0e2d9f2774e5b6dd66832ea54273597fee04b80138ba5771f'


@dataclass(repr=False)
class RealRun:
    artifacts: dict
    paths: dict
    hashes: dict


@pytest.fixture(scope='module')
def real_run():
    configured = os.environ.get('PERSON_EVENT_REAL_RUN_DIR')
    if not configured:
        pytest.skip('Set PERSON_EVENT_REAL_RUN_DIR to the extracted PBUILD-dee74d7e4a1d directory')
    root = Path(configured)
    paths = {name: root / relative for name, relative in {
        'input': 'input.json',
        'graph': 'attempts/0004/epg.json',
        'facts': 'attempts/0004/facts.json',
    }.items()}
    for name, path in paths.items():
        if not path.is_file():
            pytest.fail(f'Missing real run {name}: {path}')
    raw = {name: path.read_bytes() for name, path in paths.items()}
    assert hashlib.sha256(raw['input']).hexdigest() == ORIGINAL_INPUT_SHA256
    return RealRun({name: json.loads(data) for name, data in raw.items()}, paths, {
        name: hashlib.sha256(data).hexdigest() for name, data in raw.items()})


def assert_originals_unchanged(paths, hashes):
    for name, path in paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[name], name


def test_real_input_and_original_outputs_remain_valid(real_run):
    artifacts, paths, hashes = real_run.artifacts, real_run.paths, real_run.hashes
    payload = artifacts['input']
    assert len(payload['samples']) == 19
    assert check_graph(seed_facts(payload), payload)['valid']
    for name in ('graph', 'facts'):
        original = artifacts[name]
        before = deepcopy(original)
        assert check_graph(original, payload)['valid']
        assert original == before
    assert_originals_unchanged(paths, hashes)
