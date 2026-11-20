"""Sources remain readable before any extraction evidence has been adopted."""
from copy import deepcopy
import json

import pytest

from test_person_event_contract import payload
from finmy.person_epg.event.build import Construction, body_ranges
from finmy.person_epg.event.prompts import system_prompt
from finmy.person_epg.event.proposals import validate_envelope
from finmy.person_epg.event.runtime import Corpus, EventBuildConfig, Execution


@pytest.mark.parametrize('workers', [1, 6])
def test_empty_evidence_snapshot_can_read_other_source_samples(tmp_path, payload, workers):
    target = payload['samples'][1]
    payload['samples'].append(dict(sample_id='independent-sample-name',
        raw_data_id=target['raw_data_id'], content='Another passage: 甲乙。'))
    expected = [s for s in payload['samples'] if s['raw_data_id'] == target['raw_data_id']]
    before = deepcopy(payload)

    def model(system, user, name):
        incoming = json.loads(user)
        task = incoming['task']
        assert not task['facts_index']['evidence_index']
        source = next(s for s in task['sources'] if s['source_id'] == target['raw_data_id'])
        if not incoming['read_results']:
            entries = [s for s in task['readable_samples'] if s['source_id'] == source['source_id']]
            return dict(read_requests=[dict(tool='read_sample', sample_id=s['sample_id'],
                start=0, end=min(s['length'], task['read_limits']['read_chars'])) for s in entries])
        results = [r['result'] for r in incoming['read_results']]
        assert [r['sample_id'] for r in results] == [s['sample_id'] for s in expected]
        assert [r['text'] for r in results] == [s['content'][:4000] for s in expected]
        return dict(entities=[], actions=[], contexts=[], relation_candidates=[], evidence=[], pending=[])

    config = EventBuildConfig(extraction_workers=workers)
    run = Execution(tmp_path, payload, config, model)
    build = Construction(run)
    request = build.request('extraction', build.facts, body=next(body_ranges(payload, config)),
                            sources=build.facts['sources'])
    system = system_prompt('extraction')
    if workers > 1:
        run.prefetch_tasks([('extract.0', system, request, build.facts)])
    run.infer('extract.0', system, request, build.facts, lambda v: validate_envelope('extraction', v))
    assert [c['status'] for c in run.state['calls']] == ['read_requested', 'accepted']
    assert len(run.state['reads']) == len(expected)
    assert payload == before


@pytest.mark.parametrize('role', ['extraction', 'consolidation', 'organization', 'relations'])
def test_all_read_enabled_roles_and_corrections_keep_sample_directory(tmp_path, payload, role):
    config = EventBuildConfig()
    run = Execution(tmp_path, payload, config, None)
    build = Construction(run)
    request = build.request(role, build.facts)
    # Correction requests carry fields forward from the preceding request.
    fields = {k: v for k, v in request.items() if k not in
        {'role', 'identity', 'query_text', 'facts_index', 'read_limits', 'related_records', 'context_selection'}}
    corrected = build.request(role, build.facts, **fields)
    assert corrected['readable_samples'] == request['readable_samples']
    corpus = Corpus(payload, build.facts, config)
    for entry in corrected['readable_samples']:
        result = corpus.read(dict(tool='read_sample', sample_id=entry['sample_id'],
            start=0, end=min(entry['length'], config.read_chars)))
        assert result['source_id'] == entry['source_id']
