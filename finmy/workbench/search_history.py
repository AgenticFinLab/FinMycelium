"""Read-only projection of search traces; never loads credentials or executes a task."""
import json
from pathlib import Path

LABELS = {'search': '搜索', 'read_source': '阅读来源', 'finish': '整理交接', 'model': '模型决策'}


def budget_policy_label(selection):
    """Describe saved policies without changing their recorded identifiers."""
    from finmy.search.budget import BUDGET_POLICY
    # Persisted identifiers from older runs remain readable as descriptive labels.
    labels = {
        BUDGET_POLICY: '材料预算分配（来源配额与共享余量）',
        'balanced_source_windows_v1': '材料预算分配（来源配额与共享余量）',
        'c2_base_shared_bm25_windows_v1': '材料预算分配（来源配额与共享余量）',
        'source_order_complete_paragraphs': '按来源顺序保留完整段落',
        'fair_source_quotas_bm25_windows': '按来源配额选取原文段落',
    }
    return labels.get(selection.get('budget_policy'),
                      '按片段组装' if selection.get('mode') != 'sources' else '已保存策略，详见记录')


def read_trace(run_dir):
    path = Path(run_dir) / 'trace.jsonl'
    if not path.exists():
        return [], 0
    events, incomplete = [], 0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('not an event')
                events.append(event)
            except (ValueError, TypeError):
                # A concurrent append may not yet have written its final newline.
                incomplete += 1
    return events, incomplete


def timeline(events, data):
    rows, current, model_number, seen = [], None, 0, set()

    def new(event, kind='model', number=None):
        row = dict(step=len(rows) + 1, time=event.get('time'), action=kind,
                   model_call=number, status='waiting', providers=[], errors=[],
                   usage=None, duration=None)
        rows.append(row)
        return row

    for event in events:
        kind = event.get('action')
        if kind == 'model_started':
            model_number = event.get('model_call', model_number + 1)
            current = new(event, number=model_number)
        elif kind == 'model_response':
            if current is None or current['status'] != 'waiting' or current.get('decision') is not None:
                model_number += 1
                current = new(event, number=event.get('model_call', model_number))
            current['usage'] = event.get('usage')
            current['duration'] = event.get('duration_seconds')
            try:
                action = event.get('response')
                action = json.loads(action) if isinstance(action, str) else action
                if not isinstance(action, dict):
                    raise ValueError('not an action')
                # Only the public action decision, never internal model reasoning.
                current['decision'] = {k: action[k] for k in ('action', 'query', 'gap', 'source', 'location', 'source_ids', 'gaps', 'reason', 'reason_detail') if k in action}
                current['action'] = action.get('action', 'model')
                for key in ('query', 'gap', 'source', 'location', 'source_ids', 'gaps', 'reason', 'reason_detail'):
                    if key in action:
                        current[key] = action[key]
                selected = action.get('source_ids', action.get('selections', action.get('evidence_ids', [])))
                current['selection_unit'] = '份来源' if 'source_ids' in action else '段'
                current['selected_count'] = len(selected) if isinstance(selected, list) else 0
            except (ValueError, TypeError):
                current['action'] = 'model'
                current['decision'] = {}
        elif kind == 'provider_started':
            if current is None or current['status'] != 'waiting':
                current = new(event, 'search')
            current['action'] = 'search'
            current['query'] = event.get('query', '')
            current['pending_provider'] = event.get('provider')
            current['pending_since'] = event.get('time')
        elif kind == 'provider_result':
            if current is not None:
                current['providers'].append({k: event.get(k) for k in ('provider', 'status', 'result_count', 'error_type', 'duration_seconds')})
                current.pop('pending_provider', None)
                current.pop('pending_since', None)
        elif kind == 'read_started':
            if current is None or current['status'] != 'waiting':
                current = new(event, 'read_source')
            current.update(action='read_source', source=event.get('source'), location=event.get('location'))
            if event.get('query') is not None:
                current['query'] = event['query']
        elif kind in {'search', 'read_source'}:
            if current is None or current['status'] != 'waiting':
                current = new(event, kind)
            current['action'] = kind
            current['status'] = 'completed'
            result = event.get('result', {})
            if kind == 'search':
                current['query'] = event.get('query', '')
                ids = set(result.get('source_ids', []))
                current.update(candidate_count=len(ids), new_count=len(ids-seen), source_ids=list(result.get('source_ids', [])))
                seen.update(ids)
                details = {p['provider']: p for p in current['providers']}
                current['providers'] = [{**details.get(p['provider'], {}), **p} for p in result.get('providers', [])]
                if any(p.get('status') in {'failed', 'limit'} for p in current['providers']):
                    current['status'] = 'warning'
            else:
                current.update(source=event.get('source'), read_status=result.get('status'),
                               chars=sum(len(s.get('text', '')) for s in result.get('spans', [])),
                               span_count=len(result.get('spans', [])), next_location=result.get('next_location'),
                               at_end=result.get('at_end_of_saved_text'), reading=result.get('reading'),
                               read_duration=event.get('duration_seconds'), spans=result.get('spans', []))
                if result.get('error_type'):
                    current['errors'].append({'error': result['error_type']})
                    current['status'] = 'error'
                elif not result.get('spans'):
                    current['status'] = 'warning'
        elif kind in {'action_error', 'action_limited'}:
            if current is None or current['status'] != 'waiting':
                model_number += 1
                current = new(event, number=event.get('model_call', model_number))
            current['status'] = 'error' if kind == 'action_error' else 'warning'
            current['errors'].append(event.get('error', {}))
        elif kind == 'action_completed':
            if current is not None and current['action'] == 'finish':
                current['status'] = 'completed'
                current['sample_count'] = event.get('sample_count')
    for previous in rows[:-1]:
        if previous['status'] == 'waiting':
            previous['status'] = 'unconfirmed'
    if rows and rows[-1]['status'] == 'waiting':
        last = rows[-1]
        if last['action'] == 'finish' and data.get('selection') is not None and data.get('status') in {'finished', 'insufficient'}:
            last['status'] = 'completed'
        elif data.get('status') != 'running':
            last['status'] = 'unconfirmed'
    return rows


def experiment_runs(repo):
    """Only discover existing local experiment records; do not import or mutate them."""
    base = Path(repo) / '.local-experiments' / 'search-enhancement'
    found = []
    if base.exists():
        for path in sorted(base.glob('*/runtime/*/runs/initial/run.json'), reverse=True):
            if not path.resolve().is_relative_to(base.resolve()):
                continue
            try:
                data = json.loads(path.read_text())
                name = data['task']['target_name']
            except (ValueError, KeyError, OSError):
                continue
            task_dir = path.parents[2]
            found.append(dict(label=f'{path.parents[4].name} · {name}', root=task_dir.parent,
                              task_id=task_dir.name))
    return found
