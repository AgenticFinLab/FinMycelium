from dataclasses import asdict
import json

import pytest

from test_model_api import offline, transport
from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from test_person_event_runtime import Model as OfflineModel, valid
from finmy.person_epg.build import Model, run_event
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, semantic_config, write_json


@pytest.mark.parametrize('value', ['medium', 'none', '', 1, [], {}])
def test_invalid_effort(value):
    with pytest.raises(ValueError, match='reasoning_effort'):
        EventBuildConfig(reasoning_effort=value)


@pytest.mark.parametrize('provider', ['ark/kimi-k3-1-pro-261024', 'tokenhub/kimi-k3.1-pro'])
def test_staged_effort_reaches_transport_and_records(tmp_path, payload, transport, provider):
    config = EventBuildConfig(lm_name=provider)
    run = Execution(tmp_path, payload, config, Model(config))
    stages = [('batch.0', 'extraction', 'low'), ('batch.1.correct.1', 'extraction', 'low'),
              ('consolidate.0', 'consolidation', 'high'), ('organize', 'organization', 'high'),
              ('relate.0', 'relations', 'high'), ('repair.relations', 'relations', 'high')]
    for task_id, role, expected in stages:
        run.infer(task_id, 'Return JSON', {'role': role}, seed_facts(payload), valid)
        call = run.state['calls'][-1]
        step = run.attempt / 'steps' / call['call_id'] / 'request.json'
        assert json.loads(step.read_text())['reasoning_effort'] == expected
        assert call['reasoning_effort'] == call['transport']['reasoning_effort'] == expected
        assert transport['requests'][-1][1]['reasoning_effort'] == expected
    assert json.loads((tmp_path/'config.json').read_text())['reasoning_effort'] == 'by_stage'


@pytest.mark.parametrize('effort', [None, 'low', 'high', 'max'])
def test_workflow_can_request_a_uniform_effort(transport, effort):
    model = Model(EventBuildConfig(reasoning_effort=effort))
    for task in ('extract.0', 'relate.0'):
        assert model('Return JSON', '{}', task) == '{"ok":true}'
        body = transport['requests'][-1][1]
        if effort is None:
            assert 'reasoning_effort' not in body
        else:
            assert body['reasoning_effort'] == effort


def test_unsupported_model():
    assert EventBuildConfig(lm_name='ark/doubao-seed-evolving').reasoning_effort is None
    assert EventBuildConfig(lm_name='kimi-k3-1-pro-261024').reasoning_effort == 'by_stage'
    with pytest.raises(ValueError, match='Kimi'):
        EventBuildConfig(lm_name='ark/doubao-seed-evolving', reasoning_effort='low')


def test_saved_default_preserves_legacy_semantic_config():
    old = asdict(EventBuildConfig())
    for key in ('reasoning_effort', 'api_json_mode', 'full_corpus_supplement', 'max_calls'):
        old.pop(key)
    assert semantic_config(EventBuildConfig.from_saved(old)) == old
    assert semantic_config(EventBuildConfig()) == {**old, 'reasoning_effort': 'by_stage'}


@pytest.mark.parametrize('policy', [None, 'low', 'high', 'by_stage'])
def test_resume_uses_frozen_effort_when_only_budget_is_supplied(tmp_path, payload, policy):
    model = SyntheticEventModel()
    state = run_event(payload, tmp_path, dict(reasoning_effort=policy, max_calls=1), model=model)
    assert state['execution_status'] == 'limit'
    if policy is None:
        # Simulate a same-code checkpoint whose original task predates the field.
        del state['config']['reasoning_effort']
        write_json(tmp_path/'state.json', state)
        write_json(tmp_path/'config.json', state['config'])
    resumed = run_event(payload, tmp_path, {'max_calls': 10}, model=model, resume=True)
    assert resumed['result_status'] == 'draft'
    assert resumed['config']['reasoning_effort'] == policy
    assert model.calls.count('extract.0') == 1
    for call in resumed['calls']:
        expected = policy
        if policy == 'by_stage':
            expected = 'low' if call['task_id'].startswith('extract.') else 'high'
        assert call['reasoning_effort'] == expected


def test_effort_cannot_change_on_resume(tmp_path, payload):
    run = Execution(tmp_path, payload, EventBuildConfig(), OfflineModel([{'ok': True}]))
    run.infer('extract', 'Return JSON', {}, seed_facts(payload), valid)
    before = (tmp_path/'state.json').read_bytes()
    with pytest.raises(ValueError, match='semantic settings'):
        Execution(tmp_path, payload, EventBuildConfig(reasoning_effort='low'), OfflineModel([]), resume=True)
    assert (tmp_path/'state.json').read_bytes() == before
