"""Collect the exact search adopted by a build; never run or approve a graph."""
from contextlib import contextmanager
from copy import deepcopy
import csv
import io
import json
import shutil
import tempfile
from pathlib import Path

from finmy.dataset import catalog_event_directory, component
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest
from finmy.search.metadata import publication_metadata
from finmy.search.summary import cell, directory_lock
from finmy.workbench.records import CATALOG_KEYS, pick, public_url, relative, search_config

FILES = ('search-summary.md', 'sources.csv', 'manifest.json')
FIELDS = ('input_sample_id', 'search_task_id', 'source_id', 'title', 'url', 'published_at',
          'status', 'versions', 'parsed_hashes', 'content_sha256', 'characters')


def search_snapshot(controller, task_id, data=None):
    """Caller holds the search-task lock. Retain metadata, never source bodies."""
    data = data or controller.inspect(task_id)
    task = data['task']
    if data['status'] not in {'finished', 'insufficient', 'failed', 'limit'}:
        raise ValueError('请先结束检索并确认实际材料')
    if task.get('scope_confirmation', {}).get('scope_sha256') != digest(task.get('research_scope')):
        raise ValueError('检索范围确认不一致')
    state = SearchState(controller.root, task_id)
    revision = component(data.get('handoff_revision', ''))
    folder = state.run_dir/'handoffs'/revision
    for key in ('builder_input', 'selection'):
        if not data.get(key) or json.loads((folder/(key+'.json')).read_text()) != data[key]:
            raise ValueError('交接内容与固定版本不一致，请重新检查')
    payload, selection = data['builder_input'], data['selection']
    sources = []
    for sample in payload['samples']:
        sid = sample['raw_data_id']; source = data['sources'][sid]
        entries = [s for s in selection['selected'] if s['source_id'] == sid]
        versions = sorted({s['version'] for s in entries})
        if not versions:
            raise ValueError('交接材料缺少来源版本')
        documents = [SourceStore(state).document(sid, version) for version in versions]
        metadata = [s['metadata'] for s in entries if 'metadata' in s]
        if metadata and any(m != metadata[0] for m in metadata):
            raise ValueError('固定来源信息不一致')
        details = metadata[0] if metadata else {'source_url': source['url'],
            'title': source.get('title'), **publication_metadata(source)}
        statuses = sorted({doc['status'] for doc in documents})
        sources.append(dict(input_sample_id=sample['sample_id'], search_task_id=task_id, source_id=sid,
            title=details.get('title') or '', url=public_url(details['source_url']),
            published_at=details.get('published_at') or '', status=';'.join(statuses),
            versions=versions, parsed_hashes={v: source['parsed_hashes'][v] for v in versions},
            content_sha256=digest(sample['content'].encode()), characters=len(sample['content'])))
    if not sources:
        raise ValueError('没有可采用的正文')
    root = Path(task['catalog']['root']).resolve()
    return dict(catalog=deepcopy(task['catalog']), scope=deepcopy(task['research_scope']),
        scope_hash=task.get('scope_hash'), search_task_id=task_id, handoff_revision=revision,
        search_input_sha256=digest(payload), selection_sha256=digest(selection),
        input_file=relative(folder/'builder_input.json', root),
        selection_file=relative(folder/'selection.json', root),
        mode=data.get('mode'), configuration=search_config(data['config']),
        code_sha256_at_preparation=data.get('code_sha256'),
        status=data['status'], usage=deepcopy(data['usage']), gaps=deepcopy(selection.get('gaps', [])),
        sources=sources)


def ordinary_adoptions(store, event_id, bundle):
    """Match reviewed Store inputs to pinned search samples, including subsets."""
    from finmy.search.control import SearchController, task_lock
    controller = SearchController(store.root/'search')
    inputs = {s['sample_id']: digest(s['content'].encode()) for s in bundle['samples']}
    adopted = []
    for path in sorted(controller.root.glob('*/runs/initial/workbench_sources.json')):
        record = json.loads(path.read_text())
        if record.get('event_id') != event_id:
            continue
        mapping = [m for m in record['mapping'] if inputs.get(m['source_id']) == m['sha256']]
        if not mapping:
            continue
        snapshot = record.get('search_snapshot')
        if not snapshot:
            # Legacy associations can be upgraded only if their exact texts still match.
            tid = path.parents[2].name
            with task_lock(controller.root, tid):
                data = controller.inspect(tid)
                if not data['task'].get('catalog'):
                    continue
                snapshot = search_snapshot(controller, tid, data)
        if snapshot['catalog']['kind'] != 'event':
            raise ValueError('普通事件输入不能关联人物检索目录')
        if snapshot.get('scope_hash') != store.target(event_id, 'scope'):
            raise ValueError('检索范围已变化，请重新纳入并确认资料')
        snapshot = deepcopy(snapshot)
        rows = []
        for m in mapping:
            matches = [s for s in snapshot['sources'] if s['input_sample_id'] == m['sample_id']
                       and s['content_sha256'] == m['sha256']]
            if len(matches) != 1:
                raise ValueError('旧资料缺少可核对的固定检索版本，请重新纳入并审核')
            rows.append({**matches[0], 'input_sample_id': m['source_id']})
        snapshot['sources'] = rows
        adopted.append(snapshot)
    return adopted


def prepare_collection(task_id, body, adoptions):
    """The build row retains this small snapshot when the event adopts a successor."""
    if not adoptions:
        return None
    catalog = adoptions[0]['catalog']
    folder = catalog_event_directory(catalog)/'search'
    for adoption in adoptions:
        if catalog_event_directory(adoption['catalog']) != folder.parent:
            raise ValueError('采用的检索材料指向不同事件目录')
    bundle = body['input']
    samples = {s['sample_id']: s for s in bundle['samples']}
    sources = [deepcopy(s) for a in adoptions for s in a['sources']]
    for source in sources:
        sample = samples.get(source['input_sample_id'])
        if not sample or digest(sample['content'].encode()) != source['content_sha256']:
            raise ValueError('实际构建输入与固定检索材料不一致')
    covered = {s['input_sample_id'] for s in sources}
    registry = (bundle['user_query'].get('extras') or {}).get('source_registry', {})
    for sid, sample in samples.items():
        if sid in covered:
            continue
        meta = registry.get(sample['raw_data_id'], {})
        sources.append(dict(input_sample_id=sid, search_task_id='', source_id=sample['raw_data_id'],
            title=meta.get('title', ''), url=public_url(meta.get('url') or meta.get('source_url')),
            published_at=meta.get('published') or meta.get('published_at') or '', status='workbench_material',
            versions=[], parsed_hashes={}, content_sha256=digest(sample['content'].encode()),
            characters=len(sample['content'])))
    review = (body.get('input_confirmation') or
              pick(body.get('evidence_review', {}), ('id', 'reviewer', 'note', 'created', 'decision', 'target')))
    root = Path(catalog['root']).resolve()
    manifest = dict(format_version=1, kind='adopted_search', catalog=pick(catalog, CATALOG_KEYS),
        build_task_id=task_id, input_sha256=body['input_hash'], confirmation=review,
        research_scope=adoptions[0]['scope'], input_characters=sum(len(s['content']) for s in samples.values()),
        input_sample_count=len(samples), build_record=f'workbench/build/{task_id}/task.json',
        runtime_directory=relative(body['artifact_directory'], root),
        search_handoffs=[{k: deepcopy(v) for k, v in a.items() if k not in {'catalog', 'scope_hash', 'sources'}}
                         for a in adoptions],
        samples=[dict(sample_id=sid, content_sha256=digest(s['content'].encode()), characters=len(s['content']))
                 for sid, s in samples.items()], graph_acceptance='not_implied')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n'); writer.writeheader()
    for source in sources:
        writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v
                         for k, v in source.items()})
    lines = [f"# Adopted search: {cell(catalog['event_name'])}", '',
        f"- Event ID: {cell(catalog['event_id'])}", f'- Build task: {task_id}',
        f"- Build input SHA256: {body['input_hash']}",
        f"- Input: {len(samples)} samples; {manifest['input_characters']:,} characters.",
        '- The user confirmed this material for construction; this is not final graph acceptance.',
        '- Generated at build-task creation. Source bodies and logs remain in ignored output storage.',
        '- sources.csv lists only the actual build input. manifest.json pins the handoffs and input hashes.',
        '', '## Confirmed scope', '']
    for key in ('period', 'include', 'exclude'):
        lines.append(f"- {key.capitalize()}: {cell(manifest['research_scope'].get(key))}")
    lines += ['', '## Adopted search runs', '']
    for a in adoptions:
        config = a['configuration']
        lines += [f"- Task {a['search_task_id']}; handoff {a['handoff_revision']}.",
                  f"  Providers: {cell(', '.join(config['providers']))}; model: {cell(config.get('lm_name')) if a['mode'] != 'simple' else 'none (simple)' }.",
                  f"  Requests: {a['usage']['search']} search; {a['usage']['model']} model."]
    lines += ['', '## Known gaps', '', 'Search Agent observations; input confirmation does not resolve these gaps.', '']
    gaps = list(dict.fromkeys(g for a in adoptions for g in a['gaps']))
    lines += ['- '+cell(g) for g in gaps] or ['- No gap assessment recorded; completeness is not implied.']
    files = {'sources.csv': stream.getvalue(), 'search-summary.md': '\n'.join(lines)+'\n'}
    manifest['file_sha256'] = {name: digest(content.encode()) for name, content in files.items()}
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
    return dict(directory=str(folder.relative_to(root)), files=files,
                manifest_sha256=digest(files['manifest.json'].encode()))


@contextmanager
def publish_collection(catalog, collection, *, manifest_lookup=None):
    """Roll back file writes if saving the build task fails; protect manual files."""
    if collection is None:
        yield
        return
    parent = catalog_event_directory(catalog)
    root = Path(catalog['root']).resolve()
    if collection['directory'] != str((parent/'search').relative_to(root)):
        raise ValueError('收录目录与当前事件不一致')
    created = []
    path = parent/'search'
    while not path.exists():
        created.append(path); path = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        with directory_lock(parent):
            folder = parent/'search'
            if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
                raise ValueError('search 收录目录不能重定向')
            folder.mkdir(exist_ok=True)
            if any(p.is_symlink() or p.name not in FILES or not p.is_file() for p in folder.iterdir()):
                raise ValueError('search 目录存在其他文件，已保留；请先检查收录位置')
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            if before:
                old = json.loads(before.get('manifest.json', b'{}'))
                if (set(before) != set(FILES) or old.get('kind') != 'adopted_search'
                        or old.get('catalog', {}).get('event_id') != catalog['event_id']
                        or any(digest(before[name]) != old.get('file_sha256', {}).get(name)
                               for name in FILES if name != 'manifest.json')):
                    raise ValueError('已有收录文件被手动更改或无法识别，已保留')
            if before:
                previous = component(old.get('build_task_id', ''))
                expected = manifest_lookup(previous) if manifest_lookup else None
                if expected is None:
                    record = root/'workbench/build'/previous/'task.json'
                    saved = json.loads(record.read_text()).get('search_collection', {}) if record.is_file() else {}
                    expected = saved.get('manifest_sha256')
                if expected != digest(before['manifest.json']):
                    raise ValueError('已有收录清单与构建快照不一致，已保留')
            pending = Path(tempfile.mkdtemp(prefix='.search-pending-', dir=parent))
            backup = None
            published = False
            committed = False
            try:
                for name in FILES:
                    (pending/name).write_text(collection['files'][name], encoding='utf-8')
                backup = Path(tempfile.mkdtemp(prefix='.search-previous-', dir=parent))
                backup.rmdir()
                folder.rename(backup)
                pending.rename(folder)
                published = True
                yield
                committed = True
            except Exception:
                if published:
                    shutil.rmtree(folder)
                if backup is not None and backup.exists():
                    backup.rename(folder)
                raise
            finally:
                if pending.exists(): shutil.rmtree(pending)
                if committed and backup is not None and backup.exists(): shutil.rmtree(backup)
    except Exception:
        for path in created:
            if path.is_dir():
                try: path.rmdir()
                except OSError: pass
        raise
