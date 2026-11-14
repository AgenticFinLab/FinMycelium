"""Explicitly adopt search passages into existing evidence review, without approval."""
import hashlib
import json
from finmy.search.control import task_lock
from finmy.search.state import write_json


def adopt_sources(controller, task_id, store):
    with task_lock(controller.root,task_id):
        data=controller.inspect(task_id)
        event_id=data['task'].get('event_id')
        if not event_id:raise ValueError('该检索任务未关联主表事件')
        store.event(event_id)
        scope_hash = data['task'].get('scope_hash')
        if scope_hash and scope_hash != store.target(event_id, 'scope'):
            raise ValueError('事件范围已变化；请按新范围检索，旧任务材料仍保留可下载。')
        payload=data.get('builder_input')
        if not payload or not payload['samples']:raise ValueError('没有可纳入的材料')
        # Pin the handoff now; later reassembly must not relabel adopted Store text.
        from finmy.workbench.collection import search_snapshot
        snapshot = search_snapshot(controller, task_id, data) if data['task'].get('catalog') else None
        existing={s['sha256']:s['id'] for s in store.sources(event_id)}
        record_path = controller.root/task_id/'runs/initial/workbench_sources.json'
        previous = json.loads(record_path.read_text()) if record_path.exists() else {}
        mapping=[];added=0
        for sample in payload['samples']:
            sha=hashlib.sha256(sample['content'].encode()).hexdigest()
            source=data['sources'][sample['raw_data_id']]
            if sha not in existing:
                url=source['url'] if source['url'].startswith(('https://','http://')) else ''
                existing[sha]=store.add_source(event_id,source['title'] or source['url'],text=sample['content'],url=url)
                added+=1
            mapping.append(dict(sample_id=sample['sample_id'],source_id=existing[sha],sha256=sha))
        # A revised handoff supersedes only this task's previously adopted passages.
        # Keep original source rows and every old approval; never delete evidence.
        new_ids = {row['source_id'] for row in mapping}
        shared_ids = set()
        for other_id in controller.tasks():
            if other_id == task_id:
                continue
            other_path = controller.root/other_id/'runs/initial/workbench_sources.json'
            if other_path.exists():
                other = json.loads(other_path.read_text())
                if other.get('event_id') == event_id:
                    shared_ids.update(row['source_id'] for row in other.get('mapping', []))
        for row in previous.get('mapping', []):
            if row['source_id'] not in new_ids | shared_ids:
                store.include_source(event_id, row['source_id'], False)
        for sid in new_ids:
            store.include_source(event_id, sid, True)
        write_json(record_path,dict(event_id=event_id,mapping=mapping,search_snapshot=snapshot))
        return added


def save_preview(controller, task_id, complete, limit):
    """Save a reviewed preview as the task's current handoff; keep revision history."""
    from finmy.search.handoff import assemble_sources
    from finmy.search.state import SearchState
    with task_lock(controller.root, task_id):
        state = SearchState(controller.root, task_id)
        if any(state.data['sources'][sid].get('version') != version
               for sid, version in complete['source_versions'].items()):
            raise ValueError('来源版本已变化，请重新生成预览')
        payload = assemble_sources(state, complete['source_ids'], complete_manifest=complete, max_chars=limit)
        state.data.update(status='finished' if payload['samples'] else 'insufficient', stop_reason='manual_handoff')
        state.save()
        controller._save_summary(task_id)
        return payload


def create_catalog_search(store, controller, selection, config, mode, *, period, include, exclude,
                          confirmed=False, keywords=None, seeds=None, queries=None):
    """Freeze one catalog event; only explicit scope confirmation creates a task."""
    from finmy.dataset import search_task
    from finmy.search.state import SearchConfig, digest, now
    from finmy.workbench.domain import event_record, validate_url
    if not confirmed:
        raise ValueError('请先确认本次研究范围')
    if mode not in {'agent', 'simple'}:
        raise ValueError('无效检索模式')
    config = SearchConfig(**config) if isinstance(config, dict) else config
    task = search_task(selection, period=period, include=include, exclude=exclude)
    if keywords is not None: task['key_words'] = keywords
    if seeds is not None: task['seed_urls'] = seeds
    if any(not isinstance(k, str) for k in task['key_words']):
        raise ValueError('关键词需要字符串列表')
    for url in task['seed_urls']: validate_url(url)
    if queries: task['search_queries'] = queries
    task['scope_confirmation'] = {'time': now(), 'scope_sha256': digest(task['research_scope']),
                                  'basis': 'Explicit scope confirmation in the local workbench'}
    if selection['kind'] == 'event':
        # Local records are scope snapshots, not another catalog or an overwrite of existing data.
        row = selection['event_row']
        values = event_record(dict(event_name_en=selection['event_name'], description=selection['description'],
            domain=row.get('domain', ''), category=row.get('category', ''),
            scope_include=f"Activity period: {period or 'Unspecified'}\n{include}", scope_exclude=exclude,
            keywords=task['key_words'], source_hints=task['seed_urls'], owner=row.get('owner', '')))
        eid = 'CAT-' + digest([selection['root'], selection['event_id'], values])[:20]
        values['event_id'] = eid
        known = {e['event_id']: e for e in store.events()}
        if eid not in known: store.create_events([values])
        if store.decision(eid, 'scope') != 'approved':
            store.review(eid, 'scope', 'approved', 'Local workbench user',
                         'Confirmed this catalog task scope.', store.target(eid, 'scope'))
        task['event_id'] = eid
        task['scope_hash'] = store.target(eid, 'scope')
    # Person tasks deliberately have no ordinary EventCascade Store ID.
    return controller.create(task, config, mode)
