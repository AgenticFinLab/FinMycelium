"""Search-only CLI. Default performs local validation, never executes services."""
import argparse
import json
from pathlib import Path
from .pipeline import run_search
from .state import SearchConfig, SearchState


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',help='JSON research task; omit when resuming')
    parser.add_argument('--config',help='YAML search configuration')
    parser.add_argument('--task-id',required=True)
    parser.add_argument('--root',default='output/search')
    parser.add_argument('--run-id',default='initial')
    parser.add_argument('--steps',type=int,help='Pause after this many model actions')
    parser.add_argument('--execute',action='store_true',help='Explicitly permit search/model/network requests')
    args=parser.parse_args(argv)
    task=json.loads(Path(args.task).read_text()) if args.task else None
    config=None
    if args.config:
        import yaml
        config=SearchConfig(**yaml.safe_load(Path(args.config).read_text()))
    if not args.execute:
        # Validate without creating a run whose configuration could obstruct execution.
        if task is None:
            path=Path(args.root)/args.task_id/'runs'/args.run_id/'run.json'
            data=json.loads(path.read_text())
            print(json.dumps({'status':data['status'],'usage':data['usage']},ensure_ascii=False))
        else:
            if task.get('target_type') not in {'event','person','company'} or any(
                not isinstance(task.get(k),str) or not task[k].strip() for k in ('target_name','query_text')):
                raise ValueError('Invalid research task')
            print(json.dumps({'status':'preflight_only','online_verified':False,
                              'providers':(config or SearchConfig()).providers}))
        return 0
    if config is None and task is not None:
        raise ValueError('Execution requires an explicit search configuration')
    if config is not None:
        config.allow_network=True
    result=run_search(task,root=args.root,task_id=args.task_id,run_id=args.run_id,
                      config=config,max_steps=args.steps)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status'] in {'finished','paused'} else 1


if __name__=='__main__':
    raise SystemExit(main())
