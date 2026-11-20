"""One explicitly selected person Event draft per event in the shared dataset."""
from contextlib import contextmanager
import json
from pathlib import Path

from finmy.dataset import catalog_event_directory, component, dataset_root, within
from finmy.search.state import digest, now
from finmy.search.summary import atomic_text, directory_lock
from .graph_collection import FIELDS, graph_collection, registry, reviewed_artifacts
from .records import pick, save

IDENTITY = ('person_id', 'storyline_id', 'event_id')


def _path(catalog):
    root = Path(catalog['root']).resolve()
    parts = [component(catalog[key]) for key in IDENTITY]
    relative = Path('workbench', 'review', *parts[:-1], parts[-1] + '.json')
    if within(root, relative) != root / relative:
        raise ValueError('送审记录路径不能重定向')
    return root / relative


def _validate(item, catalog):
    if (not isinstance(item, dict) or not isinstance(item.get('catalog'), dict)
            or any(item['catalog'].get(k) != catalog.get(k) for k in (*IDENTITY, 'kind', 'event_dir'))
            or not isinstance(item.get('binding'), dict) or not all(item['binding'].get(k) for k in FIELDS)
            or item['binding']['event_id'] != catalog['event_id']
            or not isinstance(item.get('selected_at'), str) or not isinstance(item.get('material_sha256'), str)):
        raise ValueError('送审记录与事件或构建版本不符')
    return item


def selected_review(catalog):
    path = _path(catalog)
    if not path.exists():
        return None
    return _validate(json.loads(path.read_text(encoding='utf-8')), catalog)


def review_queue(root):
    """Shared pointers can be listed without a local search or build database."""
    base = Path(root).resolve()
    folder = within(base, 'workbench/review')
    if folder != base/'workbench/review':
        raise ValueError('送审目录不能重定向')
    items, errors = [], []
    for path in sorted(folder.glob('*/*/*.json')):
        try:
            if within(base, path.relative_to(base)) != path:
                raise ValueError('送审记录路径不能重定向')
            item = json.loads(path.read_text(encoding='utf-8'))
            catalog = {**item['catalog'], 'root': str(base)}
            if _path(catalog) != path or catalog.get('kind') != 'person_event':
                raise ValueError('送审记录与目录不符')
            _validate(item, catalog)
            if not graph_collection(catalog):
                items.append(item)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(f'{path.relative_to(base)} · {exc}')
    return sorted(items, key=lambda item: item['selected_at'], reverse=True), errors


def select_for_review(controller, catalog, binding, *, expected_selection):
    from .build_tasks import worker_lock
    parent = registry(catalog)[0].parent
    task_id = binding['build_task_id']
    with worker_lock(controller.root, task_id, blocking=False):
        row = controller.inspect(task_id)
        body = row['body']
        source = body['catalog']
        if (row['event_id'] != catalog['event_id']
                or Path(dataset_root(controller.store.root)).resolve() != Path(catalog['root']).resolve()
                or catalog_event_directory(source) != catalog_event_directory(catalog)
                or any(source.get(k) != catalog.get(k) for k in IDENTITY)):
            raise ValueError('草稿不属于本次选择的人物 event')
        with directory_lock(Path(body['artifact_directory'])), directory_lock(parent):
            if reviewed_artifacts(row)['binding'] != binding:
                raise ValueError('草稿已变化，请重新查看该版本')
            if graph_collection(catalog):
                raise ValueError('本事件已有正式成果')
            previous = selected_review(catalog)
            if previous and previous['binding'] == binding:
                return previous
            if digest(previous) != expected_selection:
                raise ValueError('送审选择已变化，请刷新后再选择')
            item = dict(catalog=pick(source, ('kind', *IDENTITY, 'event_dir', 'person_name', 'storyline_name', 'event_name')),
                        binding=binding, material_sha256=body['input_hash'], selected_at=now(),
                        handoff_revision=body.get('provenance', {}).get('handoff_revision'))
            path = _path(catalog)
            path.parent.mkdir(parents=True, exist_ok=True)
            save(path.parent, path.name, item)
            return selected_review(catalog)


def withdraw_selection(catalog, *, expected_selection):
    with directory_lock(registry(catalog)[0].parent):
        selected = selected_review(catalog)
        if not selected or digest(selected) != expected_selection:
            raise ValueError('送审选择已变化，请刷新后再操作')
        _path(catalog).unlink()


@contextmanager
def retire_selection(catalog, task_id=None):
    """Caller holds the registry directory lock during discard or collection."""
    selected = selected_review(catalog)
    if not selected or (task_id and selected['binding']['build_task_id'] != task_id):
        yield
        return
    path = _path(catalog)
    original = path.read_text(encoding='utf-8')
    path.unlink()
    try:
        yield
    except BaseException:
        atomic_text(path, original)
        raise
