"""Read-only diagnostics: python -m finmy.person_epg.event.status RUN [--json]."""
import argparse
import json
from pathlib import Path

from .artifacts import artifact_summary, print_artifact_summary
from .config import budget_summary
from .diagnostics import failure_details


def usage_by_stage(calls):
    """Provider-reported tokens only; unknown usage is never estimated as zero."""
    names = {'extract': 'extraction', 'consolidate': 'consolidation',
             'organize': 'organization', 'relate': 'relations',
             'supplement': 'corpus_supplement', 'repair': 'validation'}
    stages = {}
    for call in calls:
        if not call.get('started_at') and call.get('usage_status') != 'reported':
            continue
        task = call.get('task_id', '')
        stage = names.get(task.split('.')[0], task.split('.')[0])
        row = stages.setdefault(stage, dict(requests=0, reported=0, unknown=0,
            input_tokens=0, output_tokens=0, cached_input_tokens=0,
            transport_retries=0, format_retries=0, adoption_corrections=0))
        row['requests'] += 1
        if call.get('retry_of'):
            row['transport_retries'] += 1
        if call.get('retry_kind') == 'format':
            row['format_retries'] += 1
        if call.get('retry_kind') == 'adoption':
            row['adoption_corrections'] += 1
        usage = call.get('usage')
        if not isinstance(usage, dict) or not all(isinstance(usage.get(k), int)
                for k in ('prompt_tokens', 'completion_tokens')):
            row['unknown'] += 1
            continue
        row['reported'] += 1
        row['input_tokens'] += usage['prompt_tokens']
        row['output_tokens'] += usage['completion_tokens']
        cache = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        if isinstance(cache, int):
            row['cached_input_tokens'] += cache
    return stages


def inspect_run(directory):
    directory = Path(directory)
    state = json.loads((directory / 'state.json').read_text())
    prefix = 'attempts/' + str(state['attempts']).zfill(4) + '/'
    errors = []
    for call in state.get('calls', []):
        if call.get('status') not in ('transport_error', 'incomplete') or not call.get('response_path', '').startswith(prefix):
            continue
        details = call.get('failure') or failure_details(transport=call.get('transport', call),
            task_id=call['task_id'], call_id=call['call_id'])
        errors.append(details)
    return dict(run=str(directory.resolve()), latest_attempt=dict(attempt=state['attempts'],
        execution_status=state.get('execution_status'), result_status=state.get('result_status'),
        reason=state.get('reason'), output=state.get('output')),
        budgets=budget_summary(state), stages=state.get('stages', {}),
        usage_by_stage=usage_by_stage(state.get('calls', [])),
        limited_tasks=[dict(task_id=key, reason=value.get('reason'))
                       for key, value in state.get('task_states', {}).items() if value.get('status') == 'limited'],
        errors=errors, **artifact_summary(directory))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--json', action='store_true', help='Print structured diagnostics')
    args = parser.parse_args(argv)
    summary = inspect_run(args.run)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    attempt = summary['latest_attempt']
    print(f"本次 attempt={attempt['attempt']} | {attempt['execution_status']} | {attempt['result_status']}")
    if attempt['reason']:
        print('原因：' + attempt['reason'])
    budget = summary['budgets']
    for key in ('model_calls', 'read_calls', 'read_chars'):
        used = budget[key]['used'] if budget[key]['used'] is not None else 'unknown'
        print(f"{key}: {used} / {budget[key]['limit']}")
    print(f"read_rounds: 单任务最多已用 {budget['read_rounds']['max_used']} / {budget['read_rounds']['limit_per_task']}")
    print(f"timeout={budget['timeout']}s | stall={budget['stall_timeout']}s | retries={budget['retries']} | workers={budget['workers']}")
    from .scheduling import metrics_text
    for stage, record in summary['stages'].items():
        if record.get('metrics'):
            print(stage + ' | ' + metrics_text(record['metrics']).replace('\n', ' | '))
    for stage, usage in summary['usage_by_stage'].items():
        print(f"{stage} tokens: 输入 {usage['input_tokens']}（缓存 {usage['cached_input_tokens']}）"
              f" | 输出 {usage['output_tokens']} | 调用 {usage['requests']}"
              f" | usage未知 {usage['unknown']} | 传输重试 {usage['transport_retries']}"
              f" | 格式重试 {usage['format_retries']} | 语义纠错 {usage['adoption_corrections']}")
    for task in summary['limited_tasks']:
        print('受限：' + task['task_id'] + ' | ' + str(task['reason']))
    for error in summary['errors']:
        print('错误：' + error['summary'] + ' | retryable=' + str(error['retryable']))
    print_artifact_summary(summary, args.run)


if __name__ == '__main__':
    main()
