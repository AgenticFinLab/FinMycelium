"""Run the existing search workflow, then evaluate its saved original material.

Usage: python -m finmy.search.eval --task buffett_goldman.json
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .control import task_lock
from .eval_judge import JUDGE_VERSION, KIMI_MODEL, JudgeSession
from .eval_metrics import evaluate_metrics, merge_ranges, material_metrics
from .pipeline import _run_search
from .sources import SourceStore, canonical_url
from .state import SearchConfig, SearchState, digest, now, write_json
from .tools import ENDPOINTS, normalize


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    lines = path.read_text(encoding='utf-8').splitlines()
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines)-1:
                raise
            # An interrupted append may leave only the final line incomplete.
    return rows


def default_config():
    # Only this new CLI chooses Kimi. Existing Workbench defaults are untouched.
    return SearchConfig(lm_name=KIMI_MODEL, allow_network=True,
                        generation_config={'max_tokens':8192, 'reasoning_effort':'low'})


def search_fingerprint():
    directory = Path(__file__).resolve().parent
    return digest({p.relative_to(directory).as_posix():digest(p.read_bytes())
                   for p in directory.rglob('*.py') if not p.name.startswith('eval')})


def _selected_ranges(state, selection, payload):
    store = SourceStore(state)
    result = {}
    handed_sources = {s['raw_data_id'] for s in payload.get('samples', [])}
    for entry in selection.get('selected', []):
        sid, version = entry['source_id'], entry['version']
        if sid not in handed_sources:
            raise ValueError('Selection does not match the saved search payload')
        document = store.document(sid, version)
        if 'ranges' in entry:
            ranges = entry['ranges']
        elif 'blocks' in entry:
            if any(type(i) is not int or not 0 <= i < len(document['blocks']) for i in entry['blocks']):
                raise ValueError('Invalid saved selection block')
            ranges = [dict(block=i, start=0, end=len(document['blocks'][i]['text']))
                      for i in entry['blocks']]
        else:
            ranges = [entry]
        for item in ranges:
            i, start, end = item['block'], item['start'], item['end']
            if (any(type(n) is not int for n in (i, start, end))
                    or not 0 <= i < len(document['blocks'])
                    or not 0 <= start < end <= len(document['blocks'][i]['text'])):
                raise ValueError('Invalid saved selection range')
            result.setdefault((sid, version, i), []).append((start, end))
    return {key:merge_ranges(value) for key, value in result.items()}


def collect_pool(state, selection, payload):
    """Read all acquired bodies, including unread and excluded candidates.

    Evaluation windows are views of original offsets. They never rewrite parsing,
    reading history, selected text or the search algorithm's own chunks.
    """
    store = SourceStore(state)
    selected = _selected_ranges(state, selection, payload)
    wanted = {(sid, entry['version']) for sid, entry in state.data['sources'].items()
              if entry.get('version') and entry['status'] in {'success', 'partial'}}
    wanted.update((sid, version) for sid, version, _ in selected)
    units = []
    for sid, version in sorted(wanted):
        entry = state.data['sources'][sid]
        document = store.document(sid, version)
        for i, block in enumerate(document['blocks']):
            text = block['text']
            # Bounded evaluation-only views, with nearby originals for attribution.
            for start in range(0, len(text), 2000):
                end = min(len(text), start+2000)
                if not text[start:end].strip():
                    continue
                previous = text[max(0, start-400):start] if start else (
                    document['blocks'][i-1]['text'][-400:] if i else '')
                following = text[end:end+400] if end < len(text) else (
                    document['blocks'][i+1]['text'][:400] if i+1 < len(document['blocks']) else '')
                unit_id = digest([sid, version, i, start, end])[:24]
                units.append(dict(unit_id=unit_id, source_id=sid, version=version,
                    url=entry['url'], title=entry.get('title', ''),
                    source_status=document['status'], block=i, start=start, end=end,
                    locator={k:v for k, v in block.items() if k != 'text'},
                    text=text[start:end], context_before=previous, context_after=following))
    return units, selected


def selected_units(units, ranges):
    """Judge only exact delivered text; unseen context cannot earn support."""
    result = []
    for u in units:
        for a,b in ranges.get((u['source_id'],u['version'],u['block']), []):
            start,end=max(a,u['start']),min(b,u['end'])
            if start>=end: continue
            item=dict(u, start=start, end=end, text=u['text'][start-u['start']:end-u['start']])
            item['unit_id']=digest([u['source_id'],u['version'],u['block'],start,end])[:24]
            result.append(item)
    return result


def batches(units):
    """Stable source/order-independent batches bound prompt and output size."""
    batch, chars = [], 0
    for unit in sorted(units, key=lambda u:u['unit_id']):
        size = len(json.dumps(unit, ensure_ascii=False))
        if batch and (len(batch) >= 10 or chars+size > 22000):
            yield batch
            batch, chars = [], 0
        batch.append(unit)
        chars += size
    if batch:
        yield batch


def provider_rankings(state):
    result = []
    directory = state.run_dir/'responses'
    paths = sorted(directory.glob('*.json'), key=lambda p:int(p.stem))
    for path in paths:
        record = read_json(path)
        provider, request = record['provider'], record['request']
        items = normalize(provider, record['response'])[:state.config.results_for(provider)]
        ids = [digest(canonical_url(item['url']))[:24] for item in items]
        query = request['messages'][0]['content'] if provider == 'baidu' else request['query']
        result.append(dict(request_id=path.stem, provider=provider, query=query,
                           source_ids=list(dict.fromkeys(ids))))
    return result


def usage_totals(rows):
    result = dict(calls=0, reported_usage_calls=0, input_tokens=0,
                  cached_input_tokens=0, output_tokens=0, total_tokens=0,
                  request_seconds=0.0)
    for row in rows:
        result['calls'] += 1
        result['request_seconds'] += row.get('duration_seconds', 0) or 0
        usage = row.get('usage')
        if not isinstance(usage, dict):
            continue
        result['reported_usage_calls'] += 1
        prompt = usage.get('prompt_tokens', usage.get('input_tokens', 0)) or 0
        completion = usage.get('completion_tokens', usage.get('output_tokens', 0)) or 0
        details = usage.get('prompt_tokens_details') or usage.get('input_tokens_details') or {}
        result['input_tokens'] += prompt
        result['cached_input_tokens'] += details.get('cached_tokens', 0) or 0
        result['output_tokens'] += completion
        result['total_tokens'] += usage.get('total_tokens', prompt+completion) or 0
    return result


def search_usage(state):
    trace = read_jsonl(state.run_dir/'trace.jsonl')
    # Failed completions sometimes expose usage without a model_response record.
    calls = [row for row in trace if row['action'] in {'model_response', 'rerank_response'} or
             (row['action'] == 'action_error' and row.get('usage')
              and not row.get('usage_recorded_in_response'))]
    usage = usage_totals(calls)
    usage['reranking'] = usage_totals([r for r in trace if r['action'] == 'rerank_response'])
    embeddings = [r for r in trace if r['action'] == 'embedding_batch']
    usage['embedding'] = dict(batches=len(embeddings), texts=sum(r['count'] for r in embeddings), seconds=sum(r['duration_seconds'] for r in embeddings))
    usage['attempted_model_calls'] = state.data['usage']['model']
    usage['provider_requests'] = state.data['usage']['search']
    usage['provider_seconds'] = sum(r.get('duration_seconds', 0) or 0 for r in trace
                                    if r['action'] == 'provider_result')
    usage['read_seconds'] = sum(r.get('duration_seconds', 0) or 0 for r in trace
                                if r['action'] == 'read_source')
    return usage


class ProgressModel:
    def __init__(self, model, emit):
        self.model, self.emit = model, emit

    def __getattr__(self, name):
        return getattr(self.model, name)

    def __call__(self, context):
        self.emit('[search] phase=%s, candidates=%s, remaining model calls=%s' % (
            context['phase'], len(context['sources']), context['remaining']['model']))
        return self.model(context)


def evaluate(task, *, root='output/search-eval', config=None, output=None, fresh=False,
             search_model=None, transport=None, fetcher=None, judge_model=None, emit=print,
             eval_mode="manual", eval_scope="selected"):
    if eval_mode not in {'manual','auto'} or eval_scope not in {'selected','pool'}:
        raise ValueError('eval_mode must be manual/auto; eval_scope must be selected/pool')
    config = config or default_config()
    if isinstance(config, dict):
        config = SearchConfig(**config)
    if task.get('target_type') not in {'event', 'person', 'company'} or any(
            not isinstance(task.get(k), str) or not task[k].strip()
            for k in ('target_name', 'query_text')):
        raise ValueError('Task needs target_type, target_name and query_text')
    fingerprint = search_fingerprint()
    task_id = 'eval-' + digest(dict(task=task, config=asdict(config), search_code=fingerprint))[:16]
    if fresh:
        task_id += '-' + uuid.uuid4().hex[:8]
    root = Path(root).resolve()
    directory = root/task_id
    output = Path(output).resolve() if output else directory/'output.json'
    # Keep a custom report from overwriting the original task/checkpoints/sources.
    if output == directory or (directory in output.parents and output != directory/'output.json'):
        raise ValueError('Inside the task directory the report must be named output.json')
    started = time.monotonic()
    repo = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                         stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    report = dict(schema='search-eval-1', status='searching', created_at=now(),
                  task_id=task_id, task=task, git_commit=commit, search_code_sha256=fingerprint,
                  search_config=asdict(config), judge_model=KIMI_MODEL,
                  evaluation_version=JUDGE_VERSION, eval_mode=eval_mode, eval_scope=eval_scope, output=str(output))
    session = None
    # Same coordinator and lock as Workbench; no Builder imports or calls.
    with task_lock(root, task_id):
        write_json(output, report)
        try:
            if search_model is None:
                from .agent import LmbaseModel
                search_model = LmbaseModel(config)
            emit('[search] ' + task['target_name'])
            result = _run_search(task, root=root, task_id=task_id, config=config,
                model=ProgressModel(search_model, emit), transport=transport, fetcher=fetcher)
            state = SearchState(root, task_id)
            payload = read_json(state.run_dir/'builder_input.json', {'samples':[]})
            selection = read_json(state.run_dir/'selection.json', {})
            units, selected_ranges = collect_pool(state, selection, payload)
            rankings = provider_rankings(state)
            candidates = [dict(source_id=sid, **{k:e[k] for k in
                ('url', 'title', 'status', 'version', 'discoveries', 'fetch_error') if k in e})
                for sid, e in state.data['sources'].items()]
            report.update(search=dict(result=result, usage=search_usage(state),
                stop_reason=state.data.get('stop_reason'), stop_detail=state.data.get('stop_detail'),
                gaps=selection.get('gaps', []), selection=selection,
                final_material=payload, candidate_sources=candidates,
                actions=state.data.get('actions', [])),
                reference_passages=units, pool=dict(
                    candidates=len(candidates), acquired_sources=len({u['source_id'] for u in units}),
                    annotation_units=len(units), body_chars=sum(len(u['text']) for u in units),
                    unacquired_source_ids=sorted(set(state.data['sources'])-{u['source_id'] for u in units})))
            if result['status'] not in {'finished', 'insufficient'}:
                report['status'] = 'search_incomplete'
                emit('[search] stopped with %s; same command resumes saved work' % result['status'])
                return report
            report['selected_passages'] = selected_units(units, selected_ranges)
            bodies = [' '.join(u['text'].split()) for u in report['selected_passages']]
            total = sum(map(len, bodies))
            report['material_stats'] = dict(selected_body_chars=sum(len(u['text']) for u in report['selected_passages']),
                selected_units=len(bodies), exact_duplicate_text_fraction=(1-sum(map(len,set(bodies)))/total) if total else None)
            report['fact_checks'] = state.data.get('fact_checks', [])
            report['source_lead_review'] = state.data.get('source_lead_review', [])
            if eval_mode == 'manual':
                report.update(status='finished', judgments={}, metrics=None,
                    evaluation_status='manual_review_pending',
                    review_instructions='Assess entity/attribute relevance, personal attribution, atomic fact coverage, conditions, planned versus completed actions and missing originals. Pool evidence is available for checking omissions.')
                return report
            report.update(status='judging', judgments={}, metrics=None)
            write_json(output, report)  # Search output survives a subsequent judge failure.
            if not units:
                report.update(status='no_acquired_evidence')
                return report
            session = JudgeSession(directory/'judge', judge_model, cache_directory=root/'judge-cache')
            report['questions'] = session.questions(task)
            judged = report['selected_passages'] if eval_scope == 'selected' else units
            groups = list(batches(judged))
            for index, group in enumerate(groups, 1):
                emit('[judge] %s/%s batches (%s passages)' % (index, len(groups), len(group)))
                report['judgments'].update(session.label(task, report['questions'], group))
                report['judged_units'] = len(report['judgments'])
                write_json(output, report)
            versions = {sid:e.get('version') for sid, e in state.data['sources'].items()}
            if eval_scope == 'pool':
                report['metrics'] = evaluate_metrics(units, report['judgments'], selected_ranges,
                                                      report['questions'], rankings, versions)
            else:
                material = material_metrics(judged, report['judgments'], selected_ranges, report['questions'])
                for key in ('evidence_quote_recall_in_saved_pool','reference_evidence_quotes',
                            'question_coverage_in_saved_pool','missed_supported_question_ids',
                            'questions_without_pool_support'):
                    material[key] = None
                report['metrics'] = dict(material=material, scope='selected',
                    provider_rankings=None, provider_macro_at=None,
                    note='Selected originals only: no candidate-pool recall or provider ranking estimates.')
            report['evaluation_status'] = 'judged'
            report['status'] = 'finished'
            return report
        except BaseException as exc:
            report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                          error_type=type(exc).__name__)
            # Persist any search artifacts even when transport/configuration failed.
            state_file = directory/'runs'/'initial'/'run.json'
            if state_file.exists() and 'search' not in report:
                state = SearchState(root, task_id)
                report['search'] = dict(status=state.data['status'], usage=search_usage(state),
                    final_material=read_json(state.run_dir/'builder_input.json', {'samples':[]}),
                    candidate_sources=state.data['sources'])
            raise
        finally:
            report['invocation_seconds'] = time.monotonic()-started
            report['updated_at'] = now()
            report['judge_usage'] = usage_totals(read_jsonl(directory/'judge'/'calls.jsonl'))
            report['judge_cache_hits_this_invocation'] = session.cache_hits if session else 0
            write_json(output, report)
            emit('[output] ' + str(output))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True, help='Research task JSON, e.g. buffett_goldman.json')
    parser.add_argument('--output', help='Optional combined output JSON path')
    parser.add_argument('--config', help='Optional existing SearchConfig JSON/YAML; default uses Kimi')
    parser.add_argument('--eval_mode', choices=['manual','auto'], default='manual')
    parser.add_argument('--eval_scope', choices=['selected','pool'], default='selected', help='auto only: delivered text or full saved candidate pool')
    parser.add_argument('--fresh', action='store_true', help='Start a new run instead of resuming this task/config')
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2]/'.env', override=False)
    try:
        if args.output and any(Path(args.output).resolve() == Path(p).resolve()
                               for p in (args.task, args.config) if p):
            raise ValueError('Output must not overwrite the task or configuration file')
        task = json.loads(Path(args.task).read_text(encoding='utf-8-sig'))
        if not isinstance(task, dict):
            raise ValueError('Task JSON must contain one research task object')
        config = default_config()
        if args.config:
            import yaml
            values = yaml.safe_load(Path(args.config).read_text(encoding='utf-8-sig'))
            if not isinstance(values, dict):
                raise ValueError('Search configuration must be an object')
            config = SearchConfig(**{**asdict(config), **values, 'allow_network':True})
        from finmy.model_config import api_key_variable, model_name
        required = {api_key_variable(model_name(config.lm_name).split('/', 1)[0])}
        if args.eval_mode == 'auto': required.add('ARK_API_KEY')
        required.update(ENDPOINTS[p][1] for p in config.providers)
        missing = sorted(k for k in required if not os.environ.get(k))
        if missing:
            raise ValueError('Set these existing .env entries: ' + ', '.join(missing))
        report = evaluate(task, config=config, output=args.output, fresh=args.fresh,
                          eval_mode=args.eval_mode, eval_scope=args.eval_scope)
        if report.get('metrics'):
            material = report['metrics']['material']
            print(json.dumps(dict(status=report['status'],
                question_coverage=material['question_coverage'],
                evidence_quote_recall=material['evidence_quote_recall_in_saved_pool'],
                topic_mismatch_rate=material['topic_mismatch_rate']), ensure_ascii=False))
        else:
            print(json.dumps(dict(status=report['status'], eval_mode=args.eval_mode,
                evaluation_status=report.get('evaluation_status')), ensure_ascii=False))
        return 0 if report['status'] == 'finished' else 2
    except KeyboardInterrupt:
        print('Interrupted; rerun the same command to resume.', file=sys.stderr)
        return 130
    except Exception as exc:
        detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        print('Search eval: ' + detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
