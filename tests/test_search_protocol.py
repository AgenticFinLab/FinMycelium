"""Search action compatibility without real model, search or download calls."""
from copy import deepcopy
import json

import pytest

from finmy.person_epg.build import Model
from finmy.person_epg.event.runtime import EventBuildConfig
from finmy.search.agent import LmbaseModel, run_agent
from finmy.search.pipeline import run_search
from finmy.search.protocol import InvalidActionOutput, parse_action
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools
from test_model_api import offline, transport


TASK = dict(target_type='event', target_name='Synthetic acquisition',
            query_text='Trace the announcement and closing of an invented acquisition.')
READ = {'action': 'read_source', 'source': 'https://example.org/notice',
        'location': {'block': 0, 'offset': 0}}
DSML = ('<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="read_source">'
        '<｜｜DSML｜｜ parameter name="source" string="true">source-b'
        '</｜｜DSML｜｜ parameter></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>')
FENCE = chr(96) * 3


@pytest.mark.parametrize('raw', [json.dumps(READ), '\n ' + json.dumps(READ) + '\t',
    FENCE + 'json\n' + json.dumps(READ) + '\n' + FENCE,
    FENCE + '\n' + json.dumps(READ) + '\n' + FENCE, READ])
def test_one_plain_or_fenced_action(raw):
    assert parse_action(raw) == READ


@pytest.mark.parametrize('raw', [
    None, '', ' \n\t ', DSML, json.dumps(READ) + '\n' + DSML,
    json.dumps(READ) + '\n<commentary>More text</commentary>',
    json.dumps(READ) + '\n' + json.dumps(READ),
    'Here is the action:\n' + json.dumps(READ),
    FENCE + 'json\n' + json.dumps(READ) + '\n' + FENCE + '\nextra',
    json.dumps([READ]), 'null', '42', '"action"',
    '{"action":"search","action":"finish","query":"test"}',
    '{"action":"read_source","source":"source-a","location":{"offset":0,"offset":4}}',
    '{"action":"read_source","source":"source-a","location":{"offset":NaN}}',
])
def test_ambiguous_or_malformed_output_is_rejected(raw):
    with pytest.raises(InvalidActionOutput):
        parse_action(raw)


@pytest.mark.parametrize('remote', ['deepseek/deepseek-flash', 'deepseek-v4-pro-202606'])
def test_json_policy_is_search_only_and_survives_sdk_extra_body_merge(transport, remote):
    original = dict(max_tokens=4096, response_format={'type':'text'}, thinking={'type':'enabled'},
                    enable_thinking=True, reasoning_effort='high',
                    extra_body={'response_format':{'type':'text'}, 'thinking':{'type':'enabled'},
                                'enable_thinking':True, 'thinking_budget':8192, 'reasoning_effort':'high'})
    snapshot = deepcopy(original)
    config = SearchConfig(lm_name='tokenhub/'+remote, allow_network=True, generation_config=original)
    model = LmbaseModel(config)
    transport['content'] = json.dumps(READ)
    assert parse_action(model({'task':TASK})) == READ
    _, body = transport['requests'][-1]
    assert body['model'] == remote
    assert body['response_format'] == {'type':'json_object'}
    assert body['thinking'] == {'type':'disabled'}
    assert not {'enable_thinking','thinking_budget','reasoning_effort','tools','tool_choice'} & body.keys()
    assert (body['temperature'], body['top_p'], body['max_tokens']) == (1.0, 1.0, 4096)
    assert model.adapter.client.max_retries == 0
    assert config.generation_config == original == snapshot
    assert model.last_request_options['response_format'] == {'type':'json_object'}
    assert model.last_request_options['thinking'] == {'type':'disabled'}
    assert 'synthetic-tokenhub-key' not in json.dumps(model.last_request_options)
    builder = Model(EventBuildConfig(lm_name='tokenhub/'+remote))
    builder('Return a JSON object.', 'Synthetic input', 'Extract')
    _, build_body = transport['requests'][-1]
    assert 'response_format' not in build_body and 'thinking' not in build_body
    assert build_body['max_tokens'] == 12288


@pytest.mark.parametrize('name', ['ark/doubao-seed-2-1-lite-260915', 'tokenhub/glm-5.3-flash',
                                 'tokenhub/synthetic-other'])
def test_other_models_keep_their_supplied_protocol(transport, name):
    options = {'max_tokens':4096, 'extra_body':{'thinking':{'type':'enabled'}}}
    model = LmbaseModel(SearchConfig(lm_name=name, allow_network=True, generation_config=options))
    model({'task':TASK})
    _, body = transport['requests'][-1]
    assert 'response_format' not in body
    assert body['thinking'] == {'type':'enabled'}


def test_sdk_loop_search_read_finish_preserves_provider_and_budget_rules(tmp_path, transport):
    url = READ['source']
    sid = digest(url)[:24]
    transport['contents'] = iter([
        json.dumps({'action':'search','query':'synthetic acquisition closing'}),
        FENCE + 'json\n' + json.dumps(READ) + '\n' + FENCE,
        json.dumps({'action':'finish','source_ids':[sid],'gaps':[],'reason':'supported'}),
    ])
    calls = []
    def provider(name, payload, config):
        calls.append(name)
        item = {'url':url, 'title':'Synthetic announcement', 'name':'Synthetic announcement'}
        return {'references':[item]} if name == 'baidu' else (
            {'data':{'webPages':{'value':[item]}}} if name == 'bocha' else {'results':[item]})
    config = SearchConfig(lm_name='tokenhub/deepseek/deepseek-flash', allow_network=True,
                          providers=['baidu','bocha','exa'], max_search_requests=3, max_model_calls=6)
    model = LmbaseModel(config)
    result = run_search(TASK, root=tmp_path, task_id='synthetic', config=config, model=model,
        transport=provider, fetcher=lambda url:(b'The fictional deal closed on 1 February 2024.', 'txt', 'utf-8'))
    assert result['status'] == 'finished'
    assert result['usage'] == {'model':3,'search':3}
    assert calls == ['baidu','bocha','exa'] and len(transport['requests']) == 3
    state = SearchState(tmp_path, 'synthetic')
    payload = json.loads((state.run_dir/'builder_input.json').read_text())
    assert len(payload['samples']) == 1
    assert 'fictional deal closed' in payload['samples'][0]['content']
    trace = [json.loads(line) for line in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    responses = [r for r in trace if r['action'] == 'model_response']
    assert all(r['request_options']['response_format'] == {'type':'json_object'} for r in responses)
    assert all(r['request_options']['thinking'] == {'type':'disabled'} for r in responses)


def test_empty_json_mode_content_stops_within_existing_failure_budget(tmp_path, transport):
    transport['content'] = '  \n  '
    config = SearchConfig(lm_name='tokenhub/deepseek/deepseek-flash', allow_network=True, max_model_calls=8)
    result = run_search(TASK, root=tmp_path, task_id='empty', config=config,
                        model=LmbaseModel(config), transport=lambda *a:pytest.fail('No valid search action'))
    assert result['status'] == 'failed' and result['usage'] == {'model':3,'search':0}
    assert result['builder_input_path'] is None and len(transport['requests']) == 3
    state = SearchState(tmp_path, 'empty')
    assert state.data['feedback']['error'] == 'InvalidActionOutput'
    assert 'Empty' in state.data['feedback']['hint']
    trace = [json.loads(line) for line in (state.run_dir/'trace.jsonl').read_text().splitlines()]
    assert sum(r['usage']['total_tokens'] for r in trace if r['action']=='model_response') == 105


def test_resume_preserves_failure_history_source_bytes_and_cumulative_calls(tmp_path):
    state = SearchState(tmp_path, 'resume', task=TASK, config=SearchConfig(max_model_calls=30))
    responses = iter([json.dumps(READ)+'\nextra', json.dumps(READ)+DSML, json.dumps(READ),
                      DSML, DSML, DSML])
    tools = SearchTools(state, transport=lambda *a:pytest.fail('No search action'),
                        fetcher=lambda url:(b'Original synthetic evidence.', 'txt', 'utf-8'))
    run_agent(state, tools, lambda context:next(responses))
    assert state.data['status'] == 'failed'
    assert state.data['usage'] == {'model':6,'search':0}
    sid = state.data['read_sources'][0]
    source = deepcopy(state.data['sources'][sid])
    original_trace = (state.run_dir/'trace.jsonl').read_bytes()
    originals = {p:p.read_bytes() for p in (state.root/'sources').rglob('*') if p.is_file()}
    resumed = SearchState(tmp_path, 'resume')
    run_agent(resumed, SearchTools(resumed, fetcher=lambda *a:pytest.fail('Do not refetch')),
        lambda context:json.dumps({'action':'finish','source_ids':[sid],'gaps':[],'reason':'supported'}))
    assert resumed.data['status'] == 'finished'
    assert resumed.data['usage'] == {'model':7,'search':0}
    assert resumed.data['sources'][sid] == source
    assert (state.run_dir/'trace.jsonl').read_bytes().startswith(original_trace)
    assert all(p.read_bytes() == data for p, data in originals.items())
