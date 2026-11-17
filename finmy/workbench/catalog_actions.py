"""Explicit catalog collection and withdrawal; never start or rewrite a run."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil

from finmy.dataset import catalog_event_directory, component, output_directory, within
from finmy.search.state import digest, now
from finmy.search.summary import directory_lock
from finmy.workbench.records import CATALOG_KEYS, pick, destination, save, find_build_record
from finmy.workbench.store import identifier


def folder_files(folder, allowed):
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError('收录目录不能重定向')
    if not folder.exists():
        return {}
    if any(p.is_symlink() or not p.is_file() or p.name not in allowed for p in folder.iterdir()):
        raise ValueError('收录目录含其他文件，请先检查；现有文件已保留')
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def search_collection(catalog):
    """Check the published files and their independent or build-bound receipt."""
    from .collection import FILES, LEGACY_FILES
    folder = catalog_event_directory(catalog)/'search'
    files = folder_files(folder, FILES)
    if not files:
        return None
    manifest = json.loads(files.get('manifest.json', b'{}'))
    expected = set(LEGACY_FILES) if manifest.get('format_version') == 1 else set(FILES)
    if (manifest.get('format_version') not in {1, 2, 3} or set(files) != expected or manifest.get('kind') != 'adopted_search'
            or manifest.get('catalog', {}).get('event_id') != catalog['event_id']
            or any(digest(raw) != manifest.get('file_sha256', {}).get(name)
                   for name, raw in files.items() if name != 'manifest.json')):
        raise ValueError('已收录检索文件已变化或缺失，请检查后再操作')
    root = Path(catalog['root'])
    if manifest.get('format_version') == 3:
        path = within(root, 'workbench/collections/'+component(manifest.get('collection_id'))+'.json')
        record = json.loads(path.read_text())
        known = record.get('file_sha256', {}).get('manifest.json')
    else:
        path = find_build_record(root, component(manifest.get('build_task_id')))
        record = json.loads(path.read_text()) if path else {}
        known = record.get('search_collection', {}).get('manifest_sha256')
    if known != digest(files['manifest.json']):
        raise ValueError('检索收录清单与确认记录不一致')
    return dict(manifest=manifest, files=files, sha256=digest(files['manifest.json']), directory=folder)


def collected_search(data, task_id=None):
    catalog = data.get('task', {}).get('catalog')
    if not catalog or not data.get('handoff_revision'):
        return None
    try:
        record = search_collection(catalog)
        if record and any(h.get('search_task_id') == (task_id or data.get('task_id'))
                          and h.get('handoff_revision') == data['handoff_revision']
                          and h.get('search_input_sha256') == digest(data.get('builder_input'))
                          for h in record['manifest']['search_handoffs']):
            return record
    except (ValueError, OSError, KeyError, TypeError):
        pass
    return None


def action_record(catalog, category, action, files, *, reviewer, reason='', action_id=None):
    if not reviewer.strip():
        raise ValueError('请填写确认人')
    return dict(action_id=action_id or identifier('COLL-'), action=action, category=category,
                created_at=now(), reviewer=reviewer.strip(), reason=reason.strip(),
                catalog=pick(catalog, CATALOG_KEYS),
                file_sha256={k: digest(v) for k, v in files.items()})


def save_action(catalog, receipt, files):
    """Original bytes stay in ignored output; only hashes and decisions enter Git."""
    root, folder = destination(catalog['root'], 'collections')
    archive = output_directory(root, 'collections', component(receipt['action_id']))
    if archive.exists() or (folder/(receipt['action_id']+'.json')).exists():
        raise ValueError('收录操作 ID 已存在')
    archive.mkdir(parents=True)
    try:
        for name, raw in files.items():
            (archive/component(name)).write_bytes(raw)
        save(folder, receipt['action_id']+'.json', receipt)
    except Exception:
        shutil.rmtree(archive)
        raise


def confirm_search(controller, task_id, *, expected_revision, reviewer, confirmed=False):
    from finmy.search.control import task_lock
    from finmy.person_epg.input import freeze_search_input
    from .collection import search_snapshot, prepare_collection, publish_collection
    if not confirmed:
        raise ValueError('请先确认交接材料及已知缺口')
    before = controller.inspect(task_id)
    if before['task'].get('catalog', {}).get('kind') == 'person_event':
        bundle, provenance = freeze_search_input(controller, task_id, confirmed=True)
    else:
        bundle, provenance = deepcopy(before.get('builder_input')), None
    with task_lock(controller.root, task_id):
        data = controller.inspect(task_id)
        if data.get('build_disposition') == 'excluded':
            raise ValueError('检索已标为不参与构建，请先恢复')
        if data.get('handoff_revision') != expected_revision or (provenance and provenance['handoff_revision'] != expected_revision):
            raise ValueError('交接版本已变化，请重新检查')
        if not provenance and bundle != data.get('builder_input'):
            raise ValueError('交接正文已变化，请重新检查')
        adopted = search_snapshot(controller, task_id, data)
        catalog = adopted['catalog']
        action_id = identifier('COLL-')
        body = dict(input=bundle, input_hash=digest(bundle), collection_id=action_id,
                    input_confirmation=dict(time=now(), reviewer=reviewer, basis='User confirmed material and known gaps'))
        collection = prepare_collection(None, body, [adopted], created_at=now())
        files = {k: v.encode() for k, v in collection['files'].items()}
        receipt = action_record(catalog, 'search', 'collected', files, reviewer=reviewer, action_id=action_id)
        with publish_collection(catalog, collection):
            save_action(catalog, receipt, files)
    from .records import export_search
    export_search(controller.root, task_id)
    return receipt


@contextmanager
def replace_folder(folder, files):
    """Exception-safe replacement; caller holds the catalog lock and validates old bytes."""
    import tempfile
    folder.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    pending = Path(tempfile.mkdtemp(prefix='.collection-', dir=folder.parent))
    published = False
    try:
        for name, raw in files.items():
            (pending/component(name)).write_bytes(raw)
        if folder.exists():
            backup = Path(tempfile.mkdtemp(prefix='.previous-', dir=folder.parent))
            backup.rmdir()
            folder.rename(backup)
        if files:
            pending.rename(folder)
            published = True
        yield
    except Exception:
        if published and folder.exists():
            shutil.rmtree(folder)
        if backup is not None:
            backup.rename(folder)
            backup = None
        raise
    finally:
        if pending.exists(): shutil.rmtree(pending)
        if backup is not None and backup.exists(): shutil.rmtree(backup)


def withdraw_search(catalog, *, expected_manifest, reviewer, reason):
    if not reason.strip():
        raise ValueError('请填写撤回原因')
    parent = catalog_event_directory(catalog)
    with directory_lock(parent):
        current = search_collection(catalog)
        if not current or current['sha256'] != expected_manifest:
            raise ValueError('收录版本已变化，请刷新后检查')
        receipt = action_record(catalog, 'search', 'withdrawn', current['files'], reviewer=reviewer, reason=reason)
        with replace_folder(parent/'search', {}):
            save_action(catalog, receipt, current['files'])
    return receipt
