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
    max_calls = max(before['config'].get('max_calls', 0), len(before['calls']) + args.extra_calls)
    previous = before['config']
    read_extensions = dict(
        read_call_extension=max(previous.get('read_call_extension', 0),
            len(before['reads']) + args.extra_read_calls - previous['max_read_calls']),
        read_round_extension=max(previous.get('read_round_extension', 0),
            (args.max_read_rounds or previous['max_read_rounds']) - previous['max_read_rounds']),
        read_char_extension=previous.get('read_char_extension', 0) + args.extra_read_chars)
    print(f"恢复 {directory} | 已记录 {len(before['calls'])} 次调用 | 总调用上限 {max_calls} | 复用已完成检查点", flush=True)
    state = run_event(json.loads((directory / 'input.json').read_text()), directory=directory,
        config=dict(timeout=900, stall_timeout=60, max_transport_retries=5, max_calls=max_calls, **read_extensions),
        allow_network=True, resume=True, resume_transport_upgrade=True,
        stop_after_organization=False)
    print(json.dumps({key: state.get(key) for key in
        ('execution_status', 'result_status', 'output', 'checks', 'reason')}, ensure_ascii=False))
    print('复用阶段：', ', '.join(name for name, info in state.get('stages', {}).items() if info.get('reused')))


if __name__ == '__main__':
    main()
