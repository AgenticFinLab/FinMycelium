"""Reading rounds are bounded per semantic task, independently of corrections."""
import pytest

from test_person_event_contract import payload
from test_person_event_runtime import Model, valid
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, LimitReached
from finmy.person_epg.event.scheduling import Task


def reads(payload):
    return {'read_requests': [dict(tool='read_sample', sample_id=s['sample_id'],
                                  start=0, end=10) for s in payload['samples'][:2]]}


def test_two_batches_then_result_and_format_retry(tmp_path, payload):
    model = Model(['bad json', reads(payload), reads(payload), {'ok': True}])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    assert run.infer('relate.0', 'system', {}, seed_facts(payload), valid) == {'ok': True}
    assert len(model.calls) == 4 and len(run.state['reads']) == 4
    assert list(map(len, run.state['read_rounds'].values())) == [2]
    assert [len(b) for b in run.state['validation_attempts'].values()] == [1]


def test_third_read_stops_only_its_task_and_resume_cannot_reset(tmp_path, payload):
    calls = []
    def model(system, user, name):
        calls.append(name)
        return reads(payload) if name == 'relate.0' else {'ok': True}
    config = EventBuildConfig(extraction_workers=2)
    run = Execution(tmp_path, payload, config, model)
    facts = seed_facts(payload)
    tasks = [Task(name, run.infer_steps(name, 'system', {}, facts, valid))
             for name in ('relate.0', 'relate.1')]
    outcomes = run.execute_tasks('relations', tasks)
    assert isinstance(outcomes['relate.0'].error, LimitReached)
    assert outcomes['relate.1'].result == {'ok': True}
    assert calls.count('relate.0') == 3 and calls.count('relate.1') == 1
    assert run.state['task_states']['relations:relate.0']['status'] == 'limited'
    assert run.state['task_states']['relations:relate.0']['reason'] == 'read_rounds'
    assert len(run.state['reads']) == 4
    resumed = Execution(tmp_path, payload, config, Model([]), resume=True)
    with pytest.raises(LimitReached, match='read_rounds'):
        resumed.infer('relate.0', 'system', {}, facts, valid)
    assert not resumed.model.calls


def test_correction_shares_read_rounds(tmp_path, payload):
    model = Model([reads(payload), reads(payload), {'ok': True}, reads(payload)])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    facts = seed_facts(payload)
    run.infer('relate.0', 'system', {}, facts, valid, attempt_group='same-task')
    with pytest.raises(LimitReached, match='read_rounds'):
        run.infer('relate.0.correct.1', 'system', {}, facts, valid, attempt_group='same-task')
    assert len(model.calls) == 4 and len(run.state['reads']) == 4
    assert len(run.state['read_rounds']['same-task']) == 2


def test_transport_resume_retains_rounds_but_can_finish(tmp_path, payload):
    model = Model([reads(payload), TimeoutError(), reads(payload), {'ok': True}])
    config = EventBuildConfig()
    facts = seed_facts(payload)
    run = Execution(tmp_path, payload, config, model)
    with pytest.raises(TimeoutError):
        run.infer('relate.0', 'system', {}, facts, valid)
    resumed = Execution(tmp_path, payload, config, model, resume=True)
    assert resumed.infer('relate.0', 'system', {}, facts, valid) == {'ok': True}
    assert list(map(len, resumed.state['read_rounds'].values())) == [2]
    assert len(resumed.state['reads']) == 4


def test_zero_disables_reading_followups(tmp_path, payload):
    model = Model([reads(payload)])
    run = Execution(tmp_path, payload, EventBuildConfig(max_read_rounds=0), model)
    with pytest.raises(LimitReached, match='read_rounds'):
        run.infer('relate.0', 'system', {}, seed_facts(payload), valid)
    assert len(model.calls) == 1 and not run.state['reads']


@pytest.mark.parametrize('value', [-1, True, 1.5])
def test_invalid_read_round_config(value):
    with pytest.raises(ValueError, match='max_read_rounds'):
        EventBuildConfig(max_read_rounds=value)
