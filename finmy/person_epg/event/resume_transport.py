"""Resume an existing event run after the transport guard upgrade."""
import argparse
import fcntl
import json
import os
from pathlib import Path

from .build import run_event
from .config import resume_settings, budget_summary
from .artifacts import print_artifact_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='Existing run directory; input.json is read from it')
    parser.add_argument('--allow-model', action='store_true')
    parser.add_argument('--extra-calls', type=int, default=60,
                        help='Available calls beyond those already spent (default 60)')
    parser.add_argument('--extra-read-calls', type=int, default=0,
                        help='Ensure this many additional read deliveries remain')
    parser.add_argument('--max-read-rounds', type=int, default=None,
                        help='Raise the total read rounds per task without resetting completed rounds')
    parser.add_argument('--extra-read-chars', type=int, default=0,
                        help='Increase the current unique-character budget by this amount')
    args = parser.parse_args(argv)
    if args.extra_calls < 1:
        parser.error('--extra-calls must be positive')
    if args.extra_read_calls < 0 or args.extra_read_chars < 0 or (args.max_read_rounds is not None and args.max_read_rounds < 0):
        parser.error('Read budgets cannot be negative')
    directory = args.run.resolve()
    if not args.allow_model:
        parser.error('Resume requires --allow-model')
    if not (directory / 'state.json').is_file() or not (directory / 'input.json').is_file():
        parser.error('Choose the existing output run directory containing state.json and input.json')
    # Do not silently wait behind the old process's run lock.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('The old process is still running. Stop it first; keep this directory intact.')
    finally:
        os.close(fd)
    (directory / 'pause_requested').unlink(missing_ok=True)
    before = json.loads((directory / 'state.json').read_text())
    settings = resume_settings(before, extra_calls=args.extra_calls, extra_read_calls=args.extra_read_calls,
        max_read_rounds=args.max_read_rounds, extra_read_chars=args.extra_read_chars)
    effective = budget_summary({**before, 'config': {**before['config'], **settings}})
    print(f"恢复 {directory} | 复用已完成检查点 | 有效预算 " + json.dumps(effective, ensure_ascii=False), flush=True)
    state = run_event(json.loads((directory / 'input.json').read_text()), directory=directory,
        config=settings,
        allow_network=True, resume=True, resume_transport_upgrade=True,
        stop_after_organization=False)
    print(json.dumps({key: state.get(key) for key in
        ('execution_status', 'result_status', 'output', 'checks', 'reason')}, ensure_ascii=False))
    print('复用阶段：', ', '.join(name for name, info in state.get('stages', {}).items() if info.get('reused')))
    print_artifact_summary(state, directory)


if __name__ == '__main__':
    main()
