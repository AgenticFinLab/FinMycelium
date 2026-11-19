"""Offline scheduler check over a real frozen input; no model API and no pytest."""
import argparse
import json
from pathlib import Path

from .records import seed_facts
from .runtime import EventBuildConfig, Execution, write_json
from .scheduling import Task


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding='utf-8'))
    facts = seed_facts(payload)
    sample = next(s for s in payload['samples'] if s['content'])

    def model(system, user, task_id):
        incoming = json.loads(user)
        if task_id == 'smoke.timeout':
            raise TimeoutError('Simulated timeout')
        if task_id == 'smoke.limit' or (task_id == 'smoke.read' and not incoming['read_results']):
            return dict(read_requests=[dict(tool='read_sample', sample_id=sample['sample_id'],
                start=0, end=min(20, len(sample['content'])))])
        if task_id == 'smoke.read':
            assert incoming['read_results'][0]['result']['text'] == sample['content'][:20]
        return dict(ok=True)

    def validate(value):
        if value != dict(ok=True):
            raise ValueError('Expected ok=true')

    run = Execution(args.output, payload, EventBuildConfig(extraction_workers=2), model)
    names = ['smoke.timeout', 'smoke.read', 'smoke.limit', 'smoke.success']
    outcomes = run.execute_tasks('smoke', [Task(name,
        run.infer_steps(name, 'Offline transport fixture', {}, facts, validate)) for name in names])
    states = {name: run.state['task_states']['smoke:' + name]['status'] for name in names}
    assert states == dict(zip(names, ['failed', 'succeeded', 'limited', 'succeeded']))
    assert len(run.state['calls']) == 7
    assert run.state['task_states']['smoke:smoke.limit']['reason'] == 'read_rounds'
    assert len([r for r in run.state['reads'] if r['task_id'] == 'smoke.limit']) == 2
    assert outcomes['smoke.read'].result == dict(ok=True)
    report = dict(passed=True, model_api_calls=0, tasks=states,
                  max_read_rounds=run.config.max_read_rounds, timeout=run.config.timeout,
                  response_calls=len(run.state['calls']), reads=len(run.state['reads']))
    write_json(args.output / 'smoke-report.json', report)
    run.state.update(execution_status='finished', result_status='partial')
    run.persist()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
