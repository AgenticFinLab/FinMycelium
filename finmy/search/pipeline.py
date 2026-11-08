"""Independent search orchestration. This module never starts a Builder."""
from .state import SearchConfig, SearchState
from .tools import SearchTools
from .agent import run_agent


def _run_search(task=None, *, root='output/search', task_id, run_id='initial', config=None,
               model=None, transport=None, fetcher=None, max_steps=None):
    if isinstance(config,dict):
        config=SearchConfig(**config)
    state=SearchState(root,task_id,run_id,task=task,config=config)
    tools=SearchTools(state,transport=transport,fetcher=fetcher)
    if not state.data.get('seeds_imported'):
        for url in state.data['task'].get('seed_urls',[]):
            tools.sources.register(url)
        for path in state.data['task'].get('local_files',[]):
            tools.sources.import_file(path)
        state.data['seeds_imported']=True
        state.save()
    run_agent(state,tools,model,max_steps=max_steps)
    return dict(task_id=task_id,status=state.data['status'],usage=state.data['usage'],
                read_sources=len(state.data['read_sources']),run_dir=str(state.run_dir),
                builder_input_path=str(state.run_dir/'builder_input.json') if (state.run_dir/'builder_input.json').exists() else None)


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
