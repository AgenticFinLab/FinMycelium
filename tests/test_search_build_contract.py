"""Search -> existing Builder entry contract; no Builder or API execution."""
import copy
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.builder.agent_build_adapter import BuildOnlyAgentEventBuilder
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput
from finmy.runner import build_only_runner, search_pipeline_runner
from finmy.runner.sparse_build_runner import load_inputs
from finmy.search.handoff import assemble_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Contract check must not connect, initialize or run a Builder')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    for cls in (AgentEventBuilder, BuildOnlyAgentEventBuilder, SparseRagBuilder):
        monkeypatch.setattr(cls, '__init__', forbidden)
        monkeypatch.setattr(cls, 'run', forbidden)


def search_output(tmp_path, budget):
    task = dict(target_type='event', target_name='Acquisition',
                query_text='Trace proposal, approval and closing; 区分公告与交割。',
                key_words=['approval', 'closing'])
    state = SearchState(tmp_path/'search', 'case', task=task)
    store = SourceStore(state)
    ids = []
    for i in range(2):
        sid = store.register(f'https://example.org/filing-{i}', title=f'Filing {i}')
        text = '\n\n'.join(f'Approval {i}-{j}: subject to closing conditions. ' * 5
                            for j in range(20))
        text += '\n\nClosing terms: {"amount": "{unconfirmed}"}; not yet effective.'
        store.save_raw(sid, text.encode(), 'txt', partial=True)
        store.read(sid)
        ids.append(sid)
    payload = assemble_sources(state, ids, max_chars=budget, reason='supported')
    record = json.loads((state.run_dir/'selection.json').read_text())
    return state.run_dir/'builder_input.json', payload, record


@pytest.mark.parametrize('kind', ['agent', 'sparse'])
@pytest.mark.parametrize('budget', [60000, 1800])
def test_search_material_passes_real_build_only_preflight(tmp_path, capsys, kind, budget):
    path, payload, selection = search_output(tmp_path, budget)
    build_input, _ = load_inputs(path)
    assert isinstance(build_input.user_query, UserQueryInput)
    assert all(isinstance(s, DataSample) for s in build_input.samples)
    assert build_input.user_query.query_text == payload['user_query']['query_text']
    assert build_input.user_query.key_words == payload['user_query']['key_words']
    assert [(s.sample_id, s.raw_data_id, s.content) for s in build_input.samples] == [
        (s['sample_id'], s['raw_data_id'], s['content']) for s in payload['samples']]
    config = yaml.safe_load((ROOT/f'configs/build_only_{kind}.yml').read_text())
    config['builder_config']['save_folder'] = str(tmp_path/'must-not-be-created')
    config_path = tmp_path/'builder.yml'
    config_path.write_text(yaml.safe_dump(config))
    assert build_only_runner.main(['--config', str(config_path), '--input', str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'offline_preflight_pass'
    assert report['builder_type'] == config['builder_config']['builder_type']
    assert report['source_characters'] == selection['material_chars'] <= budget
    assert report['sample_count'] == len(payload['samples']) == 2
    assert report['online_compatibility_verified'] is False
    assert not (tmp_path/'must-not-be-created').exists()
    assert bool(selection['omitted']) == (budget == 1800)


@pytest.mark.parametrize('kind', ['agent', 'sparse'])
def test_no_usable_material_is_not_build_ready(tmp_path, kind):
    path, payload, _ = search_output(tmp_path, 1)
    assert payload['samples'] == []
    with pytest.raises(ValueError, match='nonempty list'):
        build_only_runner.main(['--config', str(ROOT/f'configs/build_only_{kind}.yml'),
                                '--input', str(path)])


def test_full_entry_passes_budgeted_body_unchanged_and_keeps_model_configs_separate(tmp_path, monkeypatch):
    path, payload, selection = search_output(tmp_path, 1800)
    from finmy.search import pipeline as search
    fake_search = Mock(return_value=dict(status='finished', builder_input_path=str(path)))
    monkeypatch.setattr(search, 'run_search', fake_search)
    recorded_build = Mock(return_value='stub-build-result')
    factory = Mock(return_value=SimpleNamespace(lm_build_pipeline_with_contents=recorded_build))
    monkeypatch.setattr(search_pipeline_runner, '_create_pipeline', factory)
    monkeypatch.setattr(search_pipeline_runner, '_limit_content_length',
                        lambda *a, **k: pytest.fail('Budgeted input must not be trimmed again'))
    config = dict(search_config=dict(mode='agent', enhancement=dict(lm_name='ark/search-model')),
                  builder_config=dict(builder_type='SparseRagBuilder', lm_name='ark/build-model'),
                  all_content_config=dict(max_content_length=1))
    before = copy.deepcopy(config)
    result = search_pipeline_runner.run_search_pipeline(config, 'original', [], tmp_path/'full')
    recorded_build.assert_called_once_with(contents=[s['content'] for s in payload['samples']],
        query_text=payload['user_query']['query_text'], key_words=payload['user_query']['key_words'])
    factory.assert_called_once_with(config)
    assert fake_search.call_args.kwargs['config']['lm_name'] == 'ark/search-model'
    assert config == before
    assert sum(map(len, result['all_text_content'])) == selection['material_chars']
    assert result['pipeline_result'] == 'stub-build-result'


@pytest.mark.parametrize('status', ['paused', 'failed', 'insufficient', 'limit'])
def test_unfinished_search_never_creates_pipeline(tmp_path, monkeypatch, status):
    from finmy.search import pipeline as search
    monkeypatch.setattr(search, 'run_search', lambda *a, **k: dict(status=status, builder_input_path=None))
    factory = Mock(side_effect=AssertionError('Must not construct a Pipeline'))
    monkeypatch.setattr(search_pipeline_runner, '_create_pipeline', factory)
    result = search_pipeline_runner.run_search_pipeline(
        {'search_config': {'mode': 'agent'}}, 'event', [], tmp_path)
    assert result['pipeline_result'] is None
    factory.assert_not_called()
