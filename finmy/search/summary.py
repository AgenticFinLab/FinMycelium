"""Deterministic, lightweight catalog summaries; originals remain in the runtime."""
from contextlib import contextmanager
import fcntl
import html
import json
import os
from pathlib import Path
import re
import tempfile

from finmy.dataset import within
from .state import SearchState, digest, now

BEGIN = '<!-- finmy-search-summary:start -->'
END = '<!-- finmy-search-summary:end -->'
TERMINAL = {'finished', 'insufficient', 'limit', 'failed'}


def cell(value):
    return html.escape(' '.join(str(value or '').split()), quote=False).replace('|', '\\|')


def atomic_text(path, text):
    """Replace only after a complete write, cleaning temporary files on failure."""
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def directory_lock(path):
    # A directory inode is stable across atomic file replacement. No lockfile in Git.
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def managed(text):
    if BEGIN not in text and END not in text:
        return '', '', '\n\n## Human notes\n\n' + text.strip() + '\n'
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise ValueError('检索汇总的自动生成区域标记不完整；原文件已保留')
    before, rest = text.split(BEGIN, 1)
    body, after = rest.split(END, 1)
    return before, body.strip(), after


def history(body):
    section = body.split('## Search runs\n', 1)[-1] if '## Search runs\n' in body else ''
    rows = {}
    for line in section.splitlines():
        if not line.startswith('|'): continue
        parts = [html.unescape(v.strip().replace('\\|', '|')) for v in re.split(r'(?<!\\)\|', line.strip('|'))]
        if len(parts) == 5 and re.fullmatch(r'[A-Za-z0-9_-]+', parts[1]) and parts[0].startswith('20'):
            rows[parts[1]] = parts
    return rows


def render(data, task_id, selection, payload):
    task = data['task']; catalog = task['catalog']; scope = task['research_scope']
    stamp = data.get('handoff_updated_at') or data.get('completed_at') or data['updated_at']
    handoff = data.get('handoff_revision') or ('input-' + digest(payload)[:16] if payload else '')
    used = {s['raw_data_id'] for s in (payload or {}).get('samples', [])}
    saved = sum(s.get('status') in {'success', 'partial'} and bool(s.get('version')) for s in data['sources'].values())
    config = data['config']; usage = data['usage']
    rows = [f"# Search summary: {cell(catalog['event_name'])}", '',
            f"- Event ID: {cell(catalog['event_id'])}",
            f"- Activity period: {cell(scope['period']) or 'Unspecified'}",
            f"- Included: {cell(scope['include'])}", f"- Excluded: {cell(scope['exclude']) or 'Unspecified'}"]
    if catalog['kind'] == 'person_event':
        rows += [f"- Person: {cell(catalog['person_name'])} ({cell(catalog['person_id'])})",
                 f"- Storyline: {cell(catalog['storyline_name'])} ({cell(catalog['storyline_id'])})"]
    rows += ['', '## Latest search output', '', f'- Output timestamp: {stamp}',
             f'- Search task: {task_id}', f'- Handoff revision: {handoff or "No handoff produced"}',
             f'- Status: {cell(data["status"])}', f'- Providers: {cell(", ".join(config["providers"]))}',
             f'- Search model: {cell(config.get("lm_name")) if data.get("mode") != "simple" else "Not used (simple search)"}',
             f'- Requests: {usage["search"]} search; {usage["model"]} model.',
             f'- Sources: {len(data["sources"])} candidates; {saved} with saved text; {len(used)} in this input.',
             f'- Input characters: {sum(len(s["content"]) for s in (payload or {}).get("samples", []))}.',
             f'- Complete material characters: {selection.get("complete_material_chars", "Not recorded by this search mode")}.',
             '- This output is not automatically adopted for construction. Approved inputs are recorded with build tasks.',
             '', '## Sources', '', '| Source ID | Title | URL | Acquisition status | In this input |',
             '| --- | --- | --- | --- | --- |']
    for sid, source in sorted(data['sources'].items()):
        rows.append('| ' + ' | '.join(cell(v) for v in [sid, source.get('title'), source['url'], source['status'], 'yes' if sid in used else 'no']) + ' |')
    if not data['sources']: rows += ['', 'No sources recorded.']
    rows += ['', '## Gaps and stop notes', '', 'Search Agent observations are advisory; acquisition does not verify facts.', '']
    gaps = selection.get('gaps', [])
    rows += ['- ' + cell(g) for g in gaps] or ['- No gap assessment recorded; this is not a claim of full coverage.']
    rows += [f'- Stop reason: {cell(data.get("stop_reason")) or "Not recorded"}']
    scope_note = f"{scope['period']} / {scope['include']} / Excluded: {scope['exclude']}"
    return '\n'.join(rows), [stamp, task_id, scope_note, data['status'], handoff]


def with_history(body, records):
    body = body.split('## Search runs\n', 1)[0].rstrip()
    lines = [body, '', '## Search runs', '', '| Output date | Task ID | Scope | Status | Handoff |', '| --- | --- | --- | --- | --- |']
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in sorted(records.values(), key=lambda r:(r[0], r[1]), reverse=True)]
    return '\n'.join(lines) + '\n'


def publish_summary(root, task_id):
    """Called under the task writer lock. Failures never change the search outcome."""
    state = SearchState(root, task_id)
    data = state.data
    catalog = data['task'].get('catalog')
    if not catalog or data['status'] not in TERMINAL:
        return None
    selection_path = state.run_dir / 'selection.json'
    input_path = state.run_dir / 'builder_input.json'
    selection = json.loads(selection_path.read_text()) if selection_path.exists() else {}
    payload = json.loads(input_path.read_text()) if input_path.exists() else None
    body, entry = render(data, task_id, selection, payload)
    local_path = state.run_dir / 'search-summary.md'
    old_local = local_path.read_text() if local_path.exists() else ''
    prefix, _, suffix = managed(old_local)
    atomic_text(local_path, prefix + BEGIN + '\n' + with_history(body, {task_id:entry}) + END + suffix)
    result = {'status':'pending', 'local_path':str(local_path), 'updated_at':now()}
    try:
        root_path = Path(catalog['root'])
        if not root_path.is_dir():
            raise ValueError('数据集根目录已不存在')
        relative = Path(catalog['event_dir'])
        allowed = Path('event-epg/events') if catalog['kind'] == 'event' else Path('person-epg')
        if not relative.is_relative_to(allowed) or relative == allowed:
            raise ValueError('event 汇总目录不在对应的数据集分类下')
        folder = within(root_path, relative)
        folder.mkdir(parents=True, exist_ok=True)
        if (root_path / relative / 'search-summary.md').is_symlink():
            raise ValueError('汇总不能写入符号链接')
        target = within(root_path, relative / 'search-summary.md')
        with directory_lock(folder):
            existing = target.read_text(encoding='utf-8') if target.exists() else ''
            prefix, previous, suffix = managed(existing)
            records = history(previous)
            records[task_id] = entry
            previous_stamp = re.search(r'^- Output timestamp: (.+)$', previous, re.M)
            current = previous if previous_stamp and previous_stamp[1] > entry[0] else body
            atomic_text(target, prefix + BEGIN + '\n' + with_history(current, records) + END + suffix)
        result.update(status='saved', path=str(target))
    except (OSError, ValueError) as exc:
        result.update(status='failed', error=str(exc))
    state.data['summary'] = result
    state.save()
    return result
