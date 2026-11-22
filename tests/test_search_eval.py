"""Offline retrieval-evaluation checks; no API calls or Builder execution."""
import builtins
import json
import math
import socket
from copy import deepcopy

import pytest

from finmy.search.eval import collect_pool, default_config, evaluate, main, usage_totals
from finmy.search.eval_judge import JudgeSession, KIMI_MODEL, validate_labels
from finmy.search.eval_metrics import material_metrics, ranking_metrics
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState


GOOD = 'Buffett said he approved the Goldman investment after reviewing the terms.'
SETTLEMENT = 'Goldman reported its 2013 warrant settlement with Berkshire.'
WRONG = 'Berkshire invested in General Electric.'
TASK = dict(target_type='event', target_name='Buffett Goldman investment',
            query_text='Find Buffett personal approval and the Goldman warrant settlement; exclude GE.',
            catalog=dict(kind='person_event', person_name='Warren Buffett', event_name='Goldman investment'))
QUESTIONS = [dict(id='Q1', question='What did Buffett personally approve?'),
             dict(id='Q2', question='How were the Goldman warrants settled?')]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k:pytest.fail('Unexpected network'))
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(('finmy.builder', 'finmy.person_epg')):
            pytest.fail('Search eval must not import a Builder')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)


class Judge:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.last_usage = None

    def __call__(self, system, payload):
        self.calls += 1
        self.last_usage = dict(prompt_tokens=100, completion_tokens=30, total_tokens=130,
                               prompt_tokens_details=dict(cached_tokens=20))
        if payload['operation'] == 'rubric':
            return {'questions':QUESTIONS}
        labels = []
        for unit in payload['units']:
            assert 'selected' not in unit and 'rank' not in unit
            text = unit['text']
            question = 'Q1' if text == GOOD else 'Q2' if text == SETTLEMENT else None
            labels.append(dict(unit_id=unit['unit_id'], grade=2 if question else 0,
                mismatch=[] if question else ['wrong_event'], reason='Matched to the supplied original.',
                supports=[dict(question_id=question, quote='Invented quote' if self.fail else text)]
                         if question else []))
        return {'labels':labels}


def search_model(context):
    if not context['sources']:
        return dict(action='search', query='Buffett Goldman agreement settlement')
    good = next(s for s in context['sources'] if s['url'].endswith('/good'))
    if not good['reviewed']:
        return dict(action='read_source', source=good['source_id'])
    return dict(action='finish', source_ids=[good['source_id']], gaps=['Settlement was not read.'],
                reason='low_gain', person_evidence=dict(status='supported', detail='Explicit approval statement.'))


def transport(provider, request, config):
    assert provider == 'exa'
    return {'results':[dict(url='https://example.org/'+name, title=name, text=text)
                       for name, text in [('wrong', WRONG), ('good', GOOD), ('settlement', SETTLEMENT)]]}


def config():
    return SearchConfig(providers=['exa'], max_results=3, max_model_calls=8,
                        max_search_requests=3, max_read_sources=4)


def options(tmp_path, judge):
    return dict(root=tmp_path, config=config(), search_model=search_model,
                transport=transport, fetcher=lambda url:(GOOD.encode(), 'txt', 'utf-8'),
                judge_model=judge, emit=lambda text:None, eval_mode="auto", eval_scope="pool")


def test_complete_search_then_eval_and_resume_without_research(tmp_path):
    judge = Judge()
    report = evaluate(TASK, **options(tmp_path, judge))
    assert report['status'] == 'finished'
    assert report['search']['usage']['attempted_model_calls'] == 3
    assert report['search']['usage']['provider_requests'] == 1
    assert report['pool']['acquired_sources'] == 3
    assert len(report['search']['final_material']['samples']) == 1
    assert GOOD in report['search']['final_material']['samples'][0]['content']
    assert {u['text'] for u in report['reference_passages']} == {GOOD, SETTLEMENT, WRONG}
    material = report['metrics']['material']
    assert material['question_coverage'] == .5
    assert material['evidence_quote_recall_in_saved_pool'] == .5
    assert material['topic_mismatch_rate'] == 0
    ranks = report['metrics']['provider_rankings'][0]
    assert ranks['at']['1']['precision'] == 0
    assert ranks['at']['3']['recall'] == 1
    assert ranks['at']['10']['precision'] == .2  # Standard fixed-k denominator.
    assert judge.calls == 2
    state = SearchState(tmp_path, report['task_id'])
    original_state = deepcopy(state.data)
    again = Judge()
    settings = options(tmp_path, again)
    settings['transport'] = lambda *a:pytest.fail('Search must be reused')
    repeated = evaluate(TASK, **settings)
    assert again.calls == 0
    assert repeated['judge_cache_hits_this_invocation'] == 2
    assert repeated['metrics'] == report['metrics']
    assert repeated['judge_usage']['calls'] == 2
    # Pipeline's existing resume may refresh updated_at, but evaluator never reads/adopts new ranges.
    current = SearchState(tmp_path, report['task_id']).data
    assert current['sources'] == original_state['sources']
    assert current['actions'] == original_state['actions']
    saved = json.loads((tmp_path/report['task_id']/'output.json').read_text())
    assert saved['search']['final_material'] == report['search']['final_material']
    assert saved['judge_usage']['input_tokens'] == 200


def test_invalid_judge_quote_leaves_search_output_and_can_resume(tmp_path):
    with pytest.raises(RuntimeError, match='exact nonempty substring'):
        evaluate(TASK, **options(tmp_path, Judge(fail=True)))
    output = next(tmp_path.glob('*/output.json'))
    saved = json.loads(output.read_text())
    assert saved['status'] == 'failed'
    assert GOOD in saved['search']['final_material']['samples'][0]['content']
    assert saved['metrics'] is None
    assert saved['judge_usage']['calls'] == 3  # Rubric and two recorded rejected attempts.
    judge = Judge()
    resumed = evaluate(TASK, **options(tmp_path, judge))
    assert resumed['status'] == 'finished'
    assert judge.calls == 1  # Reuses the rubric and all search work.
    assert resumed['judge_usage']['calls'] == 4


def test_ranking_formulas_unknowns_empty_and_short_lists():
    qrels = dict(a=2, b=1, c=0)
    values = ranking_metrics(['b', 'a', 'c'], qrels, 3)
    expected = (1 + 3/math.log2(3)) / (3 + 1/math.log2(3))
    assert values['ndcg'] == pytest.approx(expected)
    assert values['ap'] == .5
    assert values['reciprocal_rank'] == .5
    assert values['recall'] == 1
    assert values['precision'] == pytest.approx(1/3)
    assert ranking_metrics(['a'], qrels, 10)['precision'] == .1
    unknown = ranking_metrics(['unfetched', 'a'], qrels, 2)
    assert unknown['ndcg'] is None and unknown['recall'] is None
    assert unknown['judged_fraction'] == .5
    assert ranking_metrics([], qrels, 3)['ndcg'] == 0
    assert ranking_metrics(['c'], {'c':0}, 3)['recall'] is None
    assert ranking_metrics(['c'], {'c':0}, 3)['ndcg'] is None
    assert ranking_metrics(['a', 'a'], qrels, 2)['recall'] == 1


def test_partial_window_and_duplicate_quotes_do_not_inflate_coverage():
    units = [dict(unit_id='a', source_id='s', version='v', block=0, start=0, end=10,
                  text='He agreed.'),
             dict(unit_id='b', source_id='other', version='v', block=0, start=0, end=10,
                  text='He agreed.')]
    labels = {u['unit_id']:dict(grade=2, mismatch=[],
              supports=[dict(question_id='Q1', quote='He agreed.')]) for u in units}
    missed = material_metrics(units, labels, {('s','v',0):[(0,5)]}, QUESTIONS)
    assert missed['evidence_quote_recall_in_saved_pool'] == 0
    retained = material_metrics(units, labels, {('s','v',0):[(0,10)]}, QUESTIONS)
    assert retained['reference_evidence_quotes'] == 1
    assert retained['evidence_quote_recall_in_saved_pool'] == 1
    assert retained['question_coverage'] == .5


def test_pool_uses_archived_selected_versions_and_does_not_fetch_unread(tmp_path):
    state = SearchState(tmp_path, 'case', task=TASK)
    store = SourceStore(state, lambda url:pytest.fail('Eval must not fetch candidates'))
    sid = store.register('https://example.org/source')
    original = store.save_raw(sid, GOOD.encode(), 'txt')
    current = store.save_raw(sid, SETTLEMENT.encode(), 'txt')
    unknown = store.register('https://example.org/unread')
    selection = dict(selected=[dict(source_id=sid, version=original['version'],
                                    ranges=[dict(block=0, start=0, end=len(GOOD))])])
    payload = dict(samples=[dict(raw_data_id=sid, content=GOOD)])
    before = deepcopy(state.data)
    units, retained = collect_pool(state, selection, payload)
    assert {u['version'] for u in units} == {original['version'], current['version']}
    assert all(u['source_id'] != unknown for u in units)
    assert retained[(sid, original['version'], 0)] == [(0,len(GOOD))]
    assert state.data == before


def test_quote_retained_at_later_occurrence():
    text = 'He agreed. Later: He agreed.'
    unit = dict(unit_id='a', source_id='s', version='v', block=0,
                start=0, end=len(text), text=text)
    labels = {'a':dict(grade=2, mismatch=[],
                       supports=[dict(question_id='Q1', quote='He agreed.')])}
    ranges = {('s','v',0):[(text.rindex('He agreed.'), len(text))]}
    result = material_metrics([unit], labels, ranges, QUESTIONS)
    assert result['evidence_quote_recall_in_saved_pool'] == 1


@pytest.mark.parametrize('change', [
    lambda rows:rows.append(deepcopy(rows[0])),
    lambda rows:rows[0].update(grade=True),
    lambda rows:rows[0].update(unit_id='invented'),
    lambda rows:rows[0]['supports'][0].update(quote='Not in the original'),
    lambda rows:rows[0]['supports'][0].update(question_id='Q999'),
])
def test_bad_qrels_are_rejected(change):
    units = [dict(unit_id='a', text=GOOD)]
    rows = [dict(unit_id='a', grade=2, mismatch=[], reason='direct',
                 supports=[dict(question_id='Q1', quote=GOOD)])]
    change(rows)
    with pytest.raises(ValueError):
        validate_labels({'labels':rows}, units, QUESTIONS)


def test_cache_is_bound_to_task_original_and_prompt(tmp_path):
    judge = Judge()
    session = JudgeSession(tmp_path, judge)
    session.questions(TASK)
    session.questions(TASK)
    assert judge.calls == 1
    session.questions(dict(TASK, query_text='Another event'))
    assert judge.calls == 2
    cached = next(p for p in tmp_path.glob('*.json'))
    saved = json.loads(cached.read_text())
    saved['answer']['questions'][0]['question'] = 'tampered'
    cached.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='integrity'):
        session.ask(saved['request']['payload'], lambda value:value)


def test_cli_needs_only_task_and_defaults_to_kimi(tmp_path, monkeypatch):
    from finmy.search import eval as module
    path = tmp_path/'task.json'
    path.write_text(json.dumps(TASK), encoding='utf-8')
    for key in ('ARK_API_KEY', 'EXA_API_KEY', 'BOCHA_API_KEY', 'BAIDUSEARCH_API_KEY'):
        monkeypatch.setenv(key, 'test-only-not-a-real-key')
    received = {}

    def run(task, **kwargs):
        received.update(task=task, **kwargs)
        return {'status':'finished'}
    monkeypatch.setattr(module, 'evaluate', run)
    assert main(['--task', str(path)]) == 0
    assert received['task'] == TASK
    assert received['config'].lm_name == KIMI_MODEL
    assert received['config'].max_model_calls == SearchConfig().max_model_calls
    assert default_config().generation_config['reasoning_effort'] == 'low'


def test_usage_counts_cached_tokens_as_subset():
    result = usage_totals([dict(usage=dict(prompt_tokens=100, completion_tokens=20,
        total_tokens=120, prompt_tokens_details=dict(cached_tokens=80)), duration_seconds=2),
        dict(usage=None, duration_seconds=3)])
    assert result['input_tokens'] == 100 and result['cached_input_tokens'] == 80
    assert result['total_tokens'] == 120
    assert result['calls'] == 2 and result['reported_usage_calls'] == 1
    assert result['request_seconds'] == 5


def test_cli_output_cannot_overwrite_task(tmp_path):
    path = tmp_path/'task.json'
    original = json.dumps(TASK)
    path.write_text(original, encoding='utf-8')
    assert main(['--task', str(path), '--output', str(path)]) == 1
    assert path.read_text() == original


def test_changed_search_code_does_not_reuse_old_search(tmp_path, monkeypatch):
    from finmy.search import eval as module
    monkeypatch.setattr(module, 'search_fingerprint', lambda:'code-a')
    first = evaluate(TASK, **options(tmp_path, Judge()))
    monkeypatch.setattr(module, 'search_fingerprint', lambda:'code-b')
    second_judge = Judge()
    second = evaluate(TASK, **options(tmp_path, second_judge))
    assert first['task_id'] != second['task_id']
    assert second['search_code_sha256'] == 'code-b'
    assert second_judge.calls == 0  # Unchanged originals reuse unit labels across search runs.


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_kimi_judge_sdk_request_and_truncation(finish):
    from types import SimpleNamespace
    from finmy.model_config import generation_parameters
    from finmy.search.eval_judge import KimiJudge
    httpx = pytest.importorskip('httpx')
    OpenAI = pytest.importorskip('openai').OpenAI
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json=dict(id='test', object='chat.completion', created=1,
            model=body['model'], choices=[dict(index=0, finish_reason=finish,
                message=dict(role='assistant', content='{"questions":[]}'))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120)))

    with OpenAI(api_key='synthetic-key', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        judge = KimiJudge()
        judge.adapter = SimpleNamespace(client=client, model_name=KIMI_MODEL.split('/',1)[1],
            request_parameters=lambda parameters:generation_parameters(KIMI_MODEL, parameters))
        if finish == 'length':
            with pytest.raises(ValueError, match='truncated'):
                judge('Return JSON', {'task':'fixture'})
        else:
            assert json.loads(judge('Return JSON', {'task':'fixture'})) == {'questions':[]}
        assert judge.last_usage['total_tokens'] == 120
        assert requests[0]['model'] == KIMI_MODEL.split('/',1)[1]
        assert requests[0]['response_format'] == {'type':'json_object'}
        assert requests[0]['reasoning_effort'] == 'low'
        assert requests[0]['max_tokens'] == 8192


def test_whitespace_quote_maps_to_original_but_neighbor_quote_is_rejected():
    units=[dict(unit_id='x',text='Goldman\nSachs paid  $5 billion.',context_before='Other evidence.')]
    row=dict(unit_id='x',grade=2,mismatch=[],reason='direct',supports=[dict(question_id='Q1',quote='Goldman Sachs paid $5 billion.')])
    answer=validate_labels({'labels':[row]},units,QUESTIONS)
    assert answer['x']['supports'][0]['quote']=='Goldman\nSachs paid  $5 billion.'
    row['supports'][0]['quote']='Other evidence.'
    with pytest.raises(ValueError):validate_labels({'labels':[row]},units,QUESTIONS)
    assert validate_labels({'labels':[dict(unit_id='x',grade=0,mismatch=[],reason='irrelevant')]},units,QUESTIONS)['x']['supports']==[]


def test_only_bad_units_are_retried_and_survive_restart(tmp_path):
    units=[dict(unit_id='good',text=GOOD),dict(unit_id='bad',text=SETTLEMENT)]
    requests=[]
    def fail(system,payload):
        requests.append([u['unit_id'] for u in payload['units']])
        return {'labels':[dict(unit_id=u['unit_id'],grade=2,mismatch=[],reason='direct',
            supports=[dict(question_id='Q1',quote=u['text'] if u['unit_id']=='good' else 'neighbor')]) for u in payload['units']]}
    with pytest.raises(RuntimeError):JudgeSession(tmp_path,fail).label(TASK,QUESTIONS,units)
    assert requests==[['good','bad'],['bad']]
    def repair(system,payload):
        assert [u['unit_id'] for u in payload['units']]==['bad']
        return {'labels':[dict(unit_id='bad',grade=1,mismatch=[],reason='context',supports=[])]}
    result=JudgeSession(tmp_path,repair).label(TASK,QUESTIONS,units)
    assert result['good']['grade']==2 and result['bad']['grade']==1
    assert JudgeSession(tmp_path,lambda *a:pytest.fail('cache lost')).label(TASK,QUESTIONS,units)==result


def test_transport_retry_preserves_correction_budget(tmp_path, monkeypatch):
    from finmy.search import eval_judge
    monkeypatch.setattr(eval_judge.time, 'sleep', lambda _: None)
    units = [dict(unit_id='good', text=GOOD), dict(unit_id='bad', text=SETTLEMENT)]
    requests = []
    def model(system, payload):
        requests.append([u['unit_id'] for u in payload['units']])
        if len(requests) == 2:
            raise TimeoutError('private SDK details')
        return {'labels': [dict(unit_id=u['unit_id'], grade=2, mismatch=[], reason='direct',
            supports=[dict(question_id='Q1', quote=(
                'neighbor' if len(requests)==1 and u['unit_id']=='bad' else u['text']))])
            for u in payload['units']]}
    result = JudgeSession(tmp_path, model).label(TASK, QUESTIONS, units)
    assert requests == [['good', 'bad'], ['bad'], ['bad']]
    assert len(result) == 2


def test_final_timeout_is_not_hidden_by_old_quote_error(tmp_path, monkeypatch):
    from finmy.search import eval_judge
    monkeypatch.setattr(eval_judge.time, 'sleep', lambda _: None)
    requests = []
    def model(system, payload):
        requests.append(payload)
        if len(requests) > 1:
            raise TimeoutError('private SDK details')
        return {'labels':[dict(unit_id='bad',grade=2,mismatch=[],reason='direct',
            supports=[dict(question_id='Q1',quote='neighbor')])]}
    with pytest.raises(RuntimeError, match='reuse completed work: TimeoutError$'):
        JudgeSession(tmp_path, model).label(TASK, QUESTIONS, [dict(unit_id='bad',text=GOOD)])
    assert len(requests) == 4
    assert 'private SDK details' not in (tmp_path/'calls.jsonl').read_text()


def test_manual_to_auto_reuses_search_and_only_judges_delivered_text(tmp_path):
    settings=options(tmp_path, lambda *a:pytest.fail('manual must not judge'))
    settings.update(eval_mode='manual',eval_scope='selected')
    report=evaluate(TASK,**settings)
    assert report['evaluation_status']=='manual_review_pending' and report['metrics'] is None
    assert report['judge_usage']['calls']==0
    settings.update(eval_mode='auto',judge_model=Judge(),
        search_model=lambda *a:pytest.fail('search must be reused'),
        transport=lambda *a:pytest.fail('search must be reused'))
    graded=evaluate(TASK,**settings)
    assert graded['task_id']==report['task_id']
    assert graded['judged_units']==1
    assert graded['metrics']['material']['evidence_quote_recall_in_saved_pool'] is None
    assert graded['metrics']['material']['atomic_fact_coverage']==.5
    assert graded['metrics']['provider_rankings'] is None


def test_unit_cache_survives_regrouping_and_rejects_changed_context(tmp_path):
    a=dict(unit_id='a',text=GOOD,context_before='Alice said:')
    b=dict(unit_id='b',text=SETTLEMENT)
    first=Judge()
    JudgeSession(tmp_path/'first',first,cache_directory=tmp_path/'shared').label(TASK,QUESTIONS,[a])
    seen=[]
    def model(system,payload):
        seen.append([u['unit_id'] for u in payload['units']])
        return Judge()(system,payload)
    session=JudgeSession(tmp_path/'second',model,cache_directory=tmp_path/'shared')
    session.label(TASK,QUESTIONS,[b,a])
    assert seen==[['b']]
    session.label(TASK,QUESTIONS,[dict(a,context_before='Someone else said:')])
    assert seen[-1]==['a']


def test_unchanged_unit_reuses_label_when_document_version_and_offsets_change(tmp_path):
    a=dict(unit_id='old',source_id='source',version='v1',block=0,start=0,end=len(GOOD),text=GOOD)
    b=dict(a,unit_id='new',version='v2',block=9)
    JudgeSession(tmp_path/'a',Judge(),cache_directory=tmp_path/'shared').label(TASK,QUESTIONS,[a])
    labels=JudgeSession(tmp_path/'b',lambda *a:pytest.fail('unchanged evidence must reuse'),
        cache_directory=tmp_path/'shared').label(TASK,QUESTIONS,[b])
    assert labels['new']['unit_id']=='new'
