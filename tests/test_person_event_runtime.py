from copy import deepcopy
import json

import pytest

from test_person_event_contract import payload
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import Corpus, EventBuildConfig, Execution, InvalidResponse, LimitReached


def valid(value):
    if value != {'ok': True}:
        raise ValueError('Need ok=true')


class Model:
    last_usage = None

    def __init__(self, answers):
        self.answers, self.calls = iter(answers), []

    def __call__(self, system, user, name):
        self.calls.append(json.loads(user))
        result = next(self.answers)
        if isinstance(result, BaseException):
            raise result
        return result


def test_checkpoint_reuse_and_cumulative_limit(tmp_path, payload):
    package = seed_facts(payload)
    model = Model([{'ok': True}])
    run = Execution(tmp_path, payload, EventBuildConfig(max_calls=1), model)
    assert run.infer('extract.1', 'contract', {}, package, valid) == {'ok': True}
    with pytest.raises(LimitReached, match='model_calls'):
        run.infer('extract.2', 'contract', {}, package, valid)
    resumed = Execution(tmp_path, payload, EventBuildConfig(max_calls=3), Model([{'ok': True}]), resume=True)
    resumed.infer('extract.1', 'contract', {}, package, valid)
    assert not resumed.model.calls
    resumed.infer('extract.2', 'contract', {}, package, valid)
    assert len(resumed.state['calls']) == 2


def test_json_attempts_survive_resume(tmp_path, payload):
    run = Execution(tmp_path, payload, EventBuildConfig(max_json_attempts=2), Model(['bad', {'wrong': True}]))
    with pytest.raises(InvalidResponse):
        run.infer('extract', 'contract', {}, seed_facts(payload), valid)
    resumed = Execution(tmp_path, payload, EventBuildConfig(max_json_attempts=2), Model([]), resume=True)
    with pytest.raises(InvalidResponse, match='exhausted'):
        resumed.infer('extract', 'contract', {}, seed_facts(payload), valid)
    assert not resumed.model.calls and len(resumed.state['calls']) == 2


def test_read_tools_are_frozen_and_bounded(tmp_path, payload):
    request = dict(tool='read_sample', sample_id='SAMPLE-1', start=0, end=30)
    model = Model([{'read_requests': [request]}, {'ok': True}])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    run.infer('relations', 'contract', {}, seed_facts(payload), valid)
    assert model.calls[1]['read_results'][0]['result']['text'] == payload['samples'][0]['content'][:30]
    assert len(run.state['reads']) == 1 and len(run.state['calls']) == 2
    corpus = Corpus(payload, seed_facts(payload), EventBuildConfig(read_chars=100))
    with pytest.raises(ValueError):
        corpus.read(dict(tool='fetch', url='https://example.org'))
    with pytest.raises(ValueError):
        corpus.read({**request, 'end': 1000})
    with pytest.raises(KeyError):
        corpus.read({**request, 'sample_id': '../../secrets'})


def test_transport_failure_keeps_call_and_does_not_auto_retry(tmp_path, payload):
    model = Model([TimeoutError('transport timeout'), {'ok': True}])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    with pytest.raises(TimeoutError):
        run.infer('extract', 'contract', {}, seed_facts(payload), valid)
    assert len(model.calls) == 1
    assert run.state['calls'][0]['usage_status'] == 'unknown'
    resumed = Execution(tmp_path, payload, EventBuildConfig(), model, resume=True)
    resumed.infer('extract', 'contract', {}, seed_facts(payload), valid)
    assert len(resumed.state['calls']) == 2


def test_corrupt_response_is_not_reused(tmp_path, payload):
    model = Model([{'ok': True}, {'ok': True}])
    run = Execution(tmp_path, payload, EventBuildConfig(), model)
    run.infer('extract', 'contract', {}, seed_facts(payload), valid)
    checkpoint = next((tmp_path / 'checkpoints').glob('*.json'))
    cached = json.loads(checkpoint.read_text())
    cached['response'] = {'wrong': True}
    checkpoint.write_text(json.dumps(cached))
    resumed = Execution(tmp_path, payload, EventBuildConfig(), model, resume=True)
    resumed.infer('extract', 'contract', {}, seed_facts(payload), valid)
    assert len(model.calls) == 2 and resumed.state['invalid_checkpoints']


def test_input_and_protocol_mismatch_are_not_resumed(tmp_path, payload):
    Execution(tmp_path, payload, EventBuildConfig(), Model([]))
    changed = deepcopy(payload)
    changed['samples'][0]['content'] += ' New input.'
    with pytest.raises(ValueError, match='input'):
        Execution(tmp_path, changed, EventBuildConfig(), Model([]), resume=True)
    state = json.loads((tmp_path / 'state.json').read_text())
    state['graph_schema_version'] = 'person-epg-3.0'
    (tmp_path / 'state.json').write_text(json.dumps(state))
    with pytest.raises(ValueError, match='protocol'):
        Execution(tmp_path, payload, EventBuildConfig(), Model([]), resume=True)


def test_invalid_request_does_not_spend_model_call(tmp_path, payload):
    run = Execution(tmp_path, payload, EventBuildConfig(max_context_chars=10), Model([]))
    with pytest.raises(LimitReached, match='context'):
        run.infer('extract', 'long contract', {}, seed_facts(payload), valid)
    assert not run.state['calls'] and not run.model.calls
