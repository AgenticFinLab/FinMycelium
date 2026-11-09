"""Local search lifecycle shared by command-line and interface clients."""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import fcntl
import json
import re
import threading
import uuid

from .state import SearchConfig, SearchState, now, write_json


def task_path(root, task_id):
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',task_id):
        raise ValueError('Invalid task ID')
    return Path(root)/task_id


def _legacy_outage(data, run_dir):
    """Recognize empty pre-fix outage handoffs only on explicit resume."""
    if data.get('status') != 'insufficient' or data.get('sources'):
        return False
    trace = run_dir / 'trace.jsonl'
    if trace.exists():
        try:
            with trace.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if (isinstance(row, dict) and row.get('action') == 'provider_result'
                            and row.get('status') in {'failed', 'cooldown', 'unavailable', 'blocked', 'retry_exhausted'}
                            and row.get('error_details')):
                        return True
        except OSError:
            pass
    # Old shared health prevented siblings with zero requests from searching.
    # Consult it only as historical migration evidence, never as current health.
    if data.get('usage', {}).get('search', 0) != 0:
        return False
    try:
        health = json.loads((run_dir.parents[2] / 'provider_health.json').read_text())
        return health.get('version') == 1 and any(
            row.get('disabled') and row.get('last_error')
            for scope in health.get('scopes', {}).values() for row in scope.values())
    except (OSError, ValueError, TypeError, AttributeError):
        return False


@contextmanager
def task_lock(root, task_id):
    path=task_path(root,task_id)
    path.mkdir(parents=True,exist_ok=True)
    with (path/'.writer.lock').open('a') as stream:
        try:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('This task is already running') from exc
        try:
            yield
        finally:
            fcntl.flock(stream,fcntl.LOCK_UN)


class SearchController:
    def __init__(self, root, *, env_file=None, **dependencies):
        self.root=Path(root)
        self.env_file=Path(env_file) if env_file else None
        self.dependencies=dependencies
        self.threads={}
        self.guard=threading.Lock()

    def create(self, task, config, mode='agent'):
        if mode not in {'agent','simple'}:
            raise ValueError('Invalid search mode')
        config=SearchConfig(**config) if isinstance(config,dict) else config
        task_id=uuid.uuid4().hex
        with task_lock(self.root,task_id):
            state=SearchState(self.root,task_id,task=task,config=config)
            state.data['mode']=mode
            state.save()
        return task_id

    def inspect(self, task_id):
        path=task_path(self.root,task_id)/'runs/initial'
        data=json.loads((path/'run.json').read_text())
        for name in ('selection','builder_input','complete_material'):
            file=path/(name+'.json')
            try:
                data[name]=json.loads(file.read_text()) if file.exists() else None
                if file.exists() and not isinstance(data[name], dict):
                    raise TypeError('Optional handoff sidecar must be an object')
            except (OSError, ValueError, TypeError) as exc:
                data[name]=None
                data.setdefault('inspection_errors', []).append(dict(
                    file=name+'.json', error_type=type(exc).__name__, stage='optional_sidecar'))
        data['can_resume'] = data['status'] not in {'finished', 'insufficient'} or _legacy_outage(data, path)
        return data

    def tasks(self):
        if not self.root.exists(): return []
        return sorted(p.name for p in self.root.iterdir() if (p/'runs/initial/run.json').exists())

    def active(self, task_id):
        thread=self.threads.get(task_id)
        return bool(thread and thread.is_alive())

    def pause(self, task_id):
        path=task_path(self.root,task_id)
        if not (path/'runs/initial/run.json').exists(): raise ValueError('Unknown task')
        (path/'pause_requested').touch()

    def configure(self, task_id, values):
        """Explicit revisions retain usage, originals and old configuration."""
        with task_lock(self.root,task_id):
            state=SearchState(self.root,task_id)
            config=SearchConfig(**{**asdict(state.config),**values})
            state.data.setdefault('config_history',[]).append(dict(time=now(),config=state.data['config']))
            state.data['config']=asdict(config)
            state.save()

    def reassemble(self, task_id, max_chars):
        from .handoff import assemble, assemble_sources
        with task_lock(self.root,task_id):
            state=SearchState(self.root,task_id)
            old=json.loads((state.run_dir/'selection.json').read_text())
            complete_path=state.run_dir/'complete_material.json'
            if old.get('mode') == 'sources' and complete_path.exists():
                payload=assemble_sources(state,old['source_ids'],complete_manifest=json.loads(complete_path.read_text()),max_chars=max_chars)
            elif old.get('mode') == 'sources':
                payload = assemble_sources(state,old['source_ids'],versions=old['source_versions'],
                                           gaps=old['gaps'],reason=old['reason'],max_chars=max_chars)
            else:
                payload = assemble(state,old['selected']+[{k:v for k,v in s.items() if k!='omission_reason'} for s in old['omitted']],
                                gaps=old['gaps'],reason=old['reason'],max_chars=max_chars)
            if state.data['status'] in {'finished', 'insufficient'}:
                state.data['status'] = 'finished' if payload['samples'] and old['reason'] != 'insufficient' else 'insufficient'
            state.save()
            return payload

    def start(self, task_id, steps=None):
        with self.guard:
            if self.active(task_id): raise ValueError('This task is already running')
            state=self.inspect(task_id)
            if not state['can_resume']:
                raise ValueError('Task ended; review or create a new task')
            # Starting/resuming is explicit; no API is triggered by page rendering.
            if not self.dependencies and not state['config']['allow_network']:
                raise ValueError('Enable external calls in task configuration before starting')
            if not self.dependencies:
                if state.get('mode','agent') == 'agent' and not state['config']['lm_name']:
                    raise ValueError('请先配置独立的搜索侧模型')
                if self.env_file and self.env_file.is_file():
                    from dotenv import load_dotenv
                    load_dotenv(self.env_file, override=False)
            (task_path(self.root,task_id)/'pause_requested').unlink(missing_ok=True)
            thread=threading.Thread(target=self._worker,args=(task_id,steps),daemon=True)
            self.threads[task_id]=thread
            thread.start()

    def _worker(self, task_id, steps):
        from .pipeline import _run_search
        try:
            with task_lock(self.root,task_id):
                state=SearchState(self.root,task_id)
                try:
                    if _legacy_outage(state.data, state.run_dir):
                        state.data.setdefault('resume_history', []).append(dict(
                            previous_status=state.data['status'], previous_stop_reason=state.data.get('stop_reason'),
                            reason='legacy_provider_interruption'))
                        state.data.update(status='paused', stop_reason='legacy_provider_interruption')
                        state.save()
                    if state.data.get('mode','agent')=='simple':
                        self._simple(state)
                    else:
                        _run_search(root=self.root,task_id=task_id,max_steps=steps,**self.dependencies)
                except Exception as exc:
                    state=SearchState(self.root,task_id)
                    state.data.update(status='failed',stop_reason=type(exc).__name__)
                    state.save()
        except ValueError:
            # Another process owns this task; do not overwrite its state.
            return

    def _simple(self, state):
        """Fixed supplied queries and original material; no search-side model."""
        from .tools import SearchTools
        from .handoff import assemble
        from .state import LimitReached
        tools=SearchTools(state,transport=self.dependencies.get('transport'),fetcher=self.dependencies.get('fetcher'))
        task=state.data['task']
        if not state.data.get('seeds_imported'):
            for url in task.get('seed_urls',[]): tools.sources.register(url)
            for path in task.get('local_files',[]): tools.sources.import_file(path)
            state.data['seeds_imported']=True
            state.save()
        queries=task.get('search_queries') or [task['target_name']+' '+' '.join(task.get('key_words',[]))]
        if not isinstance(queries,list) or any(not isinstance(q,str) or not q.strip() for q in queries):
            raise ValueError('Simple search requires nonempty queries')
        state.data['status']='running';state.save()
        for query in queries:
            if (state.root/'pause_requested').exists():
                state.data.update(status='paused',stop_reason='user_pause');state.save();return
            tools.search(query)
        selected=[]
        for sid in list(state.data['sources']):
            if (state.root/'pause_requested').exists():
                state.data.update(status='paused',stop_reason='user_pause');state.save();return
            try:
                result=tools.read_source(sid)
            except LimitReached:
                break
            while result.get('spans'):
                selected.extend(dict(source_id=sid,version=result['version'],block=s['block'],start=s['start'],end=s['end'])
                                for s in result['spans'] if s['end']>s['start'])
                if result['next_location'] is None:break
                if (state.root/'pause_requested').exists():
                    state.data.update(status='paused',stop_reason='user_pause');state.save();return
                result=tools.read_source(sid,result['next_location'])
        payload=assemble(state,selected,gaps=['Simple search has no semantic coverage assessment'],reason='fixed_queries_completed')
        state.data.update(status='finished' if payload['samples'] else 'insufficient',stop_reason='fixed_queries_completed')
        state.save()
