"""Locate dataset-owned runtime storage without starting services."""
from contextlib import closing
import json
import fcntl
import os
from pathlib import Path
import sqlite3

from finmy.dataset import DatasetCatalog, dataset_root, output_directory, save_dataset_root
from finmy.search.state import write_json


def location_file(project):
    # This ignored file contains only the local dataset path, never runtime data.
    return Path(project) / 'output/workbench-location.json'


def assert_idle(workspace):
    """Changing workspace never hides a running worker."""
    workspace = Path(workspace).resolve()
    for kind in ('search', 'builds'):
        for lock in (workspace / kind).glob('*/.writer.lock'):
            with lock.open('rb') as stream:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ValueError('任务仍在执行，请结束后再切换工作区') from exc
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)
    for path in (workspace / 'search').glob('*/runs/initial/run.json'):
        if json.loads(path.read_text())['status'] == 'running':
            raise ValueError('请先停止正在运行的检索，再切换工作区')
    database = workspace / 'workbench.sqlite3'
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='build_tasks'").fetchone()
            if exists and db.execute("SELECT 1 FROM build_tasks WHERE status IN ('queued','running')").fetchone():
                raise ValueError('请先完成或停止正在运行的构建，再切换工作区')


def select_workspace(project, root, *, current=None):
    """Select a dataset, preserving any previous workspace and its tasks."""
    catalog = DatasetCatalog(root)
    target = output_directory(catalog.root, 'workbench')
    if current and Path(current).resolve() != target:
        assert_idle(current)
    old = Path(project) / 'output/workbench'
    if (old / 'workbench.sqlite3').exists() and old.resolve() != target:
        raise ValueError('检测到旧工作区：请关闭工作台，完整迁移旧工作区后再选择数据集')
    configured = dataset_root(target)
    if configured and Path(configured).resolve() != catalog.root:
        raise ValueError('目标工作区的数据集设置不一致；已有记录已保留')
    save_dataset_root(target, str(catalog.root))
    write_json(location_file(project), {'dataset_root': str(catalog.root)})
    return target


def resolve_workspace(project, *, environ=None):
    """No implicit empty database under the code repository."""
    environ = os.environ if environ is None else environ
    if environ.get('FINMY_WORKBENCH_HOME'):
        return Path(environ['FINMY_WORKBENCH_HOME']).expanduser().resolve()
    path = location_file(project)
    if path.exists():
        root = DatasetCatalog(json.loads(path.read_text())['dataset_root']).root
        target = output_directory(root, 'workbench')
        if Path(dataset_root(target) or '').resolve() != root:
            raise ValueError('工作区的数据集设置缺失或不一致，请重新选择数据集')
        return target
    if (Path(project) / 'output/workbench/workbench.sqlite3').exists():
        raise ValueError('检测到旧工作区：请关闭工作台并迁移，避免创建空数据库覆盖任务入口')
    return None
