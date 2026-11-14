"""Portable workbench records; exclude source bodies, secrets and machine paths."""
import csv
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from finmy.dataset import DatasetCatalog, component, dataset_root, within
from finmy.search.state import now, digest
from finmy.search.summary import atomic_text, directory_lock
from finmy.workbench.material_status import confirmations, saved_confirmations, matching_builds, disposition

README = """# Workbench records

FinMycelium maintains these lightweight records for Git review and collaboration.

- [Search records](search/README.md): task scope/configuration, execution summary and source index.
- [Build records](build/README.md): frozen input manifest/configuration and execution summary.
- events/<event_id>/: workbench edits/history, source and graph indexes, and review decisions.
- plans/<task_id>.json: historical task plans, explicitly separate from executed tasks.

These are generated records, not graph acceptance or commands to start a task.
Do not edit generated files to change a live run; use the workbench.
Runtime status and catalog acceptance are separate. Accepted EPGs and Gantt files
are collected into event-epg/ or person-epg/ after review.

SQLite, source bodies, raw responses, checkpoints and logs remain under ignored
output/. These records support inspection and provenance, not complete runtime
restoration without the original workspace. No Git commit or push is automatic.
"""

SEARCH_KEYS = ('providers', 'max_results', 'max_search_requests', 'max_read_sources',
               'max_model_calls', 'max_read_chars', 'max_builder_material_chars',
               'max_model_context_chars', 'timeout', 'max_download_bytes',
               'publication_start', 'publication_end', 'include_domains',
               'exclude_domains', 'baidu_rewrite', 'lm_name', 'allow_network')
CATALOG_KEYS = ('kind', 'person_id', 'person_name', 'storyline_id', 'storyline_name',
                'event_id', 'event_name', 'event_dir', 'snapshot_sha256', 'files')
SOURCE_FIELDS = ('source_id', 'title', 'url', 'published_at', 'status', 'version', 'in_input')


def pick(value, keys):
    return {key: value[key] for key in keys if key in value}


def public_url(value):
    parsed = urlsplit(str(value or ''))
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        return ''
    sensitive = {'key', 'api_key', 'apikey', 'token', 'access_token', 'signature', 'sig', 'authorization'}
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in sensitive and not k.lower().startswith(('x-amz-', 'x-goog-'))]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def generation(config):
    value = pick(config or {}, ('max_tokens', 'max_new_tokens', 'max_completion_tokens',
                                'temperature', 'top_p', 'reasoning_effort', 'seed', 'n',
                                'presence_penalty', 'frequency_penalty', 'stop', 'verbosity', 'response_format'))
    extra = (config or {}).get('extra_body')
    if isinstance(extra, dict):
        controls = pick(extra, ('reasoning_effort', 'enable_thinking', 'thinking_budget'))
        if isinstance(extra.get('thinking'), dict):
            controls['thinking'] = pick(extra['thinking'], ('type', 'budget_tokens'))
        if controls:
            value['extra_body'] = controls
    return value


def search_config(config):
    return {**pick(config, SEARCH_KEYS), 'generation_config': generation(config.get('generation_config'))}


def numbers(value):
    if isinstance(value, dict):
        return {k: numbers(v) for k, v in value.items()
                if isinstance(v, (int, float, dict)) and not isinstance(v, bool)}
    return value


def token_summary(reported, attempted):
    result = {'reported_model_calls': len(reported), 'attempted_model_calls': attempted}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        values = [u[key] for u in reported if type(u.get(key)) is int]
        result[key] = sum(values) if len(values) == attempted else None
        result['reported_' + key] = sum(values) if values else None
    return result


def build_usage(value):
    if isinstance(value, list):
        # Person-event state retains every reserved call, including failures.
        reported = [c['usage'] for c in value if isinstance(c.get('usage'), dict)]
        return {**token_summary(reported, len(value)), 'calls': [
            {**pick(c, ('call_id', 'status', 'started_at', 'duration_seconds', 'usage_status',
                       'error_type', 'error_chain', 'http_status', 'request_id')),
             'transport': pick(c.get('transport', {}), ('mode', 'phase', 'chunks', 'content_chars',
                 'reasoning_chars', 'first_chunk_seconds', 'duration_seconds', 'finish_reason',
                 'stream_exhausted', 'http_status', 'request_id', 'response_id', 'error_type', 'error_chain')),
             'usage': numbers(c['usage']) if isinstance(c.get('usage'), dict) else None} for c in value]}
    return numbers(value) if isinstance(value, (int, dict)) else None


def relative(path, root):
    if not path:
        return None
    value = Path(path).resolve()
    return value.relative_to(root).as_posix() if value.is_relative_to(root) else None


def destination(root, *parts):
    root = DatasetCatalog(root).root
    base = root / 'workbench'
    folder = base.joinpath(*(component(p) for p in parts))
    if within(root, folder.relative_to(root)) != folder:
        raise ValueError('共享记录目录不能经过符号链接')
    folder.mkdir(parents=True, exist_ok=True)
    readme = base / 'README.md'
    if not readme.exists():
        try:
            with readme.open('x', encoding='utf-8') as stream:
                stream.write(README)
        except FileExistsError:
            pass
    return root, folder


def save(folder, name, value):
    path = folder / name
    if path.is_symlink():
        raise ValueError('共享记录文件不能是符号链接')
    text = value if isinstance(value, str) else json.dumps(
        {'format_version': 1, **value}, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        atomic_text(path, text)


def source_csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def input_manifest(bundle):
    query = bundle.get('user_query', {})
    return {'user_query': pick(query, ('user_query_id', 'query_text', 'key_words')),
            'samples': [{'sample_id': s.get('sample_id'), 'raw_data_id': s.get('raw_data_id'),
                         'characters': len(s.get('content', '')),
                         'content_sha256': hashlib.sha256(s.get('content', '').encode()).hexdigest()}
                        for s in bundle.get('samples', [])]}


def search_record_name(record, *, full_id=False, kind='search'):
    """A fixed creation-time label; model and execution status are not identity."""
    task_id = component(record['task_id'])
    stamp = datetime.fromisoformat(record['created_at'])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
    title = (record.get('catalog', {}).get('event_name')
             or record.get('research_request', {}).get('target_name') or record.get('event_name') or kind)
    title = unicodedata.normalize('NFKC', title).casefold()
    slug = re.sub(r'[\W_]+', '-', title).strip('-')
    slug = slug.encode('utf-8')[:96].decode('utf-8', errors='ignore').rstrip('-') or kind
    return f'{stamp}_{slug}_{task_id if full_id else task_id[:12]}'


def build_record_name(record, **kwargs):
    return search_record_name(record, full_id=True, kind='build')


def _record_task(folder):
    if folder.is_symlink() or (folder/'task.json').is_symlink():
        raise ValueError('共享检索记录不能是符号链接')
    path = folder/'task.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def _record_folder(base, record, naming):
    """Called under the export lock; never replace another task."""
    task_id = component(record['task_id'])
    matches = [p for p in base.iterdir() if (p.is_dir() or p.is_symlink())
               and (old := _record_task(p)) and old.get('task_id') == task_id]
    if len(matches) > 1:
        raise ValueError('共享记录存在重复任务 ID；原记录已保留')
    if matches and matches[0].name != task_id:
        return matches[0]  # Once named, metadata and status changes never rename it.
    folder = base/naming(record)
    existing = _record_task(folder)
    if existing and existing['task_id'] != task_id:
        folder = base/naming(record, full_id=True)
        existing = _record_task(folder)
    if existing and existing['task_id'] != task_id:
        raise ValueError('共享检索记录目录已属于其他任务')
    legacy = base/task_id
    if legacy.exists() or legacy.is_symlink():
        old = _record_task(legacy)
        if not old or old.get('task_id') != task_id or folder.exists():
            raise ValueError('旧检索记录身份不符或存在重复目录；原记录已保留')
        legacy.rename(folder)
    elif not folder.exists():
        folder.mkdir()
    elif not existing and any(folder.iterdir()):
        raise ValueError('共享检索记录缺少任务身份；原记录已保留')
    return folder


def _search_folder(base, record):
    return _record_folder(base, record, search_record_name)


def find_build_record(root, task_id):
    """Resolve stable IDs, including manifests written before directory renaming."""
    task_id = component(task_id)
    base = within(root, 'workbench/build')
    found = [p/'task.json' for p in base.iterdir() if p.is_dir()
             and (record := _record_task(p)) and record.get('task_id') == task_id] if base.exists() else []
    if len(found) > 1:
        raise ValueError('共享构建记录存在重复任务 ID')
    return found[0] if found else None


def _build_index(root, base):
    from finmy.search.summary import cell
    lines = ['# Build records', '',
             'Automatically updated; creation times use Asia/Shanghai (UTC+08:00).',
             'Directories use creation time, event name and task ID; resumes keep the directory.',
             'Task IDs and runtime paths stay unchanged. Look up historical manifest paths by task ID here.',
             'Execution and material confirmation do not imply graph acceptance.', '',
             '| Created | Person | Event | Model | Status | Search task | Build record |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    entries, seen = [], set()
    searches = {}
    search_base = root/'workbench/search'
    if search_base.exists():
        for folder in search_base.iterdir():
            if (folder.is_dir() or folder.is_symlink()) and (record := _record_task(folder)):
                searches[record['task_id']] = folder.name
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() and not folder.is_symlink():
            continue
        task = _record_task(folder)
        if not task:
            continue
        if task['task_id'] in seen:
            raise ValueError('共享构建记录存在重复任务 ID')
        seen.add(task['task_id'])
        path = folder/'summary.json'
        if path.is_symlink():
            raise ValueError('共享构建汇总不能是符号链接')
        summary = json.loads(path.read_text()) if path.exists() else {}
        if summary.get('task_id', task['task_id']) != task['task_id']:
            raise ValueError('构建任务与汇总的 ID 不一致')
        stamp = datetime.fromisoformat(task['created_at'])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        manifest = task.get('search_collection', {}).get('manifest', {}) if task.get('search_collection') else {}
        handoffs = manifest.get('search_handoffs') or [task.get('search_handoff', {})]
        search_ids = sorted({h['search_task_id'] for h in handoffs if h.get('search_task_id')})
        values = [stamp, task.get('catalog', {}).get('person_name'),
                  task.get('catalog', {}).get('event_name') or task.get('event_name') or task['event_id'],
                  task.get('configuration', {}).get('lm_name'), summary.get('status')]
        search_links = ', '.join(f'[{cell(tid[:12])}](../search/{quote(searches[tid])}/)'
                                 if tid in searches else cell(tid) for tid in search_ids)
        link = f"[{cell(task['task_id'])}]({quote(folder.name)}/)"
        entries.append((stamp, task['task_id'], '| '+' | '.join(map(cell, values))+' | '+search_links+' | '+link+' |'))
    lines.extend(row for _, _, row in sorted(entries))
    save(base, 'README.md', '\n'.join(lines)+'\n')
    readme = root/'workbench/README.md'
    if readme.is_symlink():
        raise ValueError('共享记录说明不能是符号链接')
    save(readme.parent, readme.name, readme.read_text().replace(
        '- build/<task_id>/: frozen input manifest/configuration and execution summary.',
        '- [Build records](build/README.md): frozen input manifest/configuration and execution summary.'))


def migrate_build_records(root):
    """Rename portable records without editing frozen manifests or runtime files."""
    root, parent = destination(root)
    _, base = destination(root, 'build')
    changes = []
    with directory_lock(parent):
        for folder in sorted(base.iterdir()):
            if not folder.is_dir() and not folder.is_symlink():
                continue
            task = _record_task(folder)
            if task and folder.name == task['task_id']:
                renamed = _record_folder(base, task, build_record_name)
                changes.append((folder.name, renamed.name))
        _build_index(root, base)
    return changes


def _search_index(root, base):
    """Small generated navigation; full IDs and provenance remain in task.json."""
    def cell(value):
        value = ' '.join(str(value if value is not None else '—').split())
        return re.sub(r'([\\`*_\[\]()<>|])', r'\\\1', value)
    entries, seen = [], set()
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() and not folder.is_symlink():
            continue
        task = _record_task(folder)
        if not task:
            continue
        if task['task_id'] in seen:
            raise ValueError('共享检索记录存在重复任务 ID；请检查原记录')
        seen.add(task['task_id'])
        summary_path = folder/'summary.json'
        if summary_path.is_symlink():
            raise ValueError('共享检索汇总不能是符号链接')
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        if summary.get('task_id', task['task_id']) != task['task_id']:
            raise ValueError('检索任务与汇总的 ID 不一致')
        stamp = datetime.fromisoformat(task['created_at'])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        model = task.get('configuration', {}).get('lm_name') if task.get('mode') != 'simple' else 'Simple (no model)'
        values = [stamp, task.get('research_request', {}).get('target_name'),
                  task.get('catalog', {}).get('event_id') or task.get('workbench_event_id'),
                  model, summary.get('status'), summary.get('build_disposition', 'pending'), summary.get('input_characters')]
        link = f"[{cell(task['task_id'][:12])}]({quote(folder.name)}/)"
        entries.append((stamp, task['task_id'], '| ' + ' | '.join(map(cell, values)) + ' | ' + link + ' |'))
    lines = ['# Search records', '',
             'Automatically updated from task records. Times use Asia/Shanghai (UTC+08:00).',
             'Directories use creation time, event name and a short task ID; retry and model/status changes keep the directory.',
             'Full task IDs, scope and configuration remain in each task.json. Runtime directories keep the full task ID.',
             'Execution status does not imply evidence approval or an accepted EPG.', '',
             '| Created | Event | Event ID | Model | Status | Build disposition | Builder input characters | Task record |',
             '| --- | --- | --- | --- | --- | --- | ---: | --- |']
    lines.extend(row for _, _, row in sorted(entries))
    save(base, 'README.md', '\n'.join(lines) + '\n')
    readme = root/'workbench/README.md'
    if readme.is_symlink():
        raise ValueError('共享记录说明不能是符号链接')
    text = readme.read_text(encoding='utf-8').replace(
        '- search/<task_id>/: task scope/configuration, execution summary and source index.',
        '- [Search records](search/README.md): task scope/configuration, execution summary and source index.')
    save(readme.parent, readme.name, text)


def migrate_search_records(root):
    """Rename portable records only, even when their runtime is not available."""
    root, base = destination(root, 'search')
    changes = []
    with directory_lock(base):
        for folder in sorted(base.iterdir()):
            if not folder.is_dir() and not folder.is_symlink():
                continue
            task = _record_task(folder)
            if task and folder.name == task['task_id']:
                renamed = _search_folder(base, task)
                changes.append((folder.name, renamed.name))
        _search_index(root, base)
    return changes


def export_search(search_root, task_id):
    """Read latest state under the export lock; never change the run."""
    task_id = component(task_id)
    run = Path(search_root) / task_id / 'runs/initial'
    initial = json.loads((run / 'run.json').read_text())
    root = initial['task'].get('catalog', {}).get('root') or dataset_root(Path(search_root).parent)
    if not root:
        return None
    root, base = destination(root, 'search')
    with directory_lock(base):
        data = json.loads((run / 'run.json').read_text())
        task, config = data['task'], data['config']
        record = {'kind': 'search', 'task_id': task_id, 'created_at': data['created_at'],
                  'build_disposition': data.get('build_disposition', 'pending'),
                  'build_disposition_history': data.get('build_disposition_history', []),
                  'mode': data.get('mode', 'agent'), 'catalog': pick(task.get('catalog', {}), CATALOG_KEYS),
                  'research_scope': task.get('research_scope'),
                  'research_request': pick(task, ('target_type', 'target_name', 'query_text', 'key_words', 'search_queries')),
                  'workbench_event_id': task.get('event_id'),
                  'scope_sha256': task.get('scope_hash'),
                  'seed_urls': [u for u in map(public_url, task.get('seed_urls', [])) if u],
                  'scope_confirmation': task.get('scope_confirmation'),
                  'input_sha256': data.get('input_sha256'), 'code_sha256': data.get('code_sha256'),
                  'configuration': search_config(config),
                  'configuration_history': [
                      {'time': h['time'], 'configuration': search_config(h['config'])}
                      for h in data.get('config_history', [])],
                  'runtime_directory': relative(run.parent.parent, root)}
        selection_path = run / 'selection.json'
        selection = json.loads(selection_path.read_text()) if selection_path.exists() else {}
        payload_path = run / 'builder_input.json'
        payload = json.loads(payload_path.read_text()) if payload_path.exists() else {}
        adopted = matching_builds(task_id, data.get('handoff_revision'), digest(payload) if payload else None,
                                  saved_confirmations(Path(search_root).resolve().parent))
        decision = disposition(data, adopted)
        record.update(build_disposition=decision, confirmed_build_tasks=adopted)
        used = {s['raw_data_id'] for s in payload.get('samples', [])}
        rows = []
        from finmy.search.metadata import publication_metadata
        selected_metadata = {r['source_id']:r['metadata'] for r in selection.get('selected', []) if 'metadata' in r}
        for sid, source in sorted(data['sources'].items()):
            metadata = selected_metadata.get(sid) or publication_metadata(source)
            rows.append(dict(source_id=sid, title=source.get('title', ''), url=public_url(source.get('url')),
                             published_at=metadata['published_at'], status=source.get('status'),
                             version=source.get('version'), in_input=sid in used))
        reported = []
        trace = run / 'trace.jsonl'
        if trace.exists():
            for line in trace.read_text().splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get('action') == 'model_response' and isinstance(item.get('usage'), dict):
                    reported.append(item['usage'])
        token_usage = token_summary(reported, data['usage']['model'])
        summary = {'task_id': task_id, 'status': data['status'],
                   'build_disposition': decision, 'confirmed_build_tasks': adopted, 'updated_at': data['updated_at'],
                   'completed_at': data.get('completed_at'), 'stop_reason': data.get('stop_reason'),
                   'requests': data['usage'], 'read_sources': len(data['read_sources']),
                   'source_count': len(rows), 'input_source_count': len(used),
                   'input_characters': sum(len(s['content']) for s in payload.get('samples', [])),
                   'handoff_revision': data.get('handoff_revision'),
                   'handoff_updated_at': data.get('handoff_updated_at'),
                   'assembly_policy': selection.get('budget_policy'),
                   'assembly_code_sha256': selection.get('assembly_code_sha256'),
                   'assembly_threshold_stages': [
                       pick(stage, ('threshold', 'material_chars'))
                       for stage in selection.get('allocation', {}).get('threshold_stages', [])],
                   'complete_material_characters': selection.get('complete_material_chars'),
                   'gaps': selection.get('gaps', []), 'token_usage': token_usage,
                   'monetary_cost': None, 'content_review': 'not_implied_by_execution',
                   'handoff': input_manifest(payload) if payload else None}
        folder = _search_folder(base, record)
        save(folder, 'task.json', record)
        save(folder, 'summary.json', summary)
        save(folder, 'sources.csv', source_csv(rows))
        _search_index(root, base)
    return folder


def export_database(workspace):
    workspace = Path(workspace).resolve()
    configured = dataset_root(workspace)
    database = workspace / 'workbench.sqlite3'
    if not configured or not database.exists():
        return None
    root, base = destination(configured)
    with directory_lock(base), closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def rows(table, columns='*', where='', args=()):
            return [dict(r) for r in db.execute(f'SELECT {columns} FROM {table} {where}', args)] if table in tables else []
        for event in rows('events'):
            eid = component(event['id'])
            _, folder = destination(root, 'events', eid)
            history = rows('event_history', where='WHERE event_id=? ORDER BY revision', args=(eid,))
            save(folder, 'event.json', {'event': json.loads(event['body']),
                'revision': event['revision'], 'updated': event['updated'],
                'history': [{**r, 'body': json.loads(r['body'])} for r in history]})
            reviews = rows('reviews', where='WHERE event_id=? ORDER BY created,id', args=(eid,))
            handoffs = rows('handoffs', where='WHERE event_id=? ORDER BY created,id', args=(eid,))
            save(folder, 'reviews.json', {'event_id': eid, 'reviews': reviews,
                'handoffs': [{**pick(r, ('id', 'input_hash', 'review_id', 'created')),
                              'input': input_manifest(json.loads(r['body']))} for r in handoffs]})
            sources = rows('sources', 'id,title,url,published,sha256,included', 'WHERE event_id=? ORDER BY created,id', (eid,))
            save(folder, 'sources.csv', source_csv([
                dict(source_id=r['id'],title=r['title'],url=public_url(r['url']),published_at=r['published'],
                     status='included' if r['included'] else 'not_included',version=r['sha256'],in_input=bool(r['included']))
                for r in sources]))
            graphs = rows('graphs', 'id,sha256,parent_id,note,input_hash,created', 'WHERE event_id=? ORDER BY created,id', (eid,))
            save(folder, 'graphs.json', {'event_id': eid, 'versions': graphs})
        build_rows = rows('build_tasks')
        build_bases = {}
        for row in build_rows:
            tid = component(row['id']); body = json.loads(row['body'])
            owner = body.get('catalog', {}).get('root') or root
            artifact = body.get('artifact_directory')
            if not body.get('catalog') and artifact:
                path = Path(artifact).resolve()
                if path.parent.name == 'builds' and path.parent.parent.name == 'output':
                    owner = path.parents[2]
            owner, build_base = destination(owner, 'build')
            build_bases[owner] = build_base
            identity = {'task_id': tid, 'created_at': row['created'],
                        'catalog': pick(body.get('catalog', {}), CATALOG_KEYS),
                        'event_name': body.get('event', {}).get('event_name_en') or body.get('event', {}).get('event_name') or row['event_id']}
            folder = _record_folder(build_base, identity, build_record_name)
            config = pick(body.get('config', {}), ('builder_type', 'lm_name'))
            if body.get('person_config'):
                from finmy.person_epg.event.runtime import EventBuildConfig
                from dataclasses import fields
                config.update(pick(body['person_config'], [f.name for f in fields(EventBuildConfig)]))
            else:
                config['generation_config'] = generation(body.get('config', {}).get('generation_config'))
                config['settings'] = pick(body.get('settings', {}), ('model', 'builder', 'concurrency'))
                config['sparse_builder_config'] = pick(body.get('config', {}).get('sparse_builder_config', {}),
                    ('enable_sparse_routing', 'enable_context_assets', 'max_calls', 'context_top_k',
                     'max_context_chars', 'excerpt_char_limit', 'max_card_tokens', 'max_json_attempts',
                     'request_timeout_seconds', 'evidence_policy', 'output_language'))
            save(folder, 'task.json', {**identity, 'kind': body.get('kind', 'event'), 'task_id': tid, 'event_id': row['event_id'],
                'created_at': row['created'], 'catalog': pick(body.get('catalog', {}), CATALOG_KEYS),
                'input_sha256': body.get('input_hash'), 'input': input_manifest(body.get('input', {})),
                'research_scope': (body.get('input', {}).get('user_query', {}).get('extras') or {}).get('person_event', {}).get('scope')
                    or pick(body.get('event', {}), ('coverage_start', 'coverage_end', 'scope_include', 'scope_exclude')),
                'search_handoff': pick(body.get('provenance', {}), ('search_task_id', 'handoff_revision', 'search_input_sha256')),
                'search_collection': ({**pick(body['search_collection'], ('directory', 'manifest_sha256')),
                    'manifest': json.loads(body['search_collection']['files']['manifest.json'])}
                    if body.get('search_collection') else None),
                'evidence_review': pick(body.get('evidence_review', {}), ('id', 'target', 'decision', 'reviewer', 'note', 'created')),
                'configuration': config, 'code': body.get('code'), 'person_code': body.get('person_code'),
                'input_confirmation': body.get('input_confirmation'), 'scope_sha256': body.get('scope_hash'),
                'artifact_directory': relative(artifact, owner)})
            save(folder, 'summary.json', {'task_id': tid, 'status': row['status'],
                **pick(body, ('finished', 'error_type', 'elapsed_seconds', 'graph_id')),
                'usage': build_usage(body.get('usage')),
                'run_state': pick(body.get('run_state', {}),
                    ('execution_status', 'result_status', 'render_status', 'output', 'checks', 'facts')),
                'artifact_directory': relative(artifact, owner), 'content_review': 'not_implied_by_execution'})
        for owner, build_base in build_bases.items():
            _build_index(owner, build_base)
        # A newly saved build confirms the exact search revision automatically.
        # Failed/cancelled builds retain that confirmation; no runtime is changed.
        for tid in sorted({c['search_task_id'] for c in confirmations(build_rows)}):
            if (workspace/'search'/component(tid)/'runs/initial/run.json').is_file():
                export_search(workspace/'search', tid)
        for row in rows('jobs'):
            body = json.loads(row['body'])
            _, folder = destination(root, 'plans')
            save(folder, component(row['id']) + '.json', {'task_id': row['id'], 'status': row['status'],
                'created_at': row['created'], 'stage': body.get('stage'),
                'configuration': pick(body.get('config', {}), ('model', 'builder', 'concurrency')),
                'events': [{'event_id': r['event']['event_id'], 'input_sha256': r.get('input_sha256')}
                           for r in body.get('events', [])]})
    return base


def _sync(workspace, key, action):
    """Export failures do not undo saved tasks or trigger repeat API requests."""
    workspace = Path(workspace)
    status_dir = workspace / 'record-exports'
    try:
        target = action()
        if target is None:
            return None
        result = {'status': 'saved', 'updated_at': now()}
    except Exception as exc:
        result = {'status': 'failed', 'error_type': type(exc).__name__, 'updated_at': now()}
    try:
        status_dir.mkdir(parents=True, exist_ok=True)
        atomic_text(status_dir / (component(key) + '.json'), json.dumps(result) + '\n')
    except OSError:
        pass
    return result


def sync_search(search_root, task_id):
    return _sync(Path(search_root).parent, 'search-' + task_id, lambda: export_search(search_root, task_id))


def sync_database(workspace):
    return _sync(workspace, 'database', lambda: export_database(workspace))


def export_all(workspace):
    """Explicit retry/export, never start or approve anything."""
    workspace = Path(workspace)
    results = [sync_database(workspace)]
    for path in sorted((workspace / 'search').glob('*/runs/initial/run.json')):
        results.append(sync_search(workspace / 'search', path.parents[2].name))
    return [r for r in results if r is not None]
