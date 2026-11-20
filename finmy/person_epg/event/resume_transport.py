"""Resume an existing event run after the transport guard upgrade."""
import argparse
import fcntl
import json
import os
from pathlib import Path

from .build import run_event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='Existing run directory; input.json is read from it')
    parser.add_argument('--allow-model', action='store_true')
    parser.add_argument('--extra-calls', type=int, default=60,
                        help='Available calls beyond those already spent (default 60)')
    args = parser.parse_args(argv)
    if args.extra_calls < 1:
        parser.error('--extra-calls must be positive')
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
    max_calls = max(before['config'].get('max_calls', 0), len(before['calls']) + args.extra_calls)
    print(f"恢复 {directory} | 已记录 {len(before['calls'])} 次调用 | 总调用上限 {max_calls} | 复用已完成检查点", flush=True)
    state = run_event(json.loads((directory / 'input.json').read_text()), directory=directory,
        config=dict(timeout=900, stall_timeout=60, max_transport_retries=5, max_calls=max_calls),
        allow_network=True, resume=True, resume_transport_upgrade=True,
        stop_after_organization=False)
    print(json.dumps({key: state.get(key) for key in
        ('execution_status', 'result_status', 'output', 'checks', 'reason')}, ensure_ascii=False))
    print('复用阶段：', ', '.join(name for name, info in state.get('stages', {}).items() if info.get('reused')))


if __name__ == '__main__':
    main()
