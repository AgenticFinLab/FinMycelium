"""Independent search orchestration. This module never starts a Builder."""
import copy

from .state import SearchConfig, SearchState
from .tools import SearchTools
from .agent import run_agent


def _run_search(task=None, *, root='output/search', task_id, run_id='initial', config=None,
               model=None, transport=None, fetcher=None, max_steps=None, source_pool=None):
    if isinstance(config,dict):
        config=SearchConfig(**config)
    state=SearchState(root,task_id,run_id,task=task,config=config)
    tools=SearchTools(state,transport=transport,fetcher=fetcher,source_pool=source_pool)
    imported = state.data.get('seeds_imported')
    failed_seeds = {(row['kind'], row['index']) for row in state.data.get('seed_errors', [])}
    if not imported or (failed_seeds and state.data['status'] not in {'finished', 'insufficient'}):
        errors = []
        for kind, load in (('seed_urls', tools.sources.register), ('local_files', tools.sources.import_file)):
            for index, value in enumerate(state.data['task'].get(kind, [])):
                if imported and (kind, index) not in failed_seeds:
                    continue
                try:
                    load(value)
                except (OSError, ValueError, TypeError) as error:
                    row = dict(kind=kind, index=index, error_type=type(error).__name__)
                    errors.append(row)
                    state.trace(dict(action='seed_import_failed', **row))
        state.data['seed_errors'] = errors
        state.data['seeds_imported']=True
        state.save()
    run_agent(state,tools,model,max_steps=max_steps)
    result = dict(task_id=task_id,status=state.data['status'],usage=state.data['usage'],
                read_sources=len(state.data['read_sources']),run_dir=str(state.run_dir),
                seed_errors=copy.deepcopy(state.data.get('seed_errors', [])),
                quarantined_sources=[copy.deepcopy(entry['quarantine'])
                    for entry in state.data['sources'].values() if entry.get('quarantine')],
                builder_input_path=str(state.run_dir/'builder_input.json') if (state.run_dir/'builder_input.json').exists() else None)
    result.update({key: copy.deepcopy(state.data[key]) for key in ('stop_reason', 'resume')
                   if state.data.get(key) is not None})
    return result


def run_batch(tasks, *, root='output/search', config=None, **dependencies):
    """Sequential task isolation; resume identifiers supplied by caller, no reset."""
    ids=[item['task_id'] for item in tasks]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate task IDs in batch')
    results=[]
    for item in tasks:
        try:
            results.append(run_search(item['task'],root=root,task_id=item['task_id'],config=config,**dependencies))
        except Exception as exc:
            results.append(dict(task_id=item['task_id'],status='failed',error_type=type(exc).__name__))
    return results


def run_search(task=None, *, root='output/search', task_id, **kwargs):
    """Serialize writers across CLI, workbench and independent Python callers."""
    from .control import task_lock
    with task_lock(root, task_id):
        return _run_search(task, root=root, task_id=task_id, **kwargs)
