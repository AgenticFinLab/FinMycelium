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

from finmy.person_epg.event.context import navigation
from finmy.person_epg.event.evidence_support import upgrade_package_evidence
from finmy.person_epg.event.proposals import Receiver
from finmy.person_epg.event.records import IdMap, seed_facts
from finmy.person_epg.event.validation import check_graph


ORIGINAL_INPUT_SHA256 = 'ef910ea7c1905fa0e2d9f2774e5b6dd66832ea54273597fee04b80138ba5771f'
REUTERS_AMENDMENT = 'EVD-308359c27b55ba94f14c'
GOLDMAN_AMENDMENT = 'EVD-8ea4241d86911c9ee2b9'
REUTERS_SHARES = 'EVD-5cdd597a6e57b2367bda'
GOLDMAN_SHARES = 'EVD-f7002073def28faeaa0c'


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
        upgraded = upgrade_package_evidence(original)
        report = check_graph(upgraded, payload)
        assert report['valid'], report['errors'][:5]
        assert len(upgraded['evidence']) == len(original['evidence'])
        for old, new in zip(original['evidence'], upgraded['evidence']):
            assert new['evidence_id'] == old['evidence_id']
            assert new['citations'] == [{key: value for key, value in old.items() if key != 'evidence_id'}]
        assert original == before
    assert_originals_unchanged(paths, hashes)


def test_two_real_sources_support_two_evidence_records(real_run):
    artifacts, paths, hashes = real_run.artifacts, real_run.paths, real_run.hashes
    payload = artifacts['input']
    old_evidence = {item['evidence_id']: item for item in artifacts['graph']['evidence']}
    samples = {sample['sample_id']: sample for sample in payload['samples']}

    def original_citation(evidence_id):
        old = old_evidence[evidence_id]
        sample = samples[old['sample_id']]
        assert sample['raw_data_id'] == old['source_id']
        assert sample['content'][old['start']:old['end']] == old['quote']
        return {key: old[key] for key in ('sample_id', 'quote', 'start', 'end')}

    # Both statements concern the recorded 2013 amendment. The quotations and
    # offsets are copied from the historical run, then grounded against input.json.
    proposals = [
        dict(evidence_id='amendment', statement='Goldman Sachs and Berkshire Hathaway amended their warrant agreement.',
             citations=[original_citation(REUTERS_AMENDMENT), original_citation(GOLDMAN_AMENDMENT)]),
        dict(evidence_id='shares', statement='The amended agreement provides for Goldman Sachs to deliver shares to Berkshire Hathaway.',
             citations=[original_citation(GOLDMAN_SHARES), original_citation(REUTERS_SHARES)]),
    ]
    response = dict(entities=[], actions=[], contexts=[], relation_candidates=[],
                    evidence=proposals, pending=[], note='Evidence only.')
    facts, report = Receiver(seed_facts(payload), payload, IdMap(), 'real-amendment').extract(response)
    assert not report['rejected'], report['rejected']
    validation = check_graph(facts, payload)
    assert validation['valid'], validation['errors'][:5]
    assert len(facts['evidence']) == 2
    reuters = old_evidence[REUTERS_AMENDMENT]['source_id']
    goldman = old_evidence[GOLDMAN_AMENDMENT]['source_id']
    assert reuters != goldman
    for evidence in facts['evidence']:
        assert {citation['source_id'] for citation in evidence['citations']} == {reuters, goldman}
        assert all(citation['location_status'] == 'matched' for citation in evidence['citations'])
    assert len([row for row in navigation(facts)['evidence_index']
                if row['source_id'] == goldman]) == 2
    assert_originals_unchanged(paths, hashes)
