from dataclasses import replace
import pytest

from test_person_event_contract import payload
from test_person_event_runtime import Model, valid
from test_person_event_read_rounds import reads
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution, LimitReached, semantic_config


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('kind', ['rounds', 'calls', 'chars'])
def test_extension_replays_pending_read_without_paying_for_it_again(tmp_path, payload, kind, legacy):
    cfg = EventBuildConfig(max_read_rounds=0 if kind == 'rounds' else 2,
        max_read_calls=1 if kind == 'calls' else 24,
        max_read_chars=1 if kind == 'chars' else 48000)
    facts = seed_facts(payload)
    run = Execution(tmp_path, payload, cfg, Model([{'ok': True}, reads(payload)]))
    run.infer('done', 'system', {}, facts, valid)
    with pytest.raises(LimitReached, match='read_' + kind):
        run.infer('pending', 'system', {}, facts, valid)
    if legacy:
        for task in run.state['tasks'].values():
            task.pop('pending_read_response', None)
        run.persist()
    count = len(run.state['calls'])
    new = replace(cfg, read_call_extension=40, read_round_extension=2, read_char_extension=96000)
    assert semantic_config(cfg) == semantic_config(new)
    model = Model([{'ok': True}])
    resumed = Execution(tmp_path, payload, new, model, resume=True)
    assert resumed.infer('done', 'system', {}, facts, valid) == {'ok': True}
    assert not model.calls
    assert resumed.infer('pending', 'system', {}, facts, valid) == {'ok': True}
    assert len(resumed.state['calls']) == count + 1
    assert len(resumed.state['reads']) == 2
    assert len(model.calls) == 1
    assert len(model.calls[0]['read_results']) == 2
    assert list(map(len, resumed.state['read_rounds'].values())) == [0, 1]


def test_same_budget_still_limits_without_another_model_call(tmp_path, payload):
    cfg = EventBuildConfig(max_read_calls=1)
    facts = seed_facts(payload)
    run = Execution(tmp_path, payload, cfg, Model([reads(payload)]))
    with pytest.raises(LimitReached, match='read_calls'):
        run.infer('pending', 'system', {}, facts, valid)
    resumed = Execution(tmp_path, payload, cfg, Model([]), resume=True)
    with pytest.raises(LimitReached, match='read_calls'):
        resumed.infer('pending', 'system', {}, facts, valid)
    assert not resumed.model.calls and len(resumed.state['reads']) == 1
